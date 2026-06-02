import os
import re

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# =====================================
# 환경변수
# =====================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHAT_MODEL_NAME = os.getenv("CHAT_MODEL_NAME", "gpt-4o-mini")
PERSIST_DIRECTORY = os.getenv("PERSIST_DIRECTORY", "C:/chroma_db_store")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "chosun_extracurricular")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# =====================================
# FastAPI
# =====================================
app = FastAPI(title="Chosun RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================
# 요청/응답 모델
# =====================================
class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    success: bool
    answer: str
    sources: list

# =====================================
# ChromaDB 연결
# =====================================
embeddings = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL
)

vectorstore = Chroma(
    collection_name=COLLECTION_NAME,
    embedding_function=embeddings,
    persist_directory=PERSIST_DIRECTORY
)

print("📦 DB 데이터 개수:", vectorstore._collection.count())

# =====================================
# 전화번호 관련 키워드
# =====================================
PHONE_KEYWORDS = [
    "전화번호",
    "연락처",
    "번호",
    "학과실",
    "학과사무실",
    "사무실",
    "교학팀"
]

def is_phone_question(question: str):
    return any(keyword in question for keyword in PHONE_KEYWORDS)

# =====================================
# 전화번호 문서 찾기
# =====================================
def find_phone_info(results):

    phone_pattern = r'062-\d{3,4}-\d{4}'

    for doc, score in results:

        text = doc.page_content

        if "전화번호" in text:
            return text

        if re.search(phone_pattern, text):
            return text

    return None

# =====================================
# 학과명 추출
# =====================================
def extract_department(results):

    keywords = [
        "학과",
        "학부",
        "전공",
        "교학팀"
    ]

    for doc, score in results:

        text = doc.page_content

        lines = text.split("\n")

        for line in lines:

            for keyword in keywords:

                if keyword in line:
                    return line.strip()

    return None

# =====================================
# 검색 함수
# =====================================
def search_docs(query: str):

    if not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="질문이 비어 있습니다."
        )

    k = 10 if is_phone_question(query) else 5

    results = vectorstore.similarity_search_with_score(
        query,
        k=k
    )

    threshold = 0.8

    docs = []
    sources = []

    for doc, score in results:

        if score < threshold:
            docs.append(doc.page_content)
            sources.append(doc.metadata.get("source", ""))

    return docs, sources, results

# =====================================
# GPT 응답
# =====================================
async def get_gpt_response(question, context):

    prompt = f"""
너는 조선대학교 정보 도우미이다.

[참고 정보]
{context}

[질문]
{question}

[규칙]

1. 참고 정보에 있는 내용만 사용한다.
2. 추측하지 않는다.
3. 교수명, 학과명, 교학팀을 혼동하지 않는다.
4. 참고 정보에 답이 없으면 반드시 아래 한 문장만 출력한다.

정보없음

5. 한국어로 답변한다.
"""

    response = await client.chat.completions.create(
        model=CHAT_MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "조선대학교 정보 챗봇"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content

# =====================================
# 기본 API
# =====================================
@app.get("/")
def root():
    return {
        "success": True,
        "message": "RAG 서버 실행 중"
    }

# =====================================
# 챗봇 API
# =====================================
@app.post(
    "/chat",
    response_model=ChatResponse
)
async def chat(req: ChatRequest):

    question = req.question

    docs, sources, raw_results = search_docs(question)

    # ==================================================
    # 1. 전화번호 질문이면 전화번호 문서 우선 반환
    # ==================================================
    if is_phone_question(question):

        phone_info = find_phone_info(raw_results)

        if phone_info:

            return {
                "success": True,
                "answer": phone_info,
                "sources": sources
            }

    # ==================================================
    # 2. 검색 결과 없음
    # ==================================================
    if not docs:

        dept = extract_department(raw_results)

        phone_results = vectorstore.similarity_search_with_score(
            question + " 학과실 전화번호",
            k=10
        )

        phone_info = find_phone_info(phone_results)

        if phone_info:

            return {
                "success": True,
                "answer":
                    "관련 정보를 찾을 수 없습니다.\n\n"
                    "정확한 내용은 아래 학과실로 문의해 주세요.\n\n"
                    + phone_info,
                "sources": []
            }

        return {
            "success": True,
            "answer": "관련 정보를 찾을 수 없습니다.",
            "sources": []
        }

    # ==================================================
    # 3. GPT 응답 생성
    # ==================================================
    context = "\n\n".join(docs)

    try:

        answer = await get_gpt_response(
            question,
            context
        )

    except Exception:

        raise HTTPException(
            status_code=500,
            detail="GPT 응답 생성 실패"
        )

    # ==================================================
    # 4. GPT가 답변 못함
    # ==================================================
    if answer.strip() == "정보없음":

        phone_results = vectorstore.similarity_search_with_score(
            question + " 학과실 전화번호",
            k=10
        )

        phone_info = find_phone_info(phone_results)

        if phone_info:

            answer = (
                "현재 챗봇이 해당 정보를 제공할 수 없습니다.\n\n"
                "정확한 확인을 위해 학과실로 문의해 주세요.\n\n"
                f"{phone_info}"
            )
        else:

            answer = (
                "현재 챗봇이 해당 정보를 제공할 수 없습니다.\n"
                "관련 학과실 또는 교학팀으로 문의해 주세요."
            )

    return {
        "success": True,
        "answer": answer,
        "sources": sources
    }

# =====================================
# 글로벌 에러 처리
# =====================================
@app.exception_handler(Exception)
def global_exception_handler(request, exc):

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "서버 내부 오류 발생",
            "detail": str(exc)
        }
    )

# =====================================
# 실행
# uvicorn main:app --reload
# =====================================

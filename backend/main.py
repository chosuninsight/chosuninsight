# ✅ FastAPI + ChromaDB + GPT 연결 (최종)

import os
import json
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
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "jhgan/ko-sroberta-multitask"
)

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# =====================================
# FastAPI 설정
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
# 요청 / 응답 모델
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

print(
    "📦 DB 데이터 개수:",
    vectorstore._collection.count()
)

# =====================================
# 학과 전화번호 로드
# =====================================
try:

    with open(
        "학과전화번호.json",
        "r",
        encoding="utf-8"
    ) as f:

        phone_data = json.load(f)

    DEPARTMENT_PHONES = {}

    for item in phone_data["학부_및_학과"]:

        dept = item.get("학과", "").strip()
        phone = item.get("전화번호", "").strip()

        if dept and phone:
            DEPARTMENT_PHONES[dept] = phone

    print(
        f"📞 학과 전화번호 "
        f"{len(DEPARTMENT_PHONES)}개 로드 완료"
    )

except Exception as e:

    print("⚠️ 학과 전화번호 로드 실패:", e)

    DEPARTMENT_PHONES = {}

# =====================================
# 학과 별칭 자동 생성
# =====================================
def generate_department_aliases():

    aliases = {}

    for dept in DEPARTMENT_PHONES.keys():

        # 정식 명칭
        aliases[dept] = dept

        # 괄호 안 전공 추출
        match = re.search(
            r"\((.*?)\)",
            dept
        )

        if match:

            major = match.group(1).strip()

            aliases[major] = dept

            if major.endswith("전공"):
                aliases[
                    major.replace("전공", "")
                ] = dept

            if major.endswith("학과"):
                aliases[
                    major.replace("학과", "")
                ] = dept

        # 전자공학과 → 전자공학
        if dept.endswith("학과"):
            aliases[
                dept.replace("학과", "")
            ] = dept

        # 경영학부 → 경영
        if dept.endswith("학부"):
            aliases[
                dept.replace("학부", "")
            ] = dept

    # 학생들이 자주 쓰는 표현
    custom_aliases = {
        "컴공": "AI·SW학부(컴퓨터공학전공)",
        "정통": "AI·SW학부(정보통신공학전공)",
        "정보보안": "AI·SW학부(정보보안전공)",
        "인공지능": "AI·SW학부(인공지능공학전공)",
        "모빌리티": "AI·SW학부(모빌리티SW전공)",
        "전자과": "전자공학과",
        "기계과": "기계공학과",
        "건축과": "건축공학과"
    }

    for alias, dept in custom_aliases.items():

        if dept in DEPARTMENT_PHONES:
            aliases[alias] = dept

    return aliases


DEPARTMENT_ALIAS = generate_department_aliases()

print(
    f"📞 학과 별칭 "
    f"{len(DEPARTMENT_ALIAS)}개 생성 완료"
)

# =====================================
# 학과 전화번호 찾기
# =====================================
def find_department_phone(
    question: str,
    docs: list
):

    question = question.strip()

    # 질문 우선 검색
    for alias, dept in DEPARTMENT_ALIAS.items():

        if alias in question:

            phone = DEPARTMENT_PHONES.get(dept)

            if phone:
                return dept, phone

    # 검색 문서 검색
    for doc in docs:

        for alias, dept in DEPARTMENT_ALIAS.items():

            if alias in doc:

                phone = DEPARTMENT_PHONES.get(dept)

                if phone:
                    return dept, phone

    return None, None


# =====================================
# 검색 함수
# =====================================
def search_docs(query: str):

    if not query.strip():

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="질문이 비어 있습니다."
        )

    results = vectorstore.similarity_search_with_score(
        query,
        k=3
    )

    threshold = 0.5

    docs = []
    sources = []

    for doc, score in results:

        if score < threshold:

            docs.append(
                doc.page_content
            )

            sources.append(
                doc.metadata.get(
                    "source",
                    ""
                )
            )

    if not docs:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="검색 결과가 없습니다."
        )

    return docs, sources


# =====================================
# GPT 응답 함수
# =====================================
async def get_gpt_response(
    question,
    context
):

    prompt = f"""
너는 조선대학교 정보 도우미야.

아래 정보를 기반으로 질문에 답변해.

[참고 정보]
{context}

[질문]
{question}

[규칙]
- 참고 정보에 있는 내용만 사용
- 정보가 없으면
  "해당 정보를 찾을 수 없습니다"
  라고 답변
- 한국어로 답변
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

    return (
        response
        .choices[0]
        .message
        .content
    )


# =====================================
# 기본 API
# =====================================
@app.get(
    "/",
    status_code=status.HTTP_200_OK
)
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
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK
)
async def chat(
    req: ChatRequest
):

    docs, sources = search_docs(
        req.question
    )

    context = "\n".join(docs)

    try:

        answer = await get_gpt_response(
            req.question,
            context
        )

    except Exception:

        raise HTTPException(
            status_code=500,
            detail="GPT 응답 생성 실패"
        )

    # =============================
    # 학과 전화번호 자동 첨부
    # =============================
    dept, phone = find_department_phone(
        req.question,
        docs
    )

    if dept and phone:

        answer += (
            "\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📞 관련 학과 문의처\n"
            f"학과 : {dept}\n"
            f"전화번호 : {phone}"
        )

    return {
        "success": True,
        "answer": answer,
        "sources": sources
    }


# =====================================
# 글로벌 예외 처리
# =====================================
@app.exception_handler(Exception)
def global_exception_handler(
    request,
    exc
):

    return JSONResponse(
        status_code=500,
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

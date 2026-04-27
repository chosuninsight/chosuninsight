# ✅ FastAPI + ChromaDB + GPT 연결 (최종)

import os

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
# 🔥 환경변수 추가 (요청사항 반영)
# =====================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHAT_MODEL_NAME = os.getenv("CHAT_MODEL_NAME", "gpt-4o-mini")
PERSIST_DIRECTORY = os.getenv("PERSIST_DIRECTORY", "/app/chroma_db")
UPDATE_DB_DIRECTORY = os.getenv("UPDATE_DB_DIRECTORY", "/app/chroma_db_update") # 갱신 DB 경로 [cite: 8]
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "chosun_insight")
UPDATE_COLLECTION_NAME = "chosun_daily_update" # Update date.py의 설정과 일치
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# =====================================
# 1. FastAPI 기본 설정
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
# 2. 요청 / 응답 모델
# =====================================
class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    success: bool
    answer: str
    sources: list

# =====================================
# 3. ChromaDB 연결 (env 적용)
# =====================================
embeddings = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL
)

vectorstore_origin = Chroma(
    collection_name=COLLECTION_NAME,
    embedding_function=embeddings,
    persist_directory=PERSIST_DIRECTORY
)

vectorstore_update = Chroma(
    collection_name=UPDATE_COLLECTION_NAME,
    embedding_function=embeddings,
    persist_directory=UPDATE_DB_DIRECTORY
)

# [수정 코드]
print("📦 기존 DB 데이터 개수:", vectorstore_origin._collection.count())
print("📦 갱신 DB 데이터 개수:", vectorstore_update._collection.count())

# =====================================
# 🔥 4. 검색 함수 (유사도 필터링 추가)
# =====================================
def search_docs(query: str):
    if not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="질문이 비어 있습니다."
        )

    res_origin = vectorstore_origin.similarity_search_with_score(query, k=3)
    res_update = vectorstore_update.similarity_search_with_score(query, k=3)
    
    all_results = res_origin + res_update

    docs, sources = [], []

    for doc, score in all_results:
        docs.append(doc.page_content)
        sources.append(doc.metadata.get("source", ""))

    if not docs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="검색 결과가 없습니다."
        )

    return docs, sources

# =====================================
# 🔥 5. GPT 응답 함수 추가
# =====================================
async def get_gpt_response(question, context):
    prompt = f"""
너는 조선대학교 정보 도우미야.
아래 정보를 기반으로 질문에 답변해.

[참고 정보]
{context}

[질문]
{question}

[규칙]
- 정보 없으면 "해당 정보를 찾을 수 없습니다"라고 답해
- 한국어로 답변
"""

    response = await client.chat.completions.create(
        model=CHAT_MODEL_NAME,  # 🔥 환경변수 적용
        messages=[
            {"role": "system", "content": "조선대학교 정보 챗봇"},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content

# =====================================
# 6. API
# =====================================

@app.get("/", status_code=status.HTTP_200_OK)
def root():
    return {
        "success": True,
        "message": "RAG 서버 실행 중"
    }

# 🔥 챗봇 API (GPT 연결됨)
@app.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK
)
async def chat(req: ChatRequest):

    docs, sources = search_docs(req.question)

    context = "\n".join(docs)

    try:
        answer = await get_gpt_response(req.question, context)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="GPT 응답 생성 실패"
        )

    return {
        "success": True,
        "answer": answer,
        "sources": sources
    }

# =====================================
# 7. 글로벌 에러 처리
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

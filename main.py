# ✅ FastAPI + ChromaDB + Ollama (최종 안정화)

import os

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM

# =====================================
# 🔥 환경변수 (추가)
# =====================================
PERSIST_DIRECTORY = os.getenv("PERSIST_DIRECTORY", "C:/chroma_db_store")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "chosun_extracurricular")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")

# =====================================
# 🔥 LLM (Ollama)
# =====================================
llm = OllamaLLM(model=OLLAMA_MODEL)

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

class SearchResponse(BaseModel):
    success: bool
    documents: list
    sources: list

# =====================================
# 3. ChromaDB 연결 (env 적용)
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
# 🔥 4. 검색 함수 (유사도 필터링 추가)
# =====================================
def search_docs(query: str):
    if not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="질문이 비어 있습니다."
        )

    # 🔥 핵심 변경 (score 기반)
    results = vectorstore.similarity_search_with_score(query, k=3)

    threshold = 0.5
    docs, sources = [], []

    for doc, score in results:
        if score < threshold:
            docs.append(doc.page_content)
            sources.append(doc.metadata.get("source", ""))

    # ❌ 필터링 후 결과 없음
    if not docs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="검색 결과가 없습니다."
        )

    return docs, sources

# =====================================
# 🔥 5. API
# =====================================

@app.get("/", status_code=status.HTTP_200_OK)
def root():
    return {
        "success": True,
        "message": "RAG 서버 실행 중"
    }

# 검색 API
@app.post(
    "/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK
)
def search(req: ChatRequest):
    docs, sources = search_docs(req.question)

    return {
        "success": True,
        "documents": docs,
        "sources": sources
    }

# 🔥 챗봇 API (Ollama 연결)
@app.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK
)
def chat(req: ChatRequest):
    docs, sources = search_docs(req.question)

    context = "\n".join(docs)

    # 🔥 프롬프트 개선 (환각 방지)
    prompt = f"""
너는 조선대학교 정보 도우미야.

아래 정보를 기반으로 질문에 답해.

[참고 정보]
{context}

[질문]
{req.question}

[규칙]
- 정보 없으면 "해당 정보를 찾을 수 없습니다"라고 답해
- 한국어로 답변
"""

    try:
        answer = llm.invoke(prompt)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM 응답 생성 실패"
        )

    return {
        "success": True,
        "answer": answer,
        "sources": [
            {"label": f"참고 자료 {i+1}", "url": src}
            for i, src in enumerate(sources)
        ]
    }

# =====================================
# 6. 글로벌 에러 처리
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

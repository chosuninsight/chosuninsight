# ✅ FastAPI + ChromaDB (상태코드 적용 버전)

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

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
# 3. ChromaDB 연결
# =====================================
PERSIST_DIRECTORY = "C:/chroma_db_store"

embeddings = HuggingFaceEmbeddings(
    model_name="jhgan/ko-sroberta-multitask"
)

vectorstore = Chroma(
    collection_name="chosun_extracurricular",
    embedding_function=embeddings,
    persist_directory=PERSIST_DIRECTORY
)

db_count = vectorstore._collection.count()
print("📦 DB 데이터 개수:", db_count)

# =====================================
# 4. 검색 함수 (에러 처리 포함)
# =====================================
def search_docs(query: str):
    # ❌ 빈 질문
    if not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="질문이 비어 있습니다."
        )

    results = vectorstore.similarity_search(query, k=3)

    # ❌ 검색 결과 없음
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="검색 결과가 없습니다."
        )

    docs = [doc.page_content for doc in results]
    sources = [doc.metadata.get("source", "") for doc in results]

    return docs, sources

# =====================================
# 5. API
# =====================================

# 기본 확인
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

# 챗봇 API
@app.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK
)
def chat(req: ChatRequest):
    docs, sources = search_docs(req.question)

    context = "\n".join(docs)

    # 🔥 현재는 임시 응답 (나중에 LLM 연결)
    answer = f"""
질문: {req.question}

참고 정보:
{context}
"""

    return {
        "success": True,
        "answer": answer,
        "sources": sources
    }

# =====================================
# 6. 글로벌 에러 처리 (실무 스타일)
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
# 7. 실행 방법
# =====================================
# uvicorn main:app --reload

# ✅ FastAPI + ChromaDB

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# =====================================
# 1. FastAPI 기본 설정
# =====================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================
# 2. 요청 모델
# =====================================
class ChatRequest(BaseModel):
    question: str

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

print("📦 DB 데이터 개수:", vectorstore._collection.count())

# =====================================
# 4. 검색 함수
# =====================================
def search_docs(query: str):
    results = vectorstore.similarity_search(query, k=3)

    docs = [doc.page_content for doc in results]
    sources = [doc.metadata.get("source", "") for doc in results]

    return docs, sources

# =====================================
# 5. API
# =====================================
@app.get("/")
def root():
    return {"msg": "RAG 서버 실행 중"}

@app.post("/search")
def search(req: ChatRequest):
    docs, sources = search_docs(req.question)
    return {
        "documents": docs,
        "sources": sources
    }

@app.post("/chat")
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
        "answer": answer,
        "sources": sources
    }

# =====================================
# 6. 실행 방법
# =====================================
# 터미널:
# uvicorn main:app --reload

# 접속:
# http://127.0.0.1:8000/docs

# =====================================
# ✅ 체크리스트
# =====================================
# 1. C:/pure_chosun_bot_db 경로 존재
# 2. collection_name 동일 (chosun_univ_info)
# 3. embedding 모델 동일
# 4. 실행 시 DB 개수 출력 확인

# =====================================
# 🚀 다음 단계
# =====================================
# - LLM 연결
# - Vue 프론트 연결
# - 답변 품질 개선

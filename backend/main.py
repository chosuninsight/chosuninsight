import os
import re
from collections import defaultdict
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from rank_bm25 import BM25Okapi

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
VECTOR_TOP_K = int(os.getenv("VECTOR_TOP_K", "6"))
BM25_TOP_K = int(os.getenv("BM25_TOP_K", "6"))
HYBRID_TOP_K = int(os.getenv("HYBRID_TOP_K", "6"))
RRF_K = int(os.getenv("RRF_K", "60"))
QUERY_EXPANSION_RULES = {
    "컴공": ["컴퓨터공학과", "컴퓨터공학전공"],
    "컴퓨터공학과": ["컴퓨터공학전공", "컴공"],
    "소웨": ["소프트웨어학부", "소프트웨어"],
    "정통": ["정보통신공학전공", "정보통신공학과"],
    "정시": ["정시모집", "정시 전형"],
    "수시": ["수시모집", "수시 전형"],
    "졸업학점": ["졸업 요건", "졸업이수학점", "졸업 이수 학점"],
    "졸업요건": ["졸업 학점", "졸업이수학점", "졸업 이수 학점"],
    "장학금": ["장학", "장학 안내", "장학안내"],
}
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://foxibu.is-a.dev:9000"
    ).split(",")
    if origin.strip()
]

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# =====================================
# 1. FastAPI 기본 설정
# =====================================
app = FastAPI(title="Chosun RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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

@dataclass(frozen=True)
class IndexedDocument:
    key: str
    content: str
    source: str
    store: str

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

def tokenize_korean_text(text: str) -> list[str]:
    return re.findall(r"[0-9A-Za-z가-힣]+", text.lower())

def expand_query_variants(query: str) -> list[str]:
    variants = [query.strip()]

    for term, expansions in QUERY_EXPANSION_RULES.items():
        if term in query:
            for expansion in expansions:
                variants.append(query.replace(term, expansion))
            variants.extend(expansions)

    seen = set()
    deduped_variants = []
    for variant in variants:
        normalized_variant = variant.strip()
        if not normalized_variant or normalized_variant in seen:
            continue
        seen.add(normalized_variant)
        deduped_variants.append(normalized_variant)

    return deduped_variants

def build_doc_key(content: str, source: str, store: str) -> str:
    return f"{store}::{source}::{content}"

def load_collection_documents(vectorstore: Chroma, store_name: str) -> list[IndexedDocument]:
    raw = vectorstore._collection.get(include=["documents", "metadatas"])
    documents = raw.get("documents", [])
    metadatas = raw.get("metadatas", [])
    indexed_docs = []

    for content, metadata in zip(documents, metadatas):
        source = ""
        if metadata:
            source = metadata.get("source", "")

        indexed_docs.append(
            IndexedDocument(
                key=build_doc_key(content, source, store_name),
                content=content,
                source=source,
                store=store_name,
            )
        )

    return indexed_docs

all_indexed_docs = (
    load_collection_documents(vectorstore_origin, "origin")
    + load_collection_documents(vectorstore_update, "update")
)
indexed_doc_map = {doc.key: doc for doc in all_indexed_docs}
bm25_corpus = [tokenize_korean_text(doc.content) for doc in all_indexed_docs]
bm25 = BM25Okapi(bm25_corpus) if bm25_corpus else None

print("🔎 하이브리드 검색 문서 개수:", len(all_indexed_docs))

def reciprocal_rank_fusion(rank_lists: list[list[str]], limit: int) -> list[str]:
    fused_scores = defaultdict(float)

    for rank_list in rank_lists:
        for rank, doc_key in enumerate(rank_list, start=1):
            fused_scores[doc_key] += 1.0 / (RRF_K + rank)

    return [
        doc_key
        for doc_key, _ in sorted(
            fused_scores.items(),
            key=lambda item: item[1],
            reverse=True
        )[:limit]
    ]

def run_vector_search(vectorstore: Chroma, store_name: str, query: str, k: int) -> list[str]:
    results = vectorstore.similarity_search_with_score(query, k=k)
    ranked_keys = []

    for doc, _score in results:
        key = build_doc_key(
            doc.page_content,
            doc.metadata.get("source", ""),
            store_name,
        )
        if key in indexed_doc_map:
            ranked_keys.append(key)

    return ranked_keys

def run_bm25_search(query: str, k: int) -> list[str]:
    if not bm25:
        return []

    tokenized_query = tokenize_korean_text(query)
    if not tokenized_query:
        return []

    scores = bm25.get_scores(tokenized_query)
    ranked_pairs = sorted(
        enumerate(scores),
        key=lambda item: item[1],
        reverse=True
    )

    ranked_keys = []
    for doc_index, score in ranked_pairs:
        if score <= 0:
            continue
        ranked_keys.append(all_indexed_docs[doc_index].key)
        if len(ranked_keys) >= k:
            break

    return ranked_keys

# =====================================
# 🔥 4. 검색 함수 (벡터 + BM25 하이브리드)
# =====================================
def search_docs(query: str):
    if not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="질문이 비어 있습니다."
        )

    query_variants = expand_query_variants(query)
    vector_ranked_keys = []
    bm25_ranked_keys = []

    for query_variant in query_variants:
        vector_ranked_keys.extend(
            run_vector_search(
                vectorstore_origin,
                "origin",
                query_variant,
                VECTOR_TOP_K // 2 + VECTOR_TOP_K % 2,
            )
        )
        vector_ranked_keys.extend(
            run_vector_search(
                vectorstore_update,
                "update",
                query_variant,
                VECTOR_TOP_K // 2,
            )
        )
        bm25_ranked_keys.extend(run_bm25_search(query_variant, BM25_TOP_K))

    fused_keys = reciprocal_rank_fusion(
        [vector_ranked_keys, bm25_ranked_keys],
        HYBRID_TOP_K
    )

    docs, sources = [], []

    for doc_key in fused_keys:
        doc = indexed_doc_map[doc_key]
        docs.append(doc.content)
        sources.append(doc.source)

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

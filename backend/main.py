from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import *
from backend.models import *
from backend.utils import *
from backend.search_logic import *
from backend.handlers import *
from backend.memory import ConversationMemoryStore

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

conversation_memory = ConversationMemoryStore(
    ttl_seconds=CHAT_MEMORY_TTL_SECONDS,
    max_sessions=CHAT_MEMORY_MAX_SESSIONS,
)

# =====================================
# 2. API Routes
# =====================================

@app.get("/", status_code=status.HTTP_200_OK)
def root():
    return {
        "success": True,
        "message": "RAG 서버 실행 중"
    }

@app.get("/health/rag", status_code=status.HTTP_200_OK)
def rag_health():
    errors = []
    def collection_count(vectorstore, label: str) -> int | None:
        try: return int(vectorstore._collection.count())
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            return None

    origin_count = collection_count(vectorstore_origin, "origin")
    update_count = collection_count(vectorstore_update, "update")
    indexed_counts = dict(indexed_doc_counts_by_store)
    healthy = origin_count is not None and update_count is not None

    return {
        "success": healthy,
        "status": "ok" if healthy else "degraded",
        "collections": {
            "origin": {
                "name": ORIGIN_COLLECTION_NAME,
                "directory": PERSIST_DIRECTORY,
                "collection_count": origin_count,
                "indexed_count": indexed_counts.get("origin", 0),
            },
            "update": {
                "name": UPDATE_COLLECTION_NAME,
                "directory": UPDATE_DB_DIRECTORY,
                "collection_count": update_count,
                "indexed_count": indexed_counts.get("update", 0),
            },
        },
        "total_indexed_documents": len(all_indexed_docs),
        "errors": errors,
    }

@app.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat(req: ChatRequest):
    # 1. 메모리 및 대화 해석
    history = req.history or []
    if not history and CHAT_MEMORY_ENABLED:
        memory_context = conversation_memory.build_context(req.session_id)
        if memory_context:
            history = [ChatHistoryMessage(role="user", content=memory_context)]
    
    interpretation = await interpret_chat_request(req.question, history)
    state = build_conversation_state(req.question, history, interpretation)
    
    # 2. 구조화된 도메인 답변 (학사일정, 교수진, 졸업요건 등)
    structured_answer = build_structured_domain_answer(req.question, history, state, interpretation)
    if structured_answer:
        if CHAT_MEMORY_ENABLED:
            conversation_memory.update(req.session_id, req.question, interpretation, state)
        return {
            "success": True,
            "answer": append_basis_line(structured_answer.answer, structured_answer.answer_mode, structured_answer.sources),
            "sources": [],
            "suggestions": suggestions_for_answer(structured_answer.answer_mode, state, structured_answer.suggestion_context),
            "debug": {"answer_mode": structured_answer.answer_mode, "interpretation": interpretation} if req.debug else None,
        }

    # 3. 공식 웹 검색 / Fallback 처리
    if state.domain_intent in ["official_fallback", "faculty"]:
        web_answer = await build_official_web_search_answer_direct(req.question, history, interpretation)
        if web_answer:
            if CHAT_MEMORY_ENABLED:
                conversation_memory.update(req.session_id, req.question, interpretation, state)
            return {
                "success": True,
                "answer": append_basis_line(web_answer.answer, web_answer.answer_mode, web_answer.sources),
                "sources": [],
                "suggestions": suggestions_for_answer(web_answer.answer_mode, state, web_answer.suggestion_context),
            }
        
        fallback_answer = build_entity_official_fallback_answer(req.question, history)
        if fallback_answer:
            return {
                "success": True,
                "answer": append_basis_line(fallback_answer.answer, fallback_answer.answer_mode, fallback_answer.sources),
                "sources": [],
                "suggestions": suggestions_for_answer(fallback_answer.answer_mode, state, fallback_answer.suggestion_context),
            }

    # 4. 일반 RAG 검색
    search_query = interpretation.get("standalone_question") or req.question
    search_result = search_docs(search_query)
    
    if not search_result.hits:
        return {"success": True, "answer": "확인된 자료에서 관련 정보를 찾지 못했습니다. 소속 학과 사무실이나 홈페이지 공지사항을 확인해 보세요.", "sources": []}

    context = "\n".join(hit.content for hit in search_result.hits)
    answer = await get_gpt_response(req.question, context, history, interpretation)
    
    if CHAT_MEMORY_ENABLED:
        conversation_memory.update(req.session_id, req.question, interpretation, state)

    return {
        "success": True,
        "answer": append_basis_line(answer, "rag", []),
        "sources": [],
        "suggestions": suggestions_for_answer("rag", state),
        "debug": search_result.debug if req.debug else None,
    }

@app.exception_handler(Exception)
def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"success": False, "message": "서버 내부 오류 발생", "detail": str(exc)}
    )

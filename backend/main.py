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
    # 1. Memory and Intent Analysis
    history = req.history or []
    if CHAT_MEMORY_ENABLED:
        memory_context = conversation_memory.build_context(req.session_id)
        if memory_context and not any(memory_context in msg.content for msg in history):
            history = [ChatHistoryMessage(role="user", content=memory_context)] + history
    
    # LLM-driven interpretation (Domain, Slots, Topic)
    interpretation = await interpret_chat_request(req.question, history)
    state = build_conversation_state(req.question, history, interpretation)
    
    # 2. Hybrid-RAG Pipeline (Primary Path)
    # Get high-accuracy context from structured data or traditional RAG
    structured_data = build_structured_domain_answer(req.question, history, state, interpretation)
    context_text = ""
    answer_mode = "rag"
    sources = []
    suggestion_context = ""

    if structured_data:
        context_text = structured_data.answer
        answer_mode = structured_data.answer_mode
        sources = structured_data.sources
        suggestion_context = structured_data.suggestion_context
    else:
        # Fallback to vector search if no structured handler matched
        search_query = interpretation.get("standalone_question") or req.question
        search_result = search_docs(search_query)
        if search_result.hits:
            context_text = "\n".join(hit.content for hit in search_result.hits)
            answer_mode = "rag"
            sources = [hit.source for hit in search_result.hits]

    # 3. Web Search Fallback
    is_realtime_query = interpretation.get("is_realtime_required", False)
    # Priority: Structured > Web Search (if realtime/missing) > RAG
    # We only call Web Search if context is empty, OR domain is explicitly web_search,
    # OR it's a realtime query that hasn't found a structured/official answer yet.
    if not context_text or state.domain_intent == "web_search" or (is_realtime_query and answer_mode == "rag"):
        web_answer = await build_official_web_search_answer_direct(req.question, history, interpretation)
        if web_answer:
            context_text = web_answer.answer
            answer_mode = web_answer.answer_mode
            sources = web_answer.sources
            suggestion_context = web_answer.suggestion_context

    # 4. Final Generation using LLM (Natural Language synthesis)
    # Exceptions: current_date, clarifying_question, official_fallback should remain structured/direct
    if answer_mode in ["current_date", "clarifying_question", "official_fallback"]:
        final_answer = context_text
    else:
        final_answer = await get_gpt_response(req.question, context_text, history, interpretation)
    
    # Validation for empty responses or low-quality RAG
    if not final_answer or "정보를 찾지 못했습니다" in final_answer:
        fallback_answer = build_entity_official_fallback_answer(req.question, history)
        if fallback_answer:
            final_answer = fallback_answer.answer
            answer_mode = fallback_answer.answer_mode

    # Final cleanup and memory update
    if not final_answer:
        final_answer = "현재 관련 정보를 찾기 어렵습니다. 조선대학교 공식 홈페이지(https://www.chosun.ac.kr)를 확인해 주시기 바랍니다."

    if CHAT_MEMORY_ENABLED:
        conversation_memory.update(req.session_id, req.question, interpretation, state)

    return {
        "success": True,
        "answer": append_basis_line(final_answer, answer_mode, sources),
        "sources": [],
        "suggestions": [], # Disabled per user request
        "debug": {"answer_mode": answer_mode, "interpretation": interpretation} if req.debug else None,
    }

@app.exception_handler(Exception)
def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"success": False, "message": "서버 내부 오류 발생", "detail": str(exc)}
    )

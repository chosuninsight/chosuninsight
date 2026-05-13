from fastapi import FastAPI, HTTPException, status, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Any

from backend.config import *
from backend.models import *
from backend.utils import *
from backend.search_logic import *
from backend.handlers import *
from backend.memory import create_conversation_memory_store

# =====================================
# 1. 보안 및 의존성 설정
# =====================================
async def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key or x_api_key != INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="유효하지 않은 API 키입니다."
        )
    return x_api_key

# =====================================
# 2. FastAPI 기본 설정
# =====================================
app = FastAPI(title="Chosun RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conversation_memory = create_conversation_memory_store(
    provider=MEMORY_PROVIDER,
    ttl_seconds=CHAT_MEMORY_TTL_SECONDS,
    max_sessions=CHAT_MEMORY_MAX_SESSIONS,
    store_path=MEMORY_STORE_PATH,
    agent_id=MEMORY_AGENT_ID,
)


def is_memory_recall_question(question: str) -> bool:
    normalized = str(question or "").replace(" ", "")
    return any(
        marker in normalized
        for marker in [
            "내가알려준정보",
            "내정보",
            "뭘기억",
            "뭐기억",
            "기억하고있는",
            "기억나는",
            "알려준게뭐",
        ]
    )


def is_memory_clear_question(question: str) -> bool:
    normalized = str(question or "").replace(" ", "")
    return any(
        marker in normalized
        for marker in [
            "내정보초기화",
            "메모리초기화",
            "기억초기화",
            "내정보다지워",
            "기억다지워",
            "모든기억삭제",
            "전체기억삭제",
        ]
    )


def is_memory_disable_question(question: str) -> bool:
    normalized = str(question or "").replace(" ", "")
    return any(
        marker in normalized
        for marker in [
            "앞으로기억하지마",
            "앞으론기억하지마",
            "이제기억하지마",
            "메모리꺼",
            "기억기능꺼",
            "저장하지마",
            "내정보저장하지마",
        ]
    )


def is_memory_enable_question(question: str) -> bool:
    normalized = str(question or "").replace(" ", "")
    return any(
        marker in normalized
        for marker in [
            "다시기억해",
            "기억다시해",
            "메모리켜",
            "기억기능켜",
            "저장해도돼",
            "기억해도돼",
        ]
    )


def is_memory_delete_question(question: str) -> bool:
    normalized = str(question or "").replace(" ", "")
    return any(
        marker in normalized
        for marker in [
            "기억하지마",
            "기억하지말아",
            "기억에서빼",
            "기억에서삭제",
            "기억삭제",
            "메모리삭제",
            "정보삭제",
            "내정보삭제",
            "지워줘",
            "지워",
            "없애줘",
            "없애",
            "삭제해줘",
            "삭제",
            "잊어줘",
            "잊어버려",
            "까먹어",
        ]
    )


def format_memory_recall_answer(memory_context: str) -> str:
    text = memory_context
    text = text.replace("이전 대화에서 사용자가 알려준 개인 상황 참고 정보: ", "")
    text = text.replace("이전 대화에서 사용자가 알려준 정보: ", "")
    text = text.replace(
        ". 이 정보는 사용자의 상황 파악용이며 조선대학교 공식 학사 정보보다 우선하지 않는다.",
        "",
    )
    facts = [part.strip() for part in text.rstrip(".").split(";") if part.strip()]
    if not facts:
        return "현재 기억하고 있는 개인 상황 정보는 없습니다."
    return "현재 기억하고 있는 정보는 다음과 같습니다.\n" + "\n".join(f"• {fact}" for fact in facts)


def memory_debug_payload(session_id: str | None, enabled: bool) -> dict[str, Any] | None:
    return conversation_memory.debug_snapshot(session_id) if enabled else None

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

@app.get("/memory/{session_id}", status_code=status.HTTP_200_OK)
def get_memory(session_id: str):
    return {
        "success": True,
        "memory": conversation_memory.debug_snapshot(session_id),
    }

@app.delete("/memory/{session_id}", status_code=status.HTTP_200_OK)
def clear_memory(session_id: str):
    deleted = conversation_memory.clear(session_id)
    return {
        "success": True,
        "deleted": deleted,
        "memory": conversation_memory.debug_snapshot(session_id),
    }

@app.delete("/memory/{session_id}/items/{memory_id}", status_code=status.HTTP_200_OK)
def delete_memory_item(session_id: str, memory_id: str):
    deleted = conversation_memory.delete_by_id(session_id, memory_id)
    return {
        "success": True,
        "deleted": deleted,
        "memory": conversation_memory.debug_snapshot(session_id),
    }

@app.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat(req: ChatRequest):
    # 1. Memory and Intent Analysis
    history = req.history or []

    if CHAT_MEMORY_ENABLED and is_memory_enable_question(req.question):
        conversation_memory.set_enabled(req.session_id, True)
        return {
            "success": True,
            "answer": "이제부터 이 채팅에서 알려준 개인 상황 정보를 다시 기억하겠습니다.",
            "sources": [],
            "suggestions": [],
            "debug": {"answer_mode": "memory_enable", "memory": memory_debug_payload(req.session_id, req.debug)} if req.debug else None,
        }

    if CHAT_MEMORY_ENABLED and is_memory_disable_question(req.question):
        deleted = conversation_memory.clear(req.session_id)
        conversation_memory.set_enabled(req.session_id, False)
        return {
            "success": True,
            "answer": f"앞으로 이 채팅에서는 개인 상황 정보를 기억하지 않겠습니다. 기존에 기억하던 정보 {deleted}개도 삭제했습니다.",
            "sources": [],
            "suggestions": [],
            "debug": {"answer_mode": "memory_disable", "memory": memory_debug_payload(req.session_id, req.debug)} if req.debug else None,
        }

    if CHAT_MEMORY_ENABLED and req.memory_enabled and is_memory_clear_question(req.question):
        deleted = conversation_memory.clear(req.session_id)
        return {
            "success": True,
            "answer": f"기억하고 있던 개인 상황 정보 {deleted}개를 삭제했습니다.",
            "sources": [],
            "suggestions": [],
            "debug": {"answer_mode": "memory_clear", "memory": memory_debug_payload(req.session_id, req.debug)} if req.debug else None,
        }

    if CHAT_MEMORY_ENABLED and req.memory_enabled and is_memory_delete_question(req.question):
        deleted = conversation_memory.delete_matching(req.session_id, req.question)
        answer = "요청하신 기억을 삭제했습니다." if deleted else "삭제할 관련 기억을 찾지 못했습니다."
        return {
            "success": True,
            "answer": answer,
            "sources": [],
            "suggestions": [],
            "debug": {"answer_mode": "memory_delete", "memory": memory_debug_payload(req.session_id, req.debug)} if req.debug else None,
        }

    memory_context = ""
    if CHAT_MEMORY_ENABLED and req.memory_enabled:
        memory_context = conversation_memory.build_context(req.session_id, req.question)
        if memory_context and not any(memory_context in msg.content for msg in history):
            history = [ChatHistoryMessage(role="user", content=memory_context)] + history

    if CHAT_MEMORY_ENABLED and req.memory_enabled and memory_context and is_memory_recall_question(req.question):
        memory_debug = conversation_memory.debug_snapshot(req.session_id) if req.debug else None
        return {
            "success": True,
            "answer": format_memory_recall_answer(memory_context),
            "sources": [],
            "suggestions": [],
            "debug": {"answer_mode": "memory_recall", "memory": memory_debug} if req.debug else None,
        }
    
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

    if CHAT_MEMORY_ENABLED and req.memory_enabled:
        conversation_memory.update(req.session_id, req.question, interpretation, state, final_answer)

    debug_payload = None
    if req.debug:
        debug_payload = {"answer_mode": answer_mode, "interpretation": interpretation}
        memory_debug = conversation_memory.debug_snapshot(req.session_id) if CHAT_MEMORY_ENABLED else None
        if memory_debug:
            debug_payload["memory"] = memory_debug

    return {
        "success": True,
        "answer": append_basis_line(final_answer, answer_mode, sources),
        "sources": [],
        "suggestions": [], # Disabled per user request
        "debug": debug_payload,
    }

@app.exception_handler(Exception)
def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"success": False, "message": "서버 내부 오류 발생", "detail": str(exc)}
    )
ss": False, "message": "서버 내부 오류 발생", "detail": str(exc)}
    )

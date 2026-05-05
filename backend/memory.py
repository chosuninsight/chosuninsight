import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationMemory:
    facts: dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)


class ConversationMemoryStore:
    def __init__(self, ttl_seconds: int = 86400, max_sessions: int = 500):
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._sessions: dict[str, ConversationMemory] = {}

    def build_context(self, session_id: str | None) -> str:
        session_key = self._normalize_session_id(session_id)
        if not session_key:
            return ""

        memory = self._sessions.get(session_key)
        if not memory or self._is_expired(memory):
            self._sessions.pop(session_key, None)
            return ""

        facts = memory.facts
        parts = []
        if facts.get("department"):
            parts.append(f"학과/전공은 {facts['department']}")
        if facts.get("cohort_year"):
            parts.append(f"입학연도는 {facts['cohort_year']}년")
        if facts.get("topic"):
            parts.append(f"최근 관심 주제는 {facts['topic']}")

        credit_progress = facts.get("credit_progress") or {}
        if isinstance(credit_progress, dict):
            credit_parts = [
                f"{area} {credits}학점"
                for area, credits in credit_progress.items()
                if area and credits
            ]
            if credit_parts:
                parts.append(f"이수학점은 {', '.join(credit_parts)}")

        if not parts:
            return ""

        memory.updated_at = time.time()
        return "이전 대화에서 사용자가 알려준 정보: " + "; ".join(parts) + "."

    def update(
        self,
        session_id: str | None,
        question: str,
        interpretation: dict[str, Any] | None,
        state: Any,
    ) -> None:
        session_key = self._normalize_session_id(session_id)
        if not session_key:
            return

        self._prune()
        memory = self._sessions.setdefault(session_key, ConversationMemory())
        facts = memory.facts

        department = str((interpretation or {}).get("department", "") or "").strip()
        department = department or str(getattr(state, "department", "") or "").strip()
        if department:
            facts["department"] = department

        cohort_year = getattr(state, "cohort_year", None)
        if cohort_year:
            facts["cohort_year"] = cohort_year

        topic = str((interpretation or {}).get("topic", "") or "").strip()
        if topic and topic != "other":
            facts["topic"] = topic

        credit_progress = self._extract_credit_progress(interpretation)
        if credit_progress:
            existing = facts.setdefault("credit_progress", {})
            if isinstance(existing, dict):
                existing.update(credit_progress)
            else:
                facts["credit_progress"] = credit_progress

        facts["last_question"] = question[:300]
        memory.updated_at = time.time()

    def debug_snapshot(self, session_id: str | None) -> dict[str, Any]:
        session_key = self._normalize_session_id(session_id)
        memory = self._sessions.get(session_key) if session_key else None
        if not memory:
            return {}
        return {
            "session_id": session_key,
            "facts": dict(memory.facts),
            "updated_at": memory.updated_at,
        }

    def _extract_credit_progress(self, interpretation: dict[str, Any] | None) -> dict[str, int]:
        progress_items = (interpretation or {}).get("credit_progress", [])
        if not isinstance(progress_items, list):
            return {}

        progress: dict[str, int] = {}
        for item in progress_items:
            if not isinstance(item, dict):
                continue
            area = str(item.get("area", "") or "").strip()
            credits = item.get("credits")
            try:
                parsed_credits = int(credits)
            except (TypeError, ValueError):
                continue
            if area and parsed_credits > 0:
                progress[area] = parsed_credits
        return progress

    def _normalize_session_id(self, session_id: str | None) -> str:
        return str(session_id or "").strip()[:128]

    def _is_expired(self, memory: ConversationMemory) -> bool:
        return self.ttl_seconds > 0 and time.time() - memory.updated_at > self.ttl_seconds

    def _prune(self) -> None:
        now = time.time()
        expired = [
            session_id
            for session_id, memory in self._sessions.items()
            if self.ttl_seconds > 0 and now - memory.updated_at > self.ttl_seconds
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)

        if len(self._sessions) <= self.max_sessions:
            return

        oldest = sorted(self._sessions.items(), key=lambda item: item[1].updated_at)
        for session_id, _ in oldest[: len(self._sessions) - self.max_sessions]:
            self._sessions.pop(session_id, None)

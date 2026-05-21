from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any
try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None


class MemoryProvider:
    def build_context(self, session_id: str | None, question: str | None = None) -> str:
        raise NotImplementedError

    def update(
        self,
        session_id: str | None,
        question: str,
        interpretation: dict[str, Any] | None,
        state: Any,
        answer: str | None = None,
    ) -> None:
        raise NotImplementedError

    def debug_snapshot(self, session_id: str | None) -> dict[str, Any]:
        return {}

    def clear(self, session_id: str | None) -> int:
        return 0

    def delete_matching(self, session_id: str | None, question: str) -> int:
        return 0

    def delete_by_id(self, session_id: str | None, memory_id: str) -> int:
        return 0

    def set_enabled(self, session_id: str | None, enabled: bool) -> None:
        return None

    def is_enabled(self, session_id: str | None) -> bool:
        return True


@dataclass
class ConversationMemory:
    facts: dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)


class LocalConversationMemoryStore(MemoryProvider):
    def __init__(self, ttl_seconds: int = 86400, max_sessions: int = 500):
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._sessions: dict[str, ConversationMemory] = {}
        self._disabled_sessions: set[str] = set()
        self._lock = threading.RLock()

    def build_context(self, session_id: str | None, question: str | None = None) -> str:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            if not session_key or session_key in self._disabled_sessions:
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
        answer: str | None = None,
    ) -> None:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            if not session_key or session_key in self._disabled_sessions:
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
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            memory = self._sessions.get(session_key) if session_key else None
            if not memory:
                return {"memory_enabled": session_key not in self._disabled_sessions} if session_key else {}
            return {
                "session_id": session_key,
                "memory_enabled": session_key not in self._disabled_sessions,
                "facts": dict(memory.facts),
                "updated_at": memory.updated_at,
            }

    def clear(self, session_id: str | None) -> int:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            if not session_key:
                return 0
            memory = self._sessions.pop(session_key, None)
            return len(memory.facts) if memory else 0

    def set_enabled(self, session_id: str | None, enabled: bool) -> None:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            if not session_key:
                return
            if enabled:
                self._disabled_sessions.discard(session_key)
            else:
                self._disabled_sessions.add(session_key)

    def is_enabled(self, session_id: str | None) -> bool:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            return bool(session_key) and session_key not in self._disabled_sessions

    def delete_matching(self, session_id: str | None, question: str) -> int:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            memory = self._sessions.get(session_key) if session_key else None
            if not memory:
                return 0

            categories = self._deletion_categories(question)
            if not categories:
                return 0

            deleted = 0
            for category in categories:
                if category == "credit_progress" and isinstance(memory.facts.get("credit_progress"), dict):
                    deleted += len(memory.facts["credit_progress"])
                    memory.facts.pop("credit_progress", None)
                elif category in memory.facts:
                    memory.facts.pop(category, None)
                    deleted += 1
            if deleted:
                memory.updated_at = time.time()
            return deleted

    def delete_by_id(self, session_id: str | None, memory_id: str) -> int:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            memory = self._sessions.get(session_key) if session_key else None
            if not memory or not memory_id:
                return 0

            key_map = {
                "department:major": "department",
                "cohort_year:admission": "cohort_year",
            }
            fact_key = key_map.get(memory_id)
            if fact_key and fact_key in memory.facts:
                memory.facts.pop(fact_key, None)
                memory.updated_at = time.time()
                return 1
            if memory_id.startswith("credit_progress:") and isinstance(memory.facts.get("credit_progress"), dict):
                area = memory_id.split(":", 1)[1]
                if area in memory.facts["credit_progress"]:
                    memory.facts["credit_progress"].pop(area, None)
                    memory.updated_at = time.time()
                    return 1
            return 0

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

    def _deletion_categories(self, question: str) -> set[str]:
        categories = set()
        if any(word in question for word in ["학과", "전공", "컴공", "소웨"]):
            categories.add("department")
        if any(word in question for word in ["학번", "입학"]):
            categories.add("cohort_year")
        if any(word in question for word in ["학점", "이수"]):
            categories.add("credit_progress")
        if any(word in question for word in ["관심", "주제"]):
            categories.add("topic")
        return categories

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


class LocalMem0MemoryStore(MemoryProvider):
    def __init__(
        self,
        store_path: str = "backend/data/local_memory_store.json",
        agent_id: str = "chosuninsight",
        ttl_seconds: int = 86400 * 30,
        max_sessions: int = 500,
        encryption_key: str | None = None,
    ):
        self.store_path = store_path
        self.agent_id = agent_id
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.encryption_key = encryption_key
        self._fernet = None
        if encryption_key and Fernet:
            try:
                self._fernet = Fernet(encryption_key.encode())
            except Exception as exc:
                print(f"Warning: 유효하지 않은 메모리 암호화 키: {exc}")

        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"sessions": {}}
        self._load()

    def build_context(self, session_id: str | None, question: str | None = None) -> str:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            if not session_key or not question or not self.is_enabled(session_key):
                return ""

            self._prune()
            memories = self._search_memories(session_key, question)
            if not memories:
                return ""

            memory_text = "; ".join(item["text"] for item in memories[:5])
            return (
                "이전 대화에서 사용자가 알려준 개인 상황 참고 정보: "
                f"{memory_text}. 이 정보는 사용자의 상황 파악용이며 조선대학교 공식 학사 정보보다 우선하지 않는다."
            )

    def update(
        self,
        session_id: str | None,
        question: str,
        interpretation: dict[str, Any] | None,
        state: Any,
        answer: str | None = None,
    ) -> None:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            if not session_key or not self.is_enabled(session_key):
                return

            if self._is_delete_memory_question(question):
                self.delete_matching(session_key, question)
                return

            if self._has_sensitive_identifier(question):
                print("Warning: 민감정보가 포함된 입력은 메모리에 저장하지 않음")
                return

            extracted = self._extract_memory_items(question, interpretation, state)
            if not extracted:
                return

            self._prune()
            session = self._session(session_key)
            for item in extracted:
                self._upsert_memory(session, item)
            session["updated_at"] = time.time()
            self._save()

    def debug_snapshot(self, session_id: str | None) -> dict[str, Any]:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            session = self._data.get("sessions", {}).get(session_key) if session_key else None
            memories = (session or {}).get("memories", [])
            return {
                "provider": "local_mem0",
                "store_path": self.store_path,
                "agent_id": self.agent_id,
                "memory_enabled": self.is_enabled(session_key),
                "memory_count": len(memories),
                "recent_memories": memories[-5:],
            }

    def clear(self, session_id: str | None) -> int:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            sessions = self._data.setdefault("sessions", {})
            session = sessions.pop(session_key, None) if session_key else None
            if session is None:
                return 0
            deleted = len(session.get("memories", []))
            self._save()
            return deleted

    def delete_matching(self, session_id: str | None, question: str) -> int:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            session = self._data.get("sessions", {}).get(session_key) if session_key else None
            if not session:
                return 0

            memories = session.get("memories", [])
            if not isinstance(memories, list) or not memories:
                return 0

            targets = self._deletion_targets(question)
            if not targets:
                return 0

            kept = []
            deleted = 0
            for memory in memories:
                if self._matches_delete_target(memory, targets):
                    deleted += 1
                else:
                    kept.append(memory)

            if deleted:
                session["memories"] = kept
                session["updated_at"] = time.time()
                self._save()
            return deleted

    def delete_by_id(self, session_id: str | None, memory_id: str) -> int:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            session = self._data.get("sessions", {}).get(session_key) if session_key else None
            if not session or not memory_id:
                return 0

            memories = session.get("memories", [])
            if not isinstance(memories, list):
                return 0

            kept = [memory for memory in memories if memory.get("id") != memory_id]
            deleted = len(memories) - len(kept)
            if deleted:
                session["memories"] = kept
                session["updated_at"] = time.time()
                self._save()
            return deleted

    def set_enabled(self, session_id: str | None, enabled: bool) -> None:
        with self._lock:
            session_key = self._normalize_session_id(session_id)
            if not session_key:
                return
            session = self._session(session_key)
            session["memory_enabled"] = enabled
            session["updated_at"] = time.time()
            self._save()

    def is_enabled(self, session_id: str | None) -> bool:
        session_key = self._normalize_session_id(session_id)
        if not session_key:
            return False
        session = self._data.get("sessions", {}).get(session_key)
        return bool((session or {}).get("memory_enabled", True))

    def _extract_memory_items(
        self,
        question: str,
        interpretation: dict[str, Any] | None,
        state: Any,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        now = time.time()

        department = str((interpretation or {}).get("department", "") or "").strip()
        department = department or str(getattr(state, "department", "") or "").strip()
        department = self._extract_department_from_text(question) or department
        if department:
            items.append(self._memory_item("department", "major", department, f"학과/전공은 {department}", question, now))

        cohort_year = getattr(state, "cohort_year", None)
        cohort_year = self._extract_cohort_year_from_text(question) or cohort_year
        if cohort_year:
            items.append(self._memory_item("cohort_year", "admission", str(cohort_year), f"입학연도는 {cohort_year}년", question, now))

        topic = str((interpretation or {}).get("topic", "") or "").strip()
        if topic and topic != "other":
            items.append(self._memory_item("topic", topic, topic, f"최근 관심 주제는 {topic}", question, now))

        credit_progress = self._extract_credit_progress(interpretation)
        credit_progress.update(self._extract_credit_progress_from_text(question))
        for area, credits in credit_progress.items():
            items.append(
                self._memory_item(
                    "credit_progress",
                    area,
                    str(credits),
                    f"{area} 영역 이수학점은 {credits}학점",
                    question,
                    now,
                )
            )

        return items

    def _memory_item(
        self,
        category: str,
        subject: str,
        value: str,
        text: str,
        question: str,
        now: float,
    ) -> dict[str, Any]:
        return {
            "id": f"{category}:{subject}",
            "category": category,
            "subject": subject,
            "value": value,
            "text": text,
            "source_question": self._redact_sensitive_text(question)[:300],
            "created_at": now,
            "updated_at": now,
            "confidence": 1.0,
        }

    def _search_memories(self, session_key: str, question: str) -> list[dict[str, Any]]:
        session = self._data.get("sessions", {}).get(session_key)
        memories = (session or {}).get("memories", [])
        if not memories:
            return []

        query_terms = self._tokenize(question)
        scored = []
        for memory in memories:
            score = self._score_memory(memory, query_terms, question)
            if score > 0:
                scored.append((score, memory))

        if not scored:
            profile_categories = {"department", "cohort_year", "credit_progress"}
            scored = [
                (0.1, memory)
                for memory in memories
                if memory.get("category") in profile_categories
            ]

        scored.sort(key=lambda item: (item[0], item[1].get("updated_at", 0)), reverse=True)
        return [memory for _, memory in scored[:5]]

    def _score_memory(self, memory: dict[str, Any], query_terms: set[str], question: str) -> float:
        text = " ".join(
            str(memory.get(key, ""))
            for key in ["category", "subject", "value", "text", "source_question"]
        )
        memory_terms = self._tokenize(text)
        overlap = len(query_terms & memory_terms)
        score = overlap * 1.0

        category = str(memory.get("category", ""))
        subject = str(memory.get("subject", ""))
        category_keywords = {
            "department": ["학과", "전공", "컴공", "소웨", "정보통신"],
            "cohort_year": ["학번", "입학", "졸업", "요건"],
            "credit_progress": ["학점", "이수", "졸업", "교양", "전공"],
            "topic": [subject],
        }
        for keyword in category_keywords.get(category, []):
            if keyword and keyword in question:
                score += 2.0

        if category in {"department", "cohort_year"}:
            score += 0.2

        age_seconds = max(0.0, time.time() - float(memory.get("updated_at", 0) or 0))
        score += max(0.0, 0.5 - age_seconds / max(self.ttl_seconds, 1))
        return score

    def _upsert_memory(self, session: dict[str, Any], item: dict[str, Any]) -> None:
        memories = session.setdefault("memories", [])
        for existing in memories:
            if existing.get("id") == item["id"]:
                value_changed = existing.get("value") != item["value"]
                existing["updated_at"] = item["updated_at"]
                existing["confidence"] = item["confidence"]
                if value_changed:
                    existing["value"] = item["value"]
                    existing["text"] = item["text"]
                    existing["source_question"] = item["source_question"]
                return
        memories.append(item)

    def _session(self, session_key: str) -> dict[str, Any]:
        sessions = self._data.setdefault("sessions", {})
        return sessions.setdefault(
            session_key,
            {
                "agent_id": self.agent_id,
                "memory_enabled": True,
                "created_at": time.time(),
                "updated_at": time.time(),
                "memories": [],
            },
        )

    def _load(self) -> None:
        if not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path, "rb") as f:
                content = f.read()
            if not content:
                return

            try:
                # If content starts with '{', it's likely plain JSON
                if content.strip().startswith(b"{"):
                    data = json.loads(content.decode("utf-8"))
                elif self._fernet:
                    decrypted = self._fernet.decrypt(content)
                    data = json.loads(decrypted.decode("utf-8"))
                else:
                    # Encrypted but no key provided
                    print("Warning: 메모리가 암호화되어 있으나 복호화 키가 없습니다.")
                    return
            except Exception as exc:
                print(f"Warning: 메모리 데이터 파싱/복호화 실패: {exc}")
                return

            if isinstance(data, dict) and isinstance(data.get("sessions"), dict):
                self._data = data
        except Exception as exc:
            print(f"Warning: local mem0 memory 로드 실패: {exc}")

    def _save(self) -> None:
        try:
            directory = os.path.dirname(self.store_path)
            if directory:
                os.makedirs(directory, exist_ok=True)

            raw_json = json.dumps(self._data, ensure_ascii=False, indent=2)
            content = raw_json.encode("utf-8")

            if self._fernet:
                content = self._fernet.encrypt(content)

            tmp_path = f"{self.store_path}.tmp"
            with open(tmp_path, "wb") as f:
                f.write(content)
            os.replace(tmp_path, self.store_path)
        except Exception as exc:
            print(f"Warning: local mem0 memory 저장 실패: {exc}")

    def _prune(self) -> None:
        sessions = self._data.setdefault("sessions", {})
        now = time.time()
        expired = [
            session_id
            for session_id, session in sessions.items()
            if self.ttl_seconds > 0 and now - float(session.get("updated_at", 0) or 0) > self.ttl_seconds
        ]
        for session_id in expired:
            sessions.pop(session_id, None)

        if len(sessions) > self.max_sessions:
            oldest = sorted(sessions.items(), key=lambda item: item[1].get("updated_at", 0))
            for session_id, _ in oldest[: len(sessions) - self.max_sessions]:
                sessions.pop(session_id, None)

    def _tokenize(self, text: str) -> set[str]:
        return {
            token.lower()
            for token in re.findall(r"[0-9A-Za-z가-힣]+", text)
            if len(token) >= 2
        }

    def _is_delete_memory_question(self, question: str) -> bool:
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

    def _deletion_targets(self, question: str) -> set[str]:
        normalized = str(question or "").replace(" ", "")
        if any(marker in normalized for marker in ["전부", "전체", "모든", "다지워", "다삭제", "초기화"]):
            return {"all"}

        targets = set()
        credit_words = ["학점", "이수", "들은학점", "이수학점"]
        if any(word in question for word in credit_words):
            area_targets = {
                "전공": ["전공", "전공학점"],
                "교양": ["교양", "교양학점"],
                "자유선택": ["자유", "자유선택"],
                "총 이수": ["총", "전체"],
            }
            for area, aliases in area_targets.items():
                if any(alias in question for alias in aliases):
                    targets.add(f"credit_progress:{area}")
            if not any(target.startswith("credit_progress:") for target in targets):
                targets.add("credit_progress")
        if any(word in question for word in ["학과", "학부", "컴공", "소웨", "정통", "전공과", "전공은"]) and "credit_progress" not in targets:
            targets.add("department")
        if any(word in question for word in ["학번", "입학연도", "입학 년도", "입학년도"]):
            targets.add("cohort_year")
        if any(word in question for word in ["관심", "주제"]):
            targets.add("topic")
        return targets

    def _matches_delete_target(self, memory: dict[str, Any], targets: set[str]) -> bool:
        if "all" in targets:
            return True
        category = str(memory.get("category", ""))
        subject = str(memory.get("subject", ""))
        return category in targets or subject in targets or f"{category}:{subject}" in targets

    def _has_sensitive_identifier(self, text: str) -> bool:
        patterns = [
            r"\b\d{6}[- ]?[1-4]\d{6}\b",  # resident registration number shape
            r"\b01[016789][- ]?\d{3,4}[- ]?\d{4}\b",
            r"\b\d{2,3}[- ]?\d{3,4}[- ]?\d{4}\b",
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        ]
        sensitive_words = ["주민번호", "주민등록번호", "전화번호", "휴대폰", "주소", "계좌", "비밀번호", "패스워드"]
        return any(re.search(pattern, text) for pattern in patterns) or any(word in text for word in sensitive_words)

    def _redact_sensitive_text(self, text: str) -> str:
        redacted = str(text or "")
        replacements = [
            (r"\b\d{6}[- ]?[1-4]\d{6}\b", "[REDACTED_ID]"),
            (r"\b01[016789][- ]?\d{3,4}[- ]?\d{4}\b", "[REDACTED_PHONE]"),
            (r"\b\d{2,3}[- ]?\d{3,4}[- ]?\d{4}\b", "[REDACTED_PHONE]"),
            (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]"),
        ]
        for pattern, replacement in replacements:
            redacted = re.sub(pattern, replacement, redacted)
        return redacted

    def _extract_department_from_text(self, text: str) -> str:
        normalized = str(text or "")
        aliases = {
            "컴공": "컴퓨터공학과",
            "컴퓨터공학": "컴퓨터공학과",
            "소웨": "소프트웨어학부",
            "소프트웨어": "소프트웨어학부",
            "정통": "정보통신공학과",
            "정보통신": "정보통신공학과",
        }

        mentions: list[tuple[int, str]] = []
        for alias, canonical in aliases.items():
            for match in re.finditer(re.escape(alias), normalized):
                mentions.append((match.start(), canonical))

        explicit_patterns = [
            r"([가-힣A-Za-z0-9]+(?:학과|학부|전공))\s*(?:학생|이야|입니다|으로|로)?",
            r"(?:학과|전공)(?:는|은|이|가|을|를|:)?\s*([가-힣A-Za-z0-9]+(?:학과|학부|전공))",
        ]
        for pattern in explicit_patterns:
            for match in re.finditer(pattern, normalized):
                mentions.append((match.start(1), match.group(1).strip()))

        if not mentions:
            return ""

        correction_markers = ["아니고", "아니라", "말고", "사실", "실은", "정정", "수정", "바꿔", "변경"]
        last_marker = max([normalized.rfind(marker) for marker in correction_markers] + [-1])
        after_marker = [(pos, value) for pos, value in mentions if pos > last_marker]
        candidates = after_marker or mentions
        return sorted(candidates, key=lambda item: item[0])[-1][1]

    def _extract_cohort_year_from_text(self, text: str) -> int | None:
        normalized = str(text or "")
        matches = list(re.finditer(r"(\d{2,4})\s*학번", normalized))
        if not matches:
            matches = list(re.finditer(r"(?:입학연도|입학 년도|입학년도)(?:는|은|이|가)?\s*(\d{2,4})", normalized))
        if not matches:
            matches = list(
                re.finditer(
                    r"(?:학번|입학연도|입학년도)(?:은|는|이|가|을|를)?\s*(?:아니고|아니라|말고|정정|수정|바꿔|변경|다시)?\s*(\d{2,4})",
                    normalized,
                )
            )
        if not matches:
            matches = list(
                re.finditer(
                    r"(\d{2,4})(?:년)?(?:으로|로)\s*(?:정정|수정|바꿔|변경)",
                    normalized,
                )
            )
        if not matches:
            return None

        raw = matches[-1].group(1)
        year = int(raw)
        if year < 100:
            year += 2000 if year < 50 else 1900
        if 1990 <= year <= 2100:
            return year
        return None

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

    def _extract_credit_progress_from_text(self, text: str) -> dict[str, int]:
        area_aliases = {
            "전공": "전공",
            "전공학점": "전공",
            "교양": "교양",
            "교양학점": "교양",
            "자유": "자유선택",
            "자유선택": "자유선택",
            "총": "총 이수",
            "전체": "총 이수",
        }
        progress: dict[str, int] = {}
        pattern = r"(전공학점|교양학점|전공|교양|자유선택|자유|총|전체)\s*(?:은|는|이|가|까지|으로|로|:)?\s*(\d{1,3})\s*학점?"
        for area, credits in re.findall(pattern, text):
            parsed = int(credits)
            if parsed > 0:
                progress[area_aliases.get(area, area)] = parsed
        correction_pattern = r"(전공학점|교양학점|전공|교양|자유선택|자유|총|전체)\s*(?:학점)?\s*(?:은|는|이|가)?\s*(?:아니고|아니라|말고|정정|수정|바꿔|변경)?\s*(\d{1,3})(?:\s*(?:으로|로))?"
        for area, credits in re.findall(correction_pattern, text):
            parsed = int(credits)
            if parsed > 0:
                progress[area_aliases.get(area, area)] = parsed
        return progress

    def _normalize_session_id(self, session_id: str | None) -> str:
        return str(session_id or "").strip()[:128]


ConversationMemoryStore = LocalConversationMemoryStore


def create_conversation_memory_store(
    provider: str = "local",
    ttl_seconds: int = 86400,
    max_sessions: int = 500,
    store_path: str = "backend/data/local_memory_store.json",
    agent_id: str = "chosuninsight",
    encryption_key: str | None = None,
) -> MemoryProvider:
    if provider == "mem0":
        return LocalMem0MemoryStore(
            store_path=store_path,
            agent_id=agent_id,
            ttl_seconds=ttl_seconds,
            max_sessions=max_sessions,
            encryption_key=encryption_key,
        )
    return LocalConversationMemoryStore(ttl_seconds=ttl_seconds, max_sessions=max_sessions)

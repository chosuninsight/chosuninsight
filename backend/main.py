import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from rank_bm25 import BM25Okapi

from openai import AsyncOpenAI
from dotenv import load_dotenv
from backend.memory import ConversationMemoryStore
from rag_pipeline import normalize_entities

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
CHAT_MEMORY_ENABLED = os.getenv("CHAT_MEMORY_ENABLED", "true").lower() not in {"0", "false", "no"}
CHAT_MEMORY_TTL_SECONDS = int(os.getenv("CHAT_MEMORY_TTL_SECONDS", "86400"))
CHAT_MEMORY_MAX_SESSIONS = int(os.getenv("CHAT_MEMORY_MAX_SESSIONS", "500"))
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
SELF_QUERY_RULES = {
    "category": {
        "scholarship": ["장학", "장학금"],
        "cafeteria": ["식단", "식당", "조식", "중식", "석식"],
        "academic_notice": ["학사공지", "수강", "휴학", "복학", "학사"],
        "extracurricular": ["비교과", "마일리지", "프로그램"],
    },
    "tags": {
        "deadline": ["마감", "신청기간", "언제까지", "d-day", "d-"],
        "graduation": ["졸업", "졸업요건", "졸업학점", "이수학점"],
        "admission": ["수시", "정시", "전형"],
        "software": ["컴퓨터공학과", "소프트웨어학부", "정보통신공학과"],
    },
}
FOCUS_TERM_RULES = {
    "컴퓨터공학과": ["컴퓨터공학과", "컴공", "컴퓨터공학전공"],
    "인공지능학과": ["인공지능학과", "인공지능공학과"],
    "정보통신공학과": ["정보통신공학과", "정보통신공학전공", "정통"],
    "정보보안전공": ["정보보안전공", "정보보안학과"],
    "모빌리티SW전공": ["모빌리티SW전공", "모빌리티SW"],
    "전자공학과": ["전자공학과", "전자공학전공"],
    "소프트웨어학부": ["소프트웨어학부", "소프트웨어", "소웨"],
    "약학과": ["약학과"],
    "간호학과": ["간호학과"],
    "법학과": ["법학과"],
}
STORE_PRIORITY_RULES = {
    "update": [
        "오늘", "최근", "최신", "공지", "신청", "마감", "언제까지",
        "식단", "장학", "비교과", "공고", "이번주", "이번 주",
    ],
    "origin": [
        "어디", "위치", "소개", "방법", "이용", "증명서", "사이트",
        "포털", "시스템", "도서관", "캠퍼스", "연락처",
    ],
}
ACADEMIC_POLICY_PATH = Path(__file__).resolve().parent / "data" / "academic_policies.json"
ACADEMIC_REFERENCE_PATH = Path(__file__).resolve().parent / "data" / "academic_reference_answers.json"
FACULTY_PROFILE_PATH = Path(__file__).resolve().parent / "data" / "faculty_profiles.json"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://foxibu.is-a.dev:9000"
    ).split(",")
    if origin.strip()
]

client = AsyncOpenAI(api_key=OPENAI_API_KEY)
conversation_memory = ConversationMemoryStore(
    ttl_seconds=CHAT_MEMORY_TTL_SECONDS,
    max_sessions=CHAT_MEMORY_MAX_SESSIONS,
)


def load_academic_policies() -> list[dict[str, Any]]:
    try:
        return json.loads(ACADEMIC_POLICY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


ACADEMIC_POLICIES = load_academic_policies()


def load_academic_references() -> dict[str, Any]:
    try:
        data = json.loads(ACADEMIC_REFERENCE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


ACADEMIC_REFERENCES = load_academic_references()


def load_faculty_profiles() -> list[dict[str, Any]]:
    try:
        data = json.loads(FACULTY_PROFILE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    return data if isinstance(data, list) else []


FACULTY_PROFILES = load_faculty_profiles()
CREDIT_PROGRESS_PATTERN = re.compile(
    r"(?P<area>교양|전공|주전공|복수전공|복수|총|전체)?\s*"
    r"(?P<credits>\d{1,3})\s*(?:학점)?\s*"
    r"(?P<verb>들었|들엇|이수|수강|채웠|채웟|완료|했|햇)?"
)
CREDIT_FOLLOWUP_KEYWORDS = [
    "졸업 가능",
    "가능해",
    "가능할",
    "뭐가 부족",
    "얼마나 부족",
    "몇 학점",
    "남았",
    "남은",
    "부족",
    "채우면",
    "계산",
]

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
class ChatHistoryMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    debug: bool = False
    session_id: str | None = None
    history: list[ChatHistoryMessage] = Field(default_factory=list)

class ChatResponse(BaseModel):
    success: bool
    answer: str
    sources: list
    suggestions: list[str] = Field(default_factory=list)
    debug: dict[str, Any] | None = None

@dataclass(frozen=True)
class IndexedDocument:
    key: str
    content: str
    source: str
    store: str
    metadata: dict


@dataclass(frozen=True)
class SearchPlan:
    query_variants: list[str]
    filters: dict
    store_priority: list[str]
    focus_terms: list[str]
    debug_reasons: list[str]


@dataclass(frozen=True)
class SearchHit:
    content: str
    source: str
    store: str
    metadata: dict


@dataclass(frozen=True)
class SearchResult:
    hits: list[SearchHit]
    debug: dict[str, Any]


@dataclass(frozen=True)
class ConversationState:
    standalone_question: str
    department: str
    cohort_year: int | None
    domain_intent: str
    topic: str


@dataclass(frozen=True)
class QueryFrame:
    intent: str
    entity: str
    confidence: float
    slots: dict[str, Any]


@dataclass(frozen=True)
class StructuredAnswer:
    answer: str
    sources: list[str]
    answer_mode: str
    suggestion_context: str = ""


def resolve_collection_name(persist_directory: str, preferred_name: str, fallback_names: list[str]) -> str:
    try:
        client = chromadb.PersistentClient(path=persist_directory)
        available = {collection.name: collection.count() for collection in client.list_collections()}
    except Exception:
        return preferred_name

    if available.get(preferred_name, 0) > 0:
        return preferred_name

    for fallback_name in fallback_names:
        if available.get(fallback_name, 0) > 0:
            return fallback_name

    return preferred_name

# =====================================
# 3. ChromaDB 연결 (env 적용)
# =====================================
embeddings = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL
)

ORIGIN_COLLECTION_NAME = resolve_collection_name(
    PERSIST_DIRECTORY,
    COLLECTION_NAME,
    ["langchain"],
)

vectorstore_origin = Chroma(
    collection_name=ORIGIN_COLLECTION_NAME,
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
print("📚 기존 DB 컬렉션:", ORIGIN_COLLECTION_NAME)

def tokenize_korean_text(text: str) -> list[str]:
    return re.findall(r"[0-9A-Za-z가-힣]+", text.lower())

def expand_query_variants(query: str) -> list[str]:
    normalized_query = normalize_entities(query.strip())
    variants = [normalized_query]

    for term, expansions in QUERY_EXPANSION_RULES.items():
        if term in normalized_query:
            for expansion in expansions:
                variants.append(normalized_query.replace(term, expansion))
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


def parse_doc_tags(metadata: dict) -> set[str]:
    return {
        tag.strip()
        for tag in str((metadata or {}).get("tags", "")).split(",")
        if tag.strip()
    }


def infer_legacy_category(doc: IndexedDocument) -> str:
    metadata = doc.metadata or {}
    category = metadata.get("category")
    if category:
        return category

    source = normalize_entities(doc.source.lower())
    title = normalize_entities(str(metadata.get("title", "")).lower())
    content = normalize_entities(doc.content.lower())
    combined_label = f"{source}\n{title}"

    if "장학" in combined_label or "장학" in content:
        return "scholarship"
    if "식단" in combined_label or "식당" in combined_label or "식단" in content:
        return "cafeteria"
    if "비교과" in combined_label or "비교과" in content:
        return "extracurricular"
    if "학사공지" in combined_label or "학사" in combined_label:
        return "academic_notice"
    if "교내일반공지" in combined_label:
        return "general_notice"
    if "외부기관공고" in combined_label:
        return "external_notice"
    return "unknown"


def infer_legacy_tags(doc: IndexedDocument) -> set[str]:
    tags = parse_doc_tags(doc.metadata or {})
    if tags:
        return tags

    title = str((doc.metadata or {}).get("title", ""))
    combined = normalize_entities(f"{doc.source}\n{title}\n{doc.content}".lower())
    inferred = set()
    if "장학" in combined:
        inferred.add("scholarship")
    if "마감" in combined or "신청기간" in combined or "d-day" in combined or "d-" in combined:
        inferred.add("deadline")
    if "졸업" in combined or "졸업학점" in combined or "이수학점" in combined:
        inferred.add("graduation")
    if "수시" in combined or "정시" in combined or "전형" in combined:
        inferred.add("admission")
    if "컴퓨터공학과" in combined or "소프트웨어학부" in combined or "정보통신공학과" in combined:
        inferred.add("software")
    if "비교과" in combined or "마일리지" in combined:
        inferred.add("program")
    if "식단" in combined or "식당" in combined:
        inferred.add("cafeteria")
    return inferred

def load_collection_documents(vectorstore: Chroma, store_name: str) -> list[IndexedDocument]:
    raw = vectorstore._collection.get(include=["documents", "metadatas"])
    documents = raw.get("documents", [])
    metadatas = raw.get("metadatas", [])
    indexed_docs = []

    for content, metadata in zip(documents, metadatas):
        source = ""
        if metadata:
            source = metadata.get("source", "") or metadata.get("title", "")

        indexed_docs.append(
            IndexedDocument(
                key=build_doc_key(content, source, store_name),
                content=content,
                source=source,
                store=store_name,
                metadata=metadata or {},
            )
        )

    return indexed_docs

all_indexed_docs = (
    load_collection_documents(vectorstore_origin, "origin")
    + load_collection_documents(vectorstore_update, "update")
)
indexed_doc_map = {doc.key: doc for doc in all_indexed_docs}
indexed_doc_counts_by_store = Counter(doc.store for doc in all_indexed_docs)
bm25_corpus = [tokenize_korean_text(doc.content) for doc in all_indexed_docs]
bm25 = BM25Okapi(bm25_corpus) if bm25_corpus else None

print("🔎 하이브리드 검색 문서 개수:", len(all_indexed_docs))


def build_academic_calendar_date_index(docs: list[IndexedDocument]) -> dict[str, list[str]]:
    date_events: dict[str, list[str]] = defaultdict(list)
    for doc in docs:
        source = normalize_entities(doc.source)
        if "학사일정" not in source or not source.endswith(".json"):
            continue
        try:
            record = json.loads(doc.content)
        except (TypeError, json.JSONDecodeError):
            continue
        date_text = str(record.get("date", "")).strip()
        events = record.get("events", [])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text) or not isinstance(events, list):
            continue
        for event in events:
            event_text = str(event).strip()
            if event_text and event_text not in date_events[date_text]:
                date_events[date_text].append(event_text)
    return dict(date_events)


ACADEMIC_CALENDAR_DATE_EVENTS = build_academic_calendar_date_index(all_indexed_docs)

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


def dedupe_preserve_order(doc_keys: list[str]) -> list[str]:
    seen = set()
    deduped = []

    for doc_key in doc_keys:
        if doc_key in seen:
            continue
        seen.add(doc_key)
        deduped.append(doc_key)

    return deduped

def run_vector_search(vectorstore: Chroma, store_name: str, query: str, k: int) -> list[str]:
    if k <= 0 or indexed_doc_counts_by_store.get(store_name, 0) <= 0:
        return []

    try:
        results = vectorstore.similarity_search_with_score(query, k=k)
    except Exception as exc:
        print(f"⚠️ {store_name} 벡터 검색 건너뜀: {exc}")
        return []

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


def infer_self_query_filters(query: str) -> dict:
    normalized_query = normalize_entities(query.lower())
    inferred = {}

    for field, mapping in SELF_QUERY_RULES.items():
        matched = []
        for label, keywords in mapping.items():
            if any(keyword.lower() in normalized_query for keyword in keywords):
                matched.append(label)
        if matched:
            inferred[field] = matched

    return inferred


def infer_store_priority(query: str, filters: dict) -> tuple[list[str], list[str]]:
    normalized_query = normalize_entities(query.lower())
    reasons = []
    update_score = 0
    origin_score = 0

    for keyword in STORE_PRIORITY_RULES["update"]:
        if keyword.lower() in normalized_query:
            update_score += 1
    for keyword in STORE_PRIORITY_RULES["origin"]:
        if keyword.lower() in normalized_query:
            origin_score += 1

    if filters.get("category"):
        dynamic_categories = {"scholarship", "cafeteria", "academic_notice", "extracurricular"}
        if any(category in dynamic_categories for category in filters["category"]):
            update_score += 2
            reasons.append("질문이 갱신형 카테고리와 매칭되어 update 우선 검색")

    if filters.get("tags") and "deadline" in filters["tags"]:
        update_score += 2
        reasons.append("마감/신청 성격 질문으로 update 우선 검색")

    if origin_score > update_score:
        reasons.append("정적 안내형 키워드 비중이 높아 origin 우선 검색")
        return ["origin", "update"], reasons
    if update_score > origin_score:
        if not reasons:
            reasons.append("최신/공지성 키워드 비중이 높아 update 우선 검색")
        return ["update", "origin"], reasons

    reasons.append("질문 성격이 혼합형이라 origin/update 균형 검색")
    return ["origin", "update"], reasons


def infer_focus_terms(query: str) -> list[str]:
    normalized_query = normalize_entities(query.lower())
    focus_terms = []

    for canonical, aliases in FOCUS_TERM_RULES.items():
        if any(alias.lower() in normalized_query for alias in aliases):
            focus_terms.append(canonical)

    return focus_terms


def build_search_plan(query: str) -> SearchPlan:
    query_variants = expand_query_variants(query)
    filters = infer_self_query_filters(query)
    store_priority, reasons = infer_store_priority(query, filters)
    focus_terms = infer_focus_terms(query)
    if focus_terms:
        reasons.append(f"질문의 핵심 대상 식별: {', '.join(focus_terms)}")
    return SearchPlan(
        query_variants=query_variants,
        filters=filters,
        store_priority=store_priority,
        focus_terms=focus_terms,
        debug_reasons=reasons,
    )


def document_matches_filters(doc: IndexedDocument, filters: dict) -> bool:
    if not filters:
        return True

    categories = filters.get("category", [])
    doc_category = infer_legacy_category(doc)
    doc_tags = infer_legacy_tags(doc)
    source_text = normalize_entities(doc.source.lower())

    if categories:
        category_match = doc_category in categories

        if not category_match and "scholarship" in categories:
            category_match = "scholarship" in doc_tags or "장학" in source_text
        if not category_match and "cafeteria" in categories:
            category_match = "cafeteria" in doc_tags or "식단" in source_text or "식당" in source_text
        if not category_match and "extracurricular" in categories:
            category_match = "program" in doc_tags or "비교과" in source_text

        if not category_match:
            return False

    tags = filters.get("tags", [])
    if tags and not doc_tags.intersection(tags):
        return False

    return True


def document_matches_focus_terms(doc: IndexedDocument, focus_terms: list[str]) -> bool:
    if not focus_terms:
        return True

    title = str((doc.metadata or {}).get("title", ""))
    normalized_text = normalize_entities(f"{doc.source}\n{title}\n{doc.content}".lower())
    return any(term.lower() in normalized_text for term in focus_terms)


def document_matches_intent(doc: IndexedDocument, plan: SearchPlan) -> bool:
    normalized_text = normalize_entities(f"{doc.source}\n{doc.content}".lower())

    if "graduation" in plan.filters.get("tags", []):
        graduation_markers = [
            "졸업학점",
            "졸업이수",
            "최소학점",
            "minimum_total_credits",
            "major_credits",
            "remaining_credits",
            "admission_cohort",
        ]
        if not any(marker in normalized_text for marker in graduation_markers):
            return False

    return True


def extract_cohort_year(text: str) -> int | None:
    matches = re.findall(r"(\d{4})\s*학년도|(\d{4})\s*학년|(\d{4})\s*년|(\d{4})\s*학번|(?<!\d)(\d{2})\s*학번", text)
    years = []

    for academic_year, school_year, calendar_year, student_year, short_student_year in matches:
        raw = academic_year or school_year or calendar_year or student_year
        if raw:
            years.append(int(raw))
        elif short_student_year:
            years.append(2000 + int(short_student_year))

    return max(years) if years else None


def query_mentions_specific_cohort(query: str) -> bool:
    return extract_cohort_year(query) is not None


def prefer_requested_cohort_hits(query: str, hits: list[SearchHit]) -> list[SearchHit]:
    requested_year = extract_cohort_year(query)
    if requested_year is None:
        return hits

    matching_hits = [
        hit for hit in hits
        if extract_cohort_year(f"{hit.source}\n{hit.content}") == requested_year
    ]
    return matching_hits or hits


def policy_matches_query(policy: dict[str, Any], query: str, focus_terms: list[str]) -> bool:
    normalized_query = normalize_entities(query).lower()
    aliases = [
        str(policy.get("department", "")),
        *[str(alias) for alias in policy.get("aliases", [])],
    ]
    normalized_aliases = [normalize_entities(alias).lower() for alias in aliases if alias]
    normalized_focus_terms = [normalize_entities(term).lower() for term in focus_terms]

    return any(alias in normalized_query for alias in normalized_aliases) or any(
        focus in normalized_aliases for focus in normalized_focus_terms
    )


def find_graduation_policy_for_text(text: str) -> dict[str, Any] | None:
    normalized_text = normalize_entities(text).lower()
    requested_year = extract_cohort_year(text)
    matching_policies = []

    for policy in ACADEMIC_POLICIES:
        if policy.get("policy_type") != "graduation_credits":
            continue

        aliases = [
            str(policy.get("department", "")),
            *[str(alias) for alias in policy.get("aliases", [])],
        ]
        normalized_aliases = []
        for alias in aliases:
            normalized_alias = normalize_entities(alias).lower()
            if not normalized_alias:
                continue
            normalized_aliases.append(normalized_alias)
            for suffix in ["과", "전공", "학과"]:
                if normalized_alias.endswith(suffix):
                    normalized_aliases.append(normalized_alias.removesuffix(suffix))
        if any(alias and alias in normalized_text for alias in normalized_aliases):
            matching_policies.append(policy)

    if not matching_policies:
        return None

    if requested_year is not None:
        cohort_matches = [
            policy for policy in matching_policies
            if int(policy.get("academic_year", 0)) <= requested_year
        ]
        if cohort_matches:
            cohort_matches.sort(
                key=lambda policy: (
                    int(policy.get("academic_year", 0)),
                    int(policy.get("priority", 0)),
                ),
                reverse=True,
            )
            return cohort_matches[0]
        return None

    latest_matches = [policy for policy in matching_policies if policy.get("is_latest")]
    if latest_matches:
        matching_policies = latest_matches

    matching_policies.sort(
        key=lambda policy: (
            int(policy.get("priority", 0)),
            int(policy.get("academic_year", 0)),
        ),
        reverse=True,
    )
    return matching_policies[0]


def find_latest_policy_for_text(text: str) -> dict[str, Any] | None:
    normalized_text = normalize_entities(text).lower()
    matching_policies = []

    for policy in ACADEMIC_POLICIES:
        if not policy.get("is_latest"):
            continue

        aliases = [
            str(policy.get("department", "")),
            *[str(alias) for alias in policy.get("aliases", [])],
        ]
        normalized_aliases = []
        for alias in aliases:
            normalized_alias = normalize_entities(alias).lower()
            if not normalized_alias:
                continue
            normalized_aliases.append(normalized_alias)
            for suffix in ["과", "전공", "학과"]:
                if normalized_alias.endswith(suffix):
                    normalized_aliases.append(normalized_alias.removesuffix(suffix))

        if any(alias and alias in normalized_text for alias in normalized_aliases):
            matching_policies.append(policy)

    if not matching_policies:
        return None

    matching_policies.sort(
        key=lambda policy: (
            int(policy.get("priority", 0)),
            int(policy.get("academic_year", 0)),
        ),
        reverse=True,
    )
    return matching_policies[0]


def build_department_affiliation_answer(
    question: str,
    history: list[ChatHistoryMessage],
    interpretation: dict[str, Any] | None = None,
) -> str | None:
    combined_text = conversation_text(question, history)
    interpreted_department = str((interpretation or {}).get("department", "") or "")
    if interpreted_department:
        combined_text = f"{combined_text}\n{interpreted_department}"

    normalized_question = normalize_entities(question).lower()
    asks_affiliation = any(
        keyword in normalized_question
        for keyword in ["단과대학", "소속", "어느 대학", "무슨 대학", "대학이 어디", "college"]
    )
    if not asks_affiliation:
        return None

    policy = find_latest_policy_for_text(combined_text)
    if not policy:
        return None

    department = policy.get("department", "해당 학과")
    college = policy.get("college", "")
    academic_year = policy.get("academic_year", "")
    if not college:
        return None

    return f"{department}은 {academic_year}학년도 최신 기준으로 {college} 소속입니다."


def build_department_summary_answer(
    question: str,
    history: list[ChatHistoryMessage],
    interpretation: dict[str, Any] | None = None,
) -> str | None:
    normalized_question = normalize_entities(question).strip()
    interpreted_department = str((interpretation or {}).get("department", "") or "").strip()
    if not interpreted_department:
        return None

    policy = find_latest_policy_for_text(interpreted_department)
    if not policy:
        return None

    department_terms = {normalize_entities(str(policy.get("department", "")))}
    department_terms.update(normalize_entities(str(alias)) for alias in policy.get("aliases", []))
    department_terms = {term for term in department_terms if term}
    bare_department_question = normalized_question in department_terms
    if not bare_department_question:
        return None

    department = policy.get("department", "해당 학과")
    college = policy.get("college", "")
    cohort = policy.get("admission_cohort", "최신 기준")
    total_credits = policy.get("minimum_total_credits")
    major_credits = policy.get("single_major_credits")
    if not college:
        return None

    return "\n".join(
        [
            f"{department}은 {college} 소속입니다.",
            f"{cohort} 졸업학점 기준은 총 {total_credits}학점, 단일전공 전공 {major_credits}학점입니다.",
            "입학연도나 원하는 항목을 말해주면 그 기준으로 더 좁혀서 답할게요.",
        ]
    )


def question_mentions_faculty(question: str) -> bool:
    normalized_question = normalize_entities(question).lower()
    return any(keyword in normalized_question for keyword in ["교수", "교수진", "전임교수"])


def question_mentions_computer_science(question: str, interpretation: dict[str, Any] | None = None) -> bool:
    combined = question
    interpreted_department = str((interpretation or {}).get("department", "") or "")
    if interpreted_department:
        combined = f"{combined}\n{interpreted_department}"
    normalized_text = normalize_entities(combined).lower()
    return any(term in normalized_text for term in ["컴퓨터공학과", "컴퓨터공학전공", "컴공", "ai·sw학부"])


def normalize_faculty_lookup_text(text: str) -> str:
    return normalize_entities(text).lower().replace("비전", "비젼").replace(" ", "")


FACULTY_FIELD_STOPWORDS = {
    "교수",
    "부교수",
    "조교수",
    "컴퓨터",
    "공학",
    "연구",
    "분야",
    "전공",
    "시스템",
    "실험실",
    "전화번호",
    "연구실",
    "교수실",
    "안전성",
    "개선",
    "등",
    "ai",
    "hci",
}


def profile_aliases(profile: dict[str, Any]) -> list[str]:
    aliases = [
        str(profile.get("department", "")),
        str(profile.get("display_department", "")),
        *[str(alias) for alias in profile.get("aliases", [])],
    ]
    return [alias for alias in aliases if alias.strip()]


def faculty_field_terms(member: dict[str, Any]) -> list[str]:
    raw_field = normalize_entities(str(member.get("field", ""))).lower().replace("비전", "비젼")
    return [
        term.replace("비전", "비젼")
        for term in tokenize_korean_text(raw_field)
        if len(term) >= 2 and term not in FACULTY_FIELD_STOPWORDS
    ]


def find_faculty_profile_for_state(state: ConversationState, question: str) -> dict[str, Any] | None:
    lookup_targets = [state.department, question]
    normalized_targets = [normalize_faculty_lookup_text(target) for target in lookup_targets if target]

    for profile in FACULTY_PROFILES:
        aliases = [normalize_faculty_lookup_text(alias) for alias in profile_aliases(profile)]
        if any(alias and any(alias in target for target in normalized_targets) for alias in aliases):
            return profile

    normalized_question = normalize_faculty_lookup_text(question)
    for profile in FACULTY_PROFILES:
        for member in profile.get("faculty", []):
            if not isinstance(member, dict):
                continue
            name = normalize_faculty_lookup_text(str(member.get("name", "")))
            if name and name in normalized_question:
                return profile

    field_matched_profiles = []
    for profile in FACULTY_PROFILES:
        faculty = [member for member in profile.get("faculty", []) if isinstance(member, dict)]
        if any(faculty_member_matches_question(member, question) for member in faculty):
            field_matched_profiles.append(profile)

    if len(field_matched_profiles) == 1:
        return field_matched_profiles[0]

    return None


def faculty_member_matches_question(member: dict[str, Any], question: str) -> bool:
    normalized_question = normalize_faculty_lookup_text(question)
    name = normalize_faculty_lookup_text(str(member.get("name", "")))
    if name and name in normalized_question:
        return True

    member_text = normalize_faculty_lookup_text(
        " ".join(str(member.get(field, "")) for field in ["field", "office", "position"])
    )
    if "컴퓨터비젼" in normalized_question and "컴퓨터비젼" in member_text:
        return True

    field_terms = faculty_field_terms(member)
    return any(term and term in normalize_entities(question).lower().replace("비전", "비젼") for term in field_terms)


def build_structured_faculty_answer(
    question: str,
    history: list[ChatHistoryMessage],
    state: ConversationState,
    interpretation: dict[str, Any] | None = None,
) -> StructuredAnswer | None:
    profile = find_faculty_profile_for_state(state, conversation_text(question, history))
    if not profile:
        return None

    faculty = [member for member in profile.get("faculty", []) if isinstance(member, dict)]
    if not faculty:
        return None

    normalized_question = normalize_entities(question).lower()
    asks_full_list = any(keyword in normalized_question for keyword in ["교수진", "전임교수"])
    matched_faculty = [] if asks_full_list else [member for member in faculty if faculty_member_matches_question(member, question)]
    visible_faculty = matched_faculty or faculty
    asks_phone = any(keyword in normalized_question for keyword in ["전화", "전화번호", "연락처"])
    asks_office = any(keyword in normalized_question for keyword in ["연구실", "방", "위치", "어디"])
    compact = not matched_faculty and not asks_phone and not asks_office

    department = str(profile.get("display_department") or profile.get("department") or "해당 학과")
    if matched_faculty:
        lines = [f"{department}에서 질문과 맞는 교수 정보입니다."]
    else:
        lines = [f"{department} 교수진 정보입니다."]

    for member in visible_faculty:
        details = [str(member.get("position", "")).strip()]
        field = str(member.get("field", "")).strip()
        office = str(member.get("office", "")).strip()
        phone = str(member.get("phone", "")).strip()
        if field:
            details.append(f"전공분야 {field}")
        if office and (asks_office or matched_faculty or not compact):
            details.append(f"연구실 {office}")
        if phone and (asks_phone or matched_faculty or not compact):
            details.append(f"전화 {phone}")
        lines.append(f"- {member.get('name')}: {', '.join(detail for detail in details if detail)}")

    return StructuredAnswer(
        answer="\n".join(lines),
        sources=[str(profile.get("source_url") or profile.get("source") or "backend/data/faculty_profiles.json")],
        answer_mode="faculty_profile",
        suggestion_context=department,
    )


def department_aliases_for_lookup(department: str) -> list[str]:
    if not department:
        return []
    aliases = {normalize_entities(department)}
    for canonical, canonical_aliases in FOCUS_TERM_RULES.items():
        if department == canonical or department in canonical_aliases:
            aliases.add(canonical)
            aliases.update(canonical_aliases)
    expanded = set()
    for alias in aliases:
        if not alias:
            continue
        expanded.add(alias)
    return [alias for alias in expanded if alias]


def extract_generic_faculty_entries(content: str) -> list[dict[str, str]]:
    normalized = re.sub(r"\s+", " ", normalize_entities(content)).strip()
    header_positions = [
        pos for marker in ["전임교수", "교수진", "교수소개"]
        if (pos := normalized.find(marker)) >= 0
    ]
    if header_positions:
        normalized = normalized[min(header_positions):]

    segments = re.split(
        r"\s+상세보기\s+|(?=이름\s+[가-힣A-Za-z·\s]{2,20}?\s+사진)|(?=[가-힣A-Za-z·]{2,12}\s+교수이미지\s+[가-힣A-Za-z·]{2,12})",
        normalized,
    )
    entries = []
    seen_names = set()

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        name = ""
        name_match = re.search(r"이름\s+([가-힣A-Za-z·\s]{2,20}?)(?:\s+사진|\s+직위)", segment)
        if name_match:
            name = re.sub(r"\s+", " ", name_match.group(1)).strip()
        else:
            image_match = re.search(r"([가-힣A-Za-z·]{2,12})\s+교수이미지\s+\1", segment)
            if image_match:
                name = image_match.group(1).strip()

        if not name or name in seen_names:
            continue

        position = ""
        position_match = re.search(r"직위\s+(.+?)(?:\s+전화번호|\s+연구실|\s+교수실|\s+전공분야|\s+담당과목|\s+홈페이지|\s+이메일|$)", segment)
        if position_match:
            position = position_match.group(1).strip()
        else:
            position_match = re.search(rf"{re.escape(name)}\s+(.{{0,30}}?교수(?:,\s*학과장)?)", segment)
            if position_match:
                position = position_match.group(1).strip()

        phone = ""
        phone_match = re.search(r"전화번호\s+([0-9\-]+)", segment)
        if phone_match:
            phone = phone_match.group(1).strip()

        office = ""
        office_match = re.search(r"연구실\s+(.+?)(?:\s+교수실|\s+전공분야|\s+담당과목|\s+홈페이지|\s+이메일|$)", segment)
        if office_match:
            office = office_match.group(1).strip()
        elif (office_match := re.search(r"교수실\s+(.+?)(?:\s+전공분야|\s+담당과목|\s+홈페이지|\s+이메일|$)", segment)):
            office = office_match.group(1).strip()

        field = ""
        field_match = re.search(r"전공분야\s+(.+?)(?:\s+홈페이지|\s+이메일|\s+전화번호|\s+연구실|$)", segment)
        if field_match:
            field = field_match.group(1).strip()
        elif (field_match := re.search(r"담당과목\s+(.+?)(?:\s+홈페이지|\s+이메일|\s+전화번호|\s+연구실|$)", segment)):
            field = field_match.group(1).strip()
        elif not position_match and "교수이미지" in segment:
            field_match = re.search(rf"{re.escape(name)}\s+교수이미지\s+{re.escape(name)}\s+.+?교수(?:,\s*학과장)?\s+(.+?)(?:\s+[가-힣A-Za-z·]{{2,12}}\s+교수이미지|$)", segment)
            if field_match:
                field = field_match.group(1).strip()

        entries.append(
            {
                "name": name,
                "position": position,
                "phone": phone,
                "office": office,
                "field": field,
            }
        )
        seen_names.add(name)

    return entries


def find_department_faculty_hits(department: str) -> list[IndexedDocument]:
    aliases = [alias.lower() for alias in department_aliases_for_lookup(department)]
    if not aliases:
        return []

    scored_docs = []
    for doc in all_indexed_docs:
        title = str((doc.metadata or {}).get("title", ""))
        normalized_text = normalize_entities(f"{doc.source}\n{title}\n{doc.content}").lower()
        if not any(alias and alias in normalized_text for alias in aliases):
            continue
        if not any(marker in normalized_text for marker in ["전임교수", "교수진", "교수소개", "직위 교수", "교수이미지"]):
            continue
        score = 0
        if "전임교수" in normalized_text:
            score += 20
        if "교수진" in normalized_text:
            score += 15
        if "교수소개" in normalized_text:
            score += 12
        if any(alias and alias in normalize_entities(doc.source.lower()) for alias in aliases):
            score += 10
        score += normalized_text.count("전화번호")
        score += normalized_text.count("직위")
        scored_docs.append((score, doc))

    scored_docs.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in scored_docs[:3]]


def build_generic_faculty_answer(
    question: str,
    history: list[ChatHistoryMessage],
    state: ConversationState,
    interpretation: dict[str, Any] | None = None,
) -> StructuredAnswer | None:
    department = state.department or str((interpretation or {}).get("department", "") or "").strip()
    if not department:
        return None

    hits = find_department_faculty_hits(department)
    entries = []
    source_names = []
    seen_names = set()

    for doc in hits:
        if doc.source and doc.source not in source_names:
            source_names.append(doc.source)
        for entry in extract_generic_faculty_entries(doc.content):
            name = entry.get("name", "")
            if not name or name in seen_names:
                continue
            entries.append(entry)
            seen_names.add(name)

    if not entries:
        return None

    normalized_question = normalize_entities(question).lower().replace("비전", "비젼")
    matched_entries = []
    for entry in entries:
        entry_text = normalize_entities(" ".join(str(value) for value in entry.values())).lower().replace("비전", "비젼")
        compact_entry_text = re.sub(r"\s+", "", entry_text)
        compact_question = re.sub(r"\s+", "", normalized_question)
        if normalize_entities(entry.get("name", "")).lower() in normalized_question:
            matched_entries.append(entry)
            continue
        if "컴퓨터비젼" in compact_question and "컴퓨터비젼" in compact_entry_text:
            matched_entries.append(entry)
            continue
        field_terms = [
            term.replace("비전", "비젼")
            for term in tokenize_korean_text(entry_text)
            if len(term) >= 2 and term not in {"교수", "부교수", "조교수", "전화번호", "연구실", "컴퓨터", "ai"}
        ]
        if any(term in normalized_question for term in field_terms):
            matched_entries.append(entry)

    visible_entries = matched_entries or entries[:12]
    asks_phone = any(keyword in normalized_question for keyword in ["전화", "전화번호", "연락처"])
    asks_office = any(keyword in normalized_question for keyword in ["연구실", "방", "위치", "어디"])
    show_details = bool(matched_entries) or asks_phone or asks_office

    lines = [f"{department} 교수진 정보입니다."]
    for entry in visible_entries:
        details = [entry.get("position", "")]
        if entry.get("field"):
            details.append(f"분야/담당 {entry['field']}")
        if entry.get("office") and show_details:
            details.append(f"연구실 {entry['office']}")
        if entry.get("phone") and show_details:
            details.append(f"전화 {entry['phone']}")
        lines.append(f"- {entry['name']}: {', '.join(detail for detail in details if detail)}")

    if not matched_entries and len(entries) > len(visible_entries):
        lines.append(f"총 {len(entries)}명 중 일부만 표시했습니다. 교수명이나 연구분야를 말하면 더 좁혀서 답할게요.")

    return StructuredAnswer(
        answer="\n".join(lines),
        sources=source_names or ["origin faculty documents"],
        answer_mode="faculty_generic",
    )


def format_date_range(start_date: str, end_date: str) -> str:
    if start_date == end_date:
        year, month, day = start_date.split("-")
        return f"{year}년 {int(month)}월 {int(day)}일"
    start_year, start_month, start_day = start_date.split("-")
    end_year, end_month, end_day = end_date.split("-")
    if start_year == end_year:
        if start_month == end_month:
            return f"{start_year}년 {int(start_month)}월 {int(start_day)}일부터 {int(end_day)}일까지"
        return f"{start_year}년 {int(start_month)}월 {int(start_day)}일부터 {int(end_month)}월 {int(end_day)}일까지"
    return f"{start_year}년 {int(start_month)}월 {int(start_day)}일부터 {end_year}년 {int(end_month)}월 {int(end_day)}일까지"


def extract_calendar_dates(question: str, default_year: int) -> list[str]:
    normalized_question = normalize_entities(question)
    dates: list[str] = []

    for year, month, day in re.findall(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", normalized_question):
        dates.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")

    without_year_dates = re.findall(r"(?<!년\s)(\d{1,2})\s*월\s*(\d{1,2})\s*일", normalized_question)
    without_year_dates.extend(re.findall(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?!\d)", normalized_question))
    for month, day in without_year_dates:
        dates.append(f"{default_year:04d}-{int(month):02d}-{int(day):02d}")

    deduped_dates = []
    seen = set()
    for date_text in dates:
        if date_text in seen:
            continue
        seen.add(date_text)
        deduped_dates.append(date_text)
    return deduped_dates


def event_contains_date(event: dict[str, Any], date_text: str) -> bool:
    start_date = str(event.get("start_date", ""))
    end_date = str(event.get("end_date", ""))
    return bool(start_date and end_date and start_date <= date_text <= end_date)


def build_calendar_event_alias_catalog() -> dict[str, list[str]]:
    reference = ACADEMIC_REFERENCES.get("academic_calendar_2026", {})
    events = reference.get("events", [])
    aliases_by_name: dict[str, list[str]] = defaultdict(list)
    if not isinstance(events, list):
        return {}
    for event in events:
        if not isinstance(event, dict):
            continue
        name = str(event.get("name", "")).strip()
        if not name:
            continue
        aliases_by_name[name].append(name)
        for alias in event.get("aliases", []):
            alias_text = str(alias).strip()
            if alias_text and alias_text not in aliases_by_name[name]:
                aliases_by_name[name].append(alias_text)
    return dict(aliases_by_name)


ACADEMIC_CALENDAR_EVENT_ALIASES = build_calendar_event_alias_catalog()


def build_academic_calendar_answer(
    question: str,
    history: list[ChatHistoryMessage],
    interpretation: dict[str, Any] | None = None,
) -> str | None:
    combined_text = conversation_text(question, history)
    normalized_question = normalize_entities(question).lower()
    normalized_combined = normalize_entities(combined_text).lower()
    reference = ACADEMIC_REFERENCES.get("academic_calendar_2026", {})
    events = reference.get("events", [])
    if not isinstance(events, list) or not events:
        return None
    default_year = int(reference.get("academic_year", 2026) or 2026)

    requested_term = ""
    if "2학기" in normalized_combined:
        requested_term = "2학기"
    elif "1학기" in normalized_combined:
        requested_term = "1학기"

    requested_dates = extract_calendar_dates(question, default_year)
    if requested_dates:
        exact_date_lines = []
        for requested_date in requested_dates:
            events_for_date = ACADEMIC_CALENDAR_DATE_EVENTS.get(requested_date, [])
            if not events_for_date:
                continue
            asked_date = format_date_range(requested_date, requested_date)
            exact_date_lines.append(f"{asked_date} 학사일정은 {', '.join(events_for_date)}입니다.")

        if exact_date_lines:
            exact_date_lines.append("학사일정은 학교 사정에 따라 변경될 수 있습니다.")
            return "\n".join(exact_date_lines)

        matched_by_date = []
        for event in events:
            if not isinstance(event, dict):
                continue
            if requested_term and event.get("term") != requested_term:
                continue
            for requested_date in requested_dates:
                if event_contains_date(event, requested_date):
                    matched_by_date.append((requested_date, event))

        if matched_by_date:
            lines = []
            for requested_date, event in matched_by_date[:3]:
                asked_date = format_date_range(requested_date, requested_date)
                event_date = format_date_range(str(event.get("start_date", "")), str(event.get("end_date", "")))
                lines.append(
                    f"{asked_date}은 {event.get('term', '')} {event.get('name', '학사일정')} 기간({event_date})에 해당합니다."
                )
            lines.append("학사일정은 학교 사정에 따라 변경될 수 있습니다.")
            return "\n".join(lines)

        asked_dates = ", ".join(format_date_range(date_text, date_text) for date_text in requested_dates)
        return f"{asked_dates}에 등록된 학사일정은 기준 자료에서 확인되지 않습니다.\n학사일정은 학교 사정에 따라 변경될 수 있습니다."

    matched_events = []
    for event in events:
        if not isinstance(event, dict):
            continue
        aliases = [str(alias).lower() for alias in event.get("aliases", [])]
        name = str(event.get("name", "")).lower()
        if not any(alias and alias in normalized_question for alias in aliases) and name not in normalized_question:
            continue
        if requested_term and event.get("term") != requested_term:
            continue
        matched_events.append(event)

    if not matched_events:
        return None

    if not requested_term and len(matched_events) > 1:
        if any(term in normalized_question for term in ["기말", "중간", "성적"]):
            matched_events = [event for event in matched_events if event.get("term") == "1학기"] or matched_events

    lines = []
    for event in matched_events[:3]:
        date_text = format_date_range(str(event.get("start_date", "")), str(event.get("end_date", "")))
        lines.append(f"{event.get('term', '')} {event.get('name', '학사일정')} 일정은 {date_text}입니다.")

    lines.append("학사일정은 학교 사정에 따라 변경될 수 있습니다.")
    return "\n".join(lines)


PORTAL_ROUTE_RULES = [
    {
        "terms": ["the조아", "더조아", "thechoa", "the 조아"],
        "topic": "THE조아",
        "subject": "THE조아는",
        "portal": "THE조아",
        "intro": "THE조아는 아래 주소로 들어가면 됩니다.",
        "path": "THE조아 바로가기: https://thechoa.chosun.ac.kr/clientMain/a/t/main.do",
        "after": "로그인 후 상담, 비교과, 진로·취업 등 필요한 학생지원 메뉴를 선택하세요.",
        "direct": True,
    },
    {
        "terms": ["평생지도교수", "지도교수상담", "교수상담"],
        "topic": "평생지도교수상담",
        "subject": "평생지도교수상담은",
        "portal": "THE조아",
        "path": "THE조아 로그인 > 학생상담 > 지도교수상담",
        "after": "신청 후 상담 일정이나 처리 상태는 THE조아의 나의 상담내역에서 확인하세요.",
        "direct": True,
    },
    {
        "terms": ["학생상담", "상담", "심리상담", "진로상담"],
        "topic": "학생상담",
        "subject": "학생상담은",
        "portal": "THE조아",
        "path": "THE조아 로그인 > 학생상담",
        "after": "세부 상담 종류를 선택한 뒤 신청하거나 상담내역에서 진행 상태를 확인하세요.",
        "direct": False,
    },
    {
        "terms": ["비교과", "비교과프로그램", "마일리지", "프로그램"],
        "topic": "비교과 프로그램",
        "subject": "비교과 프로그램은",
        "portal": "THE조아",
        "path": "THE조아 로그인 > 비교과 프로그램",
        "after": "모집 중인 프로그램을 선택해 신청기간과 참여 조건을 확인하세요.",
        "direct": False,
    },
    {
        "terms": ["수강신청"],
        "topic": "수강신청",
        "subject": "수강신청은",
        "portal": "수강신청 시스템",
        "path": "수강신청 시스템: http://s.chosun.ac.kr",
        "after": "학번과 비밀번호로 로그인한 뒤 수강신청 메뉴에서 신청하세요. 일정은 학사일정 또는 학사공지를 함께 확인하세요.",
        "source": "http://s.chosun.ac.kr",
        "direct": True,
    },
]

ENTITY_CATALOG: dict[str, dict[str, Any]] = {
    "THE조아": {
        "aliases": ["the조아", "더조아", "thechoa", "the 조아"],
        "domain": "student_support_portal",
        "official_route": "THE조아 바로가기: https://thechoa.chosun.ac.kr/clientMain/a/t/main.do",
        "fallback": "THE조아 또는 조선대학교 학생지원 관련 공식 페이지에서 확인하세요.",
    },
    "평생지도교수상담": {
        "aliases": ["평생지도교수", "평생지도교수상담", "지도교수상담", "교수상담"],
        "domain": "student_support_portal",
        "official_route": "THE조아 로그인 > 학생상담 > 지도교수상담",
        "fallback": "THE조아 학생상담 메뉴 또는 소속 학과 사무실에서 확인하세요.",
    },
    "학생상담": {
        "aliases": ["학생상담", "상담", "심리상담", "진로상담", "상담내역", "교수님 상담"],
        "domain": "student_support_portal",
        "official_route": "THE조아 로그인 > 학생상담",
        "fallback": "THE조아 학생상담 메뉴 또는 원스톱학생상담센터에서 확인하세요.",
    },
    "비교과 프로그램": {
        "aliases": ["비교과", "비교과프로그램", "비교과 프로그램", "마일리지", "프로그램"],
        "domain": "student_support_portal",
        "official_route": "THE조아 로그인 > 비교과 프로그램",
        "fallback": "THE조아 비교과 프로그램 메뉴에서 모집 여부와 신청기간을 확인하세요.",
    },
    "수강신청": {
        "aliases": ["수강신청", "수강 신청", "강의 신청"],
        "domain": "academic_calendar",
        "official_route": "수강신청 시스템: http://s.chosun.ac.kr",
        "fallback": "수강신청 시스템 또는 학사공지에서 확인하세요.",
    },
    "성적열람": {
        "aliases": ["성적열람", "성적 열람", "성적조회", "성적 조회", "성적 확인"],
        "domain": "academic_calendar",
        "fallback": "학사일정, 종합정보시스템, 학사공지에서 확인하세요.",
    },
    "기말고사": {"aliases": ["기말고사", "기말"], "domain": "academic_calendar"},
    "중간고사": {"aliases": ["중간고사", "중간"], "domain": "academic_calendar"},
    "개강": {"aliases": ["개강"], "domain": "academic_calendar"},
    "종강": {"aliases": ["종강"], "domain": "academic_calendar"},
    "학사일정": {"aliases": ["학사일정", "학사정보", "학사 정보"], "domain": "academic_calendar"},
    "교수진": {"aliases": ["교수", "교수진", "전임교수", "교수님"], "domain": "faculty"},
    "졸업요건": {"aliases": ["졸업요건", "졸업학점", "졸업 이수", "이수학점", "전공학점"], "domain": "graduation"},
    "교양교육과정": {
        "aliases": ["교양교육과정", "교양과정", "함께형", "기초교양", "균형교양", "융합교양", "선택교양", "다른 교양"],
        "domain": "general_education",
    },
    "학과소속": {"aliases": ["단과대학", "소속", "어느 대학", "무슨 대학"], "domain": "department_affiliation"},
    "휴학": {
        "aliases": ["휴학", "일반휴학", "특별휴학"],
        "domain": "rag",
        "official_route": "종합정보시스템 > 학적 > 휴학신청",
        "fallback": "정확한 신청기간과 예외 조건은 학사공지 또는 소속 대학 교학팀에서 확인하세요.",
    },
    "복학": {
        "aliases": ["복학"],
        "domain": "rag",
        "official_route": "종합정보시스템 > 학적 > 복학신청",
        "fallback": "정확한 신청기간과 수강신청 연계 조건은 학사공지 또는 소속 대학 교학팀에서 확인하세요.",
    },
    "성적포기": {
        "aliases": ["성적포기", "취득성적포기"],
        "domain": "rag",
        "official_route": "차세대종합정보시스템 > 종합정보 > 수업 > 성적 > 성적포기신청",
        "fallback": "정확한 신청기간과 대상자는 학사공지에서 확인하세요.",
    },
    "장학금": {
        "aliases": ["장학금", "장학", "국가근로장학금", "국가근로"],
        "domain": "rag",
        "fallback": "장학금 신청기간은 교내 장학공지와 한국장학재단 공지를 함께 확인하세요.",
    },
    "학식": {
        "aliases": ["학식", "학생식당", "식단", "밥", "중식", "석식"],
        "domain": "rag",
        "fallback": "당일 식단은 조선대학교 식단 안내 또는 학생식당 공지에서 확인하세요.",
    },
    "수강정정": {
        "aliases": ["수강정정", "수강 정정", "정정기간", "수강변경", "수강 변경"],
        "domain": "rag",
        "fallback": "수강정정 기간과 방법은 학사일정, 수강신청 시스템, 학사공지에서 확인하세요.",
    },
    "수강철회": {
        "aliases": ["수강철회", "수강 철회", "드랍", "drop"],
        "domain": "rag",
        "fallback": "수강철회 기간과 대상 과목은 학사공지 또는 종합정보시스템 수업 메뉴에서 확인하세요.",
    },
    "계절학기": {
        "aliases": ["계절학기", "하계 계절학기", "동계 계절학기"],
        "domain": "rag",
        "fallback": "계절학기 개설과 신청기간은 학사공지와 수강신청 시스템에서 확인하세요.",
    },
    "공결": {
        "aliases": ["공결", "출석인정", "출석 인정", "공결신청", "공결 신청"],
        "domain": "rag",
        "fallback": "공결/출석인정 신청 방법과 인정 사유는 학사공지 또는 소속 학과 사무실에서 확인하세요.",
    },
    "등록금": {
        "aliases": ["등록금", "분납", "등록 기간", "등록기간", "납부"],
        "domain": "rag",
        "fallback": "등록금 납부 기간과 분납 정보는 조선대학교 등록금 공지 또는 종합정보시스템에서 확인하세요.",
    },
    "증명서": {
        "aliases": ["증명서", "재학증명서", "성적증명서", "졸업증명서"],
        "domain": "rag",
        "fallback": "증명서 발급은 조선대학교 증명서 발급 서비스 또는 종합정보시스템에서 확인하세요.",
    },
    "학생증": {
        "aliases": ["학생증", "학생증 재발급", "모바일 학생증"],
        "domain": "rag",
        "fallback": "학생증 발급/재발급은 학생복지팀 또는 관련 공지에서 확인하세요.",
    },
    "도서관": {
        "aliases": ["도서관", "중앙도서관", "열람실"],
        "domain": "rag",
        "fallback": "도서관 위치, 운영시간, 연락처는 조선대학교 중앙도서관 공식 페이지에서 확인하세요.",
    },
    "셔틀": {
        "aliases": ["셔틀", "셔틀버스", "통학버스", "버스"],
        "domain": "rag",
        "fallback": "셔틀버스 운행 정보는 조선대학교 교통/학생복지 관련 공지에서 확인하세요.",
    },
    "와이파이": {
        "aliases": ["와이파이", "wifi", "wi-fi", "무선인터넷"],
        "domain": "rag",
        "fallback": "교내 와이파이 이용 방법은 정보전산원 또는 IT 서비스 안내에서 확인하세요.",
    },
}

for event_name, aliases in ACADEMIC_CALENDAR_EVENT_ALIASES.items():
    ENTITY_CATALOG.setdefault(event_name, {"aliases": [], "domain": "academic_calendar"})
    for alias in aliases:
        if alias not in ENTITY_CATALOG[event_name]["aliases"]:
            ENTITY_CATALOG[event_name]["aliases"].append(alias)

PORTAL_ROUTE_ACTION_TERMS = ["신청", "어디", "경로", "방법", "해야", "하려", "하고", "예약", "접수", "들어가", "바로가기", "접속", "사이트", "시스템"]
CALENDAR_TIME_TERMS = ["언제", "날짜", "기간", "일정", "몇일", "며칠", "몇 월", "몇월"]
HOW_TO_TERMS = ["어떻게", "방법", "절차", "하는 법", "하는법"]
CONTACT_TERMS = ["전화", "전화번호", "연락처", "문의"]
PERSON_LOOKUP_TERMS = ["누구", "연구실", "연구분야", "전공분야", "담당", "교수진"]


def find_entity(text: str) -> str:
    normalized_text = normalize_entities(text).lower()
    matches: list[tuple[int, str]] = []
    for entity, config in ENTITY_CATALOG.items():
        for alias in config.get("aliases", []):
            normalized_alias = normalize_entities(str(alias)).lower()
            if normalized_alias and normalized_alias in normalized_text:
                matches.append((len(normalized_alias), entity))
    if not matches:
        return ""
    matches.sort(reverse=True)
    return matches[0][1]


def infer_query_intent(text: str, entity: str = "") -> str:
    normalized_text = normalize_entities(text).lower()
    if any(term in normalized_text for term in CONTACT_TERMS):
        return "contact_lookup"
    if any(term in normalized_text for term in CALENDAR_TIME_TERMS):
        return "when_is"
    if any(term in normalized_text for term in HOW_TO_TERMS):
        return "how_to_apply"
    if any(term in normalized_text for term in PORTAL_ROUTE_ACTION_TERMS):
        return "where_to_apply"
    if entity == "교수진" and any(term in normalized_text for term in PERSON_LOOKUP_TERMS):
        return "person_lookup"
    if entity in {"졸업요건", "교양교육과정"}:
        return "requirement_lookup"
    if entity and any(term in normalized_text for term in CONTACT_TERMS):
        return "contact_lookup"
    return "general_lookup"


def build_query_frame(question: str, history: list[ChatHistoryMessage], interpretation: dict[str, Any] | None = None) -> QueryFrame:
    combined_text = conversation_text(question, history)
    entity = find_entity(combined_text)
    intent = infer_query_intent(question, entity)
    confidence = 0.85 if entity else 0.45
    if intent != "general_lookup":
        confidence = min(0.95, confidence + 0.1)
    if not entity and str((interpretation or {}).get("topic", "")) == "graduation_credits":
        entity = "졸업요건"
        intent = "requirement_lookup"
        confidence = 0.8
    return QueryFrame(
        intent=intent,
        entity=entity,
        confidence=confidence,
        slots={
            "department": infer_department_from_text(combined_text),
            "cohort_year": extract_cohort_year(combined_text),
        },
    )


DOMAIN_ROUTE_BY_FRAME = {
    ("where_to_apply", "수강신청"): "student_support_portal",
    ("how_to_apply", "수강신청"): "student_support_portal",
    ("where_to_apply", "THE조아"): "student_support_portal",
    ("where_to_apply", "평생지도교수상담"): "student_support_portal",
    ("how_to_apply", "평생지도교수상담"): "student_support_portal",
    ("where_to_apply", "학생상담"): "student_support_portal",
    ("how_to_apply", "학생상담"): "student_support_portal",
    ("where_to_apply", "비교과 프로그램"): "student_support_portal",
    ("how_to_apply", "비교과 프로그램"): "student_support_portal",
    ("when_is", "수강신청"): "academic_calendar",
    ("when_is", "성적열람"): "academic_calendar",
    ("when_is", "기말고사"): "academic_calendar",
    ("when_is", "중간고사"): "academic_calendar",
    ("when_is", "개강"): "academic_calendar",
    ("when_is", "종강"): "academic_calendar",
    ("general_lookup", "학사일정"): "academic_calendar",
    ("contact_lookup", "교수진"): "faculty",
    ("person_lookup", "교수진"): "faculty",
    ("requirement_lookup", "졸업요건"): "graduation",
    ("requirement_lookup", "교양교육과정"): "general_education",
    ("general_lookup", "학과소속"): "department_affiliation",
}


def select_portal_route(question: str, history: list[ChatHistoryMessage]) -> dict[str, Any] | None:
    normalized_text = normalize_entities(conversation_text(question, history)).lower()
    frame = build_query_frame(question, history)
    routed_domain = DOMAIN_ROUTE_BY_FRAME.get((frame.intent, frame.entity))
    if routed_domain != "student_support_portal":
        return None
    for rule in PORTAL_ROUTE_RULES:
        if rule["topic"] == frame.entity or any(term in normalized_text for term in rule["terms"]):
            if rule["topic"] == "수강신청" and any(term in normalized_text for term in CALENDAR_TIME_TERMS):
                continue
            return rule
    entity_config = ENTITY_CATALOG.get(frame.entity, {})
    if entity_config.get("official_route"):
        return {
            "topic": frame.entity,
            "subject": f"{frame.entity}은",
            "portal": "공식 시스템",
            "path": entity_config["official_route"],
            "after": entity_config.get("fallback", "해당 공식 시스템에서 세부 정보를 확인하세요."),
            "source": entity_config.get("source", ""),
            "direct": False,
        }
    return None


def build_student_support_portal_answer(question: str, history: list[ChatHistoryMessage]) -> StructuredAnswer | None:
    route = select_portal_route(question, history)
    if not route:
        return None

    confidence_prefix = "" if route.get("direct") else "정확한 세부 메뉴명은 업무에 따라 다를 수 있지만, "
    intro = route.get("intro") or f"{confidence_prefix}{route.get('subject', route['topic'])} {route['portal']}에서 확인하거나 신청하면 됩니다."
    return StructuredAnswer(
        answer=(
            f"{intro}\n"
            f"경로: {route['path']}\n"
            f"{route['after']}"
        ),
        sources=[route.get("source") or "https://thechoa.chosun.ac.kr/clientMain/a/t/main.do"],
        answer_mode="student_support_portal",
        suggestion_context=str(route["topic"]),
    )


def build_entity_official_fallback_answer(question: str, history: list[ChatHistoryMessage]) -> StructuredAnswer | None:
    frame = build_query_frame(question, history)
    entity_config = ENTITY_CATALOG.get(frame.entity, {})
    fallback = entity_config.get("fallback")
    official_route = entity_config.get("official_route")
    if not frame.entity or not fallback:
        return None
    if frame.intent not in {"where_to_apply", "how_to_apply", "when_is", "general_lookup"}:
        return None

    lines = [f"{entity_with_topic_particle(frame.entity)} 공식 자료 확인이 필요한 항목입니다."]
    if official_route:
        lines.append(f"확인 경로: {official_route}")
    lines.append(str(fallback))
    return StructuredAnswer(
        answer="\n".join(lines),
        sources=[str(entity_config.get("source", ""))] if entity_config.get("source") else [],
        answer_mode="official_fallback",
        suggestion_context=frame.entity,
    )


def entity_with_topic_particle(entity: str) -> str:
    if not entity:
        return "해당 항목은"
    last_char = entity[-1]
    if not ("가" <= last_char <= "힣"):
        return f"{entity}는"
    has_jongseong = (ord(last_char) - ord("가")) % 28 != 0
    return f"{entity}{'은' if has_jongseong else '는'}"


def hit_matches_query_frame(hit: SearchHit, frame: QueryFrame) -> bool:
    if not frame.entity:
        return True
    entity_config = ENTITY_CATALOG.get(frame.entity, {})
    aliases = [frame.entity, *[str(alias) for alias in entity_config.get("aliases", [])]]
    normalized_hit = normalize_entities(f"{hit.source}\n{hit.content}").lower()
    return any(normalize_entities(alias).lower() in normalized_hit for alias in aliases if alias)


def filter_hits_for_query_frame(hits: list[SearchHit], frame: QueryFrame) -> tuple[list[SearchHit], bool]:
    entity_config = ENTITY_CATALOG.get(frame.entity, {})
    if not hits or not frame.entity or entity_config.get("domain") not in {"rag"}:
        return hits, False

    matching_hits = [hit for hit in hits if hit_matches_query_frame(hit, frame)]
    if not matching_hits:
        if entity_config.get("fallback"):
            return [], True
        return hits, False
    return matching_hits, len(matching_hits) < len(hits)


def question_mentions_general_education_curriculum(question: str) -> bool:
    normalized_question = normalize_entities(question).lower()
    general_terms = ["교양교육과정", "교양과정", "함께형", "균형교양", "융합교양", "기초교양", "선택교양", "다른 교양", "상한"]
    return any(term in normalized_question for term in general_terms) and not any(
        excluded in normalized_question
        for excluded in ["졸업 가능", "부족", "남았", "계산"]
    )


def build_general_education_answer(
    question: str,
    history: list[ChatHistoryMessage],
    interpretation: dict[str, Any] | None = None,
) -> str | None:
    combined_text = conversation_text(question, history)
    normalized_combined = normalize_entities(combined_text)
    requested_year = extract_cohort_year(normalized_combined)
    if requested_year not in {2023, None}:
        return None
    if not question_mentions_general_education_curriculum(combined_text):
        return None

    reference = ACADEMIC_REFERENCES.get("general_education_2023", {})
    items = reference.get("items", [])
    if not isinstance(items, list) or not items:
        return None

    normalized_question = normalize_entities(question).lower()
    exclude_together = any(term in normalized_question for term in ["함께형 이외", "함께형교양 이외", "함께형 말고", "다른 교양"])
    asks_only_credit_cap = "상한" in normalized_question

    if asks_only_credit_cap and question_mentions_computer_science(combined_text, interpretation):
        policy = find_graduation_policy_for_text(combined_text)
        if policy and policy.get("general_education_credits") is not None:
            return (
                f"{policy.get('department', '컴퓨터공학과')} {policy.get('admission_cohort', '해당 입학연도')} 기준 "
                f"교양학점은 {policy.get('general_education_credits')}학점입니다. "
                "교양교육과정은 학과별 교과목 영역 및 교양이수 상한학점을 함께 확인해야 합니다."
            )

    visible_items = [
        item for item in items
        if isinstance(item, dict) and not (exclude_together and str(item.get("name", "")).startswith("함께형"))
    ]
    if not visible_items:
        return None

    cohort = reference.get("admission_cohort", "2023학년도 이후 입학생")
    minimum = reference.get("minimum_credits", 30)
    lines = [f"{cohort} 교양교육과정은 최소 {minimum}학점 이상 이수 기준입니다."]
    for item in visible_items:
        lines.append(f"- {item.get('name')}: {item.get('requirement')}")
    lines.append("학과별 편성표와 교양이수 상한학점은 별도로 따라야 합니다.")
    return "\n".join(lines)


def question_mentions_only_general_education_credits(question: str) -> bool:
    normalized_question = normalize_entities(question).lower()
    if "교양" not in normalized_question:
        return False
    if any(term in normalized_question for term in ["전공", "주전공", "복수", "전체", "총", "졸업요건", "졸업학점"]):
        return False
    return any(term in normalized_question for term in ["이수학점", "학점", "졸업"])


def build_graduation_policy_answer(question: str, history: list[ChatHistoryMessage], interpretation: dict[str, Any] | None = None) -> str | None:
    intent = str((interpretation or {}).get("intent", ""))
    normalized_question = normalize_entities(question)
    is_graduation_policy_question = (
        intent in {"graduation_policy_question", "graduation_credit_check"}
        or any(keyword in normalized_question for keyword in ["졸업요건", "졸업학점", "졸업 이수", "이수학점"])
    )
    if not is_graduation_policy_question:
        return None

    combined_text = conversation_text(question, history)
    interpreted_department = str((interpretation or {}).get("department", "") or "")
    if interpreted_department:
        combined_text = f"{combined_text}\n{interpreted_department}"

    policy = find_graduation_policy_for_text(combined_text)
    if not policy:
        return None

    department = policy.get("department", "해당 학과")
    cohort = policy.get("admission_cohort", "최신 기준")
    if question_mentions_only_general_education_credits(question):
        general_credits = policy.get("general_education_credits")
        if general_credits is None:
            return None
        return (
            f"{department} {cohort} 기준 교양학점은 {general_credits}학점입니다. "
            "세부 교양 영역은 입학연도별 교양교육과정과 학과별 편성표를 같이 확인해야 합니다."
        )

    lines = [
        f"{department} {cohort} 졸업요건 중 학점 기준은 다음과 같습니다.",
        f"- 총 이수학점: {policy.get('minimum_total_credits')}학점",
    ]
    if policy.get("special_integration"):
        lines.append(f"- 공학교육인증 이수 기준: {policy.get('special_integration')}")
    else:
        lines.extend(
            [
                f"- 교양학점: {policy.get('general_education_credits')}학점",
                f"- 단일전공 전공학점: {policy.get('single_major_credits')}학점",
                f"- 잔여/자유 이수학점: {policy.get('remaining_credits')}학점",
                f"- 복수·연계전공 주전공 학점: {policy.get('multiple_major_primary_credits')}학점",
            ]
        )
    if policy.get("multiple_major_credits") is not None:
        lines.append(f"- 복수전공 학점: {policy.get('multiple_major_credits')}학점")
    if policy.get("note"):
        lines.append(str(policy["note"]))
    lines.append("세부 졸업요건은 입학연도, 전공트랙, 교과과정에 따라 달라질 수 있어요.")
    return "\n".join(lines)


def normalize_credit_area(area: str) -> str:
    normalized_area = normalize_entities(area.strip())
    lowered_area = normalized_area.lower()
    if lowered_area in {"major", "single_major", "전공학점"}:
        return "전공"
    if lowered_area in {"primary_major", "주전공"}:
        return "주전공"
    if lowered_area in {"general", "general_education", "교양학점"}:
        return "교양"
    if lowered_area in {"total", "overall", "전체", "전체학점", "총학점"}:
        return "총"
    if lowered_area in {"multiple_major", "double_major", "복수", "복수전공학점"}:
        return "복수전공"
    return normalized_area


def extract_credit_progress_entries(text: str) -> list[tuple[str, int]]:
    normalized_text = normalize_entities(text)
    entries = []
    for match in CREDIT_PROGRESS_PATTERN.finditer(normalized_text):
        area = match.group("area") or ""
        credits = int(match.group("credits"))
        verb = match.group("verb") or ""
        if not area and not verb:
            continue
        if not area and "학점" not in normalized_text:
            continue
        entries.append((normalize_credit_area(area), credits))
    return entries


def conversation_text(question: str, history: list[ChatHistoryMessage], max_messages: int = 8) -> str:
    history_text = "\n".join(message.content for message in history[-max_messages:] if message.content.strip())
    return f"{history_text}\n{question}"


def infer_department_from_text(text: str) -> str:
    normalized_text = normalize_entities(text).lower()
    for canonical, aliases in FOCUS_TERM_RULES.items():
        if any(alias.lower() in normalized_text for alias in aliases):
            return canonical
    department_match = re.search(r"([가-힣A-Za-z·]+(?:학과|전공|학부))", normalize_entities(text))
    if department_match:
        return department_match.group(1)
    return ""


def infer_domain_intent(question: str, history: list[ChatHistoryMessage], interpretation: dict[str, Any] | None = None) -> str:
    frame = build_query_frame(question, history, interpretation)
    routed_domain = DOMAIN_ROUTE_BY_FRAME.get((frame.intent, frame.entity))
    if routed_domain:
        return routed_domain

    entity_domain = str(ENTITY_CATALOG.get(frame.entity, {}).get("domain", ""))
    if entity_domain and frame.intent in {"general_lookup", "contact_lookup", "person_lookup", "requirement_lookup", "when_is"}:
        return entity_domain

    current = normalize_entities(question).lower()
    combined = normalize_entities(conversation_text(question, history)).lower()
    interpreted_intent = str((interpretation or {}).get("intent", ""))
    interpreted_topic = str((interpretation or {}).get("topic", ""))

    if any(keyword in current for keyword in ["교수", "교수진", "전임교수"]):
        return "faculty"
    if any(keyword in current for keyword in ["학사일정", "학사정보", "학사 정보", "기말", "중간고사", "시험", "개강", "종강", "수강신청", "성적열람", "성적 열람"]):
        return "academic_calendar"
    if any(keyword in current for keyword in ["교양교육과정", "교양과정", "함께형", "기초교양", "균형교양", "융합교양", "선택교양", "다른 교양"]):
        return "general_education"
    if "교양" in current and "상한" in current:
        return "general_education"
    if interpreted_intent in {"graduation_policy_question", "graduation_credit_check"} or interpreted_topic == "graduation_credits":
        return "graduation"
    if any(keyword in current for keyword in ["졸업요건", "졸업학점", "졸업 이수", "이수학점"]):
        return "graduation"
    if any(keyword in current for keyword in ["단과대학", "소속", "어느 대학", "무슨 대학"]):
        return "department_affiliation"
    if "교양교육과정" in combined and any(keyword in current for keyword in ["말고", "이외", "다른", "더"]):
        return "general_education"
    return "rag"


def build_conversation_state(
    question: str,
    history: list[ChatHistoryMessage],
    interpretation: dict[str, Any] | None = None,
) -> ConversationState:
    standalone_question = str((interpretation or {}).get("standalone_question", "") or "").strip() or build_contextual_search_query(question, history)
    combined_text = conversation_text(question, history)
    interpreted_department = str((interpretation or {}).get("department", "") or "").strip()
    department = interpreted_department or infer_department_from_text(combined_text)
    cohort_year = extract_cohort_year(combined_text)
    domain_intent = infer_domain_intent(question, history, interpretation)
    topic = str((interpretation or {}).get("topic", "") or "")
    return ConversationState(
        standalone_question=standalone_question,
        department=department,
        cohort_year=cohort_year,
        domain_intent=domain_intent,
        topic=topic,
    )


def question_asks_credit_followup(question: str) -> bool:
    normalized_question = normalize_entities(question).lower()
    return any(keyword in normalized_question for keyword in CREDIT_FOLLOWUP_KEYWORDS)


def build_credit_progress_state(question: str, history: list[ChatHistoryMessage]) -> dict[str, int]:
    progress: dict[str, int] = {}
    for message in history[-8:]:
        if message.role != "user":
            continue
        for area, credits in extract_credit_progress_entries(message.content):
            if area:
                progress[area] = credits
    for area, credits in extract_credit_progress_entries(question):
        if area:
            progress[area] = credits
    return progress


def credit_progress_from_interpretation(interpretation: dict[str, Any] | None) -> dict[str, int]:
    if not interpretation:
        return {}

    interpreted_progress = interpretation.get("credit_progress", [])
    if not isinstance(interpreted_progress, list):
        return {}

    progress: dict[str, int] = {}
    for item in interpreted_progress:
        if not isinstance(item, dict):
            continue
        area = normalize_credit_area(str(item.get("area", "")))
        credits = item.get("credits")
        try:
            parsed_credits = int(credits)
        except (TypeError, ValueError):
            continue
        if area and parsed_credits > 0:
            progress[area] = parsed_credits
    return progress


def has_unscoped_credit_progress(question: str) -> bool:
    normalized_question = normalize_entities(question)
    if any(area in normalized_question for area in ["전공", "교양", "총", "전체", "복수", "주전공"]):
        return False
    return re.search(r"\d{1,3}\s*(?:학점)?\s*(들었|들엇|이수|수강|채웠|채웟|완료|했|햇)", normalized_question) is not None


def build_credit_gap_line(label: str, required: Any, completed: int) -> str | None:
    try:
        required_credits = int(required)
    except (TypeError, ValueError):
        return None

    remaining = max(required_credits - completed, 0)
    if remaining == 0:
        return f"- {label}: 기준 {required_credits}학점, 현재 {completed}학점으로 기준을 충족했습니다."
    return f"- {label}: 기준 {required_credits}학점, 현재 {completed}학점으로 {remaining}학점이 더 필요합니다."


def append_credit_gap_for_area(lines: list[str], policy: dict[str, Any], area: str, completed: int, question: str) -> None:
    question_text = normalize_entities(question)

    if area == "교양":
        line = build_credit_gap_line("교양학점", policy.get("general_education_credits"), completed)
        if line:
            lines.append(line)
        return

    if area == "총":
        line = build_credit_gap_line("총 이수학점", policy.get("minimum_total_credits"), completed)
        if line:
            lines.append(line)
        return

    if area == "복수전공" and "주전공" not in question_text:
        line = build_credit_gap_line("복수전공 학점", policy.get("multiple_major_credits"), completed)
        if line:
            lines.append(line)
        return

    single_line = build_credit_gap_line("단일전공 전공학점", policy.get("single_major_credits"), completed)
    if single_line:
        lines.append(single_line)

    multiple_line = build_credit_gap_line("복수·연계전공 주전공 학점", policy.get("multiple_major_primary_credits"), completed)
    if multiple_line:
        lines.append(multiple_line)


def build_graduation_credit_progress_answer(
    question: str,
    history: list[ChatHistoryMessage],
    interpretation: dict[str, Any] | None = None,
) -> str | None:
    current_progress = extract_credit_progress_entries(question)
    progress_state = build_credit_progress_state(question, history)
    interpreted_progress = credit_progress_from_interpretation(interpretation)
    combined_text = conversation_text(question, history)
    normalized_combined_for_progress = normalize_entities(combined_text)
    if "총" in interpreted_progress and not any(marker in normalized_combined_for_progress for marker in ["총", "전체"]):
        interpreted_progress.pop("총", None)
    progress_state.update(interpreted_progress)

    intent = str((interpretation or {}).get("intent", ""))
    is_credit_intent = intent in {"graduation_credit_check", "graduation_credit_progress", "graduation_planning"}
    missing_fields = interpretation.get("missing_fields", []) if interpretation else []

    if has_unscoped_credit_progress(question) and ("credit_area" in missing_fields or is_credit_intent):
        return "50학점이라고 말씀하신 건 확인했어요. 전공학점, 교양학점, 총 이수학점 중 어떤 기준인지 알려주시면 졸업요건에 맞춰 바로 계산해드릴게요."

    if not current_progress and not interpreted_progress and not (progress_state and (question_asks_credit_followup(question) or is_credit_intent)):
        return None

    interpreted_department = str((interpretation or {}).get("department", "") or "")
    if interpreted_department:
        combined_text = f"{combined_text}\n{interpreted_department}"
    normalized_combined = normalize_entities(combined_text).lower()
    if not is_credit_intent and "졸업" not in normalized_combined and not any(term in normalized_combined for term in ["전공", "교양", "이수학점"]):
        return None

    policy = find_graduation_policy_for_text(combined_text)
    if not policy:
        if current_progress or interpreted_progress:
            return "학점 계산을 하려면 학과/전공 정보가 필요합니다. 예를 들어 `컴공 전공 50학점 들었어`처럼 학과를 같이 알려주세요."
        return None

    if has_unscoped_credit_progress(question) and not progress_state:
        return "몇 학점인지 확인했습니다. 다만 전공, 교양, 총 이수학점 중 어떤 영역인지 알려주면 졸업요건 기준으로 계산해드릴게요."

    department = policy.get("department", "해당 학과")
    cohort = policy.get("admission_cohort", "최신 기준")
    lines = [f"{department} {cohort} 기준으로 보면요."]

    for area, completed in progress_state.items():
        append_credit_gap_for_area(lines, policy, area, completed, question)

    note = policy.get("note")
    if note:
        lines.append(str(note))

    if "총" not in progress_state:
        lines.append("총 졸업학점 충족 여부까지 보려면 현재 총 이수학점도 같이 알려주세요.")

    if len(lines) == 1:
        return None
    return "\n".join(lines)


def format_academic_policy_content(policy: dict[str, Any]) -> str:
    lines = [
        "# 최신 졸업이수학점 기준",
        f'- "department": "{policy.get("department", "")}"',
        f'- "admission_cohort": "{policy.get("admission_cohort", "")}"',
        f'- "academic_year": "{policy.get("academic_year", "")}"',
        f'- "minimum_total_credits": "{policy.get("minimum_total_credits", "")}"',
        f'- "general_education_credits": "{policy.get("general_education_credits", "")}"',
        f'- "single_major_credits": "{policy.get("single_major_credits", "")}"',
        f'- "remaining_credits": "{policy.get("remaining_credits", "")}"',
        f'- "multiple_major_primary_credits": "{policy.get("multiple_major_primary_credits", "")}"',
        f'- "multiple_major_credits": "{policy.get("multiple_major_credits", "")}"',
    ]
    if policy.get("note"):
        lines.append(f'- "note": "{policy["note"]}"')
    lines.append('- "usage": "입학연도나 학번이 명시되지 않으면 이 최신 기준을 우선 적용한다."')
    return "\n".join(lines)


def get_latest_graduation_policy_hit(plan: SearchPlan, query: str) -> SearchHit | None:
    if "graduation" not in plan.filters.get("tags", []):
        return None
    if query_mentions_specific_cohort(query):
        return None

    matching_policies = [
        policy for policy in ACADEMIC_POLICIES
        if policy.get("policy_type") == "graduation_credits"
        and policy.get("is_latest")
        and policy_matches_query(policy, query, plan.focus_terms)
    ]
    if not matching_policies:
        return None

    matching_policies.sort(
        key=lambda policy: (
            int(policy.get("priority", 0)),
            int(policy.get("academic_year", 0)),
        ),
        reverse=True,
    )
    policy = matching_policies[0]

    return SearchHit(
        content=format_academic_policy_content(policy),
        source=f'{policy.get("source", "학사 정책 데이터")} ({policy.get("admission_cohort", "")})',
        store="policy",
        metadata={
            "category": "academic_policy",
            "tags": "graduation, software, latest",
            "source_type": policy.get("source_type", "academic_policy"),
            "policy_type": policy.get("policy_type", "graduation_credits"),
            "department": policy.get("department", ""),
            "academic_year": policy.get("academic_year"),
            "is_latest": policy.get("is_latest", False),
            "source_url": policy.get("source_url", ""),
        },
    )


def prefer_latest_cohort_hits(plan: SearchPlan, query: str, hits: list[SearchHit]) -> list[SearchHit]:
    if "graduation" not in plan.filters.get("tags", []):
        return hits
    if query_mentions_specific_cohort(query):
        return hits

    cohort_candidates: list[tuple[int, SearchHit]] = []
    for hit in hits:
        combined = f"{hit.source}\n{hit.content}"
        year = extract_cohort_year(combined)
        if year is None:
            continue
        cohort_candidates.append((year, hit))

    if not cohort_candidates:
        return hits

    latest_year = max(year for year, _ in cohort_candidates)
    latest_hits = [hit for year, hit in cohort_candidates if year == latest_year]

    return latest_hits or hits


def inject_latest_graduation_override(plan: SearchPlan, query: str, hits: list[SearchHit]) -> list[SearchHit]:
    override_hit = get_latest_graduation_policy_hit(plan, query)
    if not override_hit:
        return hits

    return [override_hit]


def score_document_for_plan(doc: IndexedDocument, plan: SearchPlan) -> int:
    score = 0
    category = infer_legacy_category(doc)
    tags = infer_legacy_tags(doc)
    title = str((doc.metadata or {}).get("title", ""))
    normalized_text = normalize_entities(f"{doc.source}\n{title}\n{doc.content}".lower())

    if plan.store_priority and doc.store == plan.store_priority[0]:
        score += 6
    elif len(plan.store_priority) > 1 and doc.store == plan.store_priority[1]:
        score += 2

    if category and category in plan.filters.get("category", []):
        score += 12

    matched_tags = tags.intersection(plan.filters.get("tags", []))
    score += len(matched_tags) * 5

    if plan.focus_terms:
        focus_matches = [term for term in plan.focus_terms if term.lower() in normalized_text]
        if focus_matches:
            score += 30 * len(focus_matches)
            if any(term.lower() in normalize_entities(doc.source.lower()) for term in focus_matches):
                score += 15
        else:
            score -= 25

    if "graduation" in plan.filters.get("tags", []):
        if any(keyword in normalized_text for keyword in ["졸업학점", "졸업이수", "최소학점"]):
            score += 12
        if any(keyword in normalized_text for keyword in ["minimum_total_credits", "major_credits", "remaining_credits"]):
            score += 8

    normalized_source = normalize_entities(doc.source.lower())
    for variant in plan.query_variants:
        normalized_variant = normalize_entities(variant.lower())
        if "장학" in normalized_variant and ("장학" in normalized_source or category == "scholarship"):
            score += 10
        if "식단" in normalized_variant and ("식단" in normalized_source or category == "cafeteria"):
            score += 10
        if "비교과" in normalized_variant and ("비교과" in normalized_source or category == "extracurricular"):
            score += 10
        if any(term in normalized_variant for term in ["공지", "공고"]) and category in {"academic_notice", "general_notice", "external_notice"}:
            score += 4

    return score


def run_focus_search(plan: SearchPlan, limit: int) -> list[str]:
    scored_keys = []

    for doc in all_indexed_docs:
        if not document_matches_focus_terms(doc, plan.focus_terms):
            continue
        if not document_matches_filters(doc, plan.filters):
            continue
        if not document_matches_intent(doc, plan):
            continue

        score = score_document_for_plan(doc, plan)
        normalized_text = normalize_entities(f"{doc.source}\n{doc.content}".lower())

        if any(keyword in normalized_text for keyword in ["졸업학점", "졸업이수", "최소학점"]):
            score += 20
        if any(keyword in normalized_text for keyword in ["minimum_total_credits", "major_credits", "remaining_credits"]):
            score += 20
        if '"department"' in normalized_text and any(term.lower() in normalized_text for term in plan.focus_terms):
            score += 30
        if "admission_cohort" in normalized_text:
            score += 15
        if "졸업이수학점" in doc.source or "학사안내" in doc.source:
            score += 15

        scored_keys.append((score, doc.key))

    scored_keys.sort(key=lambda item: item[0], reverse=True)
    return [doc_key for _, doc_key in scored_keys[:limit]]


def collect_ranked_candidates(plan: SearchPlan) -> tuple[list[str], list[str], list[str]]:
    vector_ranked_keys = []
    bm25_ranked_keys = []
    focus_ranked_keys = []
    store_vectorstores = {
        "origin": vectorstore_origin,
        "update": vectorstore_update,
    }
    store_k_map = {
        plan.store_priority[0]: VECTOR_TOP_K // 2 + VECTOR_TOP_K % 2,
        plan.store_priority[1]: VECTOR_TOP_K // 2,
    }

    for query_variant in plan.query_variants:
        for store_name in plan.store_priority:
            vector_ranked_keys.extend(
                run_vector_search(
                    store_vectorstores[store_name],
                    store_name,
                    query_variant,
                    store_k_map.get(store_name, VECTOR_TOP_K // 2),
                )
            )
        bm25_ranked_keys.extend(run_bm25_search(query_variant, BM25_TOP_K))

    if plan.focus_terms:
        focus_ranked_keys = run_focus_search(plan, max(HYBRID_TOP_K * 3, BM25_TOP_K * 2))

    return vector_ranked_keys, bm25_ranked_keys, focus_ranked_keys


def build_debug_payload(
    plan: SearchPlan,
    query: str,
    fused_keys: list[str],
    hits: list[SearchHit],
    fallback_used: bool,
) -> dict[str, Any]:
    selected_cohort_years = [
        year
        for hit in hits
        if (year := extract_cohort_year(f"{hit.source}\n{hit.content}")) is not None
    ]
    return {
        "query_variants": plan.query_variants,
        "filters": plan.filters,
        "store_priority": plan.store_priority,
        "focus_terms": plan.focus_terms,
        "reasons": plan.debug_reasons,
        "query_has_specific_cohort": query_mentions_specific_cohort(query),
        "selected_cohort_years": selected_cohort_years,
        "fallback_used": fallback_used,
        "selected_sources": [hit.source for hit in hits],
        "selected_stores": [hit.store for hit in hits],
        "category_counts": dict(Counter(infer_legacy_category(IndexedDocument("", hit.content, hit.source, hit.store, hit.metadata)) for hit in hits)),
        "candidate_count": len(fused_keys),
    }


def ranked_hits_from_keys(
    fused_keys: list[str],
    plan: SearchPlan,
    query: str,
    apply_filters: bool,
) -> list[SearchHit]:
    scored_hits = []

    for rank, doc_key in enumerate(fused_keys):
        doc = indexed_doc_map[doc_key]
        if apply_filters and not document_matches_filters(doc, plan.filters):
            continue
        if apply_filters and not document_matches_focus_terms(doc, plan.focus_terms):
            continue
        if apply_filters and not document_matches_intent(doc, plan):
            continue
        score = score_document_for_plan(doc, plan) - rank
        scored_hits.append(
            (
                score,
                SearchHit(
                    content=doc.content,
                    source=doc.source,
                    store=doc.store,
                    metadata=doc.metadata,
                ),
            )
        )

    scored_hits.sort(key=lambda item: item[0], reverse=True)
    top_hits = [hit for _, hit in scored_hits[:HYBRID_TOP_K]]
    top_hits = prefer_requested_cohort_hits(query, top_hits)
    top_hits = prefer_latest_cohort_hits(plan, query, top_hits)
    return inject_latest_graduation_override(plan, query, top_hits)

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
def search_docs(query: str) -> SearchResult:
    if not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="질문이 비어 있습니다."
        )

    plan = build_search_plan(query)
    vector_ranked_keys, bm25_ranked_keys, focus_ranked_keys = collect_ranked_candidates(plan)

    fused_keys = reciprocal_rank_fusion(
        [vector_ranked_keys, bm25_ranked_keys, focus_ranked_keys],
        HYBRID_TOP_K * 3
    )
    if focus_ranked_keys:
        fused_keys = dedupe_preserve_order(focus_ranked_keys + fused_keys)[:HYBRID_TOP_K * 3]

    hits = ranked_hits_from_keys(fused_keys, plan, query, apply_filters=True)
    fallback_used = False

    if not hits:
        fallback_used = True
        hits = ranked_hits_from_keys(fused_keys, plan, query, apply_filters=False)
        if hits:
            return SearchResult(
                hits=hits,
                debug=build_debug_payload(plan, query, fused_keys, hits, fallback_used),
            )
        return SearchResult(
            hits=[],
            debug=build_debug_payload(plan, query, fused_keys, [], fallback_used),
        )

    return SearchResult(
        hits=hits,
        debug=build_debug_payload(plan, query, fused_keys, hits, fallback_used),
    )

# =====================================
# 🔥 5. GPT 응답 함수 추가
# =====================================
def format_chat_history(history: list[ChatHistoryMessage], max_messages: int = 8, max_chars: int = 1600) -> str:
    lines = []
    for message in history[-max_messages:]:
        role = "사용자" if message.role == "user" else "도우미"
        content = message.content.strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")

    formatted = "\n".join(lines)
    if len(formatted) > max_chars:
        return formatted[-max_chars:]
    return formatted


def history_with_memory(session_id: str | None) -> list[ChatHistoryMessage]:
    if not CHAT_MEMORY_ENABLED:
        return []

    memory_context = conversation_memory.build_context(session_id)
    if not memory_context:
        return []

    return [ChatHistoryMessage(role="user", content=memory_context)]


def build_contextual_search_query(question: str, history: list[ChatHistoryMessage]) -> str:
    history_text = format_chat_history(history, max_messages=6, max_chars=900)
    if not history_text:
        return question
    return f"{history_text}\n현재 질문: {question}"


async def interpret_chat_request(question: str, history: list[ChatHistoryMessage]) -> dict[str, Any]:
    history_text = format_chat_history(history, max_messages=8, max_chars=1800)
    system_prompt = """
너는 조선대학교 챗봇의 대화 이해기야. 사용자의 현재 질문과 이전 대화를 보고 JSON만 반환해.

반환 형식:
{
  "intent": "graduation_credit_check | graduation_policy_question | campus_info | notice_lookup | portal_route | general_question",
  "standalone_question": "이전 대명사와 생략된 대상을 복원한 독립 질문",
  "department": "학과/전공명 또는 빈 문자열",
  "topic": "graduation_credits | scholarship | cafeteria | academic_notice | counseling | portal | other",
  "credit_progress": [{"area": "major | primary_major | general | total | multiple_major", "credits": 0}],
  "missing_fields": ["department", "credit_area", "total_credits", "general_credits"],
  "should_answer_with_calculation": true,
  "should_ask_clarifying_question": false
}

규칙:
- 사용자가 말한 이수 학점은 사용자 제공 사실로 추출한다.
- "그거", "그 학과", "졸업 가능해?", "괜찮아?" 같은 말은 이전 대화에서 대상을 복원한다.
- "평생지도교수상담", "지도교수상담", "교수상담 신청"은 교수진 조회가 아니라 portal_route/counseling으로 분류한다.
- 확실하지 않은 값은 만들지 말고 missing_fields에 넣는다.
- JSON 외 텍스트는 쓰지 않는다.
""".strip()
    user_prompt = f"""
[이전 대화]
{history_text or "이전 대화 없음"}

[현재 질문]
{question}
""".strip()

    try:
        response = await client.chat.completions.create(
            model=CHAT_MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except Exception as exc:
        print(f"⚠️ 대화 해석 실패: {exc}")
        return {}


def build_search_query_from_interpretation(question: str, history: list[ChatHistoryMessage], interpretation: dict[str, Any]) -> str:
    standalone_question = str(interpretation.get("standalone_question", "")).strip()
    if standalone_question:
        return standalone_question
    return build_contextual_search_query(question, history)


def faculty_question_has_specific_target(question: str) -> bool:
    reference = ACADEMIC_REFERENCES.get("computer_science_faculty", {})
    faculty = reference.get("faculty", [])
    if not isinstance(faculty, list):
        return False

    normalized_question = normalize_entities(question).lower().replace("비전", "비젼")
    compact_question = re.sub(r"\s+", "", normalized_question)
    for member in faculty:
        if not isinstance(member, dict):
            continue
        name = normalize_entities(str(member.get("name", ""))).lower()
        if name and name in normalized_question:
            return True
        field = normalize_entities(str(member.get("field", ""))).lower().replace("비전", "비젼")
        compact_field = re.sub(r"\s+", "", field)
        if compact_field and compact_field in compact_question:
            return True
        field_terms = [
            term.replace("비전", "비젼")
            for term in tokenize_korean_text(field)
            if len(term) >= 2 and term not in {"컴퓨터", "ai", "hci"}
        ]
        if any(term in normalized_question for term in field_terms):
            return True
    return False


def academic_calendar_question_has_event(question: str) -> bool:
    normalized_question = normalize_entities(question).lower()
    reference = ACADEMIC_REFERENCES.get("academic_calendar_2026", {})
    events = reference.get("events", [])
    if not isinstance(events, list):
        return False
    for event in events:
        if not isinstance(event, dict):
            continue
        aliases = [str(alias).lower() for alias in event.get("aliases", [])]
        name = str(event.get("name", "")).lower()
        if any(alias and alias in normalized_question for alias in aliases) or name in normalized_question:
            return True
    return False


def academic_calendar_question_has_lookup_target(question: str) -> bool:
    reference = ACADEMIC_REFERENCES.get("academic_calendar_2026", {})
    default_year = int(reference.get("academic_year", 2026) or 2026)
    return academic_calendar_question_has_event(question) or bool(extract_calendar_dates(question, default_year))


def build_clarifying_domain_answer(
    question: str,
    history: list[ChatHistoryMessage],
    state: ConversationState,
    interpretation: dict[str, Any] | None = None,
) -> StructuredAnswer | None:
    combined_text = conversation_text(question, history)
    if state.domain_intent == "faculty":
        has_structured_profile = find_faculty_profile_for_state(state, combined_text) is not None
        if not has_structured_profile and not state.department and not question_mentions_computer_science(combined_text, interpretation) and not faculty_question_has_specific_target(question):
            return StructuredAnswer(
                answer="어느 학과 교수진인지 알려주세요. 예를 들어 `컴퓨터공학과 교수진` 또는 `김판구 교수 연구실`처럼 물어보면 바로 찾을 수 있습니다.",
                sources=[],
                answer_mode="clarifying_question",
            )

    if state.domain_intent == "graduation" and not state.department:
        return StructuredAnswer(
            answer="졸업요건이나 이수학점은 학과/전공별로 달라서 학과 정보가 필요합니다. 예를 들어 `2023학번 컴퓨터공학과 졸업요건`처럼 알려주세요.",
            sources=[],
            answer_mode="clarifying_question",
        )

    if state.domain_intent == "general_education" and state.cohort_year is None:
        return StructuredAnswer(
            answer="교양교육과정은 입학연도별로 달라서 학번이나 입학연도가 필요합니다. 예를 들어 `23학번 교양교육과정`처럼 알려주세요.",
            sources=[],
            answer_mode="clarifying_question",
        )

    if state.domain_intent == "academic_calendar" and not academic_calendar_question_has_lookup_target(question):
        return StructuredAnswer(
            answer="어떤 학사일정이 궁금한지 알려주세요. 예를 들어 `기말고사 언제야`, `2학기 수강신청 언제야`, `성적열람 언제야`처럼 물어볼 수 있습니다.",
            sources=[],
            answer_mode="clarifying_question",
        )

    return None


def interpretation_with_state(interpretation: dict[str, Any] | None, state: ConversationState) -> dict[str, Any]:
    enriched = dict(interpretation or {})
    if state.department and not str(enriched.get("department", "") or "").strip():
        enriched["department"] = state.department
    if state.standalone_question and not str(enriched.get("standalone_question", "") or "").strip():
        enriched["standalone_question"] = state.standalone_question
    return enriched


def build_structured_domain_answer(
    question: str,
    history: list[ChatHistoryMessage],
    state: ConversationState,
    interpretation: dict[str, Any] | None = None,
) -> StructuredAnswer | None:
    enriched_interpretation = interpretation_with_state(interpretation, state)

    credit_progress_answer = build_graduation_credit_progress_answer(question, history, enriched_interpretation)
    if credit_progress_answer:
        return StructuredAnswer(
            answer=credit_progress_answer,
            sources=["backend/data/academic_policies.json"],
            answer_mode="graduation_credit_progress",
        )

    clarifying_answer = build_clarifying_domain_answer(question, history, state, enriched_interpretation)
    if clarifying_answer:
        return clarifying_answer

    if state.domain_intent == "department_affiliation":
        department_affiliation_answer = build_department_affiliation_answer(question, history, enriched_interpretation)
        if department_affiliation_answer:
            return StructuredAnswer(
                answer=department_affiliation_answer,
                sources=["backend/data/academic_policies.json"],
                answer_mode="department_affiliation",
            )

    department_summary_answer = build_department_summary_answer(question, history, enriched_interpretation)
    if department_summary_answer:
        return StructuredAnswer(
            answer=department_summary_answer,
            sources=["backend/data/academic_policies.json"],
            answer_mode="department_summary",
        )

    if state.domain_intent == "student_support_portal":
        portal_answer = build_student_support_portal_answer(question, history)
        if portal_answer:
            return portal_answer

    if state.domain_intent == "faculty":
        structured_faculty_answer = build_structured_faculty_answer(question, history, state, enriched_interpretation)
        if structured_faculty_answer:
            return structured_faculty_answer
        generic_faculty_answer = build_generic_faculty_answer(question, history, state, enriched_interpretation)
        if generic_faculty_answer:
            return generic_faculty_answer

    if state.domain_intent == "academic_calendar":
        calendar_answer = build_academic_calendar_answer(question, history, enriched_interpretation)
        if calendar_answer:
            return StructuredAnswer(
                answer=calendar_answer,
                sources=["backend/data/academic_reference_answers.json"],
                answer_mode="academic_calendar_2026",
            )

    if state.domain_intent == "general_education":
        general_education_answer = build_general_education_answer(question, history, enriched_interpretation)
        if general_education_answer:
            return StructuredAnswer(
                answer=general_education_answer,
                sources=["backend/data/academic_reference_answers.json"],
                answer_mode="general_education_2023",
            )

    if state.domain_intent == "graduation":
        graduation_policy_answer = build_graduation_policy_answer(question, history, enriched_interpretation)
        if graduation_policy_answer:
            return StructuredAnswer(
                answer=graduation_policy_answer,
                sources=["backend/data/academic_policies.json"],
                answer_mode="graduation_policy",
            )

    return None


def basis_line_for_answer(answer_mode: str, sources: list[str]) -> str:
    if answer_mode == "clarifying_question":
        return ""
    if answer_mode in {"computer_science_faculty", "faculty_profile"}:
        return "기준: 조선대학교 학과 홈페이지 교수소개 구조화 데이터"
    if answer_mode == "faculty_generic":
        return "기준: 조선대학교 학과 홈페이지 교수소개 문서"
    if answer_mode == "academic_calendar_2026":
        return "기준: 조선대학교 2026년 학사일정"
    if answer_mode == "student_support_portal":
        return "기준: 조선대학교 공식 포털/업무 시스템"
    if answer_mode == "official_fallback":
        return "기준: 조선대학교 공식 확인 경로 안내"
    if answer_mode == "general_education_2023":
        return "기준: 2026학년도 1학기 수강가이드 교양과정 이수 안내"
    if answer_mode in {"graduation_policy", "graduation_credit_progress", "department_affiliation", "department_summary"}:
        return "기준: 조선대학교 학사안내 졸업이수최소학점표"
    if answer_mode == "rag" and sources:
        visible_sources = []
        for source in sources:
            if source and source not in visible_sources:
                visible_sources.append(str(source))
            if len(visible_sources) >= 2:
                break
        if visible_sources:
            return f"참고: {', '.join(visible_sources)}"
    return ""


def append_basis_line(answer: str, answer_mode: str, sources: list[str]) -> str:
    basis_line = basis_line_for_answer(answer_mode, sources)
    if not basis_line or basis_line in answer:
        return answer
    return f"{answer}\n\n{basis_line}"


def suggestions_for_answer(answer_mode: str, state: ConversationState, suggestion_context: str = "") -> list[str]:
    if answer_mode in {"computer_science_faculty", "faculty_profile"}:
        department = suggestion_context or state.department or "컴퓨터공학과"
        return [f"{department} 교수 연락처", f"{department} 교수 연구실", "교수명으로 더 찾아줘"]
    if answer_mode == "faculty_generic":
        department = state.department or "해당 학과"
        return [f"{department} 교수 연락처", f"{department} 교수 연구실", "교수명으로 더 찾아줘"]
    if answer_mode == "academic_calendar_2026":
        return ["2학기 중간고사 언제야", "성적열람 언제야", "수강신청 언제야"]
    if answer_mode == "student_support_portal":
        if suggestion_context == "수강신청":
            return ["수강신청 언제야", "2학기 수강신청 날짜", "학사일정 알려줘"]
        if suggestion_context == "비교과 프로그램":
            return ["비교과 신청기간 어디서 확인해?", "THE조아 바로가기", "상담 신청 어디서 해?"]
        return ["THE조아 바로가기", "상담내역 어디서 봐?", "비교과 신청은 어디서 해?"]
    if answer_mode == "official_fallback":
        return ["공식 공지 어디서 봐?", "문의 전화번호 알려줘", "신청기간 알려줘"]
    if answer_mode == "general_education_2023":
        return ["교양 이수학점은?", "함께형 말고 다른 교양은?", "컴퓨터공학과 교양 이수학점"]
    if answer_mode in {"graduation_policy", "graduation_credit_progress"}:
        department = state.department or "컴퓨터공학과"
        cohort = f"{str(state.cohort_year)[2:]}학번 " if state.cohort_year else ""
        return [
            f"{cohort}{department} 교양교육과정 알려줘",
            "교양 이수학점은?",
            "전공학점은?",
        ]
    if answer_mode == "clarifying_question":
        return ["2023학번 컴퓨터공학과 졸업요건", "23학번 교양교육과정", "컴퓨터공학과 교수진"]
    if answer_mode == "rag":
        return ["관련 공지 더 찾아줘", "출처 알려줘", "신청기간 알려줘"]
    return []


async def get_gpt_response(
    question: str,
    context: str,
    history: list[ChatHistoryMessage],
    interpretation: dict[str, Any] | None = None,
):
    system_prompt = """
너는 조선대학교 정보 도우미야.

목표:
- 학생이 실제로 행동할 수 있도록 확인된 조선대학교 정보만 간결하게 안내해.

답변 우선순위:
1. 구조화된 내부 데이터(학사일정, 졸업요건, 교수진, 교양교육과정, 자주 쓰는 포털 경로)
2. 제공된 RAG 참고 정보
3. 공식 웹 검색 결과가 참고 정보로 제공된 경우 그 결과
4. 확인 불가 안내

검색/확인 원칙:
- 내부 데이터나 RAG 근거가 질문에 정확히 맞으면 그 근거로 답해.
- RAG 결과가 없거나 질문 의도와 어긋나면 억지로 답하지 마.
- 신청 위치, 포털 경로, 최신 공지, 장학금, 비교과, 상담, 식단, 오늘/내일/이번 주/최근/현재/최신 정보는 최신 확인이 필요한 질문으로 취급해.
- 공식 웹 검색 결과가 참고 정보에 포함된 경우 조선대학교 공식 사이트, THE조아, 학과/부서 공식 페이지, 교내 공지를 우선해.
- 블로그, 카페, 커뮤니티, 개인 글은 공식 근거가 없을 때만 참고하고 확정적으로 말하지 마.
- 정확한 세부 메뉴를 확정할 수 없더라도, 학생이 다음에 확인할 공식 포털/부서/공지 위치는 안내해.

[답변 원칙]
- 이전 대화는 "그거", "방금", "그 학과" 같은 후속 질문의 대상을 파악할 때만 사용해.
- 실제 답변의 사실, 숫자, 날짜, 학점은 반드시 참고 정보에 있는 내용만 사용해.
- 단, 사용자가 직접 말한 이수 학점, 학과, 상황은 계산 입력값으로 사용할 수 있어.
- 정보가 부족하면 확인된 자료에서는 찾지 못했다고 말하고, 사용자가 다음에 확인할 곳을 안내해.
- 질문의 학과, 전공, 대상과 정확히 일치하는 정보만 사용해. 다른 학과 정보는 절대 섞지 마.
- 숫자, 학점, 날짜, 학년도는 참고 정보에 명시된 값만 사용해. 추정하거나 일반화하지 마.
- 참고 정보가 질문 대상과 정확히 맞지 않으면 "확인된 자료에서는 찾지 못했습니다."라고 답해.
- 질문 의도를 키워드 하나로 오판하지 마. 예를 들어 "평생지도교수상담"은 교수진 검색이 아니라 상담 신청/포털 경로 질문이고, "교수 연구실"이나 "교수 연락처"처럼 교수 개인 정보가 목적일 때만 교수진 검색으로 본다.
- 한국어로 자연스럽고 간결하게 답해.
- 먼저 결론을 말하고, 필요한 경로나 조건을 짧게 안내해.

[졸업/학점 관련 원칙]
- 입학연도나 학번이 명시되지 않으면 최신 학년도 기준을 우선해서 답해.
- 다만 참고 정보에 학년도별 기준 차이가 함께 있으면, 최신 기준으로 먼저 답한 뒤 필요하면 이전 기준이 다를 수 있다고 짧게 덧붙여.
- 사용자가 특정 학번이나 입학연도를 말하면 그 기준만 답해.
""".strip()

    history_text = format_chat_history(history)
    history_block = history_text or "이전 대화 없음"
    interpretation_block = json.dumps(interpretation or {}, ensure_ascii=False)

    user_prompt = f"""
[이전 대화]
{history_block}

[질문 해석]
{interpretation_block}

[참고 정보]
{context}

[현재 질문]
{question}
""".strip()

    response = await client.chat.completions.create(
        model=CHAT_MODEL_NAME,  # 🔥 환경변수 적용
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
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


@app.get("/health/rag", status_code=status.HTTP_200_OK)
def rag_health():
    errors = []

    def collection_count(vectorstore: Chroma, label: str) -> int | None:
        try:
            return int(vectorstore._collection.count())
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

# 🔥 챗봇 API (GPT 연결됨)
@app.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK
)
async def chat(req: ChatRequest):
    history = req.history or history_with_memory(req.session_id)
    interpretation = await interpret_chat_request(req.question, history)
    state = build_conversation_state(req.question, history, interpretation)
    structured_answer = build_structured_domain_answer(req.question, history, state, interpretation)
    if structured_answer:
        if CHAT_MEMORY_ENABLED:
            conversation_memory.update(req.session_id, req.question, interpretation, state)
        answer = append_basis_line(
            structured_answer.answer,
            structured_answer.answer_mode,
            structured_answer.sources,
        )
        return {
            "success": True,
            "answer": answer,
            "sources": structured_answer.sources,
            "suggestions": suggestions_for_answer(
                structured_answer.answer_mode,
                state,
                structured_answer.suggestion_context,
            ),
            "debug": {
                "answer_mode": structured_answer.answer_mode,
                "conversation_state": state.__dict__,
                "interpretation": interpretation,
                "memory": conversation_memory.debug_snapshot(req.session_id) if CHAT_MEMORY_ENABLED else {},
            } if req.debug else None,
        }

    search_query = state.standalone_question or build_search_query_from_interpretation(req.question, history, interpretation)
    search_result = search_docs(search_query)
    query_frame = build_query_frame(req.question, history, interpretation)
    filtered_hits, relevance_filtered = filter_hits_for_query_frame(search_result.hits, query_frame)
    if relevance_filtered:
        search_result = SearchResult(
            hits=filtered_hits,
            debug=search_result.debug | {
                "relevance_filtered": True,
                "query_frame": query_frame.__dict__,
            },
        )
    elif req.debug:
        search_result = SearchResult(
            hits=search_result.hits,
            debug=search_result.debug | {
                "relevance_filtered": False,
                "query_frame": query_frame.__dict__,
            },
        )
    if not search_result.hits:
        fallback_answer = build_entity_official_fallback_answer(req.question, history)
        if fallback_answer:
            if CHAT_MEMORY_ENABLED:
                conversation_memory.update(req.session_id, req.question, interpretation, state)
            answer = append_basis_line(
                fallback_answer.answer,
                fallback_answer.answer_mode,
                fallback_answer.sources,
            )
            return {
                "success": True,
                "answer": answer,
                "sources": fallback_answer.sources,
                "suggestions": suggestions_for_answer(
                    fallback_answer.answer_mode,
                    state,
                    fallback_answer.suggestion_context,
                ),
                "debug": (
                    search_result.debug | {
                        "answer_mode": fallback_answer.answer_mode,
                        "conversation_state": state.__dict__,
                        "interpretation": interpretation,
                        "memory": conversation_memory.debug_snapshot(req.session_id) if CHAT_MEMORY_ENABLED else {},
                    }
                ) if req.debug else None,
            }
    context = "\n".join(hit.content for hit in search_result.hits)

    try:
        answer = await get_gpt_response(req.question, context, history, interpretation)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="GPT 응답 생성 실패"
        )

    if CHAT_MEMORY_ENABLED:
        conversation_memory.update(req.session_id, req.question, interpretation, state)

    return {
        "success": True,
        "answer": append_basis_line(answer, "rag", [hit.source for hit in search_result.hits]),
        "sources": [hit.source for hit in search_result.hits],
        "suggestions": suggestions_for_answer("rag", state),
        "debug": (
            search_result.debug | {
                "answer_mode": "rag",
                "conversation_state": state.__dict__,
                "interpretation": interpretation,
                "memory": conversation_memory.debug_snapshot(req.session_id) if CHAT_MEMORY_ENABLED else {},
            }
        ) if req.debug else None,
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

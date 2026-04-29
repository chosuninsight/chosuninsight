import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from rank_bm25 import BM25Okapi

from openai import AsyncOpenAI
from dotenv import load_dotenv
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
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://foxibu.is-a.dev:9000"
    ).split(",")
    if origin.strip()
]

client = AsyncOpenAI(api_key=OPENAI_API_KEY)


def load_academic_policies() -> list[dict[str, Any]]:
    try:
        return json.loads(ACADEMIC_POLICY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


ACADEMIC_POLICIES = load_academic_policies()

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
    question: str
    debug: bool = False
    history: list[ChatHistoryMessage] = Field(default_factory=list)

class ChatResponse(BaseModel):
    success: bool
    answer: str
    sources: list
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
    matches = re.findall(r"(\d{4})\s*학년도|(\d{4})\s*년", text)
    years = []

    for academic_year, year in matches:
        raw = academic_year or year
        if raw:
            years.append(int(raw))

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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="검색 결과가 없습니다."
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


def build_contextual_search_query(question: str, history: list[ChatHistoryMessage]) -> str:
    history_text = format_chat_history(history, max_messages=6, max_chars=900)
    if not history_text:
        return question
    return f"{history_text}\n현재 질문: {question}"


async def get_gpt_response(question: str, context: str, history: list[ChatHistoryMessage]):
    system_prompt = """
너는 조선대학교 정보 도우미야.
반드시 제공된 참고 정보 안에서만 답변해.

[답변 원칙]
- 이전 대화는 "그거", "방금", "그 학과" 같은 후속 질문의 대상을 파악할 때만 사용해.
- 실제 답변의 사실, 숫자, 날짜, 학점은 반드시 참고 정보에 있는 내용만 사용해.
- 질문의 학과, 전공, 대상과 정확히 일치하는 정보만 사용해. 다른 학과 정보는 절대 섞지 마.
- 숫자, 학점, 날짜, 학년도는 참고 정보에 명시된 값만 사용해. 추정하거나 일반화하지 마.
- 참고 정보가 질문 대상과 정확히 맞지 않으면 "해당 정보를 찾을 수 없습니다."라고 답해.
- 한국어로 자연스럽고 간결하게 답해.

[졸업/학점 관련 원칙]
- 입학연도나 학번이 명시되지 않으면 최신 학년도 기준을 우선해서 답해.
- 다만 참고 정보에 학년도별 기준 차이가 함께 있으면, 최신 기준으로 먼저 답한 뒤 필요하면 이전 기준이 다를 수 있다고 짧게 덧붙여.
- 사용자가 특정 학번이나 입학연도를 말하면 그 기준만 답해.
""".strip()

    history_text = format_chat_history(history)
    history_block = history_text or "이전 대화 없음"

    user_prompt = f"""
[이전 대화]
{history_block}

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

# 🔥 챗봇 API (GPT 연결됨)
@app.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK
)
async def chat(req: ChatRequest):
    search_query = build_contextual_search_query(req.question, req.history)
    search_result = search_docs(search_query)
    context = "\n".join(hit.content for hit in search_result.hits)

    try:
        answer = await get_gpt_response(req.question, context, req.history)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="GPT 응답 생성 실패"
        )

    return {
        "success": True,
        "answer": answer,
        "sources": [hit.source for hit in search_result.hits],
        "debug": search_result.debug if req.debug else None,
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

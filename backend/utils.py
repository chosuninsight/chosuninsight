import re
import json
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from backend.config import QUERY_EXPANSION_RULES, KNOWLEDGE_STORE_PATH
from backend.models import IndexedDocument, StructuredAnswer
from rag_pipeline import normalize_entities

OFFICIAL_SOURCE_HOST_SUFFIXES = ("chosun.ac.kr",)

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

def dedupe_preserve_order(doc_keys: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for doc_key in doc_keys:
        if doc_key in seen:
            continue
        seen.add(doc_key)
        deduped.append(doc_key)
    return deduped

def extract_urls_from_value(value: Any) -> list[str]:
    urls = []
    url_pattern = re.compile(r"https?://[^\s)\]]+", re.IGNORECASE)
    def walk(obj: Any):
        if isinstance(obj, str):
            urls.extend(url_pattern.findall(obj))
        elif isinstance(obj, list):
            for item in obj: walk(item)
        elif isinstance(obj, dict):
            for v in obj.values(): walk(v)
    walk(value)
    seen = set()
    deduped = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped

def is_official_source_url(url: str) -> bool:
    try:
        host = urlparse(str(url)).netloc.lower().split("@")[-1].split(":")[0]
    except Exception:
        return False
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in OFFICIAL_SOURCE_HOST_SUFFIXES)

def filter_official_source_urls(urls: list[str]) -> list[str]:
    seen = set()
    filtered = []
    for url in urls:
        clean_url = str(url).strip()
        if not clean_url or clean_url in seen or not is_official_source_url(clean_url):
            continue
        seen.add(clean_url)
        filtered.append(clean_url)
    return filtered

def save_web_discovery(question: str, answer: str, sources: list[str], mode: str):
    try:
        if not KNOWLEDGE_STORE_PATH.exists():
            KNOWLEDGE_STORE_PATH.write_text("[]", encoding="utf-8")
        data = json.loads(KNOWLEDGE_STORE_PATH.read_text(encoding="utf-8"))
        if any(item.get("question") == question for item in data[-100:]):
            return
        if mode == "official_web_search":
            sources = filter_official_source_urls(sources)
            if not sources:
                return
        
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        # 시간 민감성 키워드 체크 (오늘, 내일, 어제, 현재, 지금, 축제 등)
        temporal_keywords = ["오늘", "내일", "어제", "현재", "지금", "축제", "식단", "밥"]
        is_temporal = any(k in question for k in temporal_keywords)
        
        # 기본 유효기간은 30일, 교수/학과는 180일, 시간 민감 질문은 2시간
        if is_temporal:
            delta = timedelta(hours=2)
        elif "교수" in question or "학과" in question:
            delta = timedelta(days=180)
        else:
            delta = timedelta(days=30)
            
        new_entry = {
            "question": question,
            "answer": answer,
            "sources": sources,
            "mode": mode,
            "updated_at": now.isoformat(),
            "expire_at": (now + delta).isoformat()
        }
        data.append(new_entry)
        if len(data) > 1000:
            data = data[-1000:]
        KNOWLEDGE_STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"ERROR: Failed to save web discovery: {e}")

def find_in_web_knowledge(question: str) -> StructuredAnswer | None:
    try:
        if not KNOWLEDGE_STORE_PATH.exists():
            return None
        data = json.loads(KNOWLEDGE_STORE_PATH.read_text(encoding="utf-8"))
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        for item in reversed(data):
            if item.get("question") == question:
                expire_at = datetime.fromisoformat(item.get("expire_at"))
                if now < expire_at:
                    sources = item.get("sources", [])
                    if item.get("mode") == "official_web_search":
                        sources = filter_official_source_urls(sources)
                        if not sources:
                            continue
                    return StructuredAnswer(
                        answer=item.get("answer", ""),
                        sources=sources,
                        answer_mode="official_web_search",
                    )
    except Exception as e:
        print(f"ERROR: Failed to lookup web knowledge: {e}")
    return None


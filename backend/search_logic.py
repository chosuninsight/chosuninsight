import json
from collections import Counter, defaultdict
from backend.config import *
from backend.models import IndexedDocument, SearchHit, SearchResult, SearchPlan, QueryFrame
from backend.utils import *
import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from rank_bm25 import BM25Okapi
from rag_pipeline import normalize_entities

# Global State for Search
embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

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

ORIGIN_COLLECTION_NAME = resolve_collection_name(PERSIST_DIRECTORY, COLLECTION_NAME, ["langchain"])
vectorstore_origin = Chroma(collection_name=ORIGIN_COLLECTION_NAME, embedding_function=embeddings, persist_directory=PERSIST_DIRECTORY)
vectorstore_update = Chroma(collection_name=UPDATE_COLLECTION_NAME, embedding_function=embeddings, persist_directory=UPDATE_DB_DIRECTORY)

def load_collection_documents(vectorstore: Chroma, store_name: str) -> list[IndexedDocument]:
    raw = vectorstore._collection.get(include=["documents", "metadatas"])
    documents = raw.get("documents", [])
    metadatas = raw.get("metadatas", [])
    indexed_docs = []
    for content, metadata in zip(documents, metadatas):
        source = ""
        if metadata:
            source = metadata.get("source", "") or metadata.get("title", "")
        indexed_docs.append(IndexedDocument(key=build_doc_key(content, source, store_name), content=content, source=source, store=store_name, metadata=metadata or {}))
    return indexed_docs

all_indexed_docs = load_collection_documents(vectorstore_origin, "origin") + load_collection_documents(vectorstore_update, "update")
indexed_doc_map = {doc.key: doc for doc in all_indexed_docs}
indexed_doc_counts_by_store = Counter(doc.store for doc in all_indexed_docs)
bm25_corpus = [tokenize_korean_text(doc.content) for doc in all_indexed_docs]
bm25 = BM25Okapi(bm25_corpus) if bm25_corpus else None

def reciprocal_rank_fusion(rank_lists: list[list[str]], limit: int) -> list[str]:
    fused_scores = defaultdict(float)
    for rank_list in rank_lists:
        for rank, doc_key in enumerate(rank_list, start=1):
            fused_scores[doc_key] += 1.0 / (RRF_K + rank)
    return [doc_key for doc_key, _ in sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)[:limit]]

def run_vector_search(vectorstore: Chroma, store_name: str, query: str, k: int) -> list[str]:
    if k <= 0 or indexed_doc_counts_by_store.get(store_name, 0) <= 0:
        return []
    try:
        results = vectorstore.similarity_search_with_score(query, k=k)
    except Exception as exc:
        print(f"Warning: {store_name} 벡터 검색 건너뜀: {exc}")
        return []
    ranked_keys = []
    for doc, _score in results:
        key = build_doc_key(doc.page_content, doc.metadata.get("source", ""), store_name)
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
    return SearchPlan(query_variants=query_variants, filters=filters, store_priority=store_priority, focus_terms=focus_terms, debug_reasons=reasons)

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
        graduation_markers = ["졸업학점", "졸업이수", "최소학점", "minimum_total_credits", "major_credits", "remaining_credits", "admission_cohort"]
        if not any(marker in normalized_text for marker in graduation_markers):
            return False
    return True

def search_docs(query: str) -> SearchResult:
    plan = build_search_plan(query)
    all_rank_lists = []
    debug_info = {"plan": plan.__dict__}
    
    for variant in plan.query_variants:
        for store in plan.store_priority:
            vs = vectorstore_origin if store == "origin" else vectorstore_update
            all_rank_lists.append(run_vector_search(vs, store, variant, VECTOR_TOP_K))
            
    if bm25:
        for variant in plan.query_variants:
            tokenized_query = tokenize_korean_text(variant)
            scores = bm25.get_scores(tokenized_query)
            top_n_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:BM25_TOP_K]
            all_rank_lists.append([all_indexed_docs[i].key for i in top_n_indices if scores[i] > 0])
            
    fused_keys = reciprocal_rank_fusion(all_rank_lists, limit=HYBRID_TOP_K)
    hits = []
    for key in fused_keys:
        doc = indexed_doc_map.get(key)
        if doc and document_matches_filters(doc, plan.filters) and document_matches_focus_terms(doc, plan.focus_terms) and document_matches_intent(doc, plan):
            hits.append(SearchHit(content=doc.content, source=doc.source, store=doc.store, metadata=doc.metadata))
            
    return SearchResult(hits=hits, debug=debug_info)

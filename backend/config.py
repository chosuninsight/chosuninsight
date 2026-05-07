import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
JINA_API_KEY = os.getenv("JINA_API_KEY")

# Model Settings
CHAT_MODEL_NAME = os.getenv("CHAT_MODEL_NAME", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
WEB_SEARCH_MODEL = os.getenv("WEB_SEARCH_MODEL", CHAT_MODEL_NAME)

# Vector DB Settings
PERSIST_DIRECTORY = os.getenv("PERSIST_DIRECTORY", "/app/chroma_db")
UPDATE_DB_DIRECTORY = os.getenv("UPDATE_DB_DIRECTORY", "/app/chroma_db_update")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "chosun_insight")
UPDATE_COLLECTION_NAME = "chosun_daily_update"

# Search Parameters
VECTOR_TOP_K = int(os.getenv("VECTOR_TOP_K", "6"))
BM25_TOP_K = int(os.getenv("BM25_TOP_K", "6"))
HYBRID_TOP_K = int(os.getenv("HYBRID_TOP_K", "6"))
RRF_K = int(os.getenv("RRF_K", "60"))
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))

# Memory Settings
CHAT_MEMORY_ENABLED = os.getenv("CHAT_MEMORY_ENABLED", "true").lower() not in {"0", "false", "no"}
CHAT_MEMORY_TTL_SECONDS = int(os.getenv("CHAT_MEMORY_TTL_SECONDS", "86400"))
CHAT_MEMORY_MAX_SESSIONS = int(os.getenv("CHAT_MEMORY_MAX_SESSIONS", "500"))

# Paths
ACADEMIC_POLICY_PATH = Path(__file__).resolve().parent / "data" / "academic_policies.json"
ACADEMIC_REFERENCE_PATH = Path(__file__).resolve().parent / "data" / "academic_reference_answers.json"
FACULTY_PROFILE_PATH = Path(__file__).resolve().parent / "data" / "faculty_profiles.json"
KNOWLEDGE_STORE_PATH = Path(__file__).resolve().parent / "data" / "web_knowledge_store.json"
CAFETERIA_DATA_PATH = Path(__file__).resolve().parent.parent / "chosun_rag_data" / "조선대학교_식단.txt"

# Web/CORS
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://foxibu.is-a.dev:9000"
    ).split(",")
    if origin.strip()
]

# Business Rules
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

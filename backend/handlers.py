import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from collections import defaultdict
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from openai import AsyncOpenAI
from backend.config import *
from backend.models import *
from backend.utils import *
from backend.search_logic import all_indexed_docs, search_docs, vectorstore_origin, vectorstore_update
from backend.jina_utils import JinaSearchTool
from rag_pipeline import normalize_entities

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# --- Constants & Rules (Migrated from main.py.bak) ---
CALENDAR_TIME_TERMS = ["언제", "날짜", "기간", "일정", "몇일", "며칠", "몇 월", "몇월"]
HOW_TO_TERMS = ["어떻게", "방법", "절차", "하는 법", "하는법"]
CONTACT_TERMS = ["전화", "전화번호", "연락처", "문의"]
PERSON_LOOKUP_TERMS = ["누구", "연구실", "연구분야", "전공분야", "담당", "교수진"]
PORTAL_ROUTE_ACTION_TERMS = ["신청", "어디", "경로", "방법", "해야", "하려", "하고", "예약", "접수", "들어가", "바로가기", "접속", "사이트", "시스템"]

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

DOMAIN_ROUTE_BY_FRAME = {
    ("where_to_apply", "수강신청"): "student_support_portal",
    ("how_to_apply", "수강신청"): "student_support_portal",
    ("where_to_apply", "THE조아"): "student_support_portal",
    ("how_to_apply", "THE조아"): "student_support_portal",
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
    ("requirement_lookup", "졸업요건"): "graduation_policy",
    ("requirement_lookup", "교양교육과정"): "general_education",
    ("general_lookup", "학과소속"): "department_affiliation",
}

# Data Loaders
def load_academic_policies() -> list[dict[str, Any]]:
    try: return json.loads(ACADEMIC_POLICY_PATH.read_text(encoding="utf-8"))
    except: return []
ACADEMIC_POLICIES = load_academic_policies()

def load_academic_references() -> dict[dict[str, Any]]:
    try:
        data = json.loads(ACADEMIC_REFERENCE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except: return {}
ACADEMIC_REFERENCES = load_academic_references()

def load_faculty_profiles() -> list[dict[str, Any]]:
    try:
        data = json.loads(FACULTY_PROFILE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except: return []
FACULTY_PROFILES = load_faculty_profiles()

def build_calendar_event_alias_catalog() -> dict[str, list[str]]:
    reference = ACADEMIC_REFERENCES.get("academic_calendar_2026", {})
    events = reference.get("events", [])
    aliases_by_name: dict[str, list[str]] = defaultdict(list)
    if not isinstance(events, list): return {}
    for event in events:
        if not isinstance(event, dict): continue
        name = str(event.get("name", "")).strip()
        if not name: continue
        aliases_by_name[name].append(name)
        for alias in event.get("aliases", []):
            alias_text = str(alias).strip()
            if alias_text and alias_text not in aliases_by_name[name]:
                aliases_by_name[name].append(alias_text)
    return dict(aliases_by_name)
ACADEMIC_CALENDAR_EVENT_ALIASES = build_calendar_event_alias_catalog()

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
    "방학": {"aliases": ["방학", "여름방학", "겨울방학", "하계방학", "동계방학"], "domain": "academic_calendar"},
    "학사일정": {"aliases": ["학사일정", "학사정보", "학사 정보"], "domain": "academic_calendar"},
    "교수진": {"aliases": ["교수", "교수진", "전임교수", "교수님"], "domain": "faculty"},
    "졸업요건": {"aliases": ["졸업요건", "졸업학점", "졸업 이수", "이수학점", "전공학점"], "domain": "graduation_policy"},
    "교양교육과정": {
        "aliases": ["교양교육과정", "교양과정", "함께형", "기초교양", "균형교양", "융합교양", "선택교양", "다른 교양"],
        "domain": "general_education",
    },
    "학과소속": {"aliases": ["단과대학", "소속", "어느 대학", "무슨 대학"], "domain": "department_affiliation"},
    "휴학": {"aliases": ["휴학", "일반휴학", "군휴학", "휴학신청"], "domain": "academic_administration"},
    "복학": {"aliases": ["복학", "복학신청", "군복학"], "domain": "academic_administration"},
    "장학": {"aliases": ["장학", "장학금", "백악장학", "국가장학"], "domain": "academic_administration"},
    "학점교류": {"aliases": ["학점교류", "교류수학", "타대학"], "domain": "academic_administration"},
    "학위취득유예": {"aliases": ["졸업유예", "학위취득유예", "졸업유보"], "domain": "academic_administration"},
    "성적포기": {
        "aliases": ["성적포기", "취득성적포기"],
        "domain": "rag",
        "official_route": "차세대종합정보시스템 > 종합정보 > 수업 > 성적 > 성적포기신청",
        "fallback": "정확한 신청기간과 대상자는 학사공지에서 확인하세요.",
    },
    "학식": {
        "aliases": ["학식", "학생식당", "식단", "밥", "중식", "석식", "점심", "저녁", "기숙사 식당", "기숙사 식단"],
        "domain": "cafeteria",
        "fallback": "당일 식단은 조선대학교 식단 안내 또는 학생식당 공지에서 확인하세요.",
    },
    "축제": {
        "aliases": ["축제", "대동제", "학교 축제", "조선대학교 축제", "라인업"],
        "domain": "official_fallback",
        "source": "https://www3.chosun.ac.kr/chosun/217/subview.do",
        "fallback": "축제 일정과 라인업은 매년 바뀌는 최신 공지성 정보라 조선대학교 공식 홈페이지 공지사항, 총학생회 공지, 학과/단과대 공지에서 확인해야 합니다.",
    },
    "오늘 날짜": {
        "aliases": ["오늘 날짜", "오늘날짜", "오늘 며칠", "오늘 몇일", "오늘이 며칠", "현재 날짜", "지금 날짜"],
        "domain": "current_date",
    },
}

for event_name, aliases in ACADEMIC_CALENDAR_EVENT_ALIASES.items():
    ENTITY_CATALOG.setdefault(event_name, {"aliases": [], "domain": "academic_calendar"})
    for alias in aliases:
        if alias not in ENTITY_CATALOG[event_name]["aliases"]:
            ENTITY_CATALOG[event_name]["aliases"].append(alias)

# --- Helper Functions ---
def conversation_text(question: str, history: list[ChatHistoryMessage], max_messages: int = 8) -> str:
    lines = [msg.content for msg in history[-max_messages:] if msg.content.strip()]
    lines.append(question)
    return "\n".join(lines)

def format_chat_history(history: list[ChatHistoryMessage], max_messages: int = 8, max_chars: int = 1600) -> str:
    lines = []
    for message in history[-max_messages:]:
        role = "사용자" if message.role == "user" else "도우미"
        content = message.content.strip()
        if content: lines.append(f"{role}: {content}")
    formatted = "\n".join(lines)
    return formatted[-max_chars:] if len(formatted) > max_chars else formatted

def extract_cohort_year(text: str) -> int | None:
    matches = re.findall(r"(\d{4})\s*학년도|(\d{4})\s*학년|(\d{4})\s*년|(\d{4})\s*학번|(?<!\d)(\d{2})\s*학번", text)
    years = []
    for ay, sy, cy, sty, ssty in matches:
        raw = ay or sy or cy or sty
        if raw: years.append(int(raw))
        elif ssty: years.append(2000 + int(ssty))
    return years[-1] if years else None

def infer_department_from_text(text: str) -> str:
    normalized_text = normalize_entities(text).lower()
    for canonical, aliases in FOCUS_TERM_RULES.items():
        if any(alias.lower() in normalized_text for alias in aliases): return canonical
    match = re.search(r"([가-힣A-Za-z·]+(?:학과|전공|학부))", normalize_entities(text))
    return match.group(1) if match else ""

def entity_with_topic_particle(entity: str) -> str:
    if not entity: return "해당 항목은"
    last_char = entity[-1]
    if not ("가" <= last_char <= "힣"): return f"{entity}는"
    has_jongseong = (ord(last_char) - ord("가")) % 28 != 0
    return f"{entity}{'은' if has_jongseong else '는'}"

def find_entity(text: str) -> str | None:
    normalized_text = normalize_entities(text).lower()
    for entity, config in ENTITY_CATALOG.items():
        aliases = [entity, *config.get("aliases", [])]
        if any(normalize_entities(alias).lower() in normalized_text for alias in aliases if alias):
            return entity
    return None

def infer_query_intent(question: str, entity: str | None) -> str:
    normalized_q = normalize_entities(question).lower()
    if any(term in normalized_q for term in HOW_TO_TERMS + PORTAL_ROUTE_ACTION_TERMS):
        return "how_to_apply"
    if any(term in normalized_q for term in CALENDAR_TIME_TERMS):
        return "when_is"
    if any(term in normalized_q for term in CONTACT_TERMS):
        return "contact_lookup"
    if any(term in normalized_q for term in PERSON_LOOKUP_TERMS):
        return "person_lookup"
    return "general_lookup"

def format_date_range(start_date: str, end_date: str) -> str:
    if not start_date or not end_date: return "일정 정보 없음"
    if start_date == end_date:
        parts = start_date.split("-")
        if len(parts) == 3: return f"{parts[0]}년 {int(parts[1])}월 {int(parts[2])}일"
        return start_date
    sp = start_date.split("-")
    ep = end_date.split("-")
    if len(sp) == 3 and len(ep) == 3:
        if sp[0] == ep[0]:
            if sp[1] == ep[1]: return f"{sp[0]}년 {int(sp[1])}월 {int(sp[2])}일부터 {int(ep[2])}일까지"
            return f"{sp[0]}년 {int(sp[1])}월 {int(sp[2])}일부터 {int(ep[1])}월 {int(ep[2])}일까지"
        return f"{sp[0]}년 {int(sp[1])}월 {int(sp[2])}일부터 {ep[0]}년 {int(ep[1])}월 {int(ep[2])}일까지"
    return f"{start_date} ~ {end_date}"

# --- Faculty Logic ---
FACULTY_FIELD_STOPWORDS = {"교수", "부교수", "조교수", "컴퓨터", "공학", "연구", "분야", "전공", "시스템", "실험실", "전화번호", "연구실", "교수실", "안전성", "개선", "등", "ai", "hci"}

def normalize_faculty_lookup_text(text: str) -> str:
    return normalize_entities(text).lower().replace("비전", "비젼").replace(" ", "")

def profile_aliases(profile: dict[str, Any]) -> list[str]:
    aliases = [str(profile.get("department", "")), str(profile.get("display_department", "")), *[str(alias) for alias in profile.get("aliases", [])]]
    return [alias for alias in aliases if alias.strip()]

def faculty_field_terms(member: dict[str, Any]) -> list[str]:
    raw_field = normalize_entities(str(member.get("field", ""))).lower().replace("비전", "비젼")
    return [term.replace("비전", "비젼") for term in tokenize_korean_text(raw_field) if len(term) >= 2 and term not in FACULTY_FIELD_STOPWORDS]

def faculty_member_matches_question(member: dict[str, Any], question: str) -> bool:
    norm_q = normalize_faculty_lookup_text(question)
    name = normalize_faculty_lookup_text(str(member.get("name", "")))
    if name and name in norm_q: return True
    member_text = normalize_faculty_lookup_text(" ".join(str(member.get(f, "")) for f in ["field", "office", "position"]))
    if "컴퓨터비젼" in norm_q and "컴퓨터비젼" in member_text: return True
    return any(term and term in normalize_entities(question).lower().replace("비전", "비젼") for term in faculty_field_terms(member))

def find_faculty_profile_for_state(state: ConversationState, question: str) -> dict[str, Any] | None:
    targets = [state.department, question]
    norm_targets = [normalize_faculty_lookup_text(t) for t in targets if t]
    for p in FACULTY_PROFILES:
        aliases = [normalize_faculty_lookup_text(a) for a in profile_aliases(p)]
        if any(a and any(a in t for t in norm_targets) for a in aliases): return p
    norm_q = normalize_faculty_lookup_text(question)
    for p in FACULTY_PROFILES:
        for m in p.get("faculty", []):
            if not isinstance(m, dict): continue
            name = normalize_faculty_lookup_text(str(m.get("name", "")))
            if name and name in norm_q: return p
    matched = [p for p in FACULTY_PROFILES if any(faculty_member_matches_question(m, question) for m in p.get("faculty", []) if isinstance(m, dict))]
    return matched[0] if len(matched) == 1 else None

def build_structured_faculty_answer(question: str, history: list[ChatHistoryMessage], state: ConversationState, interpretation: dict[str, Any] | None = None) -> StructuredAnswer | None:
    profile = find_faculty_profile_for_state(state, conversation_text(question, history))
    if not profile or not profile.get("faculty"): return None
    faculty = [m for m in profile["faculty"] if isinstance(m, dict)]
    norm_q = normalize_entities(question).lower()
    full_list = any(k in norm_q for k in ["교수진", "전임교수"])
    matched = [] if full_list else [m for m in faculty if faculty_member_matches_question(m, question)]
    visible = matched or faculty
    phone_q = any(k in norm_q for k in ["전화", "연락처"])
    office_q = any(k in norm_q for k in ["연구실", "위치"])
    compact = not matched and not phone_q and not office_q
    dept = str(profile.get("display_department") or profile.get("department") or "해당 학과")
    
    lines = [f"[{dept}]", ""]
    for m in visible:
        dtl = [str(m.get("position", "")).strip()]
        if m.get("field"): dtl.append(f"분야: {m['field']}")
        if m.get("office") and (office_q or matched or not compact): dtl.append(f"연구실: {m['office']}")
        if m.get("phone") and (phone_q or matched or not compact): dtl.append(f"전화: {m['phone']}")
        lines.append(f"- {m.get('name')} ({', '.join(d for d in dtl if d)})")
    return StructuredAnswer(answer="\n".join(lines), sources=[profile.get("source") or "https://www.chosun.ac.kr"], answer_mode="faculty_profile")

# --- Portal Logic ---
def select_portal_route(question: str, history: list[ChatHistoryMessage]) -> dict[str, Any] | None:
    norm_text = normalize_entities(conversation_text(question, history)).lower()
    frame = build_query_frame(question, history)
    if DOMAIN_ROUTE_BY_FRAME.get((frame.intent, frame.entity)) != "student_support_portal": return None
    for rule in PORTAL_ROUTE_RULES:
        if rule["topic"] == frame.entity or any(t in norm_text for t in rule["terms"]):
            if rule["topic"] == "수강신청" and any(t in norm_text for t in CALENDAR_TIME_TERMS): continue
            return rule
    return None

def build_portal_answer(question: str, history: list[ChatHistoryMessage]) -> StructuredAnswer | None:
    route = select_portal_route(question, history)
    if not route: return None
    conf_prefix = "" if route.get("direct") else "정확한 메뉴명은 다를 수 있지만, "
    intro = route.get("intro") or f"{conf_prefix}{route.get('subject', route['topic'])} {route['portal']}에서 확인/신청 가능합니다."
    path_text = f"경로: {route['path']}"
    after_text = f"{route['after']}"
    return StructuredAnswer(answer=f"{intro}\n{path_text}\n{after_text}", sources=[route.get("source") or "https://thechoa.chosun.ac.kr"], answer_mode="student_support_portal", suggestion_context=str(route["topic"]))

# --- Calendar Logic ---
def build_academic_calendar_date_index(docs: list[IndexedDocument]) -> dict[str, list[str]]:
    index = defaultdict(list)
    # 1. From RAG docs
    for doc in docs:
        if "학사일정" in doc.source or "academic_calendar" in str(doc.metadata.get("tags", "")):
            date_matches = re.findall(r"(\d{4})-(\d{2})-(\d{2})", doc.content)
            for y, m, d in date_matches:
                date_str = f"{y}-{m}-{d}"
                event_name = doc.metadata.get("title") or doc.content[:20].strip()
                if event_name and event_name not in index[date_str]: index[date_str].append(event_name)
    
    # 2. From Structured Reference
    ref = ACADEMIC_REFERENCES.get("academic_calendar_2026", {})
    events = ref.get("events", [])
    for event in events:
        if not isinstance(event, dict): continue
        start = str(event.get("start_date", ""))
        end = str(event.get("end_date", ""))
        name = str(event.get("name", ""))
        if start and end and name:
            try:
                curr = datetime.strptime(start, "%Y-%m-%d")
                stop = datetime.strptime(end, "%Y-%m-%d")
                term = str(event.get("term", ""))
                full_name = f"{term} {name}".strip()
                while curr <= stop:
                    date_str = curr.strftime("%Y-%m-%d")
                    if full_name not in index[date_str]: index[date_str].append(full_name)
                    curr += timedelta(days=1)
            except: continue
                
    return dict(index)
ACADEMIC_CALENDAR_DATE_EVENTS = build_academic_calendar_date_index(all_indexed_docs)

def extract_calendar_dates(question: str, default_year: int) -> list[str]:
    matches = re.findall(r"(\d{1,2})월\s*(\d{1,2})일", question)
    dates = []
    for m, d in matches: dates.append(f"{default_year}-{int(m):02d}-{int(d):02d}")
    return dates

def event_contains_date(event: dict[str, Any], date_text: str) -> bool:
    start = str(event.get("start_date", ""))
    end = str(event.get("end_date", ""))
    return start <= date_text <= end

def build_academic_calendar_answer(question: str, history: list[ChatHistoryMessage], interpretation: dict[str, Any] | None = None) -> StructuredAnswer | None:
    norm_q = normalize_entities(question).lower()
    ref = ACADEMIC_REFERENCES.get("academic_calendar_2026", {})
    events = ref.get("events", [])
    if not events: return None
    def_year = int(ref.get("academic_year", 2026))
    term = "2학기" if "2학기" in norm_q else "1학기" if "1학기" in norm_q else ""
    dates = extract_calendar_dates(question, def_year)
    
    lines = []
    if dates:
        for d in dates:
            evs = ACADEMIC_CALENDAR_DATE_EVENTS.get(d, [])
            if evs:
                date_label = format_date_range(d, d)
                lines.append(f"- **{date_label}** 일정: {', '.join(evs)}")
    
    if not lines:
        matched = []
        for e in events:
            if not isinstance(e, dict): continue
            if term and e.get("term") and e.get("term") != term: continue
            
            name = str(e.get("name", "")).lower()
            aliases = [str(a).lower() for a in e.get("aliases", [])]
            if name in norm_q or any(a and a in norm_q for a in aliases):
                matched.append(e)
                
        if matched:
            for e in matched:
                name_label = f"{e.get('term', '')} {e.get('name', '')}".strip()
                lines.append(f"- **{name_label}**: {format_date_range(str(e.get('start_date', '')), str(e.get('end_date', '')))}")

    if lines:
        lines.append("\n※ 학사일정은 학교 사정에 따라 변경될 수 있으니 정기적으로 확인해 주세요.")
        return StructuredAnswer(answer="\n".join(lines), sources=[ref.get("source") or "https://www.chosun.ac.kr"], answer_mode="academic_calendar_2026")
        
    return None

# --- Graduation Logic ---
CREDIT_PROGRESS_PATTERN = re.compile(r"(전공|교양|총|취득)\s*(\d{1,3})\s*(학점|점)?", re.IGNORECASE)
CREDIT_FOLLOWUP_KEYWORDS = ["부족", "남았", "더 들어", "들어야", "계산", "가능", "충족", "미달"]

def match_cohort(user_cohort: int, cohort_range_text: str) -> bool:
    if not user_cohort: return False
    
    # 1. Start~End range (e.g. 2015학년도~2017학년도)
    if "~" in cohort_range_text:
        range_match = re.findall(r"(\d{4})", cohort_range_text)
        if len(range_match) >= 2:
            start, end = map(int, range_match[:2])
            return start <= user_cohort <= end
    
    # 2. After range (e.g. 2023학년도 이후)
    if "이후" in cohort_range_text:
        after_match = re.search(r"(\d{4})", cohort_range_text)
        if after_match:
            start = int(after_match.group(1))
            return user_cohort >= start
            
    # 3. Exact year or simple containment
    year_match = re.search(r"(\d{4})", cohort_range_text)
    if year_match:
        return int(year_match.group(1)) == user_cohort
        
    return str(user_cohort) in cohort_range_text

def find_graduation_policy_for_text(text: str) -> dict[str, Any] | None:
    dept = infer_department_from_text(text)
    cohort = extract_cohort_year(text)
    
    matched_policies = []
    for p in ACADEMIC_POLICIES:
        if p.get("policy_type") != "graduation_credits": continue
        p_dept = normalize_entities(str(p.get("department",""))).lower()
        if dept and dept.lower() in p_dept:
            if cohort:
                if match_cohort(cohort, str(p.get("admission_cohort", ""))):
                    matched_policies.append(p)
            elif p.get("is_latest"):
                matched_policies.append(p)
                
    if not matched_policies: return None
    
    # Sort by priority (higher first) and academic_year (latest first) to get the most specific/recent policy
    matched_policies.sort(key=lambda x: (x.get("priority", 0), x.get("academic_year", 0)), reverse=True)
    return matched_policies[0]

def extract_credit_progress_entries(text: str) -> list[tuple[str, int]]:
    return [(m[0], int(m[1])) for m in CREDIT_PROGRESS_PATTERN.findall(text)]

def build_credit_progress_state(question: str, history: list[ChatHistoryMessage]) -> dict[str, int]:
    combined = conversation_text(question, history)
    entries = extract_credit_progress_entries(combined)
    state = {}
    for area, val in entries:
        if "전공" in area: state["전공"] = val
        elif "교양" in area: state["교양"] = val
        elif "총" in area or "취득" in area: state["총"] = val
    return state

def credit_progress_from_interpretation(interpretation: dict[str, Any] | None) -> dict[str, int]:
    if not interpretation: return {}
    res = {}
    if "major_credits" in interpretation: res["전공"] = int(interpretation["major_credits"])
    if "general_credits" in interpretation: res["교양"] = int(interpretation["general_credits"])
    if "total_credits" in interpretation: res["총"] = int(interpretation["total_credits"])
    return res

def append_credit_gap_for_area(lines: list[str], policy: dict[str, Any], area: str, completed: int, question: str) -> None:
    req_key = {"전공": "single_major_credits", "교양": "general_education_credits", "총": "minimum_total_credits"}.get(area)
    if not req_key or req_key not in policy: return
    req = int(policy[req_key])
    gap = req - completed
    if gap > 0: lines.append(f"{area}은 {completed}학점 이수하셨네요. 졸업까지 {gap}학점 더 필요합니다. (기준 {req})")
    else: lines.append(f"{area}은 {completed}학점으로 기준({req})을 충족하셨습니다!")

def build_graduation_credit_progress_answer(question: str, history: list[ChatHistoryMessage], interpretation: dict[str, Any] | None = None) -> str | None:
    # Disable structured calculation logic to favor LLM-driven RAG response
    return None

# --- Main Entry Handlers ---
async def interpret_chat_request(question: str, history: list[ChatHistoryMessage]) -> dict[str, Any]:
    history_text = format_chat_history(history, max_messages=8, max_chars=1800)
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    current_date_str = now.strftime("%Y-%m-%d %A")

    system_prompt = f"""너는 조선대학교 챗봇의 대화 이해기야. [현재 시각: {current_date_str}]
사용자의 질문 의도를 분석하여 반드시 지정된 도메인 중 하나로 분류해 JSON으로 반환해.

도메인 결정 규칙 (엄격 준수):
1. 학과/학번 정보가 필요한데 누락된 경우 -> 'clarifying_question' (최우선)
   - 예: "졸업학점 알려줘", "이수체계 뭐야", "교수님 전화번호"
2. 'THE조아', '수강신청', '종합정보', '포털' 등 특정 시스템 접속 방법을 묻는 경우 -> 'student_support_portal'
3. '축제', '가수', '라인업', '대동제' 등 매년 바뀌는 공식 정보를 묻는 경우 -> 'official_fallback'
4. 구체적인 날짜나 시험, 개강, 종강 등 학사 일정을 묻는 경우 -> 'academic_calendar'
5. 학과 정보와 함께 교수님 정보를 묻는 경우 -> 'faculty'
6. 휴학, 복학, 장학금 종류, 학점교류, 졸업유예 절차를 묻는 경우 -> 'academic_administration'
7. 학과/학번 정보와 함께 졸업학점이나 교양 이수를 묻는 경우 -> 'graduation_policy' 또는 'general_education'
8. 위 사항에 해당하지 않는 일반적인 질문 -> 'rag'

필드:
- standalone_question: 문맥 포함 완성 질문
- domain: 위의 도메인 명칭 중 하나 (문자열)
- clarification_text: domain이 'clarifying_question'일 때 사용자에게 되물을 구체적인 질문
- slots: {{"department": "...", "cohort_year": 2023, "person": "..."}}
- is_realtime_required: true/false
""".strip()
    user_prompt = f"[이전 대화]\n{history_text or '이전 대화 없음'}\n\n[현재 질문]\n{question}"
    try:
        response = await client.chat.completions.create(
            model=CHAT_MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        )
        return json.loads(response.choices[0].message.content or "{}")
    except: return {}

def build_query_frame(question: str, history: list[ChatHistoryMessage], interpretation: dict[str, Any] | None = None) -> QueryFrame:
    combined_text = conversation_text(question, history)
    entity = find_entity(combined_text)
    intent = infer_query_intent(question, entity)
    confidence = 0.85 if entity else 0.45
    return QueryFrame(
        intent=intent,
        entity=entity,
        confidence=confidence,
        slots={
            "department": infer_department_from_text(combined_text),
            "cohort_year": extract_cohort_year(combined_text),
        },
    )

def build_conversation_state(question: str, history: list[ChatHistoryMessage], interpretation: dict[str, Any] | None = None) -> ConversationState:
    combined_text = conversation_text(question, history)
    interpretation = interpretation or {}
    
    # Use slots from LLM if available, otherwise fallback to heuristics
    slots = interpretation.get("slots") or {}
    department = slots.get("department") or interpretation.get("department") or infer_department_from_text(combined_text)
    
    # Prioritize cohort from question first
    cohort_year = slots.get("cohort_year") or extract_cohort_year(question) or extract_cohort_year(combined_text)
    
    standalone_question = str(interpretation.get("standalone_question", question))
    
    # Determine domain intent from LLM interpretation primarily
    domain_intent = interpretation.get("domain")
    
    # Heuristic override/fallback for specific sensitive domains
    frame = build_query_frame(question, history, interpretation)
    normalized_combined = normalize_entities(combined_text).lower().replace(" ", "")
    has_general_ed_terms = "교양" in normalized_combined and any(term in normalized_combined for term in ["이수체계", "교육과정", "교양과정", "영역", "함께형", "기초교양", "균형교양", "융합교양"])
    has_general_credit_terms = "교양" in normalized_combined and any(term in normalized_combined for term in ["이수학점", "졸업이수학점", "몇학점"])
    if has_general_ed_terms and cohort_year:
        domain_intent = "general_education"
    elif has_general_ed_terms and domain_intent in [None, "rag", "web_search"]:
        domain_intent = "clarifying_question"
        interpretation["clarification_text"] = "교양 이수 체계는 입학년도별로 달라요. 몇 학번 기준으로 안내해 드릴까요?"
    elif has_general_credit_terms and department and cohort_year:
        domain_intent = "graduation_policy"

    if frame.entity:
        entity_config = ENTITY_CATALOG.get(frame.entity, {})
        # If LLM didn't pick a specialized domain, but entity catalog has one, use it
        if domain_intent in [None, "rag", "web_search"] and entity_config.get("domain"):
            domain_intent = entity_config["domain"]
            
    if not domain_intent: domain_intent = "rag"
    
    return ConversationState(
        standalone_question=standalone_question,
        department=department,
        cohort_year=cohort_year,
        domain_intent=domain_intent,
        topic=str(interpretation.get("topic", "")),
        slots=slots
    )

# --- Cafeteria Logic ---
def build_cafeteria_answer(question: str, history: list[ChatHistoryMessage]) -> StructuredAnswer | None:
    if not CAFETERIA_DATA_PATH.exists(): return None
    
    try:
        content = CAFETERIA_DATA_PATH.read_text(encoding="utf-8")
    except:
        return None

    # Get target date
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    target_date_str = now.strftime("%Y.%m.%d")
    
    # Check if a specific date was mentioned in the question
    date_matches = re.findall(r"(\d{1,2})월\s*(\d{1,2})일", question)
    if date_matches:
        m, d = date_matches[0]
        target_date_str = f"{now.year}.{int(m):02d}.{int(d):02d}"

    sections = content.split("---")
    cafeteria_results = []

    for section in sections:
        section = section.strip()
        if not section: continue
        
        lines = section.split("\n")
        restaurant_name = "알 수 없는 식당"
        
        # First pass: find restaurant name
        for line in lines:
            if line.startswith("식당명:"):
                restaurant_name = line.replace("식당명:", "").strip()
                break
        
        # Second pass: group lines by date
        meals_by_date = defaultdict(list)
        current_date = None
        
        for line in lines:
            line = line.strip()
            if not line or "|" not in line: continue
            
            # Check if line starts with a date (YYYY.MM.DD)
            date_match = re.match(r"(\d{4}\.\d{2}\.\d{2})", line)
            if date_match:
                current_date = date_match.group(1)
                # Remove date part for processing meal content
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    # Parts[0] is date, Parts[1] is meal type, Parts[2] is content...
                    for i in range(1, len(parts), 2):
                        if i + 1 < len(parts):
                            meals_by_date[current_date].append((parts[i], parts[i+1]))
            elif current_date:
                # This line belongs to the current_date (e.g., dinner line)
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 2:
                    for i in range(0, len(parts), 2):
                        if i + 1 < len(parts):
                            meals_by_date[current_date].append((parts[i], parts[i+1]))
        
        target_meals = meals_by_date.get(target_date_str)
        if target_meals:
            # Filter out "No info"
            valid_meals = [m for m in target_meals if "등록된 식단내용이" not in m[1]]
            if valid_meals:
                cafeteria_results.append({
                    "name": restaurant_name,
                    "meals": valid_meals
                })

    if not cafeteria_results:
        return StructuredAnswer(
            answer=f"{target_date_str}의 식단 정보가 등록되지 않았습니다.",
            sources=[CAFETERIA_DATA_PATH.name],
            answer_mode="cafeteria"
        )

    # Build response text
    ans_lines = []
    for res in cafeteria_results:
        if ans_lines: ans_lines.append("") # Spacing between restaurants
        ans_lines.append(f"[{res['name']}]")
        for m_type, m_content in res["meals"]:
            # Clean up meal content
            clean_content = m_content.replace("< 선택식>", "선택식:").replace("<선택식>", "선택식:").replace("*", "")
            # Ensure no double commas from cleanup
            clean_content = re.sub(r",\s*,", ",", clean_content).strip(", ")
            ans_lines.append(f"{m_type}: {clean_content}")

    return StructuredAnswer(
        answer="\n".join(ans_lines),
        sources=[CAFETERIA_DATA_PATH.name],
        answer_mode="cafeteria"
    )

# --- Dispatch Registry ---
def build_general_education_answer(question: str, history: list[ChatHistoryMessage], state: ConversationState) -> StructuredAnswer | None:
    cohort = state.cohort_year or 2024 # Default to latest major system
    ref_key = f"general_education_{cohort}"
    
    # Precise period-based selection
    if ref_key not in ACADEMIC_REFERENCES:
        if 2018 <= cohort <= 2019:
            ref_key = "general_education_2018"
        elif 2020 <= cohort <= 2020:
            ref_key = "general_education_2020"
        elif 2021 <= cohort <= 2022:
            ref_key = "general_education_2021"
        elif 2023 <= cohort <= 2023:
            ref_key = "general_education_2023"
        elif cohort >= 2024:
            ref_key = "general_education_2024"
        else:
            ref_key = "general_education_2024" # Default fallback
            
    ref = ACADEMIC_REFERENCES.get(ref_key)
    if not ref: return None
    
    dept = state.department or "전체 학과"
    lines = [f"[{dept} {ref.get('admission_cohort', '교양교육과정')}]", ""]
    lines.append(f"최소 이수학점: {ref.get('minimum_credits', 30)}학점")
    
    norm_q = normalize_entities(question).lower()
    items = ref.get("items", [])
    
    exclude_keywords = ["말고", "제외", "다른"]
    is_exclusion = any(k in question for k in exclude_keywords)
    
    if is_exclusion:
        display_items = [
            item for item in items 
            if not any(word in norm_q for word in [item['name'].lower(), item['name'].replace('교양', '').lower(), item['name'].replace('기초교양-', '').lower()])
        ]
    else:
        matched_items = [item for item in items if normalize_entities(item['name']).lower() in norm_q]
        display_items = matched_items if matched_items else items
    
    if not display_items: display_items = items
    
    for item in display_items:
        lines.append(f"- {item['name']}: {item['requirement']}")
        
    return StructuredAnswer(answer="\n".join(lines), sources=[ref.get("source") or "https://www.chosun.ac.kr"], answer_mode=ref_key)

def build_graduation_policy_answer(question: str, history: list[ChatHistoryMessage], state: ConversationState) -> StructuredAnswer | None:
    policy = find_graduation_policy_for_text(conversation_text(question, history))
    if not policy: return None
    
    dept = policy.get("department", "해당 학과")
    cohort = policy.get("admission_cohort", "해당 학번")
    lines = [f"[{dept} {cohort} 졸업요건]", ""]
    
    if policy.get("minimum_total_credits"):
        lines.append(f"총 졸업이수학점: {policy['minimum_total_credits']}학점")
    if policy.get("single_major_credits"):
        lines.append(f"전공 이수학점: {policy['single_major_credits']}학점")
    if policy.get("general_education_credits"):
        lines.append(f"교양 이수학점: {policy['general_education_credits']}학점")
    if policy.get("special_integration"):
        lines.append(f"세부 구성: {policy['special_integration']}")
    
    if policy.get("note"):
        lines.append(f"참고 사항: {policy['note']}")
            
    return StructuredAnswer(answer="\n".join(lines), sources=[policy.get("source") or "https://www.chosun.ac.kr"], answer_mode="graduation_policy")

def build_academic_administration_answer(question: str, history: list[ChatHistoryMessage], state: ConversationState) -> StructuredAnswer | None:
    ref = ACADEMIC_REFERENCES.get("academic_administration_info")
    if not ref: return None
    
    norm_q = normalize_entities(question).lower()
    lines = []
    
    # Matching logic for sub-topics
    topics_map = {
        "휴학": ["leave_of_absence"],
        "복학": ["leave_of_absence"],
        "장학": ["scholarship"],
        "학점교류": ["credit_exchange"],
        "유예": ["graduation_deferment"],
        "졸업유보": ["graduation_deferment"]
    }
    
    found_keys = []
    for keyword, keys in topics_map.items():
        if keyword in norm_q: found_keys.extend(keys)
        
    if not found_keys: return None
    
    for key in set(found_keys):
        val = ref.get(key)
        if val:
            if isinstance(val, dict):
                # Filter sub-topics if specific words are in question
                if "휴학" in norm_q and "복학" not in norm_q:
                    if val.get("general"): lines.append(str(val["general"]))
                    if val.get("military"): lines.append(str(val["military"]))
                elif "복학" in norm_q and "휴학" not in norm_q:
                    if val.get("reinstatement"): lines.append(str(val["reinstatement"]))
                else:
                    for sub_val in val.values(): lines.append(str(sub_val))
            else:
                lines.append(str(val))
                
    if not lines: return None
    return StructuredAnswer(answer="\n\n".join(lines), sources=["조선대학교 학사규정 및 안내"], answer_mode="academic_administration")

DOMAIN_HANDLERS = {
    "student_support_portal": build_portal_answer,
    "academic_calendar": lambda q, h, s, i: build_academic_calendar_answer(q, h, i),
    "faculty": build_structured_faculty_answer,
    "cafeteria": lambda q, h, s, i: build_cafeteria_answer(q, h),
    "graduation_credit_progress": build_graduation_credit_progress_answer,
    "general_education": build_general_education_answer,
    "graduation_policy": build_graduation_policy_answer,
    "official_fallback": lambda q, h, s, i: build_entity_official_fallback_answer(q, h),
    "clarifying_question": lambda q, h, s, i: StructuredAnswer(answer=i.get("clarification_text") or "조금 더 구체적으로 말씀해 주시겠어요? (예: 학과, 학번 등)", sources=[], answer_mode="clarifying_question"),
    "academic_administration": build_academic_administration_answer,
}

def build_structured_domain_answer(question: str, history: list[ChatHistoryMessage], state: ConversationState, interpretation: dict[str, Any] | None = None) -> StructuredAnswer | None:
    # 1. Basic/Immediate data handlers
    if state.domain_intent == "current_date":
        combined_text = conversation_text(question, history).lower()
        if "오늘" in combined_text and ("날짜" in combined_text or "며칠" in combined_text):
            now = datetime.now(ZoneInfo("Asia/Seoul"))
            return StructuredAnswer(answer=f"오늘 날짜는 {now.year}년 {now.month}월 {now.day}일입니다. (한국 시간 기준)", sources=[], answer_mode="current_date")

    # 2. Registry-based dispatch
    # Map 'graduation' domain to specific calculation if it looks like one, otherwise RAG handles it
    intent = state.domain_intent
    if intent == "graduation": intent = "graduation_credit_progress"

    handler = DOMAIN_HANDLERS.get(intent)
    if handler:
        try:
            import inspect
            sig = inspect.signature(handler)
            param_count = len(sig.parameters)
            if param_count >= 4:
                answer = handler(question, history, state, interpretation)
            elif param_count == 3:
                answer = handler(question, history, state)
            elif param_count == 2:
                answer = handler(question, history)
            elif param_count == 1:
                answer = handler(question)
            else:
                answer = handler()

            if isinstance(answer, StructuredAnswer): return answer
            if isinstance(answer, str):
                return StructuredAnswer(answer=answer, sources=[], answer_mode=intent)
        except Exception:
            return None

    return None

async def build_official_web_search_answer_direct(
    question: str,
    history: list[ChatHistoryMessage],
    interpretation: dict[str, Any] | None = None,
) -> StructuredAnswer | None:
    # 1. 지식 저장소 확인
    cached = find_in_web_knowledge(question)
    if cached: return cached

    # 2. 검색어 결정 (LLM이 생성한 최적화된 검색어 우선)
    search_query = (interpretation or {}).get("optimized_search_query")
    if not search_query:
        standalone = (interpretation or {}).get("standalone_question") or question
        search_query = standalone if standalone.startswith("조선대학교") else f"조선대학교 {standalone}"

    # 3. Jina AI 검색
    jina = JinaSearchTool(api_key=JINA_API_KEY, max_results=WEB_SEARCH_MAX_RESULTS)
    search_results_text = jina.run(search_query)

    if "검색 결과가 없습니다" in search_results_text: return None

    # 4. GPT 요약 (범용적 구체화 지침)
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    system_prompt = f"""너는 조선대학교 학사 행정 안내 챗봇 '조선인사이트'야. 제공된 웹 검색 결과를 바탕으로 답변해.
    [현재 날짜: {now.strftime("%Y-%m-%d")}]

    지침:
    1. 답변 스타일: 친절하고 전문적인 학사 가이드 톤으로 작성해.
    2. 정보 강조: 사용자가 한눈에 파악할 수 있도록 중요한 정보(날짜, 장소, 금액 등)는 **볼드체**를 사용해.
    3. 리스트 활용: 항목이 여러 개인 경우 글머리 기호(•)를 사용하여 보기 좋게 나열해.
    4. 타 대학 제외: 조선대학교와 관련 없는 정보는 제외하고 조선대학교 정보만 명확히 안내해.
    5. 금지사항: 답변 본문에 직접적인 URL이나 "[공식 홈페이지]" 같은 텍스트는 포함하지 마. (시스템이 별도로 처리함)
    """.strip()
    user_prompt = f"질문: {question}\n\n검색 결과:\n{search_results_text}"

    try:
        response = await client.chat.completions.create(
            model=WEB_SEARCH_MODEL,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        )
        answer = response.choices[0].message.content.replace("*", "").strip()
        sources = extract_urls_from_value(search_results_text)[:5]

        # 5. 지식 저장소 저장
        save_web_discovery(question, answer, sources, mode="official_web_search")

        return StructuredAnswer(answer=answer, sources=sources, answer_mode="official_web_search")
    except Exception as e:
        print(f"Warning: 웹 검색 요약 실패: {e}")
        return None

def build_entity_official_fallback_answer(question: str, history: list[ChatHistoryMessage]) -> StructuredAnswer | None:
    frame = build_query_frame(question, history)
    entity_config = ENTITY_CATALOG.get(str(frame.entity), {})
    fallback = entity_config.get("fallback")
    if not frame.entity or not fallback: return None
    if frame.intent not in {"where_to_apply", "how_to_apply", "when_is", "general_lookup"}: return None

    lines = [f"{entity_with_topic_particle(str(frame.entity))} 공식 자료 확인이 필요한 항목입니다."]
    lines.append(str(fallback))
    if entity_config.get("source"):
        lines.append(f"공식 홈페이지 주소: {entity_config['source']}")
        
    return StructuredAnswer(answer="\n".join(lines), sources=[], answer_mode="official_fallback")

async def get_gpt_response(question: str, context: str, history: list[ChatHistoryMessage], interpretation: dict[str, Any] | None = None) -> str:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    current_date_str = now.strftime("%Y-%m-%d %A")
    
    system_prompt = f"""너는 조선대학교 학사 행정 안내 챗봇 '조선인사이트'야. [현재 시각: {current_date_str}]
조선대학교 학생들과 교직원들에게 정확한 학사 정보를 제공하는 것이 네 역할이야.

지침:
1. 답변 스타일: 전문적이고 명확한 문장으로 답변해. 
2. 형식 주의: **기호(•, -, *, [ ], 등)를 절대 사용하지 마.** 리스트가 필요하면 문장으로 나열하거나 줄바꿈만 사용해.
3. 정보 출처: 제공된 [참고 정보]를 바탕으로 답변하되, 질문의 의도에 맞게 필요한 정보만 간결하게 구성해.
4. **금지 사항**: '도움이 되어 기쁩니다', '더 궁금한 점이 있으시면 말씀해 주세요' 같은 상투적인 마무리 멘트는 절대 하지 마. 정보 전달이 완료되면 바로 답변을 마쳐.
5. 중요 사항: URL이나 주소 정보가 [참고 정보]에 있다면 반드시 답변에 포함해.
6. 정확성: 오늘 날짜는 {now.strftime("%Y년 %m월 %d일")}이야. 날짜와 요일을 정확히 계산해서 안내해.
""".strip()
    history_text = format_chat_history(history, max_messages=5)
    user_prompt = f"[참고 정보]\n{context}\n\n[이전 대화]\n{history_text}\n\n[질문]\n{question}"
    try:
        response = await client.chat.completions.create(
            model=CHAT_MODEL_NAME,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        )
        content = response.choices[0].message.content.replace("*", "").strip()
        # 출처 관련 문구 제거 (단, 실제 URL 주소는 보존해야 함)
        content = re.sub(r"(출처|source|url)[\s:]*", "", content, flags=re.IGNORECASE).strip()
        return content
    except Exception as e:
        return f"답변 생성 중 오류가 발생했습니다: {e}"

def basis_line_for_answer(answer_mode: str, sources: list[str]) -> str:
    return ""

def append_basis_line(answer: str, answer_mode: str, sources: list[str]) -> str:
    """답변의 가독성을 위해 불필요한 공백을 제거하고 형식을 정돈합니다."""
    # LLM이 생성한 마크다운 형식을 최대한 보존하되 양 끝 공백만 정리
    clean_answer = answer.strip()
    
    # 중복된 빈 줄 제거 (최대 1줄만 허용)
    clean_answer = re.sub(r'\n{3,}', '\n\n', clean_answer)
            
    return clean_answer

def suggestions_for_answer(answer_mode: str, state: ConversationState, suggestion_context: str = "") -> list[str]:
    """답변 모드와 상황에 맞는 추천 질문을 생성합니다."""
    suggestions = []
    
    # 1. 도메인별 기본 추천
    if answer_mode == "graduation_credit_progress":
        suggestions = ["졸업 요건 자세히 알려줘", "이번 학기 성적 확인 방법", "전공 필수 과목 조회"]
    elif answer_mode == "academic_calendar_2026":
        suggestions = ["기말고사 일정", "여름방학 언제 시작해?", "수강신청 기간 확인"]
    elif answer_mode == "cafeteria":
        suggestions = ["다른 식당 메뉴", "내일 학식 메뉴", "기숙사 식당 위치"]
    elif "faculty" in answer_mode:
        suggestions = ["다른 교수님 찾기", "학과 사무실 번호", "학사일정 확인"]
    
    # 2. 일반적인 추천 (정보가 부족할 때)
    if not suggestions:
        if "장학" in state.topic:
            suggestions = ["신청 가능한 장학금", "국가장학금 신청 기간", "장학 공지사항"]
        else:
            suggestions = ["이번 학기 학사일정", "장학금 정보 알려줘", "오늘 학식 메뉴"]

    return suggestions[:3] # 최대 3개까지만 반환

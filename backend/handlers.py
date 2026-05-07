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
    return max(years) if years else None

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
    lines = [f"{dept} {'질문과 맞는 ' if matched else ''}교수진 정보입니다."]
    for m in visible:
        dtl = [str(m.get("position", "")).strip()]
        if m.get("field"): dtl.append(f"전공분야 {m['field']}")
        if m.get("office") and (office_q or matched or not compact): dtl.append(f"연구실 {m['office']}")
        if m.get("phone") and (phone_q or matched or not compact): dtl.append(f"전화 {m['phone']}")
        lines.append(f"- {m.get('name')}: {', '.join(d for d in dtl if d)}")
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
    return StructuredAnswer(answer=f"{intro}\n경로: {route['path']}\n{route['after']}", sources=[route.get("source") or "https://thechoa.chosun.ac.kr"], answer_mode="student_support_portal", suggestion_context=str(route["topic"]))

# --- Calendar Logic ---
def build_academic_calendar_date_index(docs: list[IndexedDocument]) -> dict[str, list[str]]:
    index = defaultdict(list)
    for doc in docs:
        if "학사일정" in doc.source or "academic_calendar" in str(doc.metadata.get("tags", "")):
            date_matches = re.findall(r"(\d{4})-(\d{2})-(\d{2})", doc.content)
            for y, m, d in date_matches:
                date_str = f"{y}-{m}-{d}"
                event_name = doc.metadata.get("title") or doc.content[:20]
                if event_name not in index[date_str]: index[date_str].append(event_name)
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
    if dates:
        lines = []
        for d in dates:
            evs = ACADEMIC_CALENDAR_DATE_EVENTS.get(d, [])
            if evs: lines.append(f"{format_date_range(d,d)} 학사일정은 {', '.join(evs)}입니다.")
        if lines:
            lines.append("학사일정은 학교 사정에 따라 변경될 수 있습니다.")
            return StructuredAnswer(answer="\n".join(lines), sources=[ref.get("source") or "https://www.chosun.ac.kr"], answer_mode="academic_calendar_2026")
    matched = []
    for e in events:
        if not isinstance(e, dict): continue
        if term and e.get("term") != term: continue
        name = str(e.get("name", "")).lower()
        aliases = [str(a).lower() for a in e.get("aliases", [])]
        if name in norm_q or any(a and a in norm_q for a in aliases): matched.append(e)
    if not matched: return None
    lines = [f"{e.get('term','')} {e.get('name','')} 일정은 {format_date_range(str(e.get('start_date','')), str(e.get('end_date','')))}입니다." for e in matched[:3]]
    lines.append("학사일정은 학교 사정에 따라 변경될 수 있습니다.")
    return StructuredAnswer(answer="\n".join(lines), sources=[ref.get("source") or "https://www.chosun.ac.kr"], answer_mode="academic_calendar_2026")

# --- Graduation Logic ---
CREDIT_PROGRESS_PATTERN = re.compile(r"(전공|교양|총|취득)\s*(\d{1,3})\s*(학점|점)?", re.IGNORECASE)
CREDIT_FOLLOWUP_KEYWORDS = ["졸업", "부족", "남았", "더 들어", "들어야", "계산", "가능", "충족", "미달"]

def find_graduation_policy_for_text(text: str) -> dict[str, Any] | None:
    dept = infer_department_from_text(text)
    cohort = extract_cohort_year(text)
    for p in ACADEMIC_POLICIES:
        if p.get("policy_type") != "graduation_credits": continue
        if dept and normalize_entities(str(p.get("department",""))).lower() == dept.lower():
            if cohort and p.get("admission_cohort") == f"{cohort}학번": return p
            if not cohort and p.get("is_latest"): return p
    return None

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
    if gap > 0: lines.append(f"- {area}은 {completed}학점 이수하셨네요. 졸업까지 {gap}학점 더 필요합니다. (기준 {req})")
    else: lines.append(f"- {area}은 {completed}학점으로 기준({req})을 충족하셨습니다!")

def build_graduation_credit_progress_answer(question: str, history: list[ChatHistoryMessage], interpretation: dict[str, Any] | None = None) -> str | None:
    prog_state = build_credit_progress_state(question, history)
    prog_state.update(credit_progress_from_interpretation(interpretation))
    if not prog_state and not any(k in question for k in CREDIT_FOLLOWUP_KEYWORDS): return None
    policy = find_graduation_policy_for_text(conversation_text(question, history))
    if not policy:
        if prog_state: return "학점 계산을 하려면 학과 정보가 필요합니다. '컴공 전공 50학점 들었어'처럼 알려주세요."
        return None
    dept = policy.get("department", "해당 학과")
    cohort = policy.get("admission_cohort", "최신 기준")
    lines = [f"{dept} {cohort} 졸업이수학점 기준입니다."]
    for area, val in prog_state.items(): append_credit_gap_for_area(lines, policy, area, val, question)
    if "총" not in prog_state: lines.append("전체 충족 여부를 보려면 총 이수학점도 알려주세요.")
    return "\n".join(lines) if len(lines) > 1 else None

# --- Main Entry Handlers ---
async def interpret_chat_request(question: str, history: list[ChatHistoryMessage]) -> dict[str, Any]:
    history_text = format_chat_history(history, max_messages=8, max_chars=1800)
    system_prompt = """너는 조선대학교 챗봇의 대화 이해기야. 사용자의 현재 질문과 이전 대화를 보고 JSON만 반환해.
규칙:
- standalone_question: 이전 대화 맥락을 포함해 완성된 질문 (예: "그거 언제야?" -> "장학금 신청 기간 언제야?")
- department: 질문에서 언급된 학과/전공 (예: "컴공" -> "컴퓨터공학과")
- topic: 대화의 핵심 주제 (예: "scholarship", "graduation_credits", "faculty", "academic_calendar")
- intent: 사용자의 의도 (예: "lookup", "apply", "contact")
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
    department = str(interpretation.get("department", "") or "").strip() or infer_department_from_text(combined_text)
    standalone_question = str(interpretation.get("standalone_question", question))
    
    # Infer domain intent
    frame = build_query_frame(question, history, interpretation)
    domain_intent = "rag"
    if frame.entity:
        entity_config = ENTITY_CATALOG.get(frame.entity, {})
        domain_intent = entity_config.get("domain", "rag")
    
    return ConversationState(
        standalone_question=standalone_question,
        department=department,
        cohort_year=extract_cohort_year(combined_text),
        domain_intent=domain_intent,
        topic=str(interpretation.get("topic", ""))
    )

def build_structured_domain_answer(question: str, history: list[ChatHistoryMessage], state: ConversationState, interpretation: dict[str, Any] | None = None) -> StructuredAnswer | None:
    # 1. Portal Route
    portal_answer = build_portal_answer(question, history)
    if portal_answer: return portal_answer
    
    # 2. Academic Calendar
    if state.domain_intent == "academic_calendar":
        calendar_answer = build_academic_calendar_answer(question, history, interpretation)
        if calendar_answer: return calendar_answer
    
    # 3. Faculty
    if state.domain_intent == "faculty":
        faculty_answer = build_structured_faculty_answer(question, history, state, interpretation)
        if faculty_answer: return faculty_answer

    # 4. Graduation
    if state.domain_intent == "graduation" or any(k in question for k in CREDIT_FOLLOWUP_KEYWORDS):
        grad_answer = build_graduation_credit_progress_answer(question, history, interpretation)
        if grad_answer:
            return StructuredAnswer(answer=grad_answer, sources=[ACADEMIC_POLICY_PATH.name], answer_mode="graduation_credit_progress")
        
    # 5. Basic Date Handler
    combined_text = conversation_text(question, history).lower()
    if "오늘" in combined_text and ("날짜" in combined_text or "며칠" in combined_text):
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        return StructuredAnswer(answer=f"오늘은 {now.year}년 {now.month}월 {now.day}일입니다.", sources=[], answer_mode="current_date")
    
    return None

async def build_official_web_search_answer_direct(
    question: str,
    history: list[ChatHistoryMessage],
    interpretation: dict[str, Any] | None = None,
) -> StructuredAnswer | None:
    # 1. 지식 저장소 확인
    cached = find_in_web_knowledge(question)
    if cached: return cached

    # 2. 검색어 보강
    standalone_question = (interpretation or {}).get("standalone_question") or question
    if standalone_question.startswith("조선대학교"):
        search_query = standalone_question
    else:
        search_query = f"조선대학교 {standalone_question}"

    # 3. Jina AI 검색
    jina = JinaSearchTool(api_key=JINA_API_KEY, max_results=WEB_SEARCH_MAX_RESULTS)
    search_results_text = jina.run(search_query)

    if "검색 결과가 없습니다" in search_results_text: return None

    # 4. GPT 요약
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    system_prompt = f"""너는 조선대학교 정보 도우미야. 제공된 웹 검색 결과를 바탕으로 사용자의 질문에 답변해.
[오늘 날짜] {now.year}-{now.month:02d}-{now.day:02d}

지침:
- 검색 결과에서 공식 SNS(인스타그램 등)나 공식 홈페이지 정보를 우선적으로 반영해.
- 답변에서 '*' 문자를 절대 사용하지 마.
- 확인된 출처 URL을 반드시 포함해.
- 모르는 내용은 지어내지 말고 "공식 홈페이지를 확인해 주세요"라고 안내해.
"""
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
    entity_config = ENTITY_CATALOG.get(frame.entity, {})
    fallback = entity_config.get("fallback")
    official_route = entity_config.get("official_route")
    if not frame.entity or not fallback: return None
    if frame.intent not in {"where_to_apply", "how_to_apply", "when_is", "general_lookup"}: return None

    lines = [f"{entity_with_topic_particle(frame.entity)} 공식 자료 확인이 필요한 항목입니다."]
    if official_route: lines.append(f"확인 경로: {official_route}")
    lines.append(str(fallback))
    return StructuredAnswer(answer="\n".join(lines), sources=[entity_config.get("source") or "https://www3.chosun.ac.kr"], answer_mode="official_fallback")

async def get_gpt_response(question: str, context: str, history: list[ChatHistoryMessage], interpretation: dict[str, Any] | None = None) -> str:
    system_prompt = """너는 조선대학교 정보 도우미야. 
목표: 학생이 실제로 행동할 수 있도록 확인된 조선대학교 정보만 간결하게 안내해.
답변 우선순위:
1. 제공된 참고 정보
2. 확인된 출처 URL이 있는 정보
기타: 답변에서 '*' 문자를 사용하지 마.
"""
    history_text = format_chat_history(history, max_messages=5)
    user_prompt = f"[참고 정보]\n{context}\n\n[이전 대화]\n{history_text}\n\n[질문]\n{question}"
    try:
        response = await client.chat.completions.create(
            model=CHAT_MODEL_NAME,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        )
        return response.choices[0].message.content.replace("*", "").strip()
    except Exception as e:
        return f"답변 생성 중 오류가 발생했습니다: {e}"

def basis_line_for_answer(answer_mode: str, sources: list[str]) -> str:
    return ""

def append_basis_line(answer: str, answer_mode: str, sources: list[str]) -> str:
    return answer

def suggestions_for_answer(answer_mode: str, state: ConversationState, suggestion_context: str = "") -> list[str]:
    return []

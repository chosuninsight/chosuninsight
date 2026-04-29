import os
import re
import shutil
import time
from dataclasses import dataclass

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


ENTITY_NORMALIZATION_RULES = {
    "컴공": "컴퓨터공학과",
    "컴퓨터공학전공": "컴퓨터공학과",
    "소웨": "소프트웨어학부",
    "정통": "정보통신공학과",
    "정시모집": "정시",
    "수시모집": "수시",
    "장학안내": "장학금",
    "장학 정보": "장학금",
    "졸업이수학점": "졸업학점",
    "졸업 요건": "졸업요건",
}

BOILERPLATE_PATTERNS = [
    r"첨부파일\s*\d+\s*개",
    r"이전글.*",
    r"다음글.*",
    r"목록\s*$",
    r"^본문\s*없음$",
    r"^\s*조회수\s*[:：]?\s*\d+\s*$",
]

TABLE_LINE_PATTERN = re.compile(r"\s*\|\s*")
WHITESPACE_PATTERN = re.compile(r"\n{3,}")
KEY_VALUE_PATTERN = re.compile(r"^([^:#]{1,80}):\s+(.+)$")
DEFAULT_CHROMA_INSERT_BATCH_SIZE = int(os.getenv("CHROMA_INSERT_BATCH_SIZE", "500"))
ACADEMIC_YEAR_PATTERN = re.compile(r"(\d{4})\s*학년도")
CALENDAR_YEAR_PATTERN = re.compile(r"(\d{4})[.\-년]")
DEPARTMENT_ALIASES = {
    "컴퓨터공학과": ["컴퓨터공학과", "컴퓨터공학전공", "컴공"],
    "인공지능학과": ["인공지능학과", "인공지능공학과", "인공지능공학전공"],
    "정보통신공학과": ["정보통신공학과", "정보통신공학전공", "정통"],
    "정보보안전공": ["정보보안전공", "정보보안학과"],
    "모빌리티SW전공": ["모빌리티SW전공", "모빌리티SW"],
    "전자공학과": ["전자공학과", "전자공학전공"],
    "소프트웨어학부": ["소프트웨어학부", "AI소프트웨어학부", "소웨"],
    "간호학과": ["간호학과"],
    "약학과": ["약학과"],
    "법학과": ["법학과"],
}


@dataclass(frozen=True)
class PipelineProfile:
    name: str
    chunk_size: int
    chunk_overlap: int
    semantic_separators: list[str]
    recursive_separators: list[str]


PIPELINE_PROFILES = {
    "origin": PipelineProfile(
        name="origin",
        chunk_size=900,
        chunk_overlap=140,
        semantic_separators=["\n---\n", "\n# ", "\n## ", "\n### "],
        recursive_separators=["\n## ", "\n### ", "\n- ", "\n", ". ", " "],
    ),
    "update": PipelineProfile(
        name="update",
        chunk_size=700,
        chunk_overlap=120,
        semantic_separators=["\n---\n", "\n## ", "\n### "],
        recursive_separators=["\n## ", "\n### ", "\n- ", "\n", ". ", " "],
    ),
}


def get_pipeline_profile(profile_name: str) -> PipelineProfile:
    return PIPELINE_PROFILES.get(profile_name, PIPELINE_PROFILES["origin"])


def build_recursive_splitter(profile: PipelineProfile) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=profile.chunk_size,
        chunk_overlap=profile.chunk_overlap,
        separators=profile.recursive_separators,
        length_function=len,
    )


def normalize_entities(text: str) -> str:
    normalized = text
    for raw, canonical in ENTITY_NORMALIZATION_RULES.items():
        normalized = re.sub(rf"(?<!\w){re.escape(raw)}(?!\w)", canonical, normalized)
    return normalized


def remove_boilerplate(text: str) -> str:
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if any(re.search(pattern, stripped, re.IGNORECASE) for pattern in BOILERPLATE_PATTERNS):
            continue
        cleaned_lines.append(stripped)
    return WHITESPACE_PATTERN.sub("\n\n", "\n".join(cleaned_lines)).strip()


def normalize_table_lines(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        if TABLE_LINE_PATTERN.search(line) and not line.startswith("|"):
            cells = [cell.strip() for cell in line.split("|") if cell.strip()]
            if cells:
                lines.append("| " + " | ".join(cells) + " |")
                continue
        lines.append(line)
    return "\n".join(lines).strip()


def markdownify_chunk(text: str) -> str:
    lines = []
    for raw_line in normalize_table_lines(text).splitlines():
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        key_value_match = KEY_VALUE_PATTERN.match(line)
        if key_value_match and not line.startswith(("-", "#")):
            key, value = key_value_match.groups()
            lines.append(f"- **{key.strip()}**: {value.strip()}")
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def semantic_chunk(text: str, profile: PipelineProfile) -> list[str]:
    segments = [text.strip()]
    for separator in profile.semantic_separators:
        next_segments = []
        for segment in segments:
            parts = [part.strip() for part in segment.split(separator) if part.strip()]
            next_segments.extend(parts or [segment])
        segments = next_segments
    return [segment for segment in segments if segment]


def infer_doc_category(source: str, content: str) -> str:
    candidates = [source, content]
    for candidate in candidates:
        if "장학" in candidate:
            return "scholarship"
        if "식단" in candidate or "식당" in candidate:
            return "cafeteria"
        if "비교과" in candidate:
            return "extracurricular"
        if "학사공지" in candidate:
            return "academic_notice"
        if "교내일반공지" in candidate:
            return "general_notice"
        if "외부기관공고" in candidate:
            return "external_notice"
    return "general"


def extract_tags(source: str, content: str) -> list[str]:
    tags = set()
    lowered = normalize_entities(f"{source}\n{content}").lower()
    keyword_map = {
        "scholarship": ["장학", "장학금"],
        "deadline": ["신청기간", "마감", "d-day", "d-"],
        "graduation": ["졸업", "이수학점", "졸업요건", "졸업학점"],
        "admission": ["수시", "정시", "전형"],
        "cafeteria": ["식단", "식당", "조식", "중식", "석식"],
        "software": ["소프트웨어학부", "컴퓨터공학과", "정보통신공학과"],
        "program": ["비교과", "마일리지", "역량태그"],
    }
    for tag, needles in keyword_map.items():
        if any(needle.lower() in lowered for needle in needles):
            tags.add(tag)
    return sorted(tags)


def infer_source_type(source: str, content: str, category: str) -> str:
    normalized = normalize_entities(f"{source}\n{content}")
    if "졸업이수최소학점" in normalized or "minimum_total_credits" in normalized:
        return "academic_policy"
    if category in {"academic_notice", "general_notice", "external_notice"} or "공지" in source:
        return "notice"
    if category in {"scholarship", "cafeteria", "extracurricular"}:
        return "dynamic_info"
    return "reference"


def extract_years(text: str) -> list[int]:
    years = [int(match) for match in ACADEMIC_YEAR_PATTERN.findall(text)]
    years.extend(int(match) for match in CALENDAR_YEAR_PATTERN.findall(text))
    return sorted(set(year for year in years if 1900 <= year <= 2100))


def infer_academic_year(source: str, content: str) -> int | None:
    years = extract_years(f"{source}\n{content}")
    return max(years) if years else None


def infer_departments(source: str, content: str) -> list[str]:
    normalized = normalize_entities(f"{source}\n{content}")
    departments = []
    for department, aliases in DEPARTMENT_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            departments.append(department)
    return departments


def derive_temporal_metadata(source: str, content: str, source_type: str) -> dict[str, str | int | bool]:
    academic_year = infer_academic_year(source, content)
    departments = infer_departments(source, content)
    metadata: dict[str, str | int | bool] = {
        "source_type": source_type,
        "departments": ", ".join(departments),
    }
    if academic_year is not None:
        metadata["academic_year"] = academic_year
        metadata["effective_from"] = f"{academic_year}학년도"
    if "이후 입학생" in content and academic_year is not None:
        metadata["admission_cohort"] = f"{academic_year}학년도 이후 입학생"
    if source_type == "academic_policy" and academic_year is not None:
        metadata["is_latest_candidate"] = academic_year >= 2025
    return metadata


def build_contextual_prefix(source: str, category: str, tags: list[str], profile: PipelineProfile) -> list[str]:
    prefix = [
        f"# Source: {source}",
        f"## Category: {category}",
        f"## Pipeline: {profile.name}",
    ]
    if tags:
        prefix.append(f"## Tags: {', '.join(tags)}")
    prefix.append("")
    return prefix


def derive_self_query_metadata(source: str, category: str, tags: list[str]) -> dict[str, str]:
    return {
        "source": source,
        "category": category,
        "tags": ", ".join(tags),
        "normalized_source": normalize_entities(source),
    }


def build_structured_chunks(content: str, source: str, profile_name: str = "origin") -> list[Document]:
    profile = get_pipeline_profile(profile_name)
    base_segments = semantic_chunk(content, profile)
    if not base_segments:
        base_segments = [content.strip()]

    splitter = build_recursive_splitter(profile)
    documents = []
    for segment_index, segment in enumerate(base_segments):
        normalized = normalize_entities(segment)
        cleaned = remove_boilerplate(normalized)
        if not cleaned:
            continue

        markdown_text = markdownify_chunk(cleaned)
        category = infer_doc_category(source, markdown_text)
        tags = extract_tags(source, markdown_text)
        source_type = infer_source_type(source, markdown_text, category)
        prefix = build_contextual_prefix(source, category, tags, profile)
        enriched_text = "\n".join(prefix) + markdown_text

        split_chunks = splitter.split_text(enriched_text)
        total_chunks = len(split_chunks)

        for chunk_index, chunk_text in enumerate(split_chunks):
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue
            temporal_metadata = derive_temporal_metadata(source, chunk_text, source_type)
            metadata = derive_self_query_metadata(source, category, tags) | temporal_metadata | {
                "segment_index": segment_index,
                "chunk_index": chunk_index,
                "chunk_total": total_chunks,
                "has_table": " | " in chunk_text,
                "pipeline_profile": profile.name,
            }
            documents.append(Document(page_content=chunk_text, metadata=metadata))

    return documents


def clear_directory_contents(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)
        return

    for filename in os.listdir(path):
        file_path = os.path.join(path, filename)
        if os.path.isfile(file_path) or os.path.islink(file_path):
            os.unlink(file_path)
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)


def add_documents_in_batches(vectorstore: Chroma, documents: list[Document], batch_size: int = DEFAULT_CHROMA_INSERT_BATCH_SIZE) -> None:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    for start in range(0, len(documents), batch_size):
        vectorstore.add_documents(documents[start:start + batch_size])


def move_directory_contents(source_directory: str, target_directory: str) -> None:
    if not os.path.exists(target_directory):
        os.makedirs(target_directory)

    clear_directory_contents(target_directory)

    for filename in os.listdir(source_directory):
        shutil.move(
            os.path.join(source_directory, filename),
            os.path.join(target_directory, filename),
        )


def rebuild_collection_from_documents(
    persist_directory: str,
    collection_name: str,
    embedding_function,
    raw_documents: list[Document],
    profile_name: str = "origin",
) -> int:
    rebuilt_documents = []
    for raw_doc in raw_documents:
        source = (raw_doc.metadata or {}).get("source", "") or "unknown"
        rebuilt_documents.extend(
            build_structured_chunks(raw_doc.page_content, source, profile_name=profile_name)
        )

    parent_dir = os.path.dirname(persist_directory) or "."
    base_name = os.path.basename(os.path.abspath(persist_directory))
    temp_directory = os.path.join(parent_dir, f".{base_name}.rebuild")

    clear_directory_contents(temp_directory)
    time.sleep(1)

    vectorstore = Chroma(
        persist_directory=temp_directory,
        embedding_function=embedding_function,
        collection_name=collection_name,
    )

    if rebuilt_documents:
        add_documents_in_batches(vectorstore, rebuilt_documents)

    move_directory_contents(temp_directory, persist_directory)
    shutil.rmtree(temp_directory, ignore_errors=True)

    return len(rebuilt_documents)

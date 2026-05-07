from pydantic import BaseModel, ConfigDict, Field
from dataclasses import dataclass
from typing import Any

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

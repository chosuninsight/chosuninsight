# Architecture

**Analysis Date:** 2025-02-13

## Pattern Overview

**Overall:** Retrieval-Augmented Generation (RAG) Architecture with a Layered API.

**Key Characteristics:**
- **Hybrid Retrieval:** Combines semantic search (ChromaDB) with keyword search (BM25) using Reciprocal Rank Fusion (RRF) for improved relevance.
- **Domain-Specific Logic:** Specialized handlers for University-specific domains like faculty profiles, academic calendars, and graduation policies.
- **Dual-Store Strategy:** Separates base knowledge (`origin`) from frequently updated information (`update`) to maintain performance and data freshness.

## Layers

**Frontend Layer:**
- Purpose: Provides an interactive chat interface for students.
- Location: `frontend/`
- Contains: Vue 3 components, state management via composables, and API client services.
- Depends on: Backend API.
- Used by: End users.

**API / Orchestration Layer:**
- Purpose: Handles user requests, orchestrates retrieval, and manages LLM interactions.
- Location: `backend/`
- Contains: FastAPI endpoints, intent classification, and domain-specific search logic.
- Depends on: ChromaDB, OpenAI API, and local JSON data.
- Used by: Frontend.

**RAG Pipeline Layer:**
- Purpose: Processes raw documents into searchable chunks with rich metadata.
- Location: `rag_pipeline.py`, `rebuild_chroma.py`
- Contains: Text cleaning, entity normalization, semantic chunking, and indexing logic.
- Depends on: HuggingFace Embeddings, ChromaDB.
- Used by: Backend (indirectly via shared DB) and data management scripts.

**Data Layer:**
- Purpose: Persistent storage for knowledge base and session memory.
- Location: `chroma_db_store/`, `backend/data/`
- Contains: Vector database files, structured JSON datasets.
- Depends on: Local filesystem.
- Used by: Backend and RAG Pipeline.

## Data Flow

**Chat Query Flow:**

1. User sends a question from the `frontend/`.
2. `backend/main.py` receives the request and classifies the intent using `build_query_frame`.
3. System builds a search plan (`build_search_plan`) and determines whether to use vector search, keyword search, or domain-specific JSON lookup.
4. Retrieval is performed:
   - Hybrid Search: Vector search + BM25 merged via RRF.
   - Domain Logic: Direct lookup in `backend/data/*.json` for faculty or policies.
5. Context is combined and sent to OpenAI API via `AsyncOpenAI` for answer generation.
6. The final answer, along with sources and suggestions, is returned to the frontend.

**State Management:**
- **UI State:** Managed via Vue composables in `frontend/src/composables/useChatHistory.js`, persisting to LocalStorage.
- **Server-side Session:** Managed via `backend/memory.py` (`ConversationMemoryStore`) with TTL and LRU-like behavior.

## Key Abstractions

**IndexedDocument:**
- Purpose: Standardized representation of a document chunk in the RAG system.
- Examples: Defined in `backend/main.py` as a `dataclass`.
- Pattern: Value Object.

**PipelineProfile:**
- Purpose: Configures chunking behavior for different types of data (e.g., origin vs update).
- Examples: Defined in `rag_pipeline.py`.
- Pattern: Strategy Pattern.

**SearchPlan:**
- Purpose: Encapsulates the strategy for a specific query (which stores to search, what filters to apply).
- Examples: Created by `build_search_plan` in `backend/main.py`.

## Entry Points

**FastAPI App:**
- Location: `backend/main.py`
- Triggers: HTTP requests from frontend or external clients.
- Responsibilities: Routing, Request validation, Orchestration of RAG flow.

**Vite Frontend:**
- Location: `frontend/index.html` (mounts `frontend/src/main.js`)
- Triggers: User opening the browser.
- Responsibilities: Rendering the UI, managing user sessions.

**Indexing Script:**
- Location: `rebuild_chroma.py`
- Triggers: Manual execution for data refreshes.
- Responsibilities: Wiping and rebuilding the vector database from raw files.

## Error Handling

**Strategy:** Graceful degradation with user-facing fallback messages.

**Patterns:**
- **Try-Except Blocks:** Used extensively in `backend/main.py` for file I/O and API calls.
- **Fallback Answers:** `build_entity_official_fallback_answer` provides official links when RAG confidence is low.

## Cross-Cutting Concerns

**Logging:** Basic console logging for search results and data counts in `backend/main.py`.
**Validation:** Pydantic models in `backend/main.py` for request (`ChatRequest`) and response (`ChatResponse`) structures.
**Authentication:** Not explicitly implemented in the provided code (CORS middleware allows specific origins).

---

*Architecture analysis: 2025-02-13*

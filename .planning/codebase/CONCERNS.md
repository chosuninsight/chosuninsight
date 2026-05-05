# Codebase Concerns

**Analysis Date:** 2025-02-14

## Tech Debt

**Monolithic Backend Entrypoint:**
- Issue: `backend/main.py` is a "God File" exceeding 3,000 lines. it combines FastAPI routing, Pydantic models, RAG pipeline logic, search scoring heuristics, and manual data indexing.
- Files: `backend/main.py`
- Impact: Extremely difficult to maintain, test, or navigate. Violates the Single Responsibility Principle.
- Fix approach: Decouple into logical modules (e.g., `api/routes.py`, `services/search.py`, `models/schemas.py`, `logic/graduation.py`).

**Hardcoded Business Rules:**
- Issue: Extensive use of hardcoded dictionaries for entity normalization, department aliases, and search scoring weights.
- Files: `backend/main.py`, `rag_pipeline.py`
- Impact: System is rigid. Any change in university structure or policy requires code changes and redeployment.
- Fix approach: Move configurations to external files (YAML/JSON) or a database/config service.

**In-Memory Session Storage:**
- Issue: `ConversationMemoryStore` uses a local dictionary to store session facts.
- Files: `backend/memory.py`
- Impact: Session data is lost on server restart. Prevents horizontal scaling (multiple instances won't share session state).
- Fix approach: Implement a persistent store like Redis or a database.

**Unpinned Dependencies:**
- Issue: `backend/requirements.txt` does not specify versions for most packages.
- Files: `backend/requirements.txt`
- Impact: Inconsistent environments and high risk of breakage when new versions of libraries (like LangChain or ChromaDB) are released.
- Fix approach: Pin versions using `pip-compile` or manually specifying exact versions.

## Security Considerations

**Error Detail Leakage:**
- Issue: Global exception handler returns `str(exc)` directly to the client.
- Files: `backend/main.py`
- Risk: Internal system details, file paths, or database errors could be exposed to users.
- Current mitigation: Basic exception handling exists but is too verbose.
- Recommendations: Log the full error internally and return a generic error message with a correlation ID to the user.

**CORS Configuration:**
- Issue: `ALLOWED_ORIGINS` includes a public development domain `http://foxibu.is-a.dev:9000` by default.
- Files: `backend/main.py`
- Risk: Potential for unauthorized cross-origin requests if not properly managed in production.
- Recommendations: Ensure environment-specific CORS policies.

## Performance Bottlenecks

**Inefficient Linear Search:**
- Issue: `run_focus_search` and `find_department_faculty_hits` iterate through the entire `all_indexed_docs` list (in-memory) on every request.
- Files: `backend/main.py`
- Cause: Reliance on manual filtering and scoring instead of utilizing vector database metadata filters or a proper search engine.
- Improvement path: Migrate to ChromaDB metadata filtering or implement a dedicated search index (e.g., BM25 in a database).

**Event Loop Blocking:**
- Issue: Synchronous calls to ChromaDB and heavy CPU-bound loops are performed inside `async def` route handlers.
- Files: `backend/main.py`
- Cause: Using synchronous LangChain/ChromaDB methods in an async context.
- Improvement path: Use `run_in_executor` for CPU-bound tasks or switch to async-capable clients where available.

## Fragile Areas

**Search Scoring Heuristics:**
- Issue: The search quality depends on a complex web of manual score increments (e.g., `score += 20`).
- Files: `backend/main.py`
- Why fragile: Subtle changes to these numbers can significantly alter search results for unrelated queries.
- Safe modification: Implement a comprehensive regression test suite for search quality.

**Large Vue Components:**
- Files: `frontend/src/views/HomeView.vue`
- Why fragile: Mixes UI layout, state management, and interaction logic.
- Safe modification: Break down into smaller functional components (e.g., `MessageList`, `ChatInput`, `MenuCarousel`).

## Missing Critical Features

**Proper Logging:**
- Problem: The application uses `print()` statements for logging instead of a structured logging framework.
- Files: `backend/main.py`, `rebuild_chroma.py`, `rag_pipeline.py`
- Blocks: Effective monitoring and debugging in production environments.

**Unit Test Coverage:**
- Problem: Tests are limited to integration-level chat cases.
- Blocks: Safe refactoring of the complex logic in `main.py`.

## Test Coverage Gaps

**Internal Logic:**
- What's not tested: Data processing, query expansion, entity normalization, and scoring logic.
- Files: `backend/main.py`, `rag_pipeline.py`
- Risk: Logic errors in Korean text processing or metadata inference could go unnoticed.
- Priority: High

---

*Concerns audit: 2025-02-14*

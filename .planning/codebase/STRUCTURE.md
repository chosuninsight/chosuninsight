# Codebase Structure

**Analysis Date:** 2025-02-13

## Directory Layout

```
chosuninsight/
├── backend/                # FastAPI backend source
│   ├── data/               # Structured JSON datasets
│   ├── tests/              # Backend test suites
│   ├── main.py             # API entry point & RAG orchestrator
│   └── memory.py           # Chat session management
├── frontend/               # Vue 3 frontend source
│   ├── src/                # Frontend application code
│   │   ├── components/     # UI components
│   │   ├── composables/    # Shared state logic
│   │   ├── services/       # API integration
│   │   └── views/          # Page-level components
│   └── public/             # Static assets
├── chosun_rag_data/        # Raw source documents for RAG
├── chroma_db_store/        # Persistent Vector DB (ChromaDB)
├── docs/                   # Documentation & design notes
├── rag_pipeline.py         # Document processing & chunking logic
├── rebuild_chroma.py       # Full re-indexing script
├── Update_date.py          # Incremental data update script
├── docker-compose.yml      # Orchestration for containers
└── requirements.txt        # Top-level Python dependencies
```

## Directory Purposes

**backend/:**
- Purpose: Server-side logic for the RAG system.
- Contains: API endpoints, hybrid search logic, LLM prompt engineering.
- Key files: `backend/main.py`, `backend/memory.py`.

**frontend/:**
- Purpose: User interface for interacting with the 챗봇.
- Contains: Vue components, styling, and client-side history logic.
- Key files: `frontend/src/views/HomeView.vue`, `frontend/src/services/api.js`.

**backend/data/:**
- Purpose: Source of truth for structured university data.
- Contains: JSON files for academic policies, faculty profiles, and canned answers.
- Key files: `backend/data/academic_policies.json`, `backend/data/faculty_profiles.json`.

**chosun_rag_data/:**
- Purpose: Knowledge base for the RAG system.
- Contains: Text files (`.txt`) extracted from university notices and websites.
- Key files: `chosun_rag_data/학사공지_2026.txt`, `chosun_rag_data/academic_graduation_credits_2025.txt`.

**chroma_db_store/:**
- Purpose: Vector storage for semantic retrieval.
- Contains: SQLite databases and binary blobs managed by ChromaDB.
- Key files: `chroma_db_store/chroma.sqlite3`.

## Key File Locations

**Entry Points:**
- `backend/main.py`: Main FastAPI application file.
- `frontend/src/main.js`: Main Vue application entry.

**Configuration:**
- `frontend/vite.config.js`: Build and dev server configuration for frontend.
- `docker-compose.yml`: Defines backend and frontend services for deployment.
- `.env.example`: Template for environment variables.

**Core Logic:**
- `rag_pipeline.py`: Logic for cleaning, normalizing, and chunking text data.
- `backend/main.py`: Implementation of Hybrid Retrieval and RRF.

**Testing:**
- `backend/tests/run_chat_cases.py`: Script to run automated chat tests.
- `backend/tests/chat_cases.json`: Test scenarios and expected results.

## Naming Conventions

**Files:**
- Python: `snake_case.py` (e.g., `rag_pipeline.py`)
- Vue Components: `PascalCase.vue` (e.g., `ChatMessage.vue`)
- Services/Composables: `camelCase.js` (e.g., `useChatHistory.js`)

**Directories:**
- General: `snake_case` or `kebab-case` (e.g., `chosun_rag_data`, `node_modules`)

## Where to Add New Code

**New Feature (Backend):**
- Primary code: `backend/main.py` for new endpoints or retrieval logic.
- Domain Data: Add new JSON files to `backend/data/`.

**New Component/Module (Frontend):**
- Implementation: `frontend/src/components/` for UI elements, `frontend/src/views/` for pages.
- Styling: `frontend/src/style.css` for global styles, or scoped blocks in `.vue` files.

**Data Updates:**
- Knowledge Base: Add `.txt` files to `chosun_rag_data/` and run `python rebuild_chroma.py`.

## Special Directories

**chroma_db_store/:**
- Purpose: Persistent vector database.
- Generated: Yes (by `rebuild_chroma.py`).
- Committed: Yes (currently in repo to provide default data).

**frontend/dist/:**
- Purpose: Production-ready frontend build.
- Generated: Yes (by `npm run build`).
- Committed: No.

---

*Structure analysis: 2025-02-13*

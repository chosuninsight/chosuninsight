# External Integrations

**Analysis Date:** 2025-02-12

## APIs & External Services

**Large Language Models:**
- OpenAI - Used for generating conversational answers and intent classification.
  - SDK: `openai` (AsyncOpenAI)
  - Auth: `OPENAI_API_KEY` in `.env`
  - Model: `gpt-4o-mini` (configurable via `CHAT_MODEL_NAME`)

**Embeddings:**
- HuggingFace - Provides the embedding model for vector search.
  - Model: `jhgan/ko-sroberta-multitask` (loaded locally via `langchain_huggingface`)

**Web Scrapers (Dynamic Data Sources):**
- Chosun University Portals - Crawled daily for latest information.
  - THE조아 (Extra-curricular): `https://thechoa.chosun.ac.kr/ncrProgramAppl/a/m/getProgramApplList.do`
  - Academic Notices: `https://www4.chosun.ac.kr/acguide/9326/subview.do`
  - General Notices: `https://www3.chosun.ac.kr/chosun/217/subview.do`
  - External Notices: `https://www3.chosun.ac.kr/chosun/2500/subview.do`
  - Scholarship Notices: `https://scho.chosun.ac.kr/scho/2138/subview.do`
  - Cafeteria Menus: Multiple URLs on `www3.chosun.ac.kr`

## Data Storage

**Databases:**
- ChromaDB (Vector Database)
  - Connection: Local persistent storage mapped to `./chroma_db_store` (origin) and `./chroma_db_update` (updates).
  - Client: `langchain_chroma.Chroma`

**File Storage:**
- Local JSON files - Used for static reference data in `backend/data/`.
  - `academic_policies.json`
  - `academic_reference_answers.json`
  - `faculty_profiles.json`
- Local Text files - Temporary storage for crawled data in `chosun_rag_data/`.

**Caching:**
- In-memory conversation store implemented in `backend/memory.py` with TTL and session management.

## Authentication & Identity

**Auth Provider:**
- Custom Session Management - Uses `session_id` passed in requests for tracking conversation state.

## Monitoring & Observability

**Error Tracking:**
- Basic console logging and FastAPI exception handlers in `backend/main.py`.

**Logs:**
- Standard output (stdout) captured by Docker containers.

## CI/CD & Deployment

**Hosting:**
- Docker Compose based deployment.

**CI Pipeline:**
- Not detected in the immediate codebase, but Docker-ready.

## Environment Configuration

**Required env vars:**
- `OPENAI_API_KEY` - OpenAI API authentication.
- `CHAT_MODEL_NAME` - Targeted LLM model.
- `PERSIST_DIRECTORY` - Path for ChromaDB storage.
- `ALLOWED_ORIGINS` - CORS configuration for the API.

**Secrets location:**
- `.env` file (local development and container environment).

## Webhooks & Callbacks

**Incoming:**
- None detected.

**Outgoing:**
- Flag file synchronization between `updater` and `backend` services via shared volume (`/root/tmp/update_complete.flag`).

---

*Integration audit: 2025-02-12*

# Technology Stack

**Analysis Date:** 2025-02-12

## Languages

**Primary:**
- Python 3.10 - Backend API, RAG pipeline, and data crawler.
- JavaScript (ES6+) - Frontend application.

**Secondary:**
- HTML/CSS - UI structure and styling.
- Shell (Bash) - Docker entrypoints and build scripts.

## Runtime

**Environment:**
- Node.js 20 - Frontend build environment.
- Python 3.10 - Backend runtime.

**Package Manager:**
- npm (Node Package Manager) - Frontend dependencies.
- pip (Python Package Installer) - Backend dependencies.
- Lockfile: `package-lock.json` present.

## Frameworks

**Core:**
- FastAPI - Backend web framework.
- Vue.js 3.5 - Frontend component framework.
- Vite 8.0 - Frontend build tool and dev server.

**Testing:**
- Custom JSON-based test cases and runner in `backend/tests/run_chat_cases.py`.

**Build/Dev:**
- Docker & Docker Compose - Containerization and orchestration.
- Nginx - Production frontend server.

## Key Dependencies

**Critical:**
- LangChain / LangChain-Chroma / LangChain-HuggingFace - RAG orchestration and vector store integration.
- OpenAI - LLM provider (`gpt-4o-mini`).
- ChromaDB - Vector database for document storage and retrieval.
- HuggingFace Embeddings - Local embedding model (`jhgan/ko-sroberta-multitask`).

**Infrastructure:**
- Selenium & BeautifulSoup4 - Web scraping for dynamic data updates.
- Uvicorn - ASGI server for FastAPI.
- Pydantic v2 - Data validation and settings management.
- Rank-BM25 - BM25 implementation for hybrid search.

## Configuration

**Environment:**
- `.env` file - Stores API keys and system configurations (e.g., `OPENAI_API_KEY`, `CHAT_MODEL_NAME`).
- `docker-compose.yml` - Manages environment variables and volume mappings for containers.

**Build:**
- `vite.config.js` - Frontend build configuration.
- `backend/Dockerfile` & `frontend/Dockerfile` - Container build specifications.

## Platform Requirements

**Development:**
- Docker Desktop or Docker Engine.
- Python 3.10+ (for local development).
- Node.js 20+ (for local development).

**Production:**
- Linux-based container host (as seen in Dockerfiles).
- Chromium/Chromedriver (required for backend crawler).

---

*Stack analysis: 2025-02-12*

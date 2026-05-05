# Coding Conventions

**Analysis Date:** 2024-05-05

## Naming Patterns

**Files:**
- **Frontend Components:** PascalCase (e.g., `ChatMessage.vue`, `ChatSidebar.vue`, `HomeView.vue`).
- **Frontend Services/Composables:** camelCase (e.g., `api.js`, `useChatHistory.js`).
- **Backend/Python Files:** snake_case (e.g., `main.py`, `rag_pipeline.py`, `rebuild_chroma.py`).

**Functions:**
- **JavaScript:** camelCase (e.g., `fetchChatResponse`, `sendMessage`, `scrollToBottom`).
- **Python:** snake_case (e.g., `load_academic_policies`, `normalize_entities`, `get_pipeline_profile`).

**Variables:**
- **JavaScript:** camelCase for local variables and refs (e.g., `inputText`, `isLoading`).
- **Python:** snake_case (e.g., `session_id`, `chat_model_name`).
- **Constants:** SCREAMING_SNAKE_CASE (e.g., `API_BASE_URL` in JS, `OPENAI_API_KEY` in Python).

**Types:**
- **Python Classes:** PascalCase (e.g., `ChatRequest`, `ConversationMemory`, `PipelineProfile`).
- **Dataclasses:** PascalCase (e.g., `IndexedDocument`).

## Code Style

**Formatting:**
- **JavaScript:** No explicit tool (Prettier/ESLint) config found. Standard ES6+ syntax. Uses semicolons.
- **Python:** 4-space indentation. No explicit `black` or `ruff` config found, but follows PEP 8.

**Linting:**
- Not explicitly configured via `.eslintrc` or `pyproject.toml`.

## Import Organization

**Order (Python):**
1. Standard library imports (e.g., `os`, `json`, `re`).
2. Third-party library imports (e.g., `fastapi`, `langchain`, `pydantic`).
3. Local application imports (e.g., `from backend.memory import ...`).

**Path Aliases:**
- **Frontend:** Relative paths used (e.g., `import MenuCard from '../components/MenuCard.vue'`). No `@` or custom aliases detected in `vite.config.js`.

## Error Handling

**Patterns:**
- **JavaScript/Frontend:** `try/catch` blocks around API calls with user-facing error messages in Korean. Logs errors to `console.error`.
- **Python/Backend:** `try/except` for file operations (returning default empty values like `[]` or `{}`) and `HTTPException` for API errors.

## Logging

**Framework:** `console` for frontend. Python standard `print` or built-in logging (minimal usage seen).

**Patterns:**
- Frontend logs API errors using `console.error('API Error:', error)`.
- Backend uses `print` for test results and simple logging.

## Comments

**When to Comment:**
- Labeling major sections in `main.py` using `// ===` or `# ===`.
- Brief explanations for logic or TODOs.

**JSDoc/TSDoc:**
- Used in `frontend/src/services/api.js` to describe parameters and return types.

## Function Design

**Size:** Functions are generally focused, but `main.py` contains large setup logic and dictionary definitions.

**Parameters:**
- JavaScript: Uses positional parameters, sometimes with defaults.
- Python: Uses type hints and default values liberally.

**Return Values:**
- Python: Uses type hints (e.g., `-> dict`, `-> list[dict[str, Any]]`).

## Module Design

**Exports:**
- **JavaScript:** `export const` for named exports in services. `export default` for Vue components.
- **Python:** Standard module imports.

**Barrel Files:**
- Not used.

---

*Convention analysis: 2024-05-05*

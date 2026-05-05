# Testing Patterns

**Analysis Date:** 2024-05-05

## Test Framework

**Runner:**
- Custom Python script: `backend/tests/run_chat_cases.py`

**Assertion Library:**
- Python standard library (`json`, `urllib.request`)

**Run Commands:**
```bash
python3 backend/tests/run_chat_cases.py  # Run backend integration tests
```

## Test File Organization

**Location:**
- Backend: `backend/tests/`

**Naming:**
- `run_chat_cases.py`: The test runner.
- `chat_cases.json`: The data file containing test scenarios.

**Structure:**
```
backend/tests/
├── chat_cases.json
└── run_chat_cases.py
```

## Test Structure

**Suite Organization:**
```python
# From backend/tests/run_chat_cases.py
def main() -> int:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    failures = []

    for case in cases:
        response = post_chat({
            "question": case["question"],
            "history": case.get("history", []),
            "debug": True,
        })
        # ... validation logic ...
```

**Patterns:**
- **Setup pattern:** Requires a running API server at `http://127.0.0.1:8001/chat`.
- **Teardown pattern:** None (stateless API testing).
- **Assertion pattern:** Checks response `answer_mode` against `expected_mode`, and ensures `must_include` strings are present and `must_not_include` strings are absent in the `answer`.

## Mocking

**Framework:** None detected.

**Patterns:**
- The tests interact directly with the running backend, which in turn uses the real ChromaDB and OpenAI API (unless configured otherwise in `.env`).

**What to Mock:**
- Not currently using mocks in the integration test suite.

**What NOT to Mock:**
- RAG pipeline components (the goal of the current suite is to verify the combined output of retrieval and generation).

## Fixtures and Factories

**Test Data:**
```json
[
  {
    "name": "Admission Query",
    "question": "수시모집 일정이 어떻게 돼?",
    "expected_mode": "origin",
    "must_include": ["수시", "일정"],
    "must_not_include": ["정시"]
  }
]
```

**Location:**
- `backend/tests/chat_cases.json`

## Coverage

**Requirements:** None enforced.

**View Coverage:**
- Not applicable (no coverage tool configured).

## Test Types

**Unit Tests:**
- Not detected.

**Integration Tests:**
- Backend API integration tests in `backend/tests/`. These verify the end-to-end RAG response for specific questions.

**E2E Tests:**
- The `run_chat_cases.py` acts as a functional E2E test for the backend API.
- Frontend E2E tests: Not used.

## Common Patterns

**Async Testing:**
- Not used in the test runner (uses synchronous `urllib.request`), despite the backend being asynchronous.

**Error Testing:**
- Basic failure reporting in `run_chat_cases.py` if assertions fail.

---

*Testing analysis: 2024-05-05*

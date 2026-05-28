from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


API_BASE = os.getenv("TEST_API_BASE", "http://127.0.0.1:8001")
API_KEY = os.getenv("INTERNAL_API_KEY", "")
CASES_PATH = Path(__file__).with_name("deep_chat_cases.json")

_AUTH_HEADERS = {"Content-Type": "application/json", "X-Api-Key": API_KEY}


def post_chat(payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}/chat",
        data=data,
        headers=_AUTH_HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=70) as response:
        return json.loads(response.read().decode("utf-8"))


def clear_memory(session_id: str) -> None:
    request = urllib.request.Request(
        f"{API_BASE}/memory/{session_id}",
        headers={"X-Api-Key": API_KEY},
        method="DELETE",
    )
    try:
        urllib.request.urlopen(request, timeout=10).read()
    except Exception:
        pass


def validate_response(check: dict, response: dict) -> list[str]:
    answer = response.get("answer", "")
    mode = (response.get("debug") or {}).get("answer_mode")
    failures = []

    expected = check.get("expected_mode")
    if expected and mode != expected:
        failures.append(f"mode expected {expected!r}, got {mode!r}")

    for required in check.get("must_include", []):
        if required not in answer:
            failures.append(f"missing answer text {required!r}")

    for forbidden in check.get("must_not_include", []):
        if forbidden in answer:
            failures.append(f"forbidden answer text {forbidden!r}")

    return failures


def main() -> int:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    failures = []

    for case in cases:
        session_id = case.get("session_id") or f"deep-{case['name']}"
        clear_memory(session_id)
        response = post_chat(
            {
                "question": case["question"],
                "history": case.get("history", []),
                "debug": True,
                "session_id": session_id,
            }
        )
        case_failures = validate_response(case, response)
        mode = (response.get("debug") or {}).get("answer_mode")
        answer_preview = response.get("answer", "")[:600]

        if case_failures:
            failures.append((case["name"], case_failures, answer_preview))
            print(f"FAIL {case['name']}: {'; '.join(case_failures)}")
            print(f"  answer: {answer_preview}")
        else:
            print(f"PASS {case['name']} [{mode}]")

        clear_memory(session_id)

    if failures:
        print("\nFailures:")
        for name, case_failures, answer_preview in failures:
            print(f"- {name}: {'; '.join(case_failures)}")
            print(f"  answer: {answer_preview}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

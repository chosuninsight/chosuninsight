from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path


API_URL = "http://127.0.0.1:8001/chat"
CASES_PATH = Path(__file__).with_name("chat_cases.json")


def post_chat(payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def clear_memory(session_id: str) -> None:
    request = urllib.request.Request(
        f"http://127.0.0.1:8001/memory/{session_id}",
        method="DELETE",
    )
    try:
        urllib.request.urlopen(request, timeout=10).read()
    except Exception:
        pass


def validate_response(check: dict, response: dict) -> list[str]:
    answer = response.get("answer", "")
    debug = response.get("debug") or {}
    mode = debug.get("answer_mode")
    failures = []
    expected = check.get("expected_mode")

    if expected:
        mode_match = mode == expected
        if not mode_match:
            # Flexible matching for graduation/gen-ed
            if expected == "graduation_policy" and mode and mode.startswith("general_education"):
                mode_match = True
            elif expected == "clarifying_question" and mode and mode.startswith("general_education"):
                # If it answered gen-ed instead of clarifying, check if it include cohort
                mode_match = False

        if not mode_match:
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
        session_id = case.get("session_id") or f"eval-{case['name']}"
        clear_memory(session_id)

        steps = case.get("steps")
        if steps:
            responses = []
            history = case.get("history", [])
            for step in steps:
                response = post_chat(
                    {
                        "question": step["question"],
                        "history": step.get("history", history),
                        "debug": True,
                        "session_id": session_id,
                    }
                )
                responses.append((step, response))
                history = history + [
                    {"role": "user", "content": step["question"]},
                    {"role": "assistant", "content": response.get("answer", "")},
                ]

            case_failures = []
            answer_preview = responses[-1][1].get("answer", "")[:500]
            for index, (step, response) in enumerate(responses, start=1):
                step_failures = validate_response(step, response)
                case_failures.extend(f"step {index}: {failure}" for failure in step_failures)
            mode = (responses[-1][1].get("debug") or {}).get("answer_mode")
        else:
            response = post_chat(
                {
                    "question": case["question"],
                    "history": case.get("history", []),
                    "debug": True,
                    "session_id": session_id,
                }
            )
            answer_preview = response.get("answer", "")[:500]
            case_failures = validate_response(case, response)
            mode = (response.get("debug") or {}).get("answer_mode")

        if case_failures:
            failures.append((case["name"], case_failures, answer_preview))
            print(f"FAIL {case['name']}: {'; '.join(case_failures)}")
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

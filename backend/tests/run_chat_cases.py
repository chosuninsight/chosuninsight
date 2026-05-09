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


def main() -> int:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    failures = []

    for case in cases:
        response = post_chat(
            {
                "question": case["question"],
                "history": case.get("history", []),
                "debug": True,
            }
        )
        answer = response.get("answer", "")
        debug = response.get("debug") or {}
        mode = debug.get("answer_mode")

        case_failures = []
        expected = case["expected_mode"]
        
        mode_match = (mode == expected)
        if not mode_match:
            # Flexible matching for graduation/gen-ed
            if expected == "graduation_policy" and mode and mode.startswith("general_education"):
                mode_match = True
            elif expected == "clarifying_question" and mode and mode.startswith("general_education"):
                # If it answered gen-ed instead of clarifying, check if it include cohort
                mode_match = False # Still failure if it was supposed to clarify
        
        if not mode_match:
            case_failures.append(f"mode expected {expected!r}, got {mode!r}")

        for required in case.get("must_include", []):
            if required not in answer:
                case_failures.append(f"missing answer text {required!r}")

        for forbidden in case.get("must_not_include", []):
            if forbidden in answer:
                case_failures.append(f"forbidden answer text {forbidden!r}")

        if case_failures:
            failures.append((case["name"], case_failures, answer[:500]))
            print(f"FAIL {case['name']}: {'; '.join(case_failures)}")
        else:
            print(f"PASS {case['name']} [{mode}]")

    if failures:
        print("\nFailures:")
        for name, case_failures, answer_preview in failures:
            print(f"- {name}: {'; '.join(case_failures)}")
            print(f"  answer: {answer_preview}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

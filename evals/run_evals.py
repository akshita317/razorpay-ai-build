"""Agent-level eval harness.

Feeds natural-language customer complaints to the full agent (Gemini + tools)
and checks that the rules-engine verdict it obtained matches the expected
action and rule. This catches regressions in prompt wording, tool
descriptions, and dispute-type classification — the parts an LLM can silently
get wrong.

Usage:  GEMINI_API_KEY=... python evals/run_evals.py
Gate:   exits 1 if accuracy < PASS_THRESHOLD.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent import run_agent  # noqa: E402

PASS_THRESHOLD = 0.9
CASES_PATH = Path(__file__).parent / "cases.json"


def extract_verdict(trace: list[dict]) -> dict | None:
    """Return the last successful decide_dispute result in the trace."""
    verdict = None
    for step in trace:
        if step["tool"] == "decide_dispute" and "action" in step.get("result", {}):
            verdict = step["result"]
    return verdict


def main() -> int:
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set — cannot run agent evals.")
        return 2

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    passed, results = 0, []

    for case in cases:
        try:
            out = run_agent(case["message"])
        except Exception as exc:
            results.append((case["id"], False, f"agent error: {exc}"))
            continue

        verdict = extract_verdict(out["trace"])
        if verdict is None:
            results.append((case["id"], False, "agent never called decide_dispute"))
        elif verdict["action"] != case["expected_action"]:
            results.append(
                (case["id"], False,
                 f"expected {case['expected_action']} ({case['expected_rule']}), "
                 f"got {verdict['action']} ({verdict['rule_id']})")
            )
        elif verdict["rule_id"] != case["expected_rule"]:
            results.append(
                (case["id"], False,
                 f"right action, wrong rule: expected {case['expected_rule']}, got {verdict['rule_id']}")
            )
        else:
            passed += 1
            results.append((case["id"], True, f"{verdict['action']} via {verdict['rule_id']}"))

        time.sleep(2)  # stay under free-tier rate limits

    print(f"\n{'=' * 62}")
    for case_id, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL':4}  {case_id:28}  {detail}")
    accuracy = passed / len(cases)
    print(f"{'=' * 62}\n{passed}/{len(cases)} passed  (accuracy {accuracy:.0%}, gate {PASS_THRESHOLD:.0%})")

    return 0 if accuracy >= PASS_THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main())

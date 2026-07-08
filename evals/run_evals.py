"""Eval harness — loads each scenario, runs the supervisor + specialists,
grades the resulting ActionPlan with Layer A assertions (authoritative) and
Layer B LLM-as-judge (directional). docs/feature.prd §10.

Run with: uv run python -m evals.run_evals [case_name ...]

Each case's result is appended to eval_log.json (repo root, git-ignored — a
run artifact, like action_log.json) IMMEDIATELY after it finishes, not only
at the end of the whole batch. A transient network error partway through a
multi-case run must not discard results from cases that already succeeded.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.supervisor_agent import create_app
from evals.cases import CASES, EvalCase
from evals.judge import judge_rationale
from loader import load_scenario

APP_NAME = "supply_agents_eval"
USER_ID = "eval_user"
EVAL_LOG_PATH = Path(__file__).resolve().parent.parent / "eval_log.json"
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 10


async def _run_case(case: EvalCase) -> dict:
    world = load_scenario(case.scenario)
    world["situation"] = world.get("situation")

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=f"eval-{case.name}",
        state={"world": world, "situation": world.get("situation")},
    )

    runner = Runner(
        app=create_app(name=APP_NAME),
        session_service=session_service,
    )

    async for _event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text="Produce an action plan for the current situation.")],
        ),
    ):
        pass

    final_session = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session.id
    )
    state = final_session.state
    action_plan = state.get("action_plan", {"purchase_orders": [], "rationale": ""})

    layer_a = [assertion(action_plan, world) for assertion in case.assertions]

    try:
        layer_b = judge_rationale(
            situation=world.get("situation", ""),
            world=world,
            recommendations={
                "demand": state.get("rec:demand"),
                "inventory": state.get("rec:inventory"),
                "procurement": state.get("rec:procurement"),
            },
            action_plan=action_plan,
            rationale=action_plan.get("rationale", ""),
        )
    except Exception as exc:  # judge is directional; a judge error must not fail the run
        layer_b = f"judge_error: {exc}"

    return {
        "case": case.name,
        "scenario": case.scenario,
        "description": case.description,
        "layer_a": layer_a,
        "layer_b": layer_b,
        "action_plan": action_plan,
        "guardrail_trips": state.get("guardrail_trips", []),
        "error": None,
    }


async def _run_case_resilient(case: EvalCase) -> dict:
    """Retries transient failures (network blips, 503s); never raises — a
    case that still fails after retries comes back as an error result
    instead of killing the rest of the batch.
    """
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            return await _run_case(case)
        except Exception as exc:
            last_exc = exc
            print(f"  [{case.name}] attempt {attempt} failed: {exc!r}")
            if attempt < MAX_RETRIES + 1:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
    return {
        "case": case.name,
        "scenario": case.scenario,
        "description": case.description,
        "layer_a": [],
        "layer_b": None,
        "action_plan": None,
        "guardrail_trips": [],
        "error": f"{type(last_exc).__name__}: {last_exc}",
    }


def _serialize_result(result: dict) -> dict:
    layer_b = result["layer_b"]
    layer_a = [dataclasses.asdict(a) for a in result["layer_a"]]
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "case": result["case"],
        "scenario": result["scenario"],
        "description": result["description"],
        "layer_a": layer_a,
        "layer_a_passed": bool(layer_a) and all(a["passed"] for a in layer_a) if result["error"] is None else False,
        "layer_b": layer_b.model_dump() if hasattr(layer_b, "model_dump") else layer_b,
        "action_plan": result["action_plan"],
        "guardrail_trips": result["guardrail_trips"],
        "error": result["error"],
    }


def _append_to_eval_log(entry: dict) -> None:
    log = []
    if EVAL_LOG_PATH.exists():
        try:
            log = json.loads(EVAL_LOG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log = []
    log.append(entry)
    EVAL_LOG_PATH.write_text(json.dumps(log, indent=2), encoding="utf-8")


def _print_case_report(serialized: dict) -> None:
    print(f"\n=== {serialized['case']} ===")
    print(f"  {serialized['description']}")
    if serialized["error"] is not None:
        print(f"  [ERROR] case did not complete: {serialized['error']}")
        return
    for a in serialized["layer_a"]:
        status = "PASS" if a["passed"] else "FAIL"
        print(f"  [Layer A] {status} — {a['name']}: {a['detail']}")
    print(f"  [Layer B] {serialized['layer_b']}")
    if serialized["guardrail_trips"]:
        print(f"  [Guardrails] trips: {serialized['guardrail_trips']}")


async def _main_async(case_names: list[str] | None) -> bool:
    cases = [c for c in CASES if not case_names or c.name in case_names]
    if not cases:
        print(f"No matching cases for {case_names}. Available: {[c.name for c in CASES]}")
        return False

    all_passed = True
    for case in cases:
        result = await _run_case_resilient(case)
        serialized = _serialize_result(result)
        _append_to_eval_log(serialized)
        _print_case_report(serialized)
        all_passed = all_passed and serialized["layer_a_passed"]

    print(f"\nEval results appended to {EVAL_LOG_PATH} ({len(cases)} case(s))")
    return all_passed


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run supply-chain agent evals.")
    parser.add_argument("cases", nargs="*", help="Case names to run (default: all).")
    args = parser.parse_args()
    passed = asyncio.run(_main_async(args.cases or None))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()

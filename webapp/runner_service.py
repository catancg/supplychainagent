"""Service layer behind the FastAPI routes — scenario listing/detail, a
synchronous "run this scenario and capture the full trace" operation, and
readers for the persistent log store (data/supply_agents.db, via db.py —
see docs/phase1-db-mcp.prd).

Kept separate from webapp/main.py so the HTTP layer stays thin and this
logic is testable/reusable on its own (e.g. from a script or notebook).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

import db
from agents.observability import TraceCollectorPlugin
from agents.supervisor_agent import create_app
from evals.cases import CASES
from loader import list_scenarios, load_scenario

APP_NAME = "supply_agents_webapp"
USER_ID = "webapp_user"
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 10

_CASE_BY_SCENARIO = {c.scenario: c for c in CASES}

db.init_db()


def list_scenario_summaries() -> list[dict[str, Any]]:
    """One summary card's worth of data per scenario, cheapest-first fields only."""
    summaries = []
    for scenario_id in list_scenarios():
        world = load_scenario(scenario_id)
        case = _CASE_BY_SCENARIO.get(scenario_id)
        summaries.append(
            {
                "id": scenario_id,
                "situation": world.get("situation"),
                "sku_count": len(world.get("skus", [])),
                "warehouse_count": len(world.get("warehouses", [])),
                "supplier_count": len(world.get("suppliers", [])),
                "unavailable_suppliers": [
                    s["id"] for s in world.get("suppliers", []) if not s.get("available", True)
                ],
                "budget_per_cycle": world.get("budget_per_cycle"),
                "description": case.description if case else None,
            }
        )
    return summaries


def get_scenario_detail(scenario_id: str) -> dict[str, Any]:
    world = load_scenario(scenario_id)
    case = _CASE_BY_SCENARIO.get(scenario_id)
    return {
        "id": scenario_id,
        "world": world,
        "description": case.description if case else None,
        "case_name": case.name if case else None,
    }


async def run_scenario(scenario_id: str) -> dict[str, Any]:
    """Runs the supervisor pipeline for a scenario, retrying transient
    failures (Gemini 503s / network blips are common — see evals/run_evals.py
    for the same pattern) before giving up and letting the last exception
    propagate to the caller.
    """
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            return await _run_scenario_once(scenario_id)
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES + 1:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
    assert last_exc is not None
    raise last_exc


async def _run_scenario_once(scenario_id: str) -> dict[str, Any]:
    """Runs the supervisor pipeline for a scenario synchronously and returns
    the full trace (every tool call/result and model text across the whole
    nested agent tree) plus the final recommendations, action plan, and any
    guardrail trips.
    """
    world = load_scenario(scenario_id)
    world["situation"] = world.get("situation")

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=f"webapp-{scenario_id}-{int(time.time())}",
        state={"world": world, "situation": world.get("situation")},
    )

    trace_plugin = TraceCollectorPlugin()
    runner = Runner(
        app=create_app(name=APP_NAME, extra_plugins=[trace_plugin]),
        session_service=session_service,
    )

    started_at = time.time()
    async for _event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text="Produce an action plan for the current situation.")],
        ),
    ):
        pass
    duration_seconds = time.time() - started_at

    final_session = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session.id
    )
    state = final_session.state

    trace = []
    for entry in trace_plugin.trace:
        entry = dict(entry)
        entry["elapsed"] = round(entry.pop("timestamp") - started_at, 2)
        trace.append(entry)

    return {
        "scenario": scenario_id,
        "situation": world.get("situation"),
        "world": world,
        "trace": trace,
        "recommendations": {
            "demand": state.get("rec:demand"),
            "inventory": state.get("rec:inventory"),
            "procurement": state.get("rec:procurement"),
        },
        "action_plan": state.get("action_plan", {"purchase_orders": [], "rationale": ""}),
        "guardrail_trips": state.get("guardrail_trips", []),
        "duration_seconds": round(duration_seconds, 1),
    }


def load_action_log() -> list[dict]:
    return db.list_action_plans()


def load_eval_log() -> list[dict]:
    return db.list_eval_results()

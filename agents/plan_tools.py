"""read_recommendations / emit_action_plan — the supervisor's reconciliation
and persistence tools (docs/feature.prd §5, §9). Guardrail enforcement runs
as a before_tool_callback on emit_action_plan (see guardrails.py); by the
time this tool body runs, purchase_orders have already been clamped and
state["guardrail_trips"] is already set.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pydantic
from google.adk.tools import ToolContext

from agents.schemas import ActionPlan, PurchaseOrder

ACTION_LOG_PATH = Path(__file__).resolve().parent.parent / "action_log.json"


def read_recommendations(tool_context: ToolContext) -> dict:
    """Reads the three specialists' recommendations from state, if present."""
    state = tool_context.state
    return {
        "demand": state.get("rec:demand"),
        "inventory": state.get("rec:inventory"),
        "procurement": state.get("rec:procurement"),
    }


def _append_to_action_log(entry: dict) -> None:
    log = []
    if ACTION_LOG_PATH.exists():
        try:
            log = json.loads(ACTION_LOG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log = []
    log.append(entry)
    ACTION_LOG_PATH.write_text(json.dumps(log, indent=2), encoding="utf-8")


def emit_action_plan(
    purchase_orders: list[PurchaseOrder], rationale: str, tool_context: ToolContext
) -> dict:
    """Validates the ActionPlan and appends it (with any guardrail trips) to the action log.

    Args:
        purchase_orders: proposed orders.
        rationale: short explanation of how the plan reconciles the three
            specialists' recommendations, in this priority order: (1) cover
            demand/shortfall, (2) minimize cost, (3) respect the budget cap.
    """
    try:
        plan = ActionPlan(purchase_orders=purchase_orders, rationale=rationale)
    except pydantic.ValidationError as e:
        return {
            "status": "error",
            "message": f"Invalid purchase_orders: {e}. Fix and call this tool again.",
        }
    plan_dict = plan.model_dump()
    tool_context.state["action_plan"] = plan_dict

    world = tool_context.state.get("world", {})
    _append_to_action_log(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "situation": world.get("situation"),
            "action_plan": plan_dict,
            "guardrail_trips": tool_context.state.get("guardrail_trips", []),
        }
    )
    return {"status": "ok", "action_plan": plan_dict}

"""read_recommendations / emit_action_plan — the supervisor's reconciliation
tool (docs/feature.prd §5, §9). Guardrail enforcement runs as a
before_tool_callback on emit_action_plan (see guardrails.py); by the time
this tool body runs, purchase_orders have already been clamped and
state["guardrail_trips"] is already set.

Persistence is a separate step, not this tool's job: after emit_action_plan
returns status "ok", the supervisor calls the write_action_plan MCP tool
(mcp_server/log_store.py) with this tool's own return values, per
docs/phase1-db-mcp.prd — MCP is for agent-initiated writes, so persistence
lives one level up, at the point the LLM actually decides to log the plan.
"""

from __future__ import annotations

import pydantic
from google.adk.tools import ToolContext

from agents.schemas import ActionPlan, PurchaseOrder


def read_recommendations(tool_context: ToolContext) -> dict:
    """Reads the three specialists' recommendations from state, if present."""
    state = tool_context.state
    return {
        "demand": state.get("rec:demand"),
        "inventory": state.get("rec:inventory"),
        "procurement": state.get("rec:procurement"),
    }


def emit_action_plan(
    purchase_orders: list[PurchaseOrder], rationale: str, tool_context: ToolContext
) -> dict:
    """Validates the ActionPlan and writes it to state.

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
    guardrail_trips = tool_context.state.get("guardrail_trips", [])
    return {
        "status": "ok",
        "action_plan": plan_dict,
        "situation": world.get("situation"),
        "guardrail_trips": guardrail_trips,
    }

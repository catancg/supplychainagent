from agents.plan_tools import emit_action_plan
from agents.state_tools import (
    emit_demand_recommendation,
    emit_procurement_recommendation,
)


class FakeToolContext:
    def __init__(self, state: dict):
        self.state = state


def test_emit_demand_recommendation_writes_state():
    ctx = FakeToolContext({})
    result = emit_demand_recommendation(
        items=[
            {
                "sku": "AC-12",
                "forecast_daily_demand": 10.0,
                "historical_avg_daily_demand": 5.0,
                "is_spike": True,
                "note": "spike",
            }
        ],
        summary="AC-12 is spiking.",
        tool_context=ctx,
    )
    assert result["status"] == "ok"
    assert ctx.state["rec:demand"]["items"][0]["sku"] == "AC-12"


def test_emit_demand_recommendation_returns_error_on_malformed_item():
    ctx = FakeToolContext({})
    result = emit_demand_recommendation(
        items=[{"sku": "AC-12"}],  # missing required fields
        summary="oops",
        tool_context=ctx,
    )
    assert result["status"] == "error"
    assert "rec:demand" not in ctx.state


def test_emit_procurement_recommendation_returns_error_on_missing_warehouse():
    # Regression guard: a live run crashed the whole `adk run` process when
    # the model omitted a required field on one item. That must come back
    # as a retriable tool error instead of an uncaught exception.
    ctx = FakeToolContext({})
    result = emit_procurement_recommendation(
        items=[
            {
                "sku": "AC-12",
                "supplier": "S-DOM",
                "qty": 10,
                "unit_cost_ars": 100.0,
                "est_cost": 1000.0,
                "lead_time_days": 7,
                # "warehouse" missing on purpose
            }
        ],
        summary="oops",
        tool_context=ctx,
    )
    assert result["status"] == "error"
    assert "rec:procurement" not in ctx.state


def test_emit_action_plan_success_returns_fields_for_write_action_plan_followup():
    # The supervisor's next step (write_action_plan, an MCP tool call) copies
    # situation/purchase_orders/rationale/guardrail_trips straight from this
    # return value rather than reconstructing them — these fields are a
    # public contract, not incidental.
    ctx = FakeToolContext(
        {
            "world": {"situation": "demand_spike", "budget_per_cycle": 500000, "suppliers": []},
            "guardrail_trips": [{"type": "invalid_quantity", "detail": "..."}],
        }
    )
    result = emit_action_plan(
        purchase_orders=[
            {"sku": "AC-12", "supplier": "S-DOM", "qty": 10, "dest_warehouse": "COR", "est_cost": 1000.0}
        ],
        rationale="Covering the AC-12 shortfall at COR.",
        tool_context=ctx,
    )
    assert result["status"] == "ok"
    assert result["situation"] == "demand_spike"
    assert result["guardrail_trips"] == [{"type": "invalid_quantity", "detail": "..."}]
    assert result["action_plan"]["purchase_orders"][0]["sku"] == "AC-12"
    assert result["action_plan"]["rationale"] == "Covering the AC-12 shortfall at COR."
    assert ctx.state["action_plan"] == result["action_plan"]


def test_emit_action_plan_returns_error_on_malformed_order():
    ctx = FakeToolContext({"world": {"budget_per_cycle": 1000, "suppliers": []}})
    result = emit_action_plan(
        purchase_orders=[{"sku": "AC-12", "supplier": "S-DOM"}],  # missing fields
        rationale="oops",
        tool_context=ctx,
    )
    assert result["status"] == "error"
    assert "action_plan" not in ctx.state

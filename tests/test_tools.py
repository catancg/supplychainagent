import pytest

from loader import load_scenario
from tools.demand_tools import forecast_demand, forecast_demand_for_all_skus
from tools.inventory_tools import (
    compute_reorder_point,
    compute_reorder_points_for_all_skus,
    get_inventory_position,
)
from tools.procurement_tools import (
    estimate_landed_cost,
    rank_and_cost_needs,
    rank_suppliers,
)
from tools.world_tools import get_world_snapshot


class FakeToolContext:
    def __init__(self, state: dict):
        self.state = state


@pytest.fixture
def demand_spike_ctx():
    return FakeToolContext({"world": load_scenario("demand_spike")})


@pytest.fixture
def normal_ctx():
    return FakeToolContext({"world": load_scenario("normal")})


def test_forecast_demand_flags_spike(demand_spike_ctx):
    result = forecast_demand("AC-12", demand_spike_ctx)
    assert result["is_spike"] is True
    assert result["spike_ratio"] >= 1.5


def test_forecast_demand_no_spike(normal_ctx):
    result = forecast_demand("AC-12", normal_ctx)
    assert result["is_spike"] is False


def test_get_inventory_position(normal_ctx):
    result = get_inventory_position("AC-12", "CABA", normal_ctx)
    assert result["on_hand"] == 80


def test_get_inventory_position_unknown_warehouse(normal_ctx):
    with pytest.raises(ValueError):
        get_inventory_position("AC-12", "XXX", normal_ctx)


def test_compute_reorder_point_flags_shortfall(demand_spike_ctx):
    result = compute_reorder_point(
        "AC-12", "COR", lead_time_days=7, safety_buffer_days=5, tool_context=demand_spike_ctx
    )
    assert result["below_reorder_point"] is True
    assert result["suggested_order_qty"] > 0


def test_compute_reorder_point_healthy_stock(normal_ctx):
    # CABA holds 40 units at ~4.5/day average — comfortably covers a fast
    # 3-day lead time plus a 2-day buffer (22.5 units needed).
    result = compute_reorder_point(
        "AC-12", "CABA", lead_time_days=3, safety_buffer_days=2, tool_context=normal_ctx
    )
    assert result["below_reorder_point"] is False


def test_rank_suppliers_excludes_unavailable():
    ctx = FakeToolContext({"world": load_scenario("supplier_down")})
    result = rank_suppliers("AC-12", ctx)
    supplier_ids = [s["supplier"] for s in result["suppliers"]]
    assert "S-IMP" not in supplier_ids
    assert "S-DOM" in supplier_ids


def test_rank_suppliers_orders_by_score_descending(normal_ctx):
    result = rank_suppliers("AC-12", normal_ctx)
    scores = [s["score"] for s in result["suppliers"]]
    assert scores == sorted(scores, reverse=True)


def test_rank_suppliers_unknown_sku_returns_empty(normal_ctx):
    result = rank_suppliers("NOPE-99", normal_ctx)
    assert result["suppliers"] == []


def test_estimate_landed_cost_domestic(normal_ctx):
    result = estimate_landed_cost(
        "S-DOM", "AC-12", qty=10, fx_rate_to_ars=1.0, tool_context=normal_ctx
    )
    assert result["total_cost_ars"] == 1000.0


def test_estimate_landed_cost_imported_uses_fx_rate(normal_ctx):
    result = estimate_landed_cost(
        "S-IMP", "AC-12", qty=10, fx_rate_to_ars=130.0, tool_context=normal_ctx
    )
    assert result["total_cost_ars"] == pytest.approx(0.7 * 130.0 * 10)


def test_estimate_landed_cost_unsupported_sku_raises(normal_ctx):
    with pytest.raises(ValueError):
        estimate_landed_cost(
            "S-REG", "AC-12", qty=1, fx_rate_to_ars=1.0, tool_context=normal_ctx
        )


def test_rank_and_cost_needs_returns_empty_when_no_inventory_rec(normal_ctx):
    result = rank_and_cost_needs(fx_rate_usd_to_ars=130.0, tool_context=normal_ctx)
    assert result["needs"] == []


def test_rank_and_cost_needs_costs_every_candidate_per_need():
    ctx = FakeToolContext(
        {
            "world": load_scenario("demand_spike"),
            "rec:inventory": {
                "items": [
                    {"sku": "AC-12", "warehouse": "COR", "suggested_order_qty": 100},
                ],
                "summary": "AC-12 short at COR",
            },
        }
    )
    result = rank_and_cost_needs(fx_rate_usd_to_ars=130.0, tool_context=ctx)
    assert len(result["needs"]) == 1
    need = result["needs"][0]
    assert need["sku"] == "AC-12"
    assert need["warehouse"] == "COR"
    assert need["suggested_order_qty"] == 100
    option_suppliers = {o["supplier"] for o in need["options"]}
    assert option_suppliers == {"S-DOM", "S-IMP", "S-PREM"}
    dom_option = next(o for o in need["options"] if o["supplier"] == "S-DOM")
    assert dom_option["total_cost_ars"] == 10000.0
    imp_option = next(o for o in need["options"] if o["supplier"] == "S-IMP")
    assert imp_option["total_cost_ars"] == pytest.approx(0.7 * 130.0 * 100)


def test_rank_and_cost_needs_excludes_unavailable_supplier():
    ctx = FakeToolContext(
        {
            "world": load_scenario("supplier_down"),
            "rec:inventory": {
                "items": [
                    {"sku": "AC-12", "warehouse": "COR", "suggested_order_qty": 50},
                ],
                "summary": "AC-12 short at COR",
            },
        }
    )
    result = rank_and_cost_needs(fx_rate_usd_to_ars=130.0, tool_context=ctx)
    option_suppliers = {o["supplier"] for o in result["needs"][0]["options"]}
    assert "S-IMP" not in option_suppliers


def test_forecast_demand_for_all_skus_covers_every_sku(normal_ctx):
    world = normal_ctx.state["world"]
    result = forecast_demand_for_all_skus(normal_ctx)
    forecasted_ids = {f["sku"] for f in result["forecasts"]}
    assert forecasted_ids == {s["id"] for s in world["skus"]}


def test_forecast_demand_for_all_skus_matches_single_sku(demand_spike_ctx):
    batch = forecast_demand_for_all_skus(demand_spike_ctx)
    single = forecast_demand("AC-12", demand_spike_ctx)
    ac12 = next(f for f in batch["forecasts"] if f["sku"] == "AC-12")
    assert ac12 == single


def test_compute_reorder_points_for_all_skus_only_returns_shortfalls(demand_spike_ctx):
    # demand_spike fixture: only AC-12 (COR/MDZ, and CABA too under a wide
    # enough buffer) should be below reorder point — everything else is
    # comfortably stocked and must NOT show up as a need.
    result = compute_reorder_points_for_all_skus(
        major_appliance_safety_buffer_days=5,
        small_item_safety_buffer_days=3,
        lead_time_days=7,
        tool_context=demand_spike_ctx,
    )
    needed_skus = {n["sku"] for n in result["needs"]}
    assert needed_skus == {"AC-12"}


def test_compute_reorder_points_for_all_skus_applies_category_buffer(normal_ctx):
    # A wide enough major-appliance buffer with a tiny small-item buffer
    # should surface major_appliance SKUs as needs while small_item SKUs
    # (comfortably stocked relative to their own tiny buffer) stay out.
    result = compute_reorder_points_for_all_skus(
        major_appliance_safety_buffer_days=30,
        small_item_safety_buffer_days=0,
        lead_time_days=0,
        tool_context=normal_ctx,
    )
    needed_skus = {n["sku"] for n in result["needs"]}
    assert needed_skus.issubset({"AC-12", "RF-21", "MW-14", "TV-33", "WM-07"})
    assert "SP-25" not in needed_skus


def test_get_world_snapshot_lists_real_ids(normal_ctx):
    # Regression guard: agents must be able to discover valid ids from the
    # world instead of guessing — a hallucinated SKU id caused a live 500.
    snapshot = get_world_snapshot(normal_ctx)
    sku_ids = {s["id"] for s in snapshot["skus"]}
    assert "AC-12" in sku_ids
    assert "TTC-32" not in sku_ids
    assert snapshot["warehouses"] == ["CABA", "COR", "MDZ"]
    assert "S-DOM" in {s["id"] for s in snapshot["suppliers"]}
    assert snapshot["budget_per_cycle"] == 500000

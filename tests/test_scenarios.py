"""Validates that the new scenario fixtures actually trigger the condition
they're designed to test, using the real tool functions the agents call —
not a re-derivation of the arithmetic. We got burned once already by fixture
numbers that looked right but didn't actually cross the reorder-point
threshold; these tests exist so that mistake can't slip in silently again.
"""

import pytest

from loader import load_scenario
from tools.demand_tools import forecast_demand, forecast_demand_for_all_skus
from tools.inventory_tools import compute_reorder_points_for_all_skus
from tools.procurement_tools import rank_suppliers

MAJOR_BUFFER = 5
SMALL_BUFFER = 3
LEAD_TIME = 7

ALL_SKUS = [
    "AC-12", "FN-05", "HT-09", "RF-21", "MW-14",
    "TV-33", "WM-07", "BL-02", "VC-18", "SP-25",
]


class FakeToolContext:
    def __init__(self, state: dict):
        self.state = state


def _needs_for(scenario: str) -> list[dict]:
    ctx = FakeToolContext({"world": load_scenario(scenario)})
    result = compute_reorder_points_for_all_skus(
        major_appliance_safety_buffer_days=MAJOR_BUFFER,
        small_item_safety_buffer_days=SMALL_BUFFER,
        lead_time_days=LEAD_TIME,
        tool_context=ctx,
    )
    return result["needs"]


def test_normal_has_no_needs():
    assert _needs_for("normal") == []


def test_healthy_tight_margins_has_no_needs():
    assert _needs_for("healthy_tight_margins") == []


def test_demand_spike_ac12_is_flagged_and_needed():
    ctx = FakeToolContext({"world": load_scenario("demand_spike")})
    forecast = forecast_demand("AC-12", ctx)
    assert forecast["is_spike"] is True

    needs = {n["sku"] for n in _needs_for("demand_spike")}
    assert "AC-12" in needs


def test_demand_spike_small_item_sp25_is_flagged_and_needed():
    ctx = FakeToolContext({"world": load_scenario("demand_spike_small_item")})
    forecast = forecast_demand("SP-25", ctx)
    assert forecast["is_spike"] is True

    needs = {n["sku"] for n in _needs_for("demand_spike_small_item")}
    assert "SP-25" in needs


def test_supplier_down_all_for_sku_has_zero_suppliers_for_ac12():
    ctx = FakeToolContext({"world": load_scenario("supplier_down_all_for_sku")})
    result = rank_suppliers("AC-12", ctx)
    assert result["suppliers"] == []
    # and it genuinely needs replenishment (otherwise the "no suppliers" fact is moot)
    needs = {n["sku"] for n in _needs_for("supplier_down_all_for_sku")}
    assert "AC-12" in needs


def test_supplier_down_small_item_has_zero_suppliers_for_fn05():
    ctx = FakeToolContext({"world": load_scenario("supplier_down_small_item")})
    result = rank_suppliers("FN-05", ctx)
    assert result["suppliers"] == []
    needs = {n["sku"] for n in _needs_for("supplier_down_small_item")}
    assert "FN-05" in needs


def test_budget_tight_partial_budget_is_binding():
    world = load_scenario("budget_tight_partial")
    assert world["budget_per_cycle"] == 5000
    needs = {n["sku"] for n in _needs_for("budget_tight_partial")}
    assert "AC-12" in needs
    # Confirm the constraint is genuinely binding: even the cheapest single
    # warehouse's shortfall alone costs more than the whole budget.
    ctx = FakeToolContext({"world": world})
    result = rank_suppliers("AC-12", ctx)
    cheapest_unit_cost = min(s["unit_cost"] for s in result["suppliers"] if s["currency"] == "ARS")
    cheapest_need = min(
        n["suggested_order_qty"] for n in _needs_for("budget_tight_partial") if n["sku"] == "AC-12"
    )
    assert cheapest_unit_cost * cheapest_need > world["budget_per_cycle"]


def test_spike_and_supplier_down_same_sku():
    ctx = FakeToolContext({"world": load_scenario("spike_and_supplier_down_same_sku")})
    assert forecast_demand("AC-12", ctx)["is_spike"] is True
    result = rank_suppliers("AC-12", ctx)
    supplier_ids = {s["supplier"] for s in result["suppliers"]}
    assert "S-IMP" not in supplier_ids
    assert supplier_ids  # S-DOM / S-PREM still available


def test_multi_sku_shortage_broad_targets_exactly_three_skus():
    needs = {n["sku"] for n in _needs_for("multi_sku_shortage_broad")}
    assert needs == {"RF-21", "VC-18", "HT-09"}


def test_warehouse_single_short_only_cor_is_below_reorder_point():
    needs = [n for n in _needs_for("warehouse_single_short") if n["sku"] == "AC-12"]
    warehouses = {n["warehouse"] for n in needs}
    assert warehouses == {"COR"}


def test_zero_demand_edge_case_does_not_crash_and_needs_nothing():
    ctx = FakeToolContext({"world": load_scenario("zero_demand_edge_case")})
    forecast = forecast_demand("HT-09", ctx)  # must not raise ZeroDivisionError
    assert forecast["spike_ratio"] == 0.0
    assert forecast["is_spike"] is False

    all_forecasts = forecast_demand_for_all_skus(ctx)  # sweep must also not crash
    assert {f["sku"] for f in all_forecasts["forecasts"]} == set(ALL_SKUS)

    needs = {n["sku"] for n in _needs_for("zero_demand_edge_case")}
    assert "HT-09" not in needs

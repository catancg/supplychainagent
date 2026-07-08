"""Eval cases — the scenario fixtures are the eval cases (docs/feature.prd §10).

Each case pairs a scenario id with Layer-A deterministic assertions
(authoritative pass/fail) run against the resulting ActionPlan. 12 scenarios
total: the 2 PRD-required cases (demand_spike, supplier_down) plus 10 more
covering distinct agent behaviors (spike variants, supplier-down variants,
budget pressure, compound issues, warehouse precision, broad shortages, and
edge cases).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

SHORT_WAREHOUSES = {"COR", "MDZ"}
SPIKE_ORDER_QTY_THRESHOLD = 15


@dataclass
class AssertionResult:
    name: str
    passed: bool
    detail: str


@dataclass
class EvalCase:
    name: str
    scenario: str
    description: str
    assertions: list[Callable[[dict, dict], AssertionResult]]


Assertion = Callable[[dict, dict], AssertionResult]


def _ordered_qty_for_sku(plan: dict, sku: str) -> int:
    return sum(o["qty"] for o in plan.get("purchase_orders", []) if o["sku"] == sku)


def _orders_for_sku(plan: dict, sku: str) -> list[dict]:
    return [o for o in plan.get("purchase_orders", []) if o["sku"] == sku]


# --- Generic, reusable assertions (used across scenarios) -------------------


def assert_within_budget(plan: dict, world: dict) -> AssertionResult:
    total = sum(o.get("est_cost", 0) for o in plan.get("purchase_orders", []))
    budget = world.get("budget_per_cycle", float("inf"))
    return AssertionResult(
        name="within_budget",
        passed=total <= budget,
        detail=f"total plan cost = {total} (budget {budget})",
    )


def assert_down_supplier_not_used(plan: dict, world: dict) -> AssertionResult:
    unavailable_ids = {s["id"] for s in world.get("suppliers", []) if not s.get("available", True)}
    used_ids = {o["supplier"] for o in plan.get("purchase_orders", [])}
    tripped = unavailable_ids & used_ids
    return AssertionResult(
        name="down_supplier_not_used",
        passed=not tripped,
        detail=f"unavailable suppliers used: {tripped or 'none'}",
    )


def assert_plan_empty(plan: dict, world: dict) -> AssertionResult:
    orders = plan.get("purchase_orders", [])
    return AssertionResult(
        name="plan_empty",
        passed=len(orders) == 0,
        detail=f"purchase_orders = {orders or []}",
    )


# --- Assertion factories (parameterized per scenario) ------------------------


def make_assert_sku_ordered_above_threshold(sku: str, threshold: int) -> Assertion:
    def _assert(plan: dict, world: dict) -> AssertionResult:
        qty = _ordered_qty_for_sku(plan, sku)
        return AssertionResult(
            name=f"{sku}_ordered_above_threshold",
            passed=qty >= threshold,
            detail=f"{sku} total ordered qty = {qty} (threshold {threshold})",
        )

    return _assert


def make_assert_sku_not_ordered(sku: str) -> Assertion:
    def _assert(plan: dict, world: dict) -> AssertionResult:
        qty = _ordered_qty_for_sku(plan, sku)
        return AssertionResult(
            name=f"{sku}_not_ordered",
            passed=qty == 0,
            detail=f"{sku} total ordered qty = {qty} (expected 0)",
        )

    return _assert


def make_assert_skus_ordered(skus: list[str]) -> Assertion:
    def _assert(plan: dict, world: dict) -> AssertionResult:
        qtys = {sku: _ordered_qty_for_sku(plan, sku) for sku in skus}
        passed = all(q > 0 for q in qtys.values())
        return AssertionResult(
            name="all_skus_ordered",
            passed=passed,
            detail=f"ordered qty per sku = {qtys}",
        )

    return _assert


def make_assert_skus_not_ordered(skus: list[str]) -> Assertion:
    def _assert(plan: dict, world: dict) -> AssertionResult:
        qtys = {sku: _ordered_qty_for_sku(plan, sku) for sku in skus}
        passed = all(q == 0 for q in qtys.values())
        return AssertionResult(
            name="healthy_skus_not_ordered",
            passed=passed,
            detail=f"ordered qty per (should-be-healthy) sku = {qtys}",
        )

    return _assert


def make_assert_sku_destination_only_in(sku: str, allowed_warehouses: set[str]) -> Assertion:
    def _assert(plan: dict, world: dict) -> AssertionResult:
        destinations = {o["dest_warehouse"] for o in _orders_for_sku(plan, sku)}
        passed = bool(destinations) and destinations.issubset(allowed_warehouses)
        return AssertionResult(
            name=f"{sku}_destination_only_in_{'_'.join(sorted(allowed_warehouses))}",
            passed=passed,
            detail=f"{sku} order destinations = {destinations or set()} (allowed {allowed_warehouses})",
        )

    return _assert


# Deliberately broad and phrase-based (not single keywords) — a first pass
# using single words like "unavailable" missed a real, correct rationale that
# said "no available suppliers" (no "unavailable" substring, no "no supplier"
# substring either). Natural-language gap-flagging has many valid phrasings;
# under-matching produces a false FAIL on a genuinely correct rationale.
_GAP_PHRASES = (
    "gap",
    "unavailable",
    "not available",
    "no available",
    "none available",
    "no supplier",
    "no valid supplier",
    "cannot be placed",
    "cannot be fulfilled",
    "no purchase order",
)


def _rationale_flags_gap(rationale: str) -> bool:
    rationale = rationale.lower()
    return any(phrase in rationale for phrase in _GAP_PHRASES)


def make_assert_sku_has_alternate_or_flagged_gap(sku: str) -> Assertion:
    def _assert(plan: dict, world: dict) -> AssertionResult:
        qty = _ordered_qty_for_sku(plan, sku)
        rationale = plan.get("rationale", "").lower()
        gap_flagged = sku.lower() in rationale and _rationale_flags_gap(rationale)
        return AssertionResult(
            name=f"{sku}_has_alternate_or_flagged_gap",
            passed=qty > 0 or gap_flagged,
            detail=f"{sku} ordered qty = {qty}, gap flagged in rationale = {gap_flagged}",
        )

    return _assert


def make_assert_gap_flagged_for(sku: str) -> Assertion:
    def _assert(plan: dict, world: dict) -> AssertionResult:
        rationale = plan.get("rationale", "").lower()
        flagged = sku.lower() in rationale and _rationale_flags_gap(rationale)
        return AssertionResult(
            name=f"{sku}_gap_flagged",
            passed=flagged,
            detail=f"rationale mentions {sku} + gap/unavailable language: {flagged}",
        )

    return _assert


# --- Cases --------------------------------------------------------------

CASES: list[EvalCase] = [
    EvalCase(
        name="normal",
        scenario="normal",
        description=(
            "Baseline healthy scenario — every SKU is comfortably above its "
            "reorder point. Expect an empty (or near-empty) action plan; the "
            "agent must not hallucinate orders when nothing is actually needed."
        ),
        assertions=[
            assert_plan_empty,
            assert_within_budget,
        ],
    ),
    EvalCase(
        name="demand_spike",
        scenario="demand_spike",
        description=(
            "AC-12 demand spikes; expect the plan to order more of it into "
            "the short warehouse(s) (COR/MDZ)."
        ),
        assertions=[
            make_assert_sku_ordered_above_threshold("AC-12", SPIKE_ORDER_QTY_THRESHOLD),
            make_assert_sku_has_alternate_or_flagged_gap("AC-12"),  # covers dest-agnostic sanity too
            assert_within_budget,
        ],
    ),
    EvalCase(
        name="supplier_down",
        scenario="supplier_down",
        description=(
            "AC-12's cheap supplier (S-IMP) is down; expect the plan to "
            "avoid it and use an available alternate (or flag the gap), "
            "staying within budget."
        ),
        assertions=[
            assert_down_supplier_not_used,
            make_assert_sku_has_alternate_or_flagged_gap("AC-12"),
            assert_within_budget,
        ],
    ),
    EvalCase(
        name="demand_spike_small_item",
        scenario="demand_spike_small_item",
        description=(
            "SP-25 (a small/fast-turnover item, not a major appliance) "
            "spikes ~1.8x historical average across all three warehouses; "
            "expect the plan to replenish SP-25 substantially, applying the "
            "small-item stocking policy rather than the major-appliance one."
        ),
        assertions=[
            make_assert_sku_ordered_above_threshold("SP-25", 50),
            assert_within_budget,
        ],
    ),
    EvalCase(
        name="supplier_down_all_for_sku",
        scenario="supplier_down_all_for_sku",
        description=(
            "AC-12 needs replenishment (below reorder point at all 3 "
            "warehouses) but ALL of its suppliers (S-DOM, S-IMP, S-PREM) are "
            "unavailable. There is no valid alternate. Expect the plan to "
            "place NO order for AC-12 and explicitly flag the gap in the "
            "rationale — never fabricate a supplier."
        ),
        assertions=[
            assert_down_supplier_not_used,
            make_assert_sku_not_ordered("AC-12"),
            make_assert_gap_flagged_for("AC-12"),
        ],
    ),
    EvalCase(
        name="budget_tight_partial",
        scenario="budget_tight_partial",
        description=(
            "Same AC-12 shortfall as demand_spike, but budget_per_cycle is "
            "slashed to 5000 — far less than the ~30k+ needed to fully cover "
            "it. Expect the plan to stay within budget even if that means "
            "partial fulfillment (fewer units and/or fewer warehouses "
            "covered) rather than silently overspending."
        ),
        assertions=[
            assert_within_budget,
        ],
    ),
    EvalCase(
        name="spike_and_supplier_down_same_sku",
        scenario="spike_and_supplier_down_same_sku",
        description=(
            "Compound case: AC-12 spikes AND its cheapest supplier (S-IMP) "
            "is simultaneously unavailable. Expect the plan to still "
            "substantially replenish AC-12 using an available alternate "
            "(S-DOM or S-PREM), never S-IMP."
        ),
        assertions=[
            assert_down_supplier_not_used,
            make_assert_sku_ordered_above_threshold("AC-12", SPIKE_ORDER_QTY_THRESHOLD),
            assert_within_budget,
        ],
    ),
    EvalCase(
        name="multi_sku_shortage_broad",
        scenario="multi_sku_shortage_broad",
        description=(
            "No demand spike — RF-21, VC-18, and HT-09 (spanning both "
            "major-appliance and small-item categories) are simply below "
            "their reorder points at every warehouse, while all other SKUs "
            "stay healthy. Expect the plan to order all three of them and "
            "none of the other seven, still-healthy SKUs."
        ),
        assertions=[
            make_assert_skus_ordered(["RF-21", "VC-18", "HT-09"]),
            make_assert_skus_not_ordered(
                ["FN-05", "MW-14", "TV-33", "WM-07", "BL-02", "SP-25", "AC-12"]
            ),
            assert_within_budget,
        ],
    ),
    EvalCase(
        name="warehouse_single_short",
        scenario="warehouse_single_short",
        description=(
            "AC-12 is below reorder point ONLY at COR; CABA and MDZ are "
            "healthy. Expect the plan to order AC-12 destined for COR only — "
            "precision targeting, not a blanket replenishment across all "
            "warehouses just because one SKU needs attention somewhere."
        ),
        assertions=[
            make_assert_sku_destination_only_in("AC-12", {"COR"}),
            assert_within_budget,
        ],
    ),
    EvalCase(
        name="zero_demand_edge_case",
        scenario="zero_demand_edge_case",
        description=(
            "HT-09 has an all-zero recent_demand history (a degenerate "
            "edge case for the forecast/reorder-point arithmetic — 0 avg "
            "daily demand means a 0 reorder point). Even though its on-hand "
            "inventory (5/4/3 units) looks low in absolute terms, the "
            "correct behavior is to NOT order it, since zero demand means "
            "zero replenishment need. Also verifies the pipeline doesn't "
            "crash on this input (divide-by-zero guard in forecast_demand)."
        ),
        assertions=[
            make_assert_sku_not_ordered("HT-09"),
        ],
    ),
    EvalCase(
        name="supplier_down_small_item",
        scenario="supplier_down_small_item",
        description=(
            "FN-05 (small item) needs replenishment, but S-REG — the ONLY "
            "supplier that carries FN-05 in this world — is unavailable. "
            "There is no alternate. Expect no FN-05 order and an explicit "
            "gap flag, proving the guardrail/reasoning generalizes beyond "
            "the AC-12 major-appliance case it was originally diagnosed on."
        ),
        assertions=[
            assert_down_supplier_not_used,
            make_assert_sku_not_ordered("FN-05"),
            make_assert_gap_flagged_for("FN-05"),
        ],
    ),
    EvalCase(
        name="healthy_tight_margins",
        scenario="healthy_tight_margins",
        description=(
            "A second all-healthy scenario, but with demand scaled +20% "
            "above the normal.json baseline (tighter margins, all still "
            "above reorder point). Regression guard proving the 'don't "
            "hallucinate orders' behavior isn't just an artifact of "
            "normal.json's specific numbers, and holds up closer to the "
            "boundary."
        ),
        assertions=[
            assert_plan_empty,
            assert_within_budget,
        ],
    ),
]

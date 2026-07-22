"""The generic rule engine — evaluates GuardrailRules against a plan or
text. No ADK dependency, no domain-specific dependency beyond reading
generic dict shapes (purchase_orders, suppliers, budget_per_cycle) —
reusable beyond this project. See docs/phase1-guardrail-templates.prd.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import yaml

from guardrails.schemas import GuardrailRule, GuardrailTemplate, GuardrailTrip

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_REDACTION = "[neutralized: instruction-like content removed]"

# Per-order rules drop individual bad orders; whole-plan rules evaluate the
# aggregate. Execution always runs per-order rules first, then whole-plan
# rules — regardless of the order rules are listed in a template — because
# budget must be checked against the final, already-clamped set of orders,
# not an intermediate one. Rule TYPE determines execution phase, not list
# position.
_PER_ORDER_RULE_TYPES = {"supplier_availability", "quantity_range"}
_WHOLE_PLAN_RULE_TYPES = {"budget_cap"}


def load_template(path: Path) -> GuardrailTemplate:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return GuardrailTemplate.model_validate(data)


def _check_budget_cap(
    rule: GuardrailRule, orders: list[dict], world: dict
) -> tuple[list[dict], list[GuardrailTrip]]:
    total_cost = sum(o.get("est_cost", 0) for o in orders)
    budget = world.get("budget_per_cycle", float("inf"))
    if total_cost > budget:
        return orders, [
            GuardrailTrip(
                type="over_budget",
                detail=f"total cost {total_cost} exceeds budget_per_cycle {budget}",
            )
        ]
    return orders, []


def _check_supplier_availability(
    rule: GuardrailRule, orders: list[dict], world: dict
) -> tuple[list[dict], list[GuardrailTrip]]:
    suppliers_by_id = {s["id"]: s for s in world.get("suppliers", [])}
    kept: list[dict] = []
    trips: list[GuardrailTrip] = []
    for order in orders:
        supplier_id = order.get("supplier")
        supplier = suppliers_by_id.get(supplier_id)
        if supplier is None or not supplier.get("available", True):
            trips.append(
                GuardrailTrip(
                    type="unavailable_supplier",
                    sku=order.get("sku", ""),
                    supplier=supplier_id or "",
                    detail=f"supplier '{supplier_id}' is not available",
                )
            )
            continue
        kept.append(order)
    return kept, trips


def _check_quantity_range(
    rule: GuardrailRule, orders: list[dict], world: dict
) -> tuple[list[dict], list[GuardrailTrip]]:
    min_qty = rule.params.get("min", 1)
    max_qty = rule.params.get("max", 100_000)
    kept: list[dict] = []
    trips: list[GuardrailTrip] = []
    for order in orders:
        qty = order.get("qty", 0)
        if not isinstance(qty, (int, float)) or qty < min_qty or qty > max_qty:
            trips.append(
                GuardrailTrip(
                    type="invalid_quantity",
                    sku=order.get("sku", ""),
                    supplier=order.get("supplier") or "",
                    detail=f"qty {qty!r} outside allowed range [{min_qty}, {max_qty}]",
                )
            )
            continue
        kept.append(order)
    return kept, trips


_PLAN_RULE_HANDLERS: dict[
    str, Callable[[GuardrailRule, list[dict], dict], tuple[list[dict], list[GuardrailTrip]]]
] = {
    "budget_cap": _check_budget_cap,
    "supplier_availability": _check_supplier_availability,
    "quantity_range": _check_quantity_range,
}


def evaluate_plan_rules(
    rules: list[GuardrailRule], plan: dict, world: dict
) -> tuple[dict, list[GuardrailTrip]]:
    """Returns (cleaned_plan, trips) — same contract as the original
    validate_action_plan.
    """
    trips: list[GuardrailTrip] = []
    orders = list(plan.get("purchase_orders", []))

    for phase in (_PER_ORDER_RULE_TYPES, _WHOLE_PLAN_RULE_TYPES):
        for rule in rules:
            if rule.type not in phase:
                continue
            handler = _PLAN_RULE_HANDLERS[rule.type]
            orders, rule_trips = handler(rule, orders, world)
            trips.extend(rule_trips)

    cleaned_plan = dict(plan)
    cleaned_plan["purchase_orders"] = orders
    return cleaned_plan, trips


def neutralize_text(rules: list[GuardrailRule], text: str) -> str:
    """Applies every injection_pattern rule's regexes to text — same
    contract as the original neutralize_injection.
    """
    cleaned = text
    for rule in rules:
        if rule.type != "injection_pattern":
            continue
        for pattern_str in rule.params.get("patterns", []):
            cleaned = re.sub(pattern_str, _REDACTION, cleaned, flags=re.IGNORECASE)
    return cleaned


def sanitize_strings(value: Any, rules: list[GuardrailRule]) -> Any:
    """Recursively applies neutralize_text to every string in value (walking
    dicts/lists), leaving other types untouched and the overall shape
    unchanged. Used to sanitize data at the point it enters the system
    (e.g. a loaded scenario) rather than wrapping every tool response that
    reads it.
    """
    if isinstance(value, str):
        return neutralize_text(rules, value)
    if isinstance(value, list):
        return [sanitize_strings(v, rules) for v in value]
    if isinstance(value, dict):
        return {k: sanitize_strings(v, rules) for k, v in value.items()}
    return value

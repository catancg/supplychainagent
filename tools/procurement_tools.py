"""Deterministic procurement tools. Pure arithmetic — the procurement agent
decides which supplier to pick (reasoning over cost vs. lead time vs.
reliability, and budget), consulting the FX-rate MCP tool and RAG supplier
policy. See docs/feature.prd §6 and §8.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from tools._world import get_supplier, get_world


def rank_suppliers(sku: str, tool_context: ToolContext) -> dict:
    """Ranks available suppliers for a SKU by weighted cost, lead time, reliability.

    The cost score uses each supplier's raw unit_cost — currencies are NOT
    converted here. Call estimate_landed_cost (with an FX rate for non-ARS
    suppliers) for a precise, apples-to-apples cost before deciding.

    Args:
        sku: SKU id, e.g. "AC-12".
    """
    world = get_world(tool_context)
    candidates = [
        s for s in world["suppliers"] if sku in s["skus"] and s.get("available", True)
    ]
    if not candidates:
        return {"sku": sku, "suppliers": []}

    costs = [s["unit_cost"] for s in candidates]
    lead_times = [s["lead_time_days"] for s in candidates]
    min_cost, max_cost = min(costs), max(costs)
    min_lead, max_lead = min(lead_times), max(lead_times)

    def _norm(value: float, lo: float, hi: float) -> float:
        return (value - lo) / (hi - lo) if hi > lo else 0.0

    ranked = []
    for supplier in candidates:
        cost_score = 1 - _norm(supplier["unit_cost"], min_cost, max_cost)
        lead_score = 1 - _norm(supplier["lead_time_days"], min_lead, max_lead)
        reliability_score = supplier["reliability"]
        weighted_score = round(
            0.45 * cost_score + 0.25 * lead_score + 0.30 * reliability_score, 4
        )
        ranked.append(
            {
                "supplier": supplier["id"],
                "unit_cost": supplier["unit_cost"],
                "currency": supplier["currency"],
                "lead_time_days": supplier["lead_time_days"],
                "reliability": supplier["reliability"],
                "score": weighted_score,
            }
        )
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return {"sku": sku, "suppliers": ranked}


def estimate_landed_cost(
    supplier: str,
    sku: str,
    qty: float,
    fx_rate_to_ars: float,
    tool_context: ToolContext,
) -> dict:
    """Computes landed cost in ARS for an order quantity from a supplier.

    Args:
        supplier: supplier id, e.g. "S-DOM".
        sku: SKU id, e.g. "AC-12".
        qty: order quantity in units.
        fx_rate_to_ars: ARS per unit of the supplier's currency. Use 1.0 for
            ARS suppliers; for USD suppliers, fetch the rate from the
            get_fx_rate MCP tool first.
    """
    world = get_world(tool_context)
    supplier_record = get_supplier(world, supplier)
    if sku not in supplier_record["skus"]:
        raise ValueError(f"Supplier '{supplier}' does not offer SKU '{sku}'")

    unit_cost_ars = supplier_record["unit_cost"] * fx_rate_to_ars
    total_cost_ars = round(unit_cost_ars * qty, 2)

    return {
        "supplier": supplier,
        "sku": sku,
        "qty": qty,
        "currency": supplier_record["currency"],
        "unit_cost_original": supplier_record["unit_cost"],
        "fx_rate_to_ars": fx_rate_to_ars,
        "unit_cost_ars": round(unit_cost_ars, 4),
        "total_cost_ars": total_cost_ars,
    }


def rank_and_cost_needs(fx_rate_usd_to_ars: float, tool_context: ToolContext) -> dict:
    """Ranks and precisely costs every candidate supplier for every inventory need, in one call.

    Reads state["rec:inventory"] (the inventory specialist's needs list)
    directly — no need to call read_recommendations, rank_suppliers, or
    estimate_landed_cost separately first. For each need, returns every
    available supplier with its ranking score and precise landed cost in ARS
    (ARS suppliers use fx_rate 1.0 automatically; USD suppliers use
    fx_rate_usd_to_ars). Fetch fx_rate_usd_to_ars from the get_fx_rate MCP
    tool once, regardless of how many needs there are.

    Args:
        fx_rate_usd_to_ars: ARS per 1 USD, from the get_fx_rate MCP tool.
    """
    inventory_rec = tool_context.state.get("rec:inventory") or {}
    needs = inventory_rec.get("items", [])
    if not needs:
        return {"needs": []}

    results = []
    for need in needs:
        sku = need["sku"]
        qty = need.get("suggested_order_qty", 0)
        ranked = rank_suppliers(sku, tool_context)["suppliers"]
        options = []
        for candidate in ranked:
            fx_rate = 1.0 if candidate["currency"] == "ARS" else fx_rate_usd_to_ars
            cost = estimate_landed_cost(
                candidate["supplier"], sku, qty, fx_rate, tool_context
            )
            options.append({**candidate, **cost})
        results.append(
            {
                "sku": sku,
                "warehouse": need["warehouse"],
                "suggested_order_qty": qty,
                "options": options,
            }
        )
    return {"needs": results}

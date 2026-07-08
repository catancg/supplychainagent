"""Deterministic inventory-position tools. Pure arithmetic — the inventory
agent decides how to size lead time / safety buffer (informed by RAG stocking
policy) and interprets the results. See docs/feature.prd §6.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from tools._world import get_sku, get_world


def get_inventory_position(sku: str, warehouse: str, tool_context: ToolContext) -> dict:
    """Returns current on-hand inventory for a SKU at a specific warehouse.

    Args:
        sku: SKU id, e.g. "AC-12".
        warehouse: warehouse id, e.g. "CABA".
    """
    world = get_world(tool_context)
    record = get_sku(world, sku)
    if warehouse not in record["inventory"]:
        raise ValueError(f"No inventory record for SKU '{sku}' at warehouse '{warehouse}'")
    return {"sku": sku, "warehouse": warehouse, "on_hand": record["inventory"][warehouse]}


def _reorder_point_for(record: dict, warehouse: str, lead_time_days: float, safety_buffer_days: float) -> dict:
    history = record["recent_demand"]
    avg_daily_demand = sum(history) / len(history)
    on_hand = record["inventory"][warehouse]
    reorder_point = avg_daily_demand * (lead_time_days + safety_buffer_days)
    suggested_order_qty = max(0, round(reorder_point - on_hand))

    return {
        "sku": record["id"],
        "warehouse": warehouse,
        "on_hand": on_hand,
        "avg_daily_demand": round(avg_daily_demand, 2),
        "reorder_point": round(reorder_point, 2),
        "below_reorder_point": on_hand < reorder_point,
        "suggested_order_qty": suggested_order_qty,
    }


def compute_reorder_point(
    sku: str,
    warehouse: str,
    lead_time_days: float,
    safety_buffer_days: float,
    tool_context: ToolContext,
) -> dict:
    """Computes the reorder point and suggested order quantity for a SKU/warehouse.

    reorder_point = avg_daily_demand * (lead_time_days + safety_buffer_days).
    Pass lead_time_days from the candidate supplier and safety_buffer_days from
    the stocking policy (search_policy) for the SKU's category.

    Args:
        sku: SKU id, e.g. "AC-12".
        warehouse: warehouse id, e.g. "CABA".
        lead_time_days: expected replenishment lead time in days.
        safety_buffer_days: extra days of demand to hold as safety stock.
    """
    world = get_world(tool_context)
    record = get_sku(world, sku)
    if warehouse not in record["inventory"]:
        raise ValueError(f"No inventory record for SKU '{sku}' at warehouse '{warehouse}'")
    return _reorder_point_for(record, warehouse, lead_time_days, safety_buffer_days)


def compute_reorder_points_for_all_skus(
    major_appliance_safety_buffer_days: float,
    small_item_safety_buffer_days: float,
    lead_time_days: float,
    tool_context: ToolContext,
) -> dict:
    """Computes reorder points for every SKU/warehouse pair in one sweep.

    Applies major_appliance_safety_buffer_days to SKUs whose category (from
    get_world_snapshot) is "major_appliance", and small_item_safety_buffer_days
    to SKUs categorized "small_item" — pull both from the stocking policy via
    search_policy first. Use lead_time_days=7 unless policy suggests otherwise.
    One call instead of one compute_reorder_point call per SKU/warehouse pair.

    Args:
        major_appliance_safety_buffer_days: safety buffer for major appliances.
        small_item_safety_buffer_days: safety buffer for small/fast-turnover items.
        lead_time_days: expected replenishment lead time in days, applied to all SKUs.
    """
    world = get_world(tool_context)
    needs = []
    for record in world.get("skus", []):
        buffer_days = (
            major_appliance_safety_buffer_days
            if record.get("category") == "major_appliance"
            else small_item_safety_buffer_days
        )
        for warehouse in record["inventory"]:
            result = _reorder_point_for(record, warehouse, lead_time_days, buffer_days)
            if result["below_reorder_point"]:
                needs.append(result)
    return {"needs": needs}

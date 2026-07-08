"""Shared scenario-lookup helpers used by the deterministic tools.

Not a tool itself — just the tiny bit of repeated dict-navigation the tools
in demand_tools.py / inventory_tools.py / procurement_tools.py all need.
"""

from __future__ import annotations

from typing import Any


def get_world(tool_context: Any) -> dict:
    world = tool_context.state.get("world")
    if world is None:
        raise ValueError(
            "No scenario loaded into state['world']. Load one first "
            "(see loader.load_scenario_into_state)."
        )
    return world


def get_sku(world: dict, sku_id: str) -> dict:
    for sku in world["skus"]:
        if sku["id"] == sku_id:
            return sku
    raise ValueError(f"Unknown SKU '{sku_id}'")


def get_supplier(world: dict, supplier_id: str) -> dict:
    for supplier in world["suppliers"]:
        if supplier["id"] == supplier_id:
            return supplier
    raise ValueError(f"Unknown supplier '{supplier_id}'")

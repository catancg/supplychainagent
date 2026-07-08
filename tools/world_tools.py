"""get_world_snapshot — lets an agent discover what's actually in the loaded
scenario (valid SKU/warehouse/supplier ids) before calling any other tool.
Every other tool takes an id as an argument; without this, an agent has no
way to know which ids are real and can hallucinate one. See docs/feature.prd §6.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from tools._world import get_world


def get_world_snapshot(tool_context: ToolContext) -> dict:
    """Returns the current scenario: situation, SKU/warehouse/supplier ids, budget.

    Call this first, before any other tool. Only ever use SKU, warehouse, and
    supplier ids that appear in this result — never guess or invent one.
    """
    world = get_world(tool_context)
    return {
        "situation": world.get("situation"),
        "warehouses": [w["id"] for w in world.get("warehouses", [])],
        "skus": [
            {"id": s["id"], "name": s.get("name"), "category": s.get("category")}
            for s in world.get("skus", [])
        ],
        "suppliers": [
            {
                "id": s["id"],
                "skus": s["skus"],
                "currency": s["currency"],
                "available": s.get("available", True),
            }
            for s in world.get("suppliers", [])
        ],
        "budget_per_cycle": world.get("budget_per_cycle"),
    }

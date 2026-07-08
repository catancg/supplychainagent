"""emit_recommendation tools — the state-writing side of the blackboard
pattern (docs/feature.prd §4). Each specialist ends its turn by calling its
domain's emit tool, which validates against the Pydantic schema and writes
state["rec:<domain>"]. (output_schema isn't used here since it would disable
tool use — this emit-to-state tool is the documented workaround.)
"""

from __future__ import annotations

from typing import Any

import pydantic
from google.adk.tools import ToolContext

from agents.schemas import (
    DemandOutlook,
    DemandRecommendation,
    InventoryNeed,
    InventoryRecommendation,
    ProcurementChoice,
    ProcurementRecommendation,
)


def _emit_recommendation(
    model_cls: type[pydantic.BaseModel],
    state_key: str,
    items: list[Any],
    summary: str,
    tool_context: ToolContext,
) -> dict:
    # Never let a malformed item crash the run — hand a retriable error back
    # to the model instead (mirrors ADK's own missing-mandatory-arg pattern).
    try:
        rec = model_cls(items=items, summary=summary)
    except pydantic.ValidationError as e:
        return {
            "status": "error",
            "message": f"Invalid items for {model_cls.__name__}: {e}. Fix and call this tool again.",
        }
    tool_context.state[state_key] = rec.model_dump()
    return {"status": "ok", "recommendation": rec.model_dump()}


def emit_demand_recommendation(
    items: list[DemandOutlook], summary: str, tool_context: ToolContext
) -> dict:
    """Validates and writes the demand specialist's recommendation to state.

    Args:
        items: one DemandOutlook per SKU.
        summary: one or two sentence overall summary.
    """
    return _emit_recommendation(DemandRecommendation, "rec:demand", items, summary, tool_context)


def emit_inventory_recommendation(
    items: list[InventoryNeed], summary: str, tool_context: ToolContext
) -> dict:
    """Validates and writes the inventory specialist's recommendation to state.

    Args:
        items: one InventoryNeed per SKU/warehouse that needs replenishment.
        summary: one or two sentence overall summary.
    """
    return _emit_recommendation(InventoryRecommendation, "rec:inventory", items, summary, tool_context)


def emit_procurement_recommendation(
    items: list[ProcurementChoice], summary: str, tool_context: ToolContext
) -> dict:
    """Validates and writes the procurement specialist's recommendation to state.

    Args:
        items: one ProcurementChoice per proposed order.
        summary: one or two sentence overall summary.
    """
    return _emit_recommendation(ProcurementRecommendation, "rec:procurement", items, summary, tool_context)

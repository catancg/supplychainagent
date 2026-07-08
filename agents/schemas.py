"""Small, flat Pydantic schemas for inter-agent recommendations and the
final ActionPlan (docs/feature.prd §5). Used to validate tool-call args in
emit_recommendation / emit_action_plan before they're written to state.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DemandOutlook(BaseModel):
    sku: str
    forecast_daily_demand: float
    historical_avg_daily_demand: float
    is_spike: bool
    note: str = Field(description="Short reasoning for this SKU's outlook.")


class DemandRecommendation(BaseModel):
    items: list[DemandOutlook]
    summary: str


class InventoryNeed(BaseModel):
    sku: str
    warehouse: str
    on_hand: int
    reorder_point: float
    suggested_order_qty: int
    policy_citation: str = Field(
        default="", description="Source of the stocking policy used, if any."
    )
    note: str = Field(default="", description="Short reasoning for this need.")


class InventoryRecommendation(BaseModel):
    items: list[InventoryNeed]
    summary: str


class ProcurementChoice(BaseModel):
    sku: str
    warehouse: str
    supplier: str
    qty: int
    unit_cost_ars: float
    est_cost: float
    lead_time_days: float
    policy_citation: str = Field(
        default="", description="Source of the supplier policy used, if any."
    )
    note: str = Field(default="", description="Short reasoning for this choice.")


class ProcurementRecommendation(BaseModel):
    items: list[ProcurementChoice]
    summary: str


class PurchaseOrder(BaseModel):
    sku: str
    supplier: str
    qty: int
    dest_warehouse: str
    est_cost: float


class ActionPlan(BaseModel):
    purchase_orders: list[PurchaseOrder]
    rationale: str


class GuardrailTrip(BaseModel):
    type: str
    detail: str
    sku: str = ""
    supplier: str = ""

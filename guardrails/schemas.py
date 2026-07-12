"""Pydantic models for the guardrail rule engine (docs/phase1-guardrail-
templates.prd). No ADK/domain dependency — reusable beyond this project.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GuardrailRule(BaseModel):
    name: str
    type: Literal[
        "budget_cap",
        "supplier_availability",
        "quantity_range",
        "injection_pattern",
    ]
    params: dict[str, Any] = Field(default_factory=dict)


class GuardrailTrip(BaseModel):
    type: str
    detail: str
    sku: str = ""
    supplier: str = ""


class GuardrailTemplate(BaseModel):
    name: str
    rules: list[GuardrailRule]

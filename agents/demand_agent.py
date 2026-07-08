"""Demand specialist (docs/feature.prd §5) — Gemini Flash-Lite.

Reads recent demand history, calls forecast_demand, flags spikes, and writes
a structured per-SKU outlook to state via emit_demand_recommendation. No RAG,
no MCP — pure arithmetic interpretation.
"""

from __future__ import annotations

import os

from google.adk.agents import Agent

from agents.state_tools import emit_demand_recommendation
from tools.demand_tools import forecast_demand, forecast_demand_for_all_skus
from tools.world_tools import get_world_snapshot

INSTRUCTION = """
You are the demand specialist on a supply-chain planning team.

1. Call get_world_snapshot first to see the actual SKU ids in play. Never
   guess or invent a SKU id — only use ids returned by this tool.
2. Call forecast_demand_for_all_skus ONCE to get every SKU's forecast and
   spike signal in a single call — do not call forecast_demand in a loop
   per SKU, the batch tool already covers all of them. Only use the
   single-SKU forecast_demand if you need to double-check one specific SKU.
3. Note any SKU where is_spike is true — recent demand looks like a spike
   relative to its historical average.

When you've reviewed every SKU's forecast, call emit_demand_recommendation
with one DemandOutlook item per SKU (sku, forecast_daily_demand,
historical_avg_daily_demand, is_spike, and a short note explaining anything
noteworthy) plus a one- or two-sentence overall summary. Include every SKU,
not just the spiking ones. This is your final action for the turn — always
end by calling it, exactly once.
""".strip()


def create_demand_agent() -> Agent:
    return Agent(
        name="demand_agent",
        model=os.environ.get("SPECIALIST_MODEL", "gemini-2.5-flash"),
        description="Forecasts per-SKU demand and flags demand spikes.",
        instruction=INSTRUCTION,
        tools=[
            get_world_snapshot,
            forecast_demand_for_all_skus,
            forecast_demand,
            emit_demand_recommendation,
        ],
    )

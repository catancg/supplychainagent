"""Deterministic demand-forecasting tool. Pure arithmetic — the demand agent
decides what the numbers mean; this just produces them. See docs/feature.prd §6.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from tools._world import get_sku, get_world


def _forecast_from_history(sku: str, history: list[float]) -> dict:
    historical_avg = sum(history) / len(history)
    recent_window = history[-2:]
    recent_avg = sum(recent_window) / len(recent_window)
    spike_ratio = round(recent_avg / historical_avg, 2) if historical_avg else 0.0
    forecast = round(0.4 * historical_avg + 0.6 * recent_avg, 2)

    return {
        "sku": sku,
        "forecast_daily_demand": forecast,
        "historical_avg_daily_demand": round(historical_avg, 2),
        "recent_avg_daily_demand": round(recent_avg, 2),
        "spike_ratio": spike_ratio,
        "is_spike": spike_ratio >= 1.5,
    }


def forecast_demand(sku: str, tool_context: ToolContext) -> dict:
    """Forecasts near-term daily demand for a SKU from its trailing demand history.

    Blends the full trailing average with a recent-window average so a sudden
    spike shows up in the forecast, and flags whether recent demand looks like
    a spike relative to the historical average.

    Args:
        sku: SKU id, e.g. "AC-12".
    """
    world = get_world(tool_context)
    record = get_sku(world, sku)
    return _forecast_from_history(sku, record["recent_demand"])


def forecast_demand_for_all_skus(tool_context: ToolContext) -> dict:
    """Forecasts near-term daily demand for every SKU in the loaded scenario.

    One call instead of one forecast_demand call per SKU — use this instead
    of looping forecast_demand over get_world_snapshot's SKU list.
    """
    world = get_world(tool_context)
    forecasts = [
        _forecast_from_history(record["id"], record["recent_demand"])
        for record in world.get("skus", [])
    ]
    return {"forecasts": forecasts}

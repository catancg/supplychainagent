"""Demand-forecasting tool. forecast_daily_demand is produced by a trained
regression model (docs/phase1-ml-demand-model.prd), loaded from
ml/models/demand_forecast.joblib, with a graceful fallback to the original
trailing-average formula if that file is missing or fails to load.

is_spike/spike_ratio deliberately keep their original trailing-average
heuristic, independent of the model's prediction (PRD §7's "heuristic as a
sanity-check overlay" option) — this guarantees spike classification can't
drift on the 12 existing eval scenarios regardless of what the model
predicts for forecast_daily_demand.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from ml.predictor import load_model, predict_next_demand
from tools._world import get_sku, get_world


def _forecast_from_history(sku: str, history: list[float], category: str, model) -> dict:
    historical_avg = sum(history) / len(history)
    recent_window = history[-2:]
    recent_avg = sum(recent_window) / len(recent_window)
    spike_ratio = round(recent_avg / historical_avg, 2) if historical_avg else 0.0
    forecast = predict_next_demand(model, history, category)

    return {
        "sku": sku,
        "forecast_daily_demand": forecast,
        "historical_avg_daily_demand": round(historical_avg, 2),
        "recent_avg_daily_demand": round(recent_avg, 2),
        "spike_ratio": spike_ratio,
        "is_spike": spike_ratio >= 1.5,
    }


def forecast_demand(sku: str, tool_context: ToolContext) -> dict:
    """Forecasts near-term daily demand for a SKU from its trailing demand
    history, using a trained regression model, and flags whether recent
    demand looks like a spike relative to the historical average.

    Args:
        sku: SKU id, e.g. "AC-12".
    """
    world = get_world(tool_context)
    record = get_sku(world, sku)
    model = load_model()
    return _forecast_from_history(sku, record["recent_demand"], record.get("category", ""), model)


def forecast_demand_for_all_skus(tool_context: ToolContext) -> dict:
    """Forecasts near-term daily demand for every SKU in the loaded scenario.

    One call instead of one forecast_demand call per SKU — use this instead
    of looping forecast_demand over get_world_snapshot's SKU list.
    """
    world = get_world(tool_context)
    model = load_model()
    forecasts = [
        _forecast_from_history(record["id"], record["recent_demand"], record.get("category", ""), model)
        for record in world.get("skus", [])
    ]
    return {"forecasts": forecasts}

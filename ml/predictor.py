"""Loads the trained demand-forecast model and predicts next-period demand
(docs/phase1-ml-demand-model.prd §5). Falls back to the original trailing-
average heuristic if the model file is missing or fails to load, consistent
with this project's fail-soft tool philosophy (see agents/state_tools.py's
validation-error handling).

load_model()/predict_next_demand() are split so a caller doing multiple
predictions in one batch (forecast_demand_for_all_skus) loads the model
file once, not once per SKU.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ml.features import extract_features

MODEL_PATH = Path(__file__).resolve().parent / "models" / "demand_forecast.joblib"


def _heuristic_forecast(history: list[float]) -> float:
    """Today's original formula — the fallback when no model is available."""
    historical_avg = sum(history) / len(history)
    recent_avg = sum(history[-2:]) / 2
    return round(0.4 * historical_avg + 0.6 * recent_avg, 2)


def load_model(model_path: Path | None = None) -> Any | None:
    """Returns the fitted model, or None if the file is missing/corrupt."""
    path = model_path if model_path is not None else MODEL_PATH
    try:
        import joblib

        bundle = joblib.load(path)
        return bundle["model"]
    except Exception:
        return None


def predict_next_demand(model: Any | None, history: list[float], category: str) -> float:
    """Predicts next-period demand from a 6-value trailing history using an
    already-loaded model. Falls back to the trailing-average heuristic if
    `model` is None or prediction fails for any reason.
    """
    if model is None:
        return _heuristic_forecast(history)
    try:
        features = extract_features(history, category)
        prediction = model.predict([features])[0]
        return round(float(prediction), 2)
    except Exception:
        return _heuristic_forecast(history)

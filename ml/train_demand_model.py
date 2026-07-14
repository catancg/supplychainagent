"""Trains the demand-forecast regression model (docs/phase1-ml-demand-model.prd
§4) on the synthetic dataset. Tries a tree ensemble and a linear model, picks
whichever validates better (lower MAE) on a held-out split, and serializes
the winner to ml/models/demand_forecast.joblib.

That model file IS committed to the repo (unlike ml/data/synthetic_demand.csv)
so tools/demand_tools.py works out of the box after a clean checkout, with
no training step required first.

Run: uv run python -m ml.generate_training_data && uv run python -m ml.train_demand_model
"""

from __future__ import annotations

import csv
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split

from ml.features import FEATURE_NAMES

DATA_PATH = Path(__file__).resolve().parent / "data" / "synthetic_demand.csv"
MODEL_PATH = Path(__file__).resolve().parent / "models" / "demand_forecast.joblib"
SEED = 42


def _load_dataset() -> tuple[np.ndarray, np.ndarray]:
    with DATA_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    x = np.array([[float(row[name]) for name in FEATURE_NAMES] for row in rows])
    y = np.array([float(row["target"]) for row in rows])
    return x, y


def main() -> None:
    if not DATA_PATH.exists():
        raise SystemExit(
            f"{DATA_PATH} not found — run `uv run python -m ml.generate_training_data` first."
        )

    x, y = _load_dataset()
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=SEED)

    candidates = {
        "gradient_boosting": GradientBoostingRegressor(random_state=SEED),
        "ridge": Ridge(),
    }

    best_name, best_model, best_mae = None, None, float("inf")
    for name, model in candidates.items():
        model.fit(x_train, y_train)
        preds = model.predict(x_test)
        mae = mean_absolute_error(y_test, preds)
        rmse = mean_squared_error(y_test, preds) ** 0.5
        print(f"{name}: MAE={mae:.3f}  RMSE={rmse:.3f}")
        if mae < best_mae:
            best_name, best_model, best_mae = name, model, mae

    print(f"Selected: {best_name} (MAE={best_mae:.3f})")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": best_model, "feature_names": FEATURE_NAMES, "model_name": best_name},
        MODEL_PATH,
    )
    print(f"Saved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()

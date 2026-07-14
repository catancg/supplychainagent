"""Shared feature extraction for the demand-forecast model (docs/phase1-
ml-demand-model.prd §2). Used identically by ml/generate_training_data.py
(training) and ml/predictor.py (inference) so features never drift between
train and serve — a single source of truth for the feature vector shape.
"""

from __future__ import annotations

import statistics

FEATURE_NAMES = [
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_4",
    "lag_5",
    "lag_6",
    "rolling_mean",
    "rolling_std",
    "rolling_min",
    "rolling_max",
    "spike_ratio",
    "is_major_appliance",
]


def extract_features(history: list[float], category: str) -> list[float]:
    """Builds the model's feature vector (FEATURE_NAMES order) from exactly
    6 trailing daily demand values (oldest to newest, matching scenario
    fixtures' recent_demand) plus a SKU category.
    """
    if len(history) != 6:
        raise ValueError(f"expected exactly 6 trailing values, got {len(history)}")

    lags = list(reversed(history))  # lag_1 = most recent = history[-1]
    historical_avg = statistics.fmean(history)
    recent_avg = sum(history[-2:]) / 2
    spike_ratio = recent_avg / historical_avg if historical_avg else 0.0

    return [
        *lags,
        historical_avg,
        statistics.pstdev(history),
        min(history),
        max(history),
        spike_ratio,
        1.0 if category == "major_appliance" else 0.0,
    ]

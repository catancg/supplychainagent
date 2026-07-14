"""Synthetic training-data generator for the demand-forecast model
(docs/phase1-ml-demand-model.prd §3). The 10-SKU scenario fixtures alone are
far too little data to train anything, so this simulates many independent
daily demand series (baseline level by category + gaussian noise +
occasional spikes + mild seasonality) and slides a 6-day window over each
to produce (features..., target) rows.

Deterministic given SEED, so a clean checkout reproduces the exact same
CSV. Output is git-ignored (regenerable, not source — same treatment as
chroma_data/).

Run: uv run python -m ml.generate_training_data
"""

from __future__ import annotations

import csv
import math
import random
from pathlib import Path

from ml.features import FEATURE_NAMES, extract_features

SEED = 42
N_SERIES = 800
SERIES_LENGTH = 120  # simulated days per synthetic SKU
WINDOW = 6  # matches recent_demand's trailing-window size in scenario fixtures

OUTPUT_PATH = Path(__file__).resolve().parent / "data" / "synthetic_demand.csv"

CATEGORIES = ["major_appliance", "small_item"]
_BASELINE_RANGE = {
    "major_appliance": (2.0, 8.0),
    "small_item": (5.0, 25.0),
}

SPIKE_PROBABILITY = 0.03  # per-day chance of an injected demand spike
SPIKE_MAGNITUDE_RANGE = (2.0, 4.0)  # multiplier applied to that day's level
NOISE_STD_FRACTION = 0.15  # gaussian noise std, as a fraction of baseline
TREND_AMPLITUDE_FRACTION = 0.15  # sine seasonality amplitude, fraction of baseline
TREND_PERIOD_DAYS = 30


def _simulate_series(rng: random.Random, category: str) -> list[float]:
    baseline = rng.uniform(*_BASELINE_RANGE[category])
    phase = rng.uniform(0, 2 * math.pi)
    values: list[float] = []
    for day in range(SERIES_LENGTH):
        seasonal = baseline * TREND_AMPLITUDE_FRACTION * math.sin(
            2 * math.pi * day / TREND_PERIOD_DAYS + phase
        )
        level = baseline + seasonal
        noise = rng.gauss(0, baseline * NOISE_STD_FRACTION)
        value = level + noise
        if rng.random() < SPIKE_PROBABILITY:
            value *= rng.uniform(*SPIKE_MAGNITUDE_RANGE)
        values.append(max(0.0, round(value, 2)))
    return values


def _rows_from_series(series: list[float], category: str) -> list[list[float]]:
    rows = []
    for start in range(len(series) - WINDOW):
        history = series[start : start + WINDOW]
        target = series[start + WINDOW]
        rows.append([*extract_features(history, category), target])
    return rows


def generate() -> list[list[float]]:
    rng = random.Random(SEED)
    all_rows: list[list[float]] = []
    for _ in range(N_SERIES):
        category = rng.choice(CATEGORIES)
        series = _simulate_series(rng, category)
        all_rows.extend(_rows_from_series(series, category))
    return all_rows


def main() -> None:
    rows = generate()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([*FEATURE_NAMES, "target"])
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows ({N_SERIES} series x ~{SERIES_LENGTH - WINDOW} windows) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

"""Tests for the ML demand-forecast pieces (docs/phase1-ml-demand-model.prd).

Uses the actual committed ml/models/demand_forecast.joblib (per the PRD's
"commit the model file" decision) rather than training one in the test
suite — training on 90k+ synthetic rows is a deliberately manual/documented
step (uv run python -m ml.train_demand_model), not something to run on
every `pytest`.
"""

import pytest

from loader import load_scenario
from ml.features import FEATURE_NAMES, extract_features
from ml.predictor import load_model, predict_next_demand
from tools.demand_tools import forecast_demand, forecast_demand_for_all_skus


class FakeToolContext:
    def __init__(self, state: dict):
        self.state = state


def test_extract_features_shape_and_order():
    features = extract_features([1, 2, 3, 4, 5, 6], "major_appliance")
    assert len(features) == len(FEATURE_NAMES)
    # lag_1 is the most recent value (history[-1])
    assert features[0] == 6
    assert features[5] == 1
    assert features[-1] == 1.0  # is_major_appliance


def test_extract_features_small_item_flag():
    features = extract_features([1, 2, 3, 4, 5, 6], "small_item")
    assert features[-1] == 0.0


def test_extract_features_zero_history_does_not_crash():
    features = extract_features([0, 0, 0, 0, 0, 0], "small_item")
    assert features[FEATURE_NAMES.index("spike_ratio")] == 0.0


def test_extract_features_requires_exactly_six_values():
    with pytest.raises(ValueError):
        extract_features([1, 2, 3], "small_item")


def test_model_file_loads():
    model = load_model()
    assert model is not None


def test_predict_next_demand_spiking_series_higher_than_flat():
    """Directional check (PRD §7): a clearly upward-spiking series should
    predict a higher next-period demand than an otherwise-identical flat
    series.
    """
    model = load_model()
    assert model is not None, "ml/models/demand_forecast.joblib must be trained/committed"

    flat = [5, 5, 5, 5, 5, 5]
    spiking = [5, 5, 5, 5, 15, 15]

    flat_pred = predict_next_demand(model, flat, "major_appliance")
    spiking_pred = predict_next_demand(model, spiking, "major_appliance")

    assert spiking_pred > flat_pred


def test_predict_next_demand_falls_back_to_heuristic_when_model_missing():
    """Simulates a missing/corrupt model file (load_model given a bad path)."""
    missing_model = load_model(model_path="ml/models/does_not_exist.joblib")
    assert missing_model is None

    history = [4, 5, 4, 6, 18, 20]
    result = predict_next_demand(missing_model, history, "major_appliance")

    historical_avg = sum(history) / len(history)
    recent_avg = sum(history[-2:]) / 2
    expected = round(0.4 * historical_avg + 0.6 * recent_avg, 2)
    assert result == expected


def test_forecast_demand_is_spike_matches_original_heuristic():
    """is_spike/spike_ratio must stay driven by the original trailing-
    average heuristic regardless of the model swap (PRD §7's regression
    gate) — this is a direct unit-level check; the full 12-scenario sweep
    was verified manually against the original formula with zero mismatches.
    """
    world = load_scenario("demand_spike")
    ctx = FakeToolContext({"world": world})

    result = forecast_demand("AC-12", ctx)
    assert result["is_spike"] is True
    assert result["spike_ratio"] == 2.0

    world_normal = load_scenario("normal")
    ctx_normal = FakeToolContext({"world": world_normal})
    result_normal = forecast_demand("AC-12", ctx_normal)
    assert result_normal["is_spike"] is False


def test_forecast_demand_for_all_skus_still_covers_every_sku():
    world = load_scenario("normal")
    ctx = FakeToolContext({"world": world})
    result = forecast_demand_for_all_skus(ctx)
    assert len(result["forecasts"]) == len(world["skus"])
    assert all("forecast_daily_demand" in f for f in result["forecasts"])

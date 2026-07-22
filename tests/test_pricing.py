"""Tests for the estimated-USD-cost calculation (agents/pricing.py)."""

from agents.pricing import estimate_cost_usd


def test_known_model_uses_its_own_rates():
    cost = estimate_cost_usd(
        model="gemini-2.5-flash-lite",
        prompt_tokens=1_000_000,
        cached_tokens=0,
        output_tokens=0,
        thinking_tokens=0,
    )
    assert cost == 0.10  # gemini-2.5-flash-lite's input rate, $/1M


def test_unknown_model_falls_back_to_default_rates_not_raises():
    cost = estimate_cost_usd(
        model="some-future-model-id",
        prompt_tokens=1_000_000,
        cached_tokens=0,
        output_tokens=0,
        thinking_tokens=0,
    )
    assert cost == 0.30  # gemini-2.5-flash's input rate (the fallback)


def test_none_model_falls_back_to_default_rates():
    cost = estimate_cost_usd(
        model=None, prompt_tokens=0, cached_tokens=0, output_tokens=1_000_000, thinking_tokens=0
    )
    assert cost == 2.50  # gemini-2.5-flash's output rate


def test_cached_tokens_billed_at_discounted_rate_not_double_counted():
    # All prompt tokens are cached — should be billed entirely at the
    # cached rate, not the standard input rate, and not both.
    cost = estimate_cost_usd(
        model="gemini-2.5-flash",
        prompt_tokens=1_000_000,
        cached_tokens=1_000_000,
        output_tokens=0,
        thinking_tokens=0,
    )
    assert cost == 0.03  # cached input rate, not 0.30


def test_thinking_tokens_billed_at_output_rate():
    cost = estimate_cost_usd(
        model="gemini-2.5-flash",
        prompt_tokens=0,
        cached_tokens=0,
        output_tokens=0,
        thinking_tokens=1_000_000,
    )
    assert cost == 2.50  # same as output rate


def test_mixed_usage_sums_all_components():
    cost = estimate_cost_usd(
        model="gemini-2.5-flash",
        prompt_tokens=1_000_000,  # half cached, half not
        cached_tokens=500_000,
        output_tokens=500_000,
        thinking_tokens=500_000,
    )
    expected = (
        500_000 / 1_000_000 * 0.30  # non-cached input
        + 500_000 / 1_000_000 * 0.03  # cached input
        + (500_000 + 500_000) / 1_000_000 * 2.50  # output + thinking
    )
    assert cost == expected

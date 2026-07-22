"""Estimated USD cost per Gemini API call, from published per-model rates.

This is an ESTIMATE for cost-awareness during development, not a substitute
for an actual bill — these figures reflect the paid-tier, text/image/video
rates from Google's rate card (https://ai.google.dev/gemini-api/docs/pricing,
checked 2026-07) and don't reflect free-tier allowances, audio pricing,
batch/promotional discounts, or future changes. Re-check against the current
rate card before treating these numbers as authoritative.

Thinking tokens are billed at each model's output rate (Gemini bills
reasoning/thinking tokens as part of output, not a separate rate). Cached
input tokens (context caching — see ContextCacheConfig in
agents/supervisor_agent.py) are billed at a discounted per-token rate;
cached_content_token_count is already included in prompt_token_count, so
it's subtracted before pricing the non-cached portion, to avoid double
counting. NOT modeled here: Gemini also charges a separate ~$1.00/1M
tokens/hour storage fee for keeping content cached, independent of how many
times it's read — this estimate only prices the per-call read discount, not
that storage time, since per-call usage_metadata doesn't expose cache
duration.
"""

from __future__ import annotations

from typing import NamedTuple


class ModelRates(NamedTuple):
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float  # includes thinking tokens


# USD per 1,000,000 tokens, standard paid-tier text/image/video rates (not
# free-tier, not audio, not batch). Source: Google's rate card, see module
# docstring.
_RATES: dict[str, ModelRates] = {
    "gemini-2.5-flash": ModelRates(
        input_per_million=0.30, cached_input_per_million=0.03, output_per_million=2.50
    ),
    "gemini-2.5-flash-lite": ModelRates(
        input_per_million=0.10, cached_input_per_million=0.01, output_per_million=0.40
    ),
    "gemini-flash-latest": ModelRates(
        input_per_million=0.30, cached_input_per_million=0.03, output_per_million=2.50
    ),
}

_DEFAULT_RATES = _RATES["gemini-2.5-flash"]


def estimate_cost_usd(
    model: str | None,
    prompt_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    thinking_tokens: int,
) -> float:
    """Best-effort USD estimate for one model call. An unrecognized model
    falls back to gemini-2.5-flash's rates rather than raising — an
    approximate number is more useful here than a crashed run over a cost
    metric that was never meant to gate anything.
    """
    rates = _RATES.get(model or "", _DEFAULT_RATES)
    non_cached_input = max(prompt_tokens - cached_tokens, 0)
    return (
        non_cached_input / 1_000_000 * rates.input_per_million
        + cached_tokens / 1_000_000 * rates.cached_input_per_million
        + (output_tokens + thinking_tokens) / 1_000_000 * rates.output_per_million
    )

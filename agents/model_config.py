"""Automatic retry-on-transient-error for Gemini calls.

Remediation for the "This model is currently experiencing high demand"
(503 ServerError) failures hit repeatedly during development and testing —
including via `adk web`, which (unlike webapp/runner_service.py and
evals/run_evals.py) has no retry logic of its own, so a transient 503
there just kills the turn outright.

Deliberately NOT a custom ADK plugin (e.g. on_model_error_callback) — the
google-genai SDK already has its own HTTP-level retry mechanism
(HttpRetryOptions), which:
  - applies uniformly to every entry point (adk web included) because it's
    configured on the model/client itself, not wrapped around a Runner;
  - only retries the status codes that are actually worth retrying (its
    default is 408, 429, and 5xx) — it will NOT retry a 400
    INVALID_ARGUMENT (e.g. a malformed request), which would only ever
    fail again identically no matter how many times it's retried.
"""

from __future__ import annotations

from google import genai
from google.adk.models.google_llm import Gemini
from google.genai import types

# attempts=3 => the original call plus 2 retries, matching this project's
# existing MAX_RETRIES=2 convention (evals/run_evals.py, webapp/
# runner_service.py) in spirit, even though the mechanism is different.
# initial_delay/max_delay kept modest since this fires per model call (a
# full pipeline run makes ~15-25 of them) — a full run should still fail
# within a bounded time during a genuine outage, not hang for minutes.
RETRY_OPTIONS = types.HttpRetryOptions(attempts=3, initial_delay=2.0, max_delay=15.0)


def resilient_model(model_name: str) -> Gemini:
    """A Gemini model instance with automatic retry-on-transient-error —
    pass this as an Agent's `model` instead of a bare model-name string.
    """
    return Gemini(model=model_name, retry_options=RETRY_OPTIONS)


def resilient_client(api_key: str) -> genai.Client:
    """A genai.Client with the same retry policy, for callers that talk to
    Gemini directly rather than through an ADK Agent (e.g. evals/judge.py).
    """
    return genai.Client(
        api_key=api_key, http_options=types.HttpOptions(retry_options=RETRY_OPTIONS)
    )

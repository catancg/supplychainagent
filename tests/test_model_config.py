"""Tests for the retry-on-transient-error model configuration
(agents/model_config.py) — the remediation for 503s going unhandled on
adk web and elsewhere.
"""

from google.adk.models.google_llm import Gemini

from agents.model_config import RETRY_OPTIONS, resilient_client, resilient_model


def test_resilient_model_returns_gemini_instance():
    model = resilient_model("gemini-2.5-flash")
    assert isinstance(model, Gemini)
    assert model.model == "gemini-2.5-flash"


def test_resilient_model_attaches_retry_options():
    model = resilient_model("gemini-2.5-flash")
    assert model.retry_options is RETRY_OPTIONS
    assert model.retry_options.attempts == 3


def test_resilient_model_preserves_model_name_across_calls():
    model_a = resilient_model("gemini-2.5-flash-lite")
    model_b = resilient_model("gemini-flash-latest")
    assert model_a.model == "gemini-2.5-flash-lite"
    assert model_b.model == "gemini-flash-latest"


def test_retry_options_defaults_leave_status_codes_to_sdk_default():
    # http_status_codes intentionally left unset so the SDK's own default
    # (408, 429, 5xx) applies — this is what makes the non-retryable 400
    # INVALID_ARGUMENT case correctly NOT get retried.
    assert RETRY_OPTIONS.http_status_codes is None


def test_resilient_client_attaches_retry_options_via_http_options():
    client = resilient_client("fake-api-key-for-test")
    http_options = client._api_client.get_read_only_http_options()
    assert http_options["retry_options"]["attempts"] == RETRY_OPTIONS.attempts
    assert http_options["retry_options"]["initial_delay"] == RETRY_OPTIONS.initial_delay

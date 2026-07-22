"""Deterministic trigger-message gate — the strongest available defense
against prompt injection at the very first turn: the check runs before any
model call, so a non-conforming message never reaches the LLM at all.

This agent is meant to be started with one fixed instruction, not chatted
with. `enforce_expected_trigger` (a before_agent_callback) rejects anything
that doesn't match that instruction exactly, short-circuiting the whole
invocation.

Wired on by default everywhere (agents/__init__.py for adk web, the webapp,
evals) via create_app()/create_supervisor_agent()'s strict_trigger=True
default — see agents/supervisor_agent.py. Pass strict_trigger=False
explicitly if you ever need an open, unrestricted chat for interactive
debugging.
"""

from __future__ import annotations

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

# The one instruction a "worker" is allowed to send. Centralized here so the
# gate and every caller that constructs this exact message (webapp, evals)
# share a single source of truth — if they ever drifted apart, the worker
# would start rejecting its own trigger.
EXPECTED_TRIGGER_MESSAGE = "Produce an action plan for the current situation."

_REJECTION_MESSAGE = (
    "Request rejected: this agent is a fixed, automated worker that only "
    "produces an action plan for the currently loaded scenario. It does not "
    "accept alternate instructions."
)


def _extract_text(content: types.Content | None) -> str:
    if content is None or not content.parts:
        return ""
    return "".join(part.text or "" for part in content.parts).strip()


async def enforce_expected_trigger(
    callback_context: CallbackContext,
) -> types.Content | None:
    """before_agent_callback: rejects any invocation whose triggering
    message isn't exactly EXPECTED_TRIGGER_MESSAGE. Returning a Content here
    short-circuits the entire invocation — no model call, no tool calls.
    """
    message = _extract_text(callback_context.user_content)
    if message == EXPECTED_TRIGGER_MESSAGE:
        return None

    return types.Content(
        role="model",
        parts=[types.Part(text=_REJECTION_MESSAGE)],
    )

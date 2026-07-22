"""Agent package root — exposes app/root_agent so `adk web .` (agents_dir=
repo root, agent_name="agents") can discover it (docs/feature.prd §2, §13).

Wrapped in an App (rather than exporting root_agent alone) so the
TokenUsagePlugin and context caching apply across the whole agent tree,
including nested specialist runs invoked via AgentTool.

strict_trigger=True: adk web only executes on an exact match of
agents.trigger_guard.EXPECTED_TRIGGER_MESSAGE — anything else (a greeting,
a paraphrase, an injected instruction) is rejected before any model call.
This used to be opt-in for the webapp/evals only, with adk web exempt as
an open dev tool; reversed to secure-by-default everywhere, since an open
chat surface is itself a prompt-injection risk worth closing.
"""

from agents.supervisor_agent import create_app

app = create_app(strict_trigger=True)
root_agent = app.root_agent

__all__ = ["app", "root_agent"]

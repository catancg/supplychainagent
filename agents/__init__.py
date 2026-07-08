"""Agent package root — exposes app/root_agent so `adk web .` (agents_dir=
repo root, agent_name="agents") can discover it (docs/feature.prd §2, §13).

Wrapped in an App (rather than exporting root_agent alone) so the
TokenUsagePlugin and context caching apply across the whole agent tree,
including nested specialist runs invoked via AgentTool.
"""

from agents.supervisor_agent import create_app

app = create_app()
root_agent = app.root_agent

__all__ = ["app", "root_agent"]

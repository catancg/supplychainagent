"""Token usage tracking — prints prompt/output/thinking/total tokens after
every model call, tagged with which agent made it. Registered once as a
plugin (see agents/__init__.py) so it applies across the whole agent tree,
including nested specialist runs invoked via AgentTool.
"""

from __future__ import annotations

import time
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.sessions.state import State
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from agents.pricing import estimate_cost_usd

# The one tool that grounds reasoning in the RAG policy corpus (docs/feature.prd
# §7) — flagged in the trace so RAG usage is visually distinguishable from
# plain deterministic tool calls.
RAG_TOOLS = {"search_policy"}


class TraceCollectorPlugin(BasePlugin):
    """Builds a flat, chronological trace of a run for display in the webapp:
    every tool call/result, every resulting state["rec:*"/"action_plan"/...]
    change, and every model text response — across the whole agent tree.

    Reuses the same mechanism as TokenUsagePlugin — plugin callbacks fire
    across the whole agent tree, including nested specialist runs invoked via
    AgentTool, which the top-level Runner.run_async() event stream does NOT
    show (each AgentTool invocation runs its sub-agent in its own internal
    Runner/session). A plugin is the only way to see everything in order.

    State changes are detected by diffing a state snapshot taken immediately
    before and after each tool call — every state mutation in this codebase
    happens inside a tool (the emit_* tools, and the guardrail callback that
    runs before emit_action_plan), so tool-level before/after is sufficient;
    no separate agent-level bracketing is needed.
    """

    def __init__(self):
        super().__init__(name="trace_collector")
        self.trace: list[dict[str, Any]] = []
        self._state_before: dict[str, dict] = {}

    def _record(self, **entry: Any) -> None:
        entry.setdefault("timestamp", time.time())
        self.trace.append(entry)

    @staticmethod
    def _state_snapshot(tool_context: ToolContext) -> dict:
        return {
            k: v
            for k, v in tool_context.state.to_dict().items()
            if not k.startswith("_adk") and not k.startswith(State.TEMP_PREFIX)
        }

    @staticmethod
    def _diff_state(before: dict, after: dict) -> list[dict]:
        changes = []
        for key in sorted(set(before) | set(after)):
            b, a = before.get(key), after.get(key)
            if b != a:
                changes.append({"key": key, "before": b, "after": a})
        return changes

    async def before_tool_callback(
        self, *, tool: BaseTool, tool_args: dict, tool_context: ToolContext
    ) -> dict | None:
        self._record(
            type="tool_call",
            agent=tool_context.agent_name,
            tool=tool.name,
            args=tool_args,
            is_rag=tool.name in RAG_TOOLS,
        )
        self._state_before[tool_context.function_call_id] = self._state_snapshot(tool_context)
        return None

    async def after_tool_callback(
        self, *, tool: BaseTool, tool_args: dict, tool_context: ToolContext, result: dict
    ) -> dict | None:
        self._record(
            type="tool_result",
            agent=tool_context.agent_name,
            tool=tool.name,
            result=result,
            is_rag=tool.name in RAG_TOOLS,
        )

        before = self._state_before.pop(tool_context.function_call_id, {})
        after = self._state_snapshot(tool_context)
        changes = self._diff_state(before, after)
        if changes:
            self._record(
                type="state_change",
                agent=tool_context.agent_name,
                tool=tool.name,
                changes=changes,
            )
        return None

    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> LlmResponse | None:
        content = llm_response.content
        if content is None or content.parts is None:
            return None
        text = "\n".join(
            p.text for p in content.parts if getattr(p, "text", None) and not getattr(p, "thought", False)
        )
        if text:
            self._record(type="model_text", agent=callback_context.agent_name, text=text)
        return None


class TokenUsagePlugin(BasePlugin):
    """Tracks token usage and an estimated USD cost (agents/pricing.py) per
    model call, printed immediately and kept as running totals — overall and
    per agent — for the whole run this plugin instance is attached to. A
    fresh instance per run (see create_app's token_usage_plugin param) is
    what makes "per run" the natural unit: totals start at zero and
    accumulate for exactly one pipeline invocation, not across runs.
    """

    def __init__(self):
        super().__init__(name="token_usage")
        self.total_tokens = 0
        self.total_cost_usd = 0.0
        self.cost_by_agent: dict[str, float] = {}

    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> LlmResponse | None:
        usage = llm_response.usage_metadata
        if usage is None:
            return None

        self.total_tokens += usage.total_token_count or 0
        agent_name = callback_context.agent_name

        cost = estimate_cost_usd(
            model=llm_response.model_version,
            prompt_tokens=usage.prompt_token_count or 0,
            cached_tokens=usage.cached_content_token_count or 0,
            output_tokens=usage.candidates_token_count or 0,
            thinking_tokens=usage.thoughts_token_count or 0,
        )
        self.total_cost_usd += cost
        self.cost_by_agent[agent_name] = self.cost_by_agent.get(agent_name, 0.0) + cost

        print(
            f"[tokens] {agent_name}: "
            f"prompt={usage.prompt_token_count or 0} "
            f"output={usage.candidates_token_count or 0} "
            f"thinking={usage.thoughts_token_count or 0} "
            f"total={usage.total_token_count or 0} "
            f"(running total={self.total_tokens})"
        )
        print(
            f"[cost] {agent_name}: ${cost:.5f} (estimated, running total=${self.total_cost_usd:.5f})"
        )
        return None

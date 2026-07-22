"""Tests TraceCollectorPlugin's state-diffing and RAG-flagging logic —
pure logic, testable without a live agent run. No pytest-asyncio in this
project, so async plugin hooks are driven directly via asyncio.run().
"""

import asyncio

from agents.observability import RAG_TOOLS, TokenUsagePlugin, TraceCollectorPlugin


class FakeTool:
    def __init__(self, name: str):
        self.name = name


class FakeState:
    def __init__(self, data: dict):
        self._data = data

    def to_dict(self) -> dict:
        return dict(self._data)


class FakeToolContext:
    def __init__(self, agent_name: str, function_call_id: str, state_data: dict):
        self.agent_name = agent_name
        self.function_call_id = function_call_id
        self.state = FakeState(state_data)


def _run(coro):
    return asyncio.run(coro)


def test_state_change_detected_between_before_and_after():
    plugin = TraceCollectorPlugin()
    state_data = {"world": {"a": 1}}
    ctx = FakeToolContext("demand_agent", "call-1", state_data)
    tool = FakeTool("emit_demand_recommendation")

    _run(plugin.before_tool_callback(tool=tool, tool_args={}, tool_context=ctx))
    state_data["rec:demand"] = {"items": [], "summary": "stable"}  # tool "writes" to state
    _run(plugin.after_tool_callback(tool=tool, tool_args={}, tool_context=ctx, result={"status": "ok"}))

    state_changes = [e for e in plugin.trace if e["type"] == "state_change"]
    assert len(state_changes) == 1
    assert state_changes[0]["tool"] == "emit_demand_recommendation"
    assert state_changes[0]["changes"] == [
        {"key": "rec:demand", "before": None, "after": {"items": [], "summary": "stable"}}
    ]


def test_no_state_change_entry_when_state_unchanged():
    plugin = TraceCollectorPlugin()
    state_data = {"world": {"a": 1}}
    ctx = FakeToolContext("demand_agent", "call-2", state_data)
    tool = FakeTool("forecast_demand")

    _run(plugin.before_tool_callback(tool=tool, tool_args={"sku": "AC-12"}, tool_context=ctx))
    _run(
        plugin.after_tool_callback(
            tool=tool, tool_args={"sku": "AC-12"}, tool_context=ctx, result={"forecast_daily_demand": 5}
        )
    )

    assert [e for e in plugin.trace if e["type"] == "state_change"] == []


def test_search_policy_flagged_as_rag():
    assert "search_policy" in RAG_TOOLS
    plugin = TraceCollectorPlugin()
    ctx = FakeToolContext("inventory_agent", "call-3", {})
    tool = FakeTool("search_policy")

    _run(plugin.before_tool_callback(tool=tool, tool_args={"query": "x", "k": 3}, tool_context=ctx))
    _run(plugin.after_tool_callback(tool=tool, tool_args={"query": "x", "k": 3}, tool_context=ctx, result={"chunks": []}))

    tool_entries = [e for e in plugin.trace if e["type"] in ("tool_call", "tool_result")]
    assert len(tool_entries) == 2
    assert all(e["is_rag"] for e in tool_entries)


def test_non_rag_tool_not_flagged():
    plugin = TraceCollectorPlugin()
    ctx = FakeToolContext("procurement_agent", "call-4", {})
    tool = FakeTool("rank_suppliers")

    _run(plugin.before_tool_callback(tool=tool, tool_args={"sku": "AC-12"}, tool_context=ctx))

    assert plugin.trace[0]["is_rag"] is False


def test_temp_and_internal_state_keys_ignored_in_diff():
    plugin = TraceCollectorPlugin()
    state_data = {"world": {"a": 1}}
    ctx = FakeToolContext("demand_agent", "call-5", state_data)
    tool = FakeTool("some_tool")

    _run(plugin.before_tool_callback(tool=tool, tool_args={}, tool_context=ctx))
    state_data["temp:scratch"] = "ignored"
    state_data["_adk_internal"] = "ignored too"
    _run(plugin.after_tool_callback(tool=tool, tool_args={}, tool_context=ctx, result={}))

    assert [e for e in plugin.trace if e["type"] == "state_change"] == []


class FakeCallbackContext:
    def __init__(self, agent_name: str):
        self.agent_name = agent_name


class FakeUsageMetadata:
    def __init__(
        self,
        prompt_token_count=0,
        candidates_token_count=0,
        thoughts_token_count=0,
        cached_content_token_count=0,
        total_token_count=0,
    ):
        self.prompt_token_count = prompt_token_count
        self.candidates_token_count = candidates_token_count
        self.thoughts_token_count = thoughts_token_count
        self.cached_content_token_count = cached_content_token_count
        self.total_token_count = total_token_count


class FakeLlmResponse:
    def __init__(self, model_version: str, usage_metadata):
        self.model_version = model_version
        self.usage_metadata = usage_metadata


def test_token_usage_plugin_accumulates_tokens_and_cost():
    plugin = TokenUsagePlugin()
    ctx = FakeCallbackContext("demand_agent")
    usage = FakeUsageMetadata(
        prompt_token_count=1000, candidates_token_count=100, thoughts_token_count=50, total_token_count=1150
    )
    response = FakeLlmResponse("gemini-2.5-flash", usage)

    _run(plugin.after_model_callback(callback_context=ctx, llm_response=response))

    assert plugin.total_tokens == 1150
    assert plugin.total_cost_usd > 0
    assert plugin.cost_by_agent["demand_agent"] == plugin.total_cost_usd


def test_token_usage_plugin_tracks_per_agent_breakdown_across_multiple_calls():
    plugin = TokenUsagePlugin()
    usage = FakeUsageMetadata(prompt_token_count=1000, candidates_token_count=100, total_token_count=1100)

    _run(
        plugin.after_model_callback(
            callback_context=FakeCallbackContext("demand_agent"),
            llm_response=FakeLlmResponse("gemini-2.5-flash", usage),
        )
    )
    _run(
        plugin.after_model_callback(
            callback_context=FakeCallbackContext("supervisor_agent"),
            llm_response=FakeLlmResponse("gemini-2.5-flash", usage),
        )
    )

    assert set(plugin.cost_by_agent.keys()) == {"demand_agent", "supervisor_agent"}
    assert plugin.cost_by_agent["demand_agent"] == plugin.cost_by_agent["supervisor_agent"]
    assert plugin.total_cost_usd == plugin.cost_by_agent["demand_agent"] + plugin.cost_by_agent["supervisor_agent"]
    assert plugin.total_tokens == 2200


def test_token_usage_plugin_skips_when_usage_metadata_missing():
    plugin = TokenUsagePlugin()
    ctx = FakeCallbackContext("demand_agent")
    response = FakeLlmResponse("gemini-2.5-flash", None)

    _run(plugin.after_model_callback(callback_context=ctx, llm_response=response))

    assert plugin.total_tokens == 0
    assert plugin.total_cost_usd == 0.0
    assert plugin.cost_by_agent == {}

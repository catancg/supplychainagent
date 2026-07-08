"""Token usage tracking — prints prompt/output/thinking/total tokens after
every model call, tagged with which agent made it. Registered once as a
plugin (see agents/__init__.py) so it applies across the whole agent tree,
including nested specialist runs invoked via AgentTool.
"""

from __future__ import annotations

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin


class TokenUsagePlugin(BasePlugin):
    def __init__(self):
        super().__init__(name="token_usage")
        self.total_tokens = 0

    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> LlmResponse | None:
        usage = llm_response.usage_metadata
        if usage is None:
            return None

        self.total_tokens += usage.total_token_count or 0
        print(
            f"[tokens] {callback_context.agent_name}: "
            f"prompt={usage.prompt_token_count or 0} "
            f"output={usage.candidates_token_count or 0} "
            f"thinking={usage.thoughts_token_count or 0} "
            f"total={usage.total_token_count or 0} "
            f"(running total={self.total_tokens})"
        )
        return None

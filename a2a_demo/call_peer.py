"""Standalone script proving the A2A protocol mechanics end-to-end
(docs/phase1-a2a-demo.prd): resolves the peer's agent card over HTTP, wraps
it as a RemoteA2aAgent tool, sends one demo message through a local caller
agent + Runner, and prints the round-trip.

Run with the peer already serving, in a separate process:
    uv run uvicorn a2a_demo.serve_peer:app --port 8001
    uv run python -m a2a_demo.call_peer

Same decoupled-demo scope as serve_peer.py — this does not touch the
supervisor pipeline, ActionPlan, guardrails, or any eval case.
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import AgentTool
from google.genai import types

PEER_CARD_URL = "http://localhost:8001/.well-known/agent-card.json"
APP_NAME = "a2a_demo_caller"
USER_ID = "a2a_demo_user"

DEMO_MESSAGE = "Ask our partner-logistics-org peer for their estimated lead time to ship into AR-Cordoba."

CALLER_INSTRUCTION = """
You have one tool, partner_logistics_peer, a remote partner organization's
agent reached over the A2A protocol. Delegate any lead-time question to it
verbatim and relay its answer back plainly.
""".strip()


def _build_caller_agent() -> Agent:
    remote_peer = RemoteA2aAgent(
        name="partner_logistics_peer",
        agent_card=PEER_CARD_URL,
        description="Remote peer: partner-logistics-org's agent, reached over the A2A protocol.",
    )
    return Agent(
        name="a2a_demo_caller",
        model=os.environ.get("SPECIALIST_MODEL", "gemini-2.5-flash"),
        description="Local demo agent that delegates lead-time questions to a remote A2A peer.",
        instruction=CALLER_INSTRUCTION,
        tools=[AgentTool(agent=remote_peer)],
    )


async def main() -> None:
    load_dotenv()
    caller_agent = _build_caller_agent()

    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID)

    runner = Runner(agent=caller_agent, app_name=APP_NAME, session_service=session_service)

    print(f"--> {DEMO_MESSAGE}")
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=DEMO_MESSAGE)]),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    print(f"[{event.author}] {part.text}")


if __name__ == "__main__":
    asyncio.run(main())

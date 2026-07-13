"""Serves the A2A demo peer agent (docs/phase1-a2a-demo.prd) as a Starlette
ASGI app — the "remote" side of the protocol demo, a separate local process
from the main agent stack (same pattern as the standalone MCP servers under
mcp_server/).

Run with:
    uv run uvicorn a2a_demo.serve_peer:app --port 8001

Serves the agent card at http://localhost:8001/.well-known/agent-card.json
and the A2A RPC endpoint at http://localhost:8001/.
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from google.adk.a2a.utils.agent_to_a2a import to_a2a  # noqa: E402

from a2a_demo.peer_agent import peer_agent  # noqa: E402

app = to_a2a(peer_agent, host="localhost", port=8001)

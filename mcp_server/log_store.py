"""Local MCP server exposing write_action_plan — the agent-initiated side of
the persistent log store (docs/phase1-db-mcp.prd). Read queries and eval-
result logging go through db.py directly, not MCP: only this one write, made
by the supervisor's own tool-call decision, goes through the protocol (the
PRD's "MCP is for agent-initiated writes only" principle, §1).

timestamp is deliberately NOT a parameter the caller supplies — the server
stamps it at write time. That's both more correct (records when the row was
actually persisted) and removes one value an LLM could mis-copy.
"""

from __future__ import annotations

from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

import db

mcp = FastMCP("log-store")

db.init_db()


@mcp.tool()
def write_action_plan(
    situation: str,
    purchase_orders: list[dict],
    rationale: str,
    guardrail_trips: list[dict],
) -> dict:
    """Persists an accepted ActionPlan to the log store. Returns {"id": <row id>}."""
    row_id = db.insert_action_plan(
        timestamp=datetime.now(timezone.utc).isoformat(),
        situation=situation,
        purchase_orders=purchase_orders,
        rationale=rationale,
        guardrail_trips=guardrail_trips,
    )
    return {"id": row_id}


if __name__ == "__main__":
    mcp.run()

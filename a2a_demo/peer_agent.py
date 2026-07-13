"""A minimal, standalone ADK agent playing "partner-logistics-org's agent"
— the remote side of the A2A protocol demo (docs/phase1-a2a-demo.prd).

Deliberately decoupled from the main supervisor pipeline: this exists to
prove the A2A protocol mechanics (agent card resolution, HTTP transport,
message conversion) work end-to-end between two separate processes, not to
affect any ActionPlan, guardrail, or eval case. "partner-logistics-org" is
flavor text, not a modeled business relationship.
"""

from __future__ import annotations

import hashlib
import os

from google.adk.agents import Agent

# Synthetic but deterministic — same region always returns the same
# estimate, same spirit as mcp_server/market_data.py's FX rates. Unlisted
# regions fall back to a stable, hash-derived estimate (hashlib, not the
# builtin hash(), which is randomized per process) so the tool never fails
# on a free-text region name.
_KNOWN_LEAD_TIMES_DAYS: dict[str, int] = {
    "AR-Cordoba": 9,
    "AR-BuenosAires": 6,
    "US-Southeast": 4,
    "US-Midwest": 5,
}


def get_partner_lead_time_estimate(region: str) -> dict:
    """Returns partner-logistics-org's estimated lead time (in days) to ship
    into `region`. Synthetic and deterministic — a stand-in for a real
    cross-organization API call, not a real logistics estimate.
    """
    days = _KNOWN_LEAD_TIMES_DAYS.get(region)
    if days is None:
        digest = hashlib.sha256(region.encode()).hexdigest()
        days = 5 + (int(digest, 16) % 6)  # deterministic fallback, 5-10 days
    return {
        "region": region,
        "estimated_lead_time_days": days,
        "source": "partner-logistics-org (synthetic demo data)",
    }


INSTRUCTION = """
You are partner-logistics-org's logistics assistant, answering questions
from a partner organization's supply-chain planning system over the A2A
protocol.

When asked about lead times into a region, call get_partner_lead_time_estimate
with that region and report the result plainly (region, estimated days,
source). Keep responses short and factual.
""".strip()


def create_peer_agent() -> Agent:
    return Agent(
        name="partner_logistics_peer",
        model=os.environ.get("SPECIALIST_MODEL", "gemini-2.5-flash"),
        description="partner-logistics-org's demo agent — answers lead-time questions over A2A.",
        instruction=INSTRUCTION,
        tools=[get_partner_lead_time_estimate],
    )


peer_agent = create_peer_agent()

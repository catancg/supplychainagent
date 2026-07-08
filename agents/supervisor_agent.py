"""Supervisor (docs/feature.prd §5) — Gemini Flash.

Invokes the three specialists as AgentTools, reads their recommendations
from state, reconciles into one ActionPlan (cover demand/shortfall first,
then minimize cost, then respect budget), and runs the plan through the
guardrail approval gate (before_tool_callback on emit_action_plan) before
it's logged.
"""

from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps import App
from google.adk.tools import AgentTool

from agents.demand_agent import create_demand_agent
from agents.guardrails import enforce_action_plan_guardrails
from agents.inventory_agent import create_inventory_agent
from agents.observability import TokenUsagePlugin
from agents.plan_tools import emit_action_plan, read_recommendations
from agents.procurement_agent import create_procurement_agent
from loader import load_scenario_into_state
from tools.world_tools import get_world_snapshot

DEFAULT_SCENARIO = os.environ.get("SCENARIO_PATH", "demand_spike")

INSTRUCTION = """
You are the supervisor of a supply-chain planning team with three
specialists available as tools: demand_agent, inventory_agent, and
procurement_agent.

A scenario is already loaded into state["world"] (current situation:
{situation}). To produce an action plan:
1. Call get_world_snapshot to see budget_per_cycle and confirm the situation
   — never claim the budget wasn't provided, it's always in this result.
2. Call demand_agent, then inventory_agent, then procurement_agent (in that
   order — inventory needs demand context, procurement needs inventory's
   needs). Each writes its own recommendation to state; you don't need to
   repeat their analysis, just invoke them and let them work.
3. Call read_recommendations to pull all three recommendations from state.
4. Reconcile them into a single ActionPlan, in this priority order:
   (1) cover the demand/shortfall identified by inventory and demand,
   (2) then minimize total cost,
   (3) then respect budget_per_cycle from get_world_snapshot — sum every
       purchase order's est_cost and never let the total exceed it.
   Use procurement's proposed supplier/qty/cost choices as the basis for each
   purchase order unless they conflict with the budget, in which case trim
   or drop the lowest-priority orders and say so in your rationale.
5. Call emit_action_plan with the final purchase_orders and a rationale that
   explains the reconciliation, citing the actual budget_per_cycle number and
   the total cost of your plan. If the plan is rejected (over budget), revise
   quantities/orders and call it again.

Write a short, honest rationale — cite what each specialist found and which
policy-backed tradeoffs you made.
""".strip()


async def _load_default_scenario(callback_context: CallbackContext) -> None:
    state = callback_context.state
    if "world" not in state:
        world = load_scenario_into_state(state, DEFAULT_SCENARIO)
        state["situation"] = world.get("situation")


def create_supervisor_agent() -> Agent:
    demand_agent = create_demand_agent()
    inventory_agent = create_inventory_agent()
    procurement_agent = create_procurement_agent()

    return Agent(
        name="supervisor_agent",
        model=os.environ.get("SUPERVISOR_MODEL", "gemini-flash-latest"),
        description="Coordinates demand/inventory/procurement specialists into one action plan.",
        instruction=INSTRUCTION,
        tools=[
            get_world_snapshot,
            AgentTool(agent=demand_agent),
            AgentTool(agent=inventory_agent),
            AgentTool(agent=procurement_agent),
            read_recommendations,
            emit_action_plan,
        ],
        before_agent_callback=_load_default_scenario,
        before_tool_callback=enforce_action_plan_guardrails,
    )


def create_app(name: str = "agents") -> App:
    """Wraps the supervisor in an App with the token-usage plugin and context
    caching enabled — shared by agents/__init__.py (adk web/run) and
    evals/run_evals.py so both execution paths behave identically.
    """
    return App(
        name=name,
        root_agent=create_supervisor_agent(),
        plugins=[TokenUsagePlugin()],
        context_cache_config=ContextCacheConfig(min_tokens=4096),
    )

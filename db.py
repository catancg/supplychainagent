"""Shared SQLite log store — persistence for accepted ActionPlans (written
by the supervisor via mcp_server/log_store.py) and eval results (written
directly by evals/run_evals.py, since that's driven by our own deterministic
harness, not an agent decision — see docs/phase1-db-mcp.prd §1).

Plain stdlib sqlite3, no ORM — two tables is simple enough that an ORM would
be pure overhead. docs/feature.prd's "no ORM" principle still holds; Phase 1
only reverses "no database".
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent / "data" / "supply_agents.db"

# action_plan_json has no NOT NULL constraint: a failed eval case (see
# evals/run_evals.py's error path) legitimately has no action plan at all.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS action_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  situation TEXT,
  purchase_orders_json TEXT NOT NULL,
  rationale TEXT,
  guardrail_trips_json TEXT NOT NULL,
  total_cost REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  case_name TEXT NOT NULL,
  scenario TEXT NOT NULL,
  description TEXT,
  layer_a_json TEXT NOT NULL,
  layer_a_passed INTEGER NOT NULL,
  layer_b_json TEXT,
  action_plan_json TEXT,
  guardrail_trips_json TEXT NOT NULL,
  error TEXT
);

-- Estimated USD cost per pipeline run (agents/pricing.py) — a harness-level
-- observability concern like eval grading, written directly by whichever
-- deterministic caller ran the pipeline (webapp or evals), not via MCP:
-- unlike action_plans (an agent-initiated write, mid-run, before total cost
-- is known), this is written once the run has fully finished.
CREATE TABLE IF NOT EXISTS run_costs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  source TEXT NOT NULL,            -- "webapp" or "eval"
  scenario TEXT NOT NULL,
  case_name TEXT,                  -- eval case name; NULL for webapp runs
  total_tokens INTEGER NOT NULL,
  cost_usd REAL NOT NULL,
  cost_by_agent_json TEXT NOT NULL
);
"""


def init_db(db_path: Path | None = None) -> None:
    """Creates the schema if it doesn't exist yet. Idempotent, safe on every startup."""
    db_path = db_path if db_path is not None else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)


@contextmanager
def _connect(db_path: Path | None) -> Iterator[sqlite3.Connection]:
    # Resolved here, not as a `= DB_PATH` default parameter value elsewhere —
    # a default bound to a module constant is captured once at function
    # definition time, so it would silently ignore any later reassignment of
    # DB_PATH (e.g. via monkeypatching in tests, or any caller that swaps the
    # module attribute instead of always threading db_path through).
    db_path = db_path if db_path is not None else DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def insert_action_plan(
    timestamp: str,
    situation: str | None,
    purchase_orders: list[dict],
    rationale: str,
    guardrail_trips: list[dict],
    db_path: Path | None = None,
) -> int:
    total_cost = sum(o.get("est_cost", 0) for o in purchase_orders)
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO action_plans
                (timestamp, situation, purchase_orders_json, rationale, guardrail_trips_json, total_cost)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                situation,
                json.dumps(purchase_orders),
                rationale,
                json.dumps(guardrail_trips),
                total_cost,
            ),
        )
        conn.commit()
        return cur.lastrowid


def insert_eval_result(
    timestamp: str,
    case_name: str,
    scenario: str,
    description: str | None,
    layer_a: list[dict],
    layer_a_passed: bool,
    layer_b: dict | str | None,
    action_plan: dict | None,
    guardrail_trips: list[dict],
    error: str | None,
    db_path: Path | None = None,
) -> int:
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO eval_results
                (timestamp, case_name, scenario, description, layer_a_json, layer_a_passed,
                 layer_b_json, action_plan_json, guardrail_trips_json, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                case_name,
                scenario,
                description,
                json.dumps(layer_a),
                1 if layer_a_passed else 0,
                json.dumps(layer_b) if layer_b is not None else None,
                json.dumps(action_plan) if action_plan is not None else None,
                json.dumps(guardrail_trips),
                error,
            ),
        )
        conn.commit()
        return cur.lastrowid


def insert_run_cost(
    timestamp: str,
    source: str,
    scenario: str,
    case_name: str | None,
    total_tokens: int,
    cost_usd: float,
    cost_by_agent: dict[str, float],
    db_path: Path | None = None,
) -> int:
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO run_costs
                (timestamp, source, scenario, case_name, total_tokens, cost_usd, cost_by_agent_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                source,
                scenario,
                case_name,
                total_tokens,
                cost_usd,
                json.dumps(cost_by_agent),
            ),
        )
        conn.commit()
        return cur.lastrowid


def _row_to_action_plan_entry(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "timestamp": row["timestamp"],
        "situation": row["situation"],
        "action_plan": {
            "purchase_orders": json.loads(row["purchase_orders_json"]),
            "rationale": row["rationale"],
        },
        "guardrail_trips": json.loads(row["guardrail_trips_json"]),
    }


def _row_to_eval_result_entry(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "timestamp": row["timestamp"],
        "case": row["case_name"],
        "scenario": row["scenario"],
        "description": row["description"],
        "layer_a": json.loads(row["layer_a_json"]),
        "layer_a_passed": bool(row["layer_a_passed"]),
        "layer_b": json.loads(row["layer_b_json"]) if row["layer_b_json"] else None,
        "action_plan": json.loads(row["action_plan_json"]) if row["action_plan_json"] else None,
        "guardrail_trips": json.loads(row["guardrail_trips_json"]),
        "error": row["error"],
    }


def _row_to_run_cost_entry(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "timestamp": row["timestamp"],
        "source": row["source"],
        "scenario": row["scenario"],
        "case": row["case_name"],
        "total_tokens": row["total_tokens"],
        "cost_usd": row["cost_usd"],
        "cost_by_agent": json.loads(row["cost_by_agent_json"]),
    }


def list_run_costs(limit: int | None = None, db_path: Path | None = None) -> list[dict]:
    """Most recent first."""
    query = "SELECT * FROM run_costs ORDER BY id DESC"
    if limit is not None:
        query += f" LIMIT {int(limit)}"
    with _connect(db_path) as conn:
        rows = conn.execute(query).fetchall()
    return [_row_to_run_cost_entry(r) for r in rows]


def list_action_plans(limit: int | None = None, db_path: Path | None = None) -> list[dict]:
    """Most recent first — matches the JSON logs' previous reversed-order behavior."""
    query = "SELECT * FROM action_plans ORDER BY id DESC"
    if limit is not None:
        query += f" LIMIT {int(limit)}"
    with _connect(db_path) as conn:
        rows = conn.execute(query).fetchall()
    return [_row_to_action_plan_entry(r) for r in rows]


def list_eval_results(limit: int | None = None, db_path: Path | None = None) -> list[dict]:
    """Most recent first."""
    query = "SELECT * FROM eval_results ORDER BY id DESC"
    if limit is not None:
        query += f" LIMIT {int(limit)}"
    with _connect(db_path) as conn:
        rows = conn.execute(query).fetchall()
    return [_row_to_eval_result_entry(r) for r in rows]

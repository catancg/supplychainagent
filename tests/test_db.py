"""Tests the SQLite log store (docs/phase1-db-mcp.prd). Every test uses a
temp DB file (pytest's tmp_path) — never touches the real data/supply_agents.db.
"""

from pathlib import Path

import db
from mcp_server.log_store import write_action_plan


def test_init_db_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    db.init_db(db_path)  # must not raise on a second call
    assert db_path.exists()


def test_insert_and_list_action_plans_roundtrip(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    row_id = db.insert_action_plan(
        timestamp="2026-07-12T00:00:00+00:00",
        situation="demand_spike",
        purchase_orders=[
            {"sku": "AC-12", "supplier": "S-DOM", "qty": 34, "dest_warehouse": "COR", "est_cost": 3400.0}
        ],
        rationale="AC-12 short at COR.",
        guardrail_trips=[],
        db_path=db_path,
    )
    assert row_id == 1

    entries = db.list_action_plans(db_path=db_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["situation"] == "demand_spike"
    assert entry["action_plan"]["purchase_orders"][0]["sku"] == "AC-12"
    assert entry["action_plan"]["rationale"] == "AC-12 short at COR."
    assert entry["guardrail_trips"] == []


def test_insert_and_list_eval_results_roundtrip(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    db.insert_eval_result(
        timestamp="2026-07-12T00:00:00+00:00",
        case_name="demand_spike",
        scenario="demand_spike",
        description="AC-12 spikes...",
        layer_a=[{"name": "within_budget", "passed": True, "detail": "ok"}],
        layer_a_passed=True,
        layer_b={"faithfulness": 5},
        action_plan={"purchase_orders": [], "rationale": "..."},
        guardrail_trips=[],
        error=None,
        db_path=db_path,
    )

    entries = db.list_eval_results(db_path=db_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["case"] == "demand_spike"
    assert entry["layer_a_passed"] is True
    assert entry["layer_a"][0]["name"] == "within_budget"
    assert entry["layer_b"] == {"faithfulness": 5}
    assert entry["error"] is None


def test_insert_eval_result_with_error_and_null_layer_b(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    db.insert_eval_result(
        timestamp="2026-07-12T00:00:00+00:00",
        case_name="supplier_down",
        scenario="supplier_down",
        description=None,
        layer_a=[],
        layer_a_passed=False,
        layer_b=None,
        action_plan=None,
        guardrail_trips=[],
        error="ServerError: 503 UNAVAILABLE",
        db_path=db_path,
    )

    entry = db.list_eval_results(db_path=db_path)[0]
    assert entry["error"] == "ServerError: 503 UNAVAILABLE"
    assert entry["layer_b"] is None
    assert entry["action_plan"] is None


def test_list_action_plans_newest_first(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    for situation in ["first", "second", "third"]:
        db.insert_action_plan(
            timestamp="2026-07-12T00:00:00+00:00",
            situation=situation,
            purchase_orders=[],
            rationale="",
            guardrail_trips=[],
            db_path=db_path,
        )

    entries = db.list_action_plans(db_path=db_path)
    assert [e["situation"] for e in entries] == ["third", "second", "first"]


def test_list_action_plans_respects_limit(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    for i in range(5):
        db.insert_action_plan(
            timestamp="2026-07-12T00:00:00+00:00",
            situation=f"situation-{i}",
            purchase_orders=[],
            rationale="",
            guardrail_trips=[],
            db_path=db_path,
        )

    assert len(db.list_action_plans(limit=2, db_path=db_path)) == 2
    assert len(db.list_action_plans(db_path=db_path)) == 5


def test_insert_action_plan_computes_total_cost(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    db.insert_action_plan(
        timestamp="2026-07-12T00:00:00+00:00",
        situation="demand_spike",
        purchase_orders=[
            {"sku": "AC-12", "supplier": "S-DOM", "qty": 10, "dest_warehouse": "COR", "est_cost": 1000.0},
            {"sku": "AC-12", "supplier": "S-DOM", "qty": 5, "dest_warehouse": "MDZ", "est_cost": 500.0},
        ],
        rationale="",
        guardrail_trips=[],
        db_path=db_path,
    )

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        total_cost = conn.execute("SELECT total_cost FROM action_plans").fetchone()[0]
    assert total_cost == 1500.0


def test_write_action_plan_mcp_tool_persists_a_row(tmp_path: Path, monkeypatch):
    # write_action_plan uses db.DB_PATH internally (no override param — it's
    # the MCP tool surface, called by the LLM, not a test-facing API), so
    # redirect the module-level path rather than passing one in.
    db_path = tmp_path / "mcp_test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db(db_path)

    result = write_action_plan(
        situation="demand_spike",
        purchase_orders=[
            {"sku": "AC-12", "supplier": "S-DOM", "qty": 34, "dest_warehouse": "COR", "est_cost": 3400.0}
        ],
        rationale="AC-12 short at COR.",
        guardrail_trips=[],
    )

    assert result == {"id": 1}
    entries = db.list_action_plans(db_path=db_path)
    assert len(entries) == 1
    assert entries[0]["situation"] == "demand_spike"
    assert "timestamp" not in result  # server stamps it internally, not echoed back
    stored_timestamp = entries[0]["timestamp"]
    assert stored_timestamp  # non-empty — the server did generate one

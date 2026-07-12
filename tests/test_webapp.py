"""Tests the webapp's read-only routes (index, scenario detail, history).

Deliberately does NOT test POST /scenarios/{id}/run — that triggers a real,
multi-minute, multi-dollar Gemini agent run. That's covered by manual/live
smoke testing, not the automated suite.
"""

from fastapi.testclient import TestClient

from webapp.main import app

client = TestClient(app)


def test_index_lists_all_scenarios():
    response = client.get("/")
    assert response.status_code == 200
    assert "normal" in response.text
    assert "demand_spike" in response.text
    assert "supplier_down_all_for_sku" in response.text


def test_scenario_detail_renders_skus_and_suppliers():
    response = client.get("/scenarios/demand_spike")
    assert response.status_code == 200
    assert "AC-12" in response.text
    assert "S-DOM" in response.text
    assert "demand_spike" in response.text


def test_scenario_detail_shows_eval_description_when_present():
    response = client.get("/scenarios/supplier_down_all_for_sku")
    assert response.status_code == 200
    assert "flag the gap" in response.text.lower()


def test_scenario_detail_unknown_id_returns_404():
    response = client.get("/scenarios/does-not-exist")
    assert response.status_code == 404
    assert "not found" in response.text.lower()


def test_history_page_renders_with_no_logs():
    response = client.get("/history")
    assert response.status_code == 200
    assert "Action log" in response.text
    assert "Eval log" in response.text

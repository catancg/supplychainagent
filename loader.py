"""Loads a scenario fixture (world snapshot + situation) into session state.

Scenarios are static JSON files under scenarios/ — see docs/feature.prd §3.
No database, no simulator: this is the entire "world" substrate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, MutableMapping

SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"


def resolve_scenario_path(scenario: str | Path) -> Path:
    """Resolve a scenario id ("demand_spike"), filename, or path to a JSON file."""
    path = Path(scenario)
    if path.suffix == ".json" and path.exists():
        return path
    candidate = SCENARIOS_DIR / f"{scenario}.json"
    if candidate.exists():
        return candidate
    if path.exists():
        return path
    raise FileNotFoundError(
        f"No scenario fixture found for '{scenario}' (looked in {SCENARIOS_DIR})"
    )


def load_scenario(scenario: str | Path) -> dict[str, Any]:
    """Load and parse a scenario fixture JSON file into a plain dict."""
    return json.loads(resolve_scenario_path(scenario).read_text(encoding="utf-8"))


def load_scenario_into_state(
    state: MutableMapping[str, Any], scenario: str | Path
) -> dict[str, Any]:
    """Load a scenario and write it to state["world"]. Returns the world dict."""
    world = load_scenario(scenario)
    state["world"] = world
    return world


def list_scenarios() -> list[str]:
    """List available scenario ids (filenames without .json) under scenarios/."""
    return sorted(p.stem for p in SCENARIOS_DIR.glob("*.json"))

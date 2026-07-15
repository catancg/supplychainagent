# Testing Guide

Minimal commands to verify each piece works. See [README.md](README.md) for
architecture/design context.

## Setup

```bash
uv sync
cp .env.example .env          # set GOOGLE_API_KEY
uv run python -m rag.ingest   # once — builds the RAG index
uv run pytest -q              # expect: 76 passed (no API key needed)
```

---

## 1. Run scenarios

```bash
uv run adk web .
# pick "agents", send: Produce an action plan for the current situation.
```
or, for a fuller trace view:
```bash
uv run uvicorn webapp.main:app --reload
# open http://127.0.0.1:8000, pick a scenario, click Run
```

## 2. Verify tools & state use

In the webapp's Result page (or `adk web`'s session-state inspector): every
tool call is listed in order. An amber **"state changed by `<tool>`"** row
appears right after any tool that wrote to session state (the `emit_*`
tools) — no amber row means it was read-only.

## 3. Verify RAG use

In the webapp trace, `search_policy` calls/results carry a cyan **"RAG"**
badge — confirms inventory/procurement are grounding in `kb/*.md` via
ChromaDB, not just raw scenario data.

## 4. Verify MCP use

```bash
uv run python -c "import db; db.init_db(); print(len(db.list_action_plans()), len(db.list_eval_results()))"
```
Run once before and once after a scenario run (§1) — `action_plans` count
should go up by 1. That row is written via the `write_action_plan` MCP tool
(`mcp_server/log_store.py`), not a direct DB call.

## 5. Verify sessions

Run a scenario in the webapp, stop the server (`Ctrl+C`), start it again,
then:
```bash
uv run python -c "
import asyncio
from google.adk.sessions import DatabaseSessionService
import db
async def main():
    svc = DatabaseSessionService(db_url=f'sqlite+aiosqlite:///{db.DB_PATH.as_posix()}')
    r = await svc.list_sessions(app_name='supply_agents_webapp', user_id='webapp_user')
    print('sessions:', len(r.sessions))
asyncio.run(main())
"
```
Expect count >= 1 — proves the session survived the restart, not just held
in memory.

## 6. Verify A2A

Two terminals:
```bash
uv run uvicorn a2a_demo.serve_peer:app --port 8001   # terminal 1
uv run python -m a2a_demo.call_peer                  # terminal 2
```
Expect terminal 2 to print the peer's lead-time answer (e.g. "9 days").
Standalone demo — not wired into scenario runs.

## 7. Verify ML inference is being used

```bash
uv run pytest tests/test_ml.py -v   # 9 tests, no API key needed
```
```bash
uv run python -c "
from loader import load_scenario
from tools.demand_tools import forecast_demand
class Ctx:
    def __init__(self, s): self.state = s
r = forecast_demand('AC-12', Ctx({'world': load_scenario('demand_spike')}))
old = round(0.4*r['historical_avg_daily_demand'] + 0.6*r['recent_avg_daily_demand'], 2)
print('ML forecast:', r['forecast_daily_demand'], '| old formula would be:', old)
"
```
If the two numbers differ, the trained model
(`ml/models/demand_forecast.joblib`) produced it, not the fallback formula.

---

## Troubleshooting

- `ImportError` on `adk web`/`adk run`: always use `uv run adk ...`, never
  bare `adk` — another install may be on PATH.
- Gemini `503`: transient, already retried automatically — just re-run.
- RAG looks empty: run `uv run python -m rag.ingest` first.

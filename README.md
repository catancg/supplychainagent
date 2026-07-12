# Supply Chain Multi-Agent System (MVP)

A multi-agent system in **Google ADK** where a supervisor coordinates three
specialists — **demand, inventory, procurement** — to produce a supply-chain
action plan for a static scenario fixture. See [docs/feature.prd](docs/feature.prd)
for the full spec; this README covers setup and how to run things.

## Setup

```bash
uv sync
cp .env.example .env   # then fill in GOOGLE_API_KEY
```

Get a key at https://aistudio.google.com/apikey. `.env` is git-ignored.

## Project layout

See `docs/feature.prd` §13. In short:

- `scenarios/*.json` — the whole "world": 12 fixtures, loaded via `loader.py`.
  Beyond the original `normal`/`demand_spike`/`supplier_down`, there are 9
  more covering distinct agent behaviors — see the table in "Evals" below.
- `tools/` — tiny deterministic functions (forecast, reorder point, supplier
  ranking, landed cost), including batch variants (`forecast_demand_for_all_skus`,
  `compute_reorder_points_for_all_skus`, `rank_and_cost_needs`) that sweep
  every SKU/need in one call instead of one call each. Pure, unit-tested, no
  LLM involved.
- `kb/` + `rag/` — policy corpus and RAG ingest/search (ChromaDB + Gemini
  embeddings).
- `mcp_server/market_data.py` — a local MCP server (stdio) exposing
  `get_fx_rate`, used by the procurement agent.
- `agents/` — the three specialists, the supervisor, Pydantic schemas, and
  guardrails. `agents/__init__.py` exposes `app` (the supervisor wrapped with
  the token-usage plugin and context caching — see `agents/observability.py`
  and `agents/supervisor_agent.py::create_app`) for `adk web`.
- `evals/` — the eval harness (Layer A deterministic assertions + Layer B
  LLM-as-judge) over all 12 scenarios.
- `webapp/` — a small FastAPI app (Jinja2 templates, no JS build step) that's
  a purpose-built alternative to `adk web`: browse scenarios, trigger a live
  run, and see the full trace (every tool call/result across the supervisor
  *and* all three specialists — `adk web`'s own event view can't show nested
  `AgentTool` sub-runs; this uses a plugin instead, see
  `agents/observability.py::TraceCollectorPlugin`) plus the final plan and
  run history.

## Run it

### 1. Ingest the policy corpus (once, or whenever `kb/*.md` changes)

```bash
uv run python -m rag.ingest
```

This embeds `kb/*.md` with Gemini text embeddings and upserts them into a
local Chroma store at `chroma_data/` (git-ignored, rebuildable any time).

### 2. Explore interactively with `adk web`

```bash
uv run adk web .
```

Open the printed URL, pick the `agents` app, and chat with it (e.g. "Produce
an action plan for the current situation"). The supervisor auto-loads the
scenario named in `SCENARIO_PATH` (`.env`, default `demand_spike`) the first
time it runs in a session. You can inspect `session.state` in the web UI to
see `world`, each `rec:*` recommendation, `action_plan`, and
`guardrail_trips` — the whole blackboard is visible there.

To try a different scenario, just ask the supervisor, e.g.:
"Load scenario supplier_down and produce an action plan" — note the current
build auto-loads on first turn only; switching scenarios mid-session isn't
wired as a tool yet (see docs/feature.prd's open questions).

### 3. Web UI (purpose-built alternative to `adk web`)

```bash
uv run uvicorn webapp.main:app --reload
```

Open http://127.0.0.1:8000. Three pages:

- **Scenarios** (`/`) — a card per scenario (SKU/warehouse/supplier counts,
  budget, any unavailable suppliers flagged, and the matching eval case's
  expected-behavior description if one exists) plus the 5 most recent
  action-log/eval-log entries.
- **Scenario detail** (`/scenarios/{id}`) — full SKU and supplier tables for
  that world, and a "Run" button.
- **Result** (after clicking Run) — the complete trace (every tool call and
  result, every resulting `state[...]` change, and every model text response,
  across the supervisor *and* all three specialists, in chronological order
  with elapsed time), the final recommendations per specialist, the action
  plan, and any guardrail trips. Two things are specifically highlighted:
  - **State changes** — an amber `state changed by <tool>` entry appears
    right after any tool call that mutated `session.state` (the `emit_*`
    tools, `emit_action_plan`), showing exactly which key changed and its
    before/after value. Read-only tools (the forecast/reorder/supplier-cost
    calculators, `get_world_snapshot`) never produce one.
  - **RAG usage** — `search_policy` calls/results get a cyan "RAG" badge and
    tinted background, so retrieval-grounded reasoning is visually
    distinguishable from plain deterministic tool calls or the MCP FX-rate
    call.

  Runs synchronously — a request takes ~1-2 minutes (real Gemini calls) and
  the page just waits; there's no live-streaming trace, by design (kept
  simple over building SSE/WebSocket streaming for a first version). Retries
  transient failures (Gemini 503s) up to twice before showing an error page
  with a retry button.
- **History** (`/history`) — every persisted `action_log.json` /
  `eval_log.json` entry, newest first, full JSON behind a `<details>` toggle
  (no JS needed).

Requires `GOOGLE_API_KEY` — clicking "Run" makes real Gemini calls, same as
`adk run`/`adk web`.

### 4. Run the MCP server standalone (sanity check)

```bash
uv run python -m mcp_server.market_data
```

Runs over stdio and blocks waiting for an MCP client — Ctrl+C to stop. In
normal use, the procurement agent launches this automatically as a subprocess
via `McpToolset`.

### 5. Unit tests (deterministic tools + guardrail validator + webapp routes)

```bash
uv run pytest
```

No API key needed — these test pure functions and the webapp's read-only
routes only. `POST /scenarios/{id}/run` (which triggers a real, multi-minute,
multi-dollar agent run) is deliberately not covered by the automated suite —
verify that one manually.

### 6. Evals

```bash
uv run python -m evals.run_evals            # all 12 cases
uv run python -m evals.run_evals demand_spike   # a single case
```

Runs the full supervisor → specialists → ActionPlan flow for each scenario,
then grades it:

- **Layer A (authoritative):** deterministic assertions on the ActionPlan.
  Exit code is non-zero if any Layer A assertion fails.
- **Layer B (directional):** an LLM judge scores the supervisor's rationale
  1–5 on faithfulness, constraint-adherence, and relevance. Informational
  only — it doesn't gate the run, and it's called once per case, every run
  (no flag to skip it currently).

Requires `GOOGLE_API_KEY` (real Gemini calls happen here). See
`evals/cases.py` for the exact assertions; each `EvalCase.description` states
the expected behavior in prose.

| Scenario | Tests |
|---|---|
| `normal` | Healthy baseline — expect an empty plan, no hallucinated orders |
| `demand_spike` | AC-12 spikes — expect substantial replenishment into the short warehouse(s) |
| `supplier_down` | AC-12's cheap supplier is down — expect it avoided, an alternate used |
| `demand_spike_small_item` | SP-25 (small item, not major appliance) spikes — tests category-specific policy |
| `supplier_down_all_for_sku` | AC-12 needs stock but ALL its suppliers are down — expect no order + gap flagged, never fabricate a supplier |
| `budget_tight_partial` | AC-12 shortfall but budget slashed to 5000 — expect the plan to respect budget over full coverage |
| `spike_and_supplier_down_same_sku` | AC-12 spikes AND its cheapest supplier is down simultaneously — compound case |
| `multi_sku_shortage_broad` | 3 unrelated SKUs (no spike) below reorder point at once — expect exactly those 3 ordered, nothing else |
| `warehouse_single_short` | AC-12 short at COR only — expect precision targeting, not a blanket 3-warehouse order |
| `zero_demand_edge_case` | HT-09 has all-zero demand history — tests the forecast/reorder-point divide-by-zero guard |
| `supplier_down_small_item` | FN-05's sole supplier (S-REG) is down — generalizes the "flag the gap" behavior beyond AC-12 |
| `healthy_tight_margins` | All-healthy again but with demand +20% vs. `normal` — regression guard against margin-dependent false positives |

## Guardrails, demonstrated

- **Budget:** `agents/guardrails.py::validate_action_plan` rejects a plan
  whose total cost exceeds `budget_per_cycle` — the supervisor must revise
  and resubmit.
- **Unavailable suppliers:** orders from an `available: false` supplier are
  clamped out of the plan before it's accepted.
- **Untrusted content:** `search_policy` (RAG) and `get_fx_rate` (MCP)
  results are wrapped as reference-only data and scanned for obvious
  prompt-injection phrases (`agents/guardrails.py::sanitize_untrusted_tool_output`)
  before reaching the model.

Every accepted (or rejected) plan, plus any guardrail trips, is appended to
`action_log.json` (git-ignored — it's a run artifact, not source).

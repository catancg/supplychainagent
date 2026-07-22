# Supply Chain Multi-Agent System (MVP)

A multi-agent system in **Google ADK**: a supervisor coordinates three
specialists — **demand, inventory, procurement** — to produce a supply-chain
action plan for a static scenario fixture. Full spec: [docs/feature.prd](docs/feature.prd).

**To run and verify everything, see [TESTING.md](TESTING.md).** For
architecture, design trade-offs, limitations, and future work, see
[REPORT.md](REPORT.md). This README is a quick architecture reference.

## Setup

```bash
uv sync
cp .env.example .env   # then fill in GOOGLE_API_KEY (https://aistudio.google.com/apikey)
```

## Project layout

- `scenarios/*.json` — 12 world fixtures, loaded via `loader.py`.
- `tools/` — deterministic functions (forecast, reorder point, supplier
  ranking, landed cost), incl. batch variants. Pure, unit-tested, no LLM.
- `kb/` + `rag/` — policy corpus + RAG ingest/search (ChromaDB + Gemini embeddings).
- `mcp_server/market_data.py` — MCP server exposing `get_fx_rate` (read-only).
- `mcp_server/log_store.py` — MCP server exposing `write_action_plan`, persists
  to `data/supply_agents.db` via `db.py`. See `docs/phase1-db-mcp.prd`.
- `db.py` — shared SQLite log store (`action_plans`, `eval_results`).
- `agents/` — the 3 specialists, supervisor, schemas, guardrails wiring.
  `agents/__init__.py` exposes `app` for `adk web`.
- `evals/` — eval harness (Layer A deterministic + Layer B LLM-judge) over
  all 12 scenarios.
- `webapp/` — FastAPI alternative to `adk web`: browse scenarios, trigger a
  run, see the full nested trace (state changes + RAG usage highlighted),
  browse history. See `agents/observability.py::TraceCollectorPlugin`.
  Sessions persist across restarts via `DatabaseSessionService`
  (`docs/phase1-session-persistence.prd`).
- `guardrails/` — YAML-driven rule engine (budget cap, supplier
  availability, quantity range, prompt-injection patterns), loaded from
  `guardrails/templates/default.yaml`. `agents/guardrails.py` is a thin
  wrapper over it. See `docs/phase1-guardrail-templates.prd`.
- `a2a_demo/` — standalone Agent2Agent protocol demo (peer + caller, two
  processes). Decoupled from the main pipeline. See `docs/phase1-a2a-demo.prd`.
- `ml/` — trained regression model backing `forecast_demand`, replacing the
  old fixed-weight formula. `ml/models/demand_forecast.joblib` is committed.
  See `docs/phase1-ml-demand-model.prd`.
- `agents/trigger_guard.py` — the worker-trigger security gate (see
  "Trigger security" below).
- `agents/pricing.py` — estimated USD cost per model call (see "Cost
  tracking" below).
- `agents/model_config.py` — automatic retry-on-transient-error for every
  Gemini call, including `adk web` (see "Transient-error retries" below).

## Eval scenarios

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

## Guardrails

- **Budget:** rejects a plan whose total cost exceeds `budget_per_cycle`.
- **Unavailable suppliers:** orders from an `available: false` supplier are clamped out.
- **Untrusted content:** `search_policy` (RAG) and `get_fx_rate` (MCP) results
  are wrapped as reference-only and scanned for prompt-injection phrases.

Rules are YAML config (`guardrails/templates/default.yaml`), not hardcoded —
see `docs/phase1-guardrail-templates.prd`. Every **accepted** plan is
persisted to `data/supply_agents.db` via the `write_action_plan` MCP tool;
rejected (over-budget) plans are not.

## Trigger security

**Every entry point — `adk web`, the webapp, and `evals.run_evals` —
executes the pipeline only on an exact match** of a fixed string
(`agents/trigger_guard.py::EXPECTED_TRIGGER_MESSAGE`, currently
`"Produce an action plan for the current situation."`). Anything else — a
greeting, a paraphrase, an embedded instruction trying to override
behavior — is **rejected before any model call happens**: verified live,
0 model calls, rejected in ~1ms. `strict_trigger=True` is the default on
`create_app()`/`create_supervisor_agent()`; pass `strict_trigger=False`
explicitly if you want an open, unrestricted chat for interactive
debugging (no caller does this by default anymore). Scenario data itself
is separately sanitized for injection-pattern text at load time
(`loader.py`), reusing the same rule engine that scrubs RAG/MCP output.

## Cost tracking

`TokenUsagePlugin` (`agents/observability.py`) estimates a **USD cost per
run** from token usage, using a hardcoded per-model rate table
(`agents/pricing.py`) — this is an estimate for cost-awareness, **not your
actual bill** (free-tier allowances, batch discounts, and pricing changes
aren't reflected). Printed per model call (`[cost] <agent>: $...`) and as a
per-run total, tracked both overall and per agent. Persisted to
`data/supply_agents.db`'s `run_costs` table by the webapp and
`evals.run_evals` (each pipeline invocation is one row); shown in the
webapp's Result page (per-run) and History page (`run_costs` table, across
all runs). `adk web` still prints the per-call console lines but nothing
persists or reads back its totals — it's driven by the ADK CLI, not this
project's runner code.

## Transient-error retries

Every agent (demand/inventory/procurement/supervisor, the A2A demo, and the
eval judge) is built via `agents/model_config.py::resilient_model()`/
`resilient_client()`, which attaches `google.genai.types.HttpRetryOptions`
(3 attempts, 2s initial delay, 15s max) to the Gemini model/client itself.
This is the SDK's **own** HTTP-level retry mechanism, not a custom ADK
plugin — its default retryable-status-code set (`408`, `429`, and `5xx`)
already excludes non-retryable 4xx errors (e.g. a `400 INVALID_ARGUMENT`
from a malformed request would only ever fail again, so it isn't retried).
Because it's configured on the model, not wrapped around a `Runner`, it
applies uniformly to **every** entry point — including `adk web`, which
previously had no retry logic at all and would kill the whole turn on a
single transient `503 "model overloaded"` error. The webapp/`evals.run_evals`
still additionally retry the *whole run* (`MAX_RETRIES=2`) as a coarser
fallback for failures this doesn't catch (non-model errors, e.g. an MCP
server hiccup).

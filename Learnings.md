# Learnings

Personal notes on things worth remembering about how this project works.

---

## 2026-07-22 — Session `state` is not one global object

**What I thought:** `state` is a single global variable/dict shared directly
by every agent (supervisor + all specialists).

**What's actually true:**

- `state` (`tool_context.state` / `callback_context.state`) is a dict-like
  structure (ADK's `State` class, wrapping a `dict[str, Any]`) — not an
  int, not a string. Keys are strings (`world`, `situation`, `rec:demand`,
  `rec:inventory`, `rec:procurement`, `action_plan`, `guardrail_trips`);
  values are whatever's needed (nested dicts, lists, plain strings).

- It is **not** one shared object across the whole agent tree. Every time
  the supervisor calls a specialist via `AgentTool`, ADK spins up a
  **separate sub-session with its own state dict**:
  1. At the start of the call, the specialist's state is seeded as a
     **snapshot copy** of the supervisor's state at that moment.
  2. While the specialist runs, every change it makes is streamed back and
     merged into the supervisor's real state **immediately, as it
     happens** — not batched at the end.

- Because the supervisor always `await`s each specialist before doing
  anything else (fully sequential, no concurrency), this copy-and-sync-back
  mechanism *behaves* exactly like one global dict in practice: each
  specialist's snapshot already contains everything every previously-called
  specialist wrote, in order. The "global" feeling is a real, reliable
  side-effect of sequential calling — not a coincidence, and not something
  to only trust for this project's current call order.

- This copy-per-invocation only happens at `AgentTool` boundaries (supervisor
  → specialist). A single agent's own direct tool calls (e.g. supervisor's
  own `get_world_snapshot`, `read_recommendations`, `emit_action_plan`) read
  and write the one real session state directly — no copying involved.

**Why this mattered concretely:** explains a trace oddity I noticed — the
webapp trace showed `state["rec:demand"]` changing `null → value` **twice**,
once tagged `demand_agent`/`emit_demand_recommendation` and once tagged
`supervisor_agent`/`demand_agent`. Not a bug: two distinct state dicts (the
specialist's sub-session and the supervisor's real session) both genuinely
made that same transition, one right after the other, because the plugin
watching for state changes is attached to both levels of nesting.

---

## 2026-07-22 — Why `SPECIALIST_MODEL` is `gemini-2.5-flash`, not `-flash-lite`

**Short summary:** Early in the project, agents were intermittently
returning **empty, zero-token responses**. First fix was tightening the
`emit_*` tools' vague `list[dict]` schemas to concrete Pydantic types —
that helped, but empty responses kept happening specifically on
**`gemini-2.5-flash-lite`**, after large tool results came back. Root cause
was the model itself, not the schema: `flash-lite` was unreliable under
that load. Fix: bumped `SPECIALIST_MODEL` to full `gemini-2.5-flash`, which
resolved it. That's also why `JUDGE_MODEL` is still on `flash-lite` today —
it's a lighter, less critical call that never hit this problem. Documented
directly in `.env.example`'s comments.

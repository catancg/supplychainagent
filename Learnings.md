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

---

## 2026-07-22 — A custom retry plugin wasn't needed; the SDK already has one

**What I proposed:** to fix `adk web` dying on a transient Gemini `503`
("model overloaded") with no retry at all, build a custom ADK plugin using
`on_model_error_callback` — catch the error, manually re-call the model,
return the response in place of the error.

**What's actually true:** ADK's plugin hook does exist and would have
worked, but `google-genai` (the underlying SDK) already ships its own
HTTP-level retry mechanism — `types.HttpRetryOptions`, attached directly to
a `Gemini` model instance (`Agent(model=Gemini(retry_options=...))`) or a
`genai.Client` (`http_options=HttpOptions(retry_options=...)`). Its default
retryable-status-code set is exactly `408`, `429`, and `5xx` — already
excluding the `400 INVALID_ARGUMENT` case from the corrupted-session
incident, which no amount of retrying would ever fix.

**Why this is the better fix, not just a simpler one:** because it's
configured on the model/client object itself rather than wrapped around a
`Runner`, it applies to `adk web` automatically — a custom plugin would
have needed to be registered specifically wherever `create_app()` is
called, the same opt-in dance already done for `strict_trigger`. This one
needs no such dance: `agents/model_config.py::resilient_model()` just
replaces the bare model-name string every agent was already passing.

**Lesson:** before building a custom mechanism against a framework's
extension points, check whether the *underlying SDK* already solves it —
ADK sits on top of `google-genai`, and the better answer was one layer
down.

---

## 2026-07-22 — Reversed: `adk web`'s open chat is now gated too

**What we decided earlier:** `strict_trigger` (the exact-match trigger gate)
should be opt-in — on for the webapp/evals, off for `adk web`, so `adk web`
stayed a genuinely open interactive dev tool.

**What changed:** after actually using `adk web` for a while (a "Hola"
message, then a message trying to get the agent to skip real analysis and
just say "everything is fine"), it became clear the open chat *was* the
injection surface the gate was built for in the first place — leaving it
exempt defeated a good chunk of the point.

**The fix:** flipped `strict_trigger`'s default from `False` to `True` in
both `create_supervisor_agent()` and `create_app()`, and made
`agents/__init__.py` (what `adk web` loads) pass it explicitly. Now every
entry point — `adk web` included — only executes on an exact match of
`EXPECTED_TRIGGER_MESSAGE` ("Produce an action plan for the current
situation."); anything else is rejected before any model call, verified
live in ~1ms. `strict_trigger=False` still exists as an explicit opt-out
for genuine interactive debugging, it's just no longer the default.

**Lesson:** a security default chosen for a good reason ("keep the dev
tool usable") can still be wrong once you actually watch how the tool gets
used — the decision was correct given what was known at the time, and
worth reversing once real usage showed the actual trade-off differently.

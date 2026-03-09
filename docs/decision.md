# Decision Log  (Keeli Framework v0.4.0)

Record every significant decision using the template below.

---

### TEMPLATE
**Date:** 2026-02-23
**Decision:** Implement Epics as `epic-<slug>.md` files in `docs/tasks/`
**Context:** We need a way to group related tasks together into larger milestones or epics.
**Alternatives Considered:**
1. A separate `docs/epics/` directory — rejected because it complicates the state machine and `keeli list` logic.
2. Using tags/labels — rejected because epics need their own description, scope, and lifecycle.
**Consequences:** Epics will be tracked as special tasks (`epic-<slug>.md`) and regular tasks will have an `**Epic:** <slug>` field to link them.

---

### ADR-002 — Immutable Task IDs + `.keeli_index.json` Ledger
**Date:** 2025-07-14
**Decision:** Assign every task/epic/story/bug/feature an immutable per-type ID using the format `T-0001` (task), `E-0001` (epic), `S-0001` (story), `BUG-0001` (bug), `FEAT-0001` (feat). Store a never-shrinking JSON ledger at `docs/.keeli_index.json`. Embed the ID in every `ai_log.md` entry.
**Context:** Two problems drove this:
1. The `docs/tasks/` directory grew indefinitely; completed work was noise during `keeli resume`.
2. There was no stable cross-reference between task files, archive, log entries, and code comments — making "grave digging" (finding what was done and why) slow and error-prone.
**Alternatives Considered:**
1. UUIDs — rejected: opaque to humans, not grep-friendly in logs.
2. Single global counter (KL-0001 for all types) — rejected: user preferred per-type prefixes for at-a-glance context.
3. Markdown ledger file — rejected in favour of JSON for machine-readable `keeli find` queries.
**Consequences:**
- `keeli complete` auto-archives the task file to `docs/tasks/archive/` and writes to the index.
- `keeli find <id-or-keyword>` queries the index without touching the file system.
- `keeli history <ID>` greps `ai_log.md` for all entries referencing that ID.
- `keeli digest --budget N` provides a token-budgeted context snapshot for LLM session starts.
- `keeli resume --nano` returns ~200 tokens (current in-progress task ID + title only) for tight-context editors.
- All MCP tools updated: `keeli_start` stamps IDs, `keeli_complete` auto-archives, new tools `keeli_find`, `keeli_history`, `keeli_digest`, `keeli_archive_task` added.

---

### ADR-004 — Hard Enforcement at CLI State Transitions vs. Soft LLM Governance
**Date:** 2026-02-24
**Decision:** Split enforcement into two distinct layers that must never be conflated:
1. **CLI hard enforcement** — structural completeness guards at state-transition commands (`keeli start`, `keeli progress`, `keeli review`, `keeli complete`, `keeli story`). The CLI validates field presence and checklist completion before mutating state, and exits with a clear error if the guard fails.
2. **LLM soft governance** — conversational rules (when in doubt ask, no guessing) live in `copilot-instructions.md` and `PERSONAS_MD`. These govern agent behaviour between commands; the CLI cannot enforce them because they require a human exchange.
**Context:** The project goal is zero hallucination and an auditable AI ledger. Markdown-only enforcement depends on the LLM self-governing — that is hope, not a guarantee. State transitions are command boundaries the CLI already owns; validation there is deterministic and testable.
**Alternatives Considered:**
1. Enforce everything in markdown/personas only — rejected: soft enforcement at every layer means a sufficiently confident LLM can skip gates silently.
2. Enforce everything in the CLI — rejected: "when in doubt ask" requires a human response; the CLI cannot generate that exchange and should not try.
3. Separate enforcement daemon / linter — rejected: adds runtime complexity. The CLI dispatch loop is the right boundary; no new process needed.
**Consequences:**
- `keeli start` (task linked to story): fails if parent story is missing `## Non-Functional Requirements` content or `## Test Strategy` content.
- `keeli progress`: fails if task Objective field is unfilled.
- `keeli review`: fails if @developer checklist has unchecked items.
- `keeli complete`: fails if @security checklist has unchecked items.
- `keeli story`: fails if parent epic is missing `## Non-Functional Requirements` content.
- All guards use the same `_validate_transition(path, rules)` helper — no guard logic duplicated across commands.
- Guards are tested with TDD before implementation. Each guard has a "missing field" test and a "passes when filled" test.
- Conversational governance (ask gates, STOP rules) stays in templates/personas — untouched.

---

### ADR-003 — MCP Streaming Notifications (S-1/S-2/S-3)
**Date:** 2026-02-24
**Decision:** Emit three structured MCP notifications per tool call: S-1 (session-start log), S-2 (progress during work), S-3 (completion log). Implemented via `_mcp_log` and `_emit_progress` async closures inside each `call_tool` handler. Guard every notification with a `try/except LookupError` to tolerate missing request context (e.g. unit tests).
**Context:** Agentic AI clients (Claude Desktop, Copilot) benefit from real-time feedback during long-running tasks. Without notifications, calls appear to hang and there is no audit trail in the session.
**Alternatives Considered:**
1. Return all output in the final `TextContent` only — rejected: no real-time visibility for the agent.
2. WebSocket-based streaming — rejected: MCP SDK already provides `send_log_message` and `send_progress_notification` on the session object; no new transport needed.
3. S-4 (cancellation) — deferred: requires `anyio` cancel-scope integration; not needed for v0.4.0.
**Consequences:**
- All nine `call_tool` handlers emit S-1/S-2/S-3.
- `tests/test_mcp_server.py` uses `AsyncMock` on `session.send_log_message` / `session.send_progress_notification` via `PropertyMock` on `app.request_context` to assert notifications.
- S-4 (cancellation support) is tracked in `epic-streaming-mcp-responses.md`.

---

### ADR-005 — LLM Compatibility Tier for Keeli Integration
**Date:** 2026-02-25
**Decision:** Document empirical LLM performance tiers for Keeli agentic integration. Do not gate or restrict any tool by model; instead surface this as guidance so users and CI pipelines can set expectations accordingly.

**Context:** Keeli's Five-Persona Architecture relies on the model correctly interpreting persona labels, respecting STOP gates, propagating task slugs across chains, and maintaining state via `ai_log.md` / task files. These behaviours require strong instruction-following, multi-step reasoning, and tool-chaining fidelity — capabilities that vary significantly across model families.

**Observed tiers (as of 2026-02):**

| Tier | Models | Behaviour |
|------|--------|-----------|
| **Tier 1 — Full fidelity** | Claude 3.x / 4.x (Sonnet, Opus) | Respects all five personas; honours STOP gates; auto-propagates `auto` slug sentinel; updates task state without prompting; HATEOAS hints followed correctly |
| **Tier 2 — Good with nudging** | Gemini 1.5/2.x Pro/Flash, Raptor Mini | Follows persona labels and most workflow steps; occasionally skips state updates or STOP gates; tool chaining works but may need explicit slug passed; HATEOAS hints followed ~80% of the time |
| **Tier 3 — Adequate** | GPT-4.1 | Executes individual keeli commands correctly; tends to bypass persona governance in long sessions; does not reliably self-propagate slugs between chain steps; `cwd`-mismatch issue requires `_find_project_root()` workaround (already implemented) |

**Alternatives Considered:**
1. Model-specific prompt variants — rejected: doubles maintenance burden; the Five-Persona instructions should be model-agnostic.
2. Hard-blocking lower-tier models from certain MCP tools — rejected: unnecessarily restrictive; tier guidance is sufficient.
3. Silence (no documentation) — rejected: gaps silently attributed to keeli bugs rather than model behaviour.

**Consequences:**
- `docs/project.md` notes the tier table so any session's onboarding step surfaces it.
- `@author` should reference these tiers in README usage examples.
- Future sessions that observe new model behaviour should update this ADR (append a dated row to the table).
- `_find_project_root()` CWD fix remains as a permanent mitigation for Tier 3.

---

### ADR-006 — Multi-Agent Orchestration: keeli as the Bus, not the Daemon
**Date:** 2026-02-25

**Context:** The Five-Persona Architecture currently runs as one LLM, one context window, with
persona labels as governance discipline. The question arose: should keeli force parallel/multi-agent
execution, or should a separate orchestrator be built?

Key observations:
1. "Multi-agent" does not require different LLMs — it can be the same model invoked in parallel
   coroutines or serialised sub-calls, each with a scoped system prompt.
2. `docs/tasks/*.md` and `ai_log.md` already function as a shared message bus and durable state
   store. Any agent (or any LLM call) that reads them knows precisely what work is in flight,
   who owns it, and what the acceptance criteria are.
3. The MCP server is already the natural orchestration surface — every tool call can be routed
   to any agent. The missing piece is a structured **persona handoff** message that a master
   agent can use to spawn a scoped sub-call.

**Decision:** Do NOT build a separate orchestrator process or service. Instead, extend the
**existing MCP server** with a `keeli_orchestrate(task_slug)` tool that emits a structured
persona handoff payload. The keeli files remain the coordination layer; keeli provides the
API on top of them.

**Proposed `keeli_orchestrate` contract:**
```json
{
  "task_id": "T-0003",
  "task_slug": "implement-words-module",
  "current_status": "Backlog",
  "required_persona": "@developer",
  "system_prompt_hint": "You are @developer. Implement strictly within the interface defined ...",
  "context_snapshot": "## Objective\n...\n## Checklist\n...",
  "suggested_next_tool": "keeli_progress",
  "suggested_next_args": {"task_slug": "implement-words-module"},
  "blocking_reason": null
}
```

The master agent calls `keeli_orchestrate`, receives this payload, constructs a sub-call
(same LLM or different) with the `system_prompt_hint` injected as the system role, lets it
work, then polls `keeli_next` for the next handoff. The persona sub-agent uses normal keeli
tools (`keeli_progress`, `keeli_complete`, `keeli_log`) to write results back — closing the loop.

**Why not a separate orchestrator?**
1. A daemon/service adds infrastructure with no benefit over the MCP server that already
   exists and is already connected to every agentic client.
2. A separate process must replicate the task-state reading logic already in `main.py` —
   duplicating the source of truth.
3. The files-as-bus model means any external system (GitHub Actions, a cron job, a custom
   script) can already "orchestrate" by shelling out to `keeli next` and reading the handoff.

**When a separate orchestrator IS warranted:**
- If you need true parallelism (multiple personas working simultaneously on independent tasks)
  — but even then, a thin async wrapper around `keeli_orchestrate` MCP calls suffices.
- If you need cross-project orchestration spanning multiple keeli repos — out of scope for v0.4.

**Consequences:**
- `keeli_orchestrate` tool to be added to `mcp_server.py` (new task: T-0007).
- The `required_persona` field maps to a short system prompt fragment stored in `docs/personas.md`
  (already exists) so the orchestrating agent can inject it without hallucinating persona rules.
- ADR-005 tier table remains relevant: the quality of sub-agent execution still depends on
  the model used for each persona call.
- `keeli_orchestrate` is purely a READ operation — no state is mutated until the sub-agent
  calls `keeli_progress` / `keeli_complete`.

---

### ADR-007 — Gate Items, `keeli tick`, and Epic/Story Skip in `keeli next`
**Date:** 2026-02-26
**Decision:** Three related agent-friction fixes shipped together:
1. **Gate-item concept**: A checklist line is a *gate item* if it contains `@security` or `@author`. Gate items must NOT be auto-ticked and must NOT block automated `review`/`complete` transitions — they require explicit human sign-off.
2. **`keeli tick <slug>`**: New command that ticks all non-gate `- [ ]` items in a task file and reports how many gate items remain for human action.
3. **`keeli next` skips `epic-*` and `story-*` files**: Epics and stories are planning/coordination artifacts. An agent calling `keeli next` should only receive leaf implementation tasks.

**Context:** During project-2 validation (`/tmp/todo-cli`), observed three agent friction points:
- Agents had to raw-edit task files to check checklist boxes before every `review`/`complete` call — no CLI primitive existed for this.
- The guard blocked on `@security sign-off` items an agent can never fulfil, making the full lifecycle unreachable without human edit or unsafe blanket `.replace("- [ ]", "- [x]")`.
- With an epic at P1 and a task at P2, `keeli next` surfaced the epic — the agent was handed a planning artifact, not implementable work.

**Alternatives Considered:**
1. *Remove the checklist guard entirely* — rejected: the guard enforces the TDD checklist discipline that is central to keeli's value; making it optional defeats the purpose.
2. *Separate `keeli gate-approve` instead of skipping gate items* — rejected: an automated agent cannot perform a human sign-off; the right model is to let the agent complete mechanical work and explicitly signal what remains for humanshandoff.
3. *Make `keeli next` configurable with a `--include-epics` flag* — rejected: surfacing epics is never the right default for an agent; a human running `keeli list` can see epics if needed.

**Consequences:**
- `_GATE_KEYWORDS = ("@security", "@author")` and `_is_gate_item(line)` added to `main.py`.
- `cmd_review` and `cmd_complete` guard lambdas now skip gate items.
- `cmd_tick` added; wired in dispatch table and argparser.
- `_get_next_task` skips filenames starting with `epic-` or `story-`.
- 8 new tests; 177/177 passing.

---

### ADR-008 — Hierarchy Enforcement (Epic > Story > Task)
**Date:** 2026-03-07
**Status:** Approved; Pending Implementation
**Decision:** Enforce the Epic > Story > Task hierarchy at CLI state-transitions. Tasks are NOT standalone; every task must link to both an epic and a story via `**Epic:**` and `**Story:**` metadata fields. Validation guards are added to `cmd_progress()` and `cmd_complete()`.

**Context:** Tasks were created as standalone items, causing orphaned tasks that nobody knew how to prioritize or contextualize. The Five-Persona Architecture requires clear scope boundaries; a task without a parent story has no acceptance criteria and no assigned personas.

**Alternatives Considered:**
1. Make epic/story optional — rejected: defeats the organizational benefit of hierarchy.
2. Auto-create dummy stories for orphaned tasks — rejected: hides the problem; the user should fix it.
3. Warn without blocking — rejected: soft warnings are ignored; hard enforcement is clearer.

**Consequences:**
- `keeli start --epic <slug> --story <slug>` becomes mandatory; both flags required.
- `_validate_hierarchy(task_slug)` helper checks that referenced epic/story files exist.
- `cmd_progress(slug)` and `cmd_complete(slug)` call `_validate_hierarchy(slug)` before state change.
- Tasks with missing epic or story cannot transition; user must fill the fields first.
- 15 new TDD tests for hierarchy paths.
- Refactoring script provided in `ADR-008_IMPLEMENTATION_GUIDE.md` for existing projects.

---

### ADR-009 — Simplified Persona Handshakes (File-First, No Tool Calls)
**Date:** 2026-03-07
**Status:** Approved; Pending Implementation
**Decision:** Abandon MPC sign-off tool calls (e.g., `keeli_po_sign_off`, `keeli_architect_sign_off`). Instead, personas sign off by editing the task file directly: fill their assigned section + mark the handshake table row. Validation at `keeli_complete()` checks that all four persona rows are marked.

**Context:** Tool call overhead (invoke → wait for response → parse) is 1-2 seconds per call. With 4 handshake calls per workflow, this compounds to unacceptable latency for agentic AI loops. File edits are native LLM operations (instant, no tool overhead). HATEOAS hints directly in task files guide the workflow without tool latency.

**Alternatives Considered:**
1. Keep MPC tool calls; optimize them — rejected: tool latency is structural; optimization gains are small (<20%).
2. Async tool calls (fire-and-forget) — rejected: no way to validate success; state would be unauditable.
3. Merge handshakes into a single tool call instead of five — rejected: still 1-2s latency; LLM still blocked.

**Consequences:**
- 5 MPC handlers (`keeli_po_sign_off`, `keeli_architect_sign_off`, `keeli_developer_sign_off`, `keeli_security_sign_off`, `keeli_author_sign_off`) are deleted.
- Handshake table remains in task file; LLM updates it via direct file edit.
- `**Handshake Status:**` field tracks: `backlog` → `@po_pending` → `@po_approved` → `@architect_pending` → ... → `@security_approved` → ready to archive.
- `_handshake_all_signed_off(content)` helper validates all 4 checkboxes are marked.
- `cmd_complete()` calls `_handshake_all_signed_off(content)` and fails with clear error if any persona is missing.
- HATEOAS hints in task template guide LLM through sign-off sequence without tool overhead.
- 20 new TDD tests for handshake validation.

---

### ADR-010 — REJECTED: MCP-Tool-Heavy Workflow
**Date:** 2026-02-28
**Status:** ❌ REJECTED (Replaced by ADR-011)
**Reason for Rejection:** User feedback: "MPC tools significantly slow agents." Analysis confirmed tool call overhead (1-2s per call × 4-6 mutations per workflow = 4-12s total) is unacceptable for agentic loops. ADR-010 proposed 5 new sign-off tools, which would make latency worse. Superseded by ADR-011 (File-First approach).

---

### ADR-011 — File-First, LLM-Native Workflow
**Date:** 2026-03-07
**Status:** ✅ Approved; Phase 1 Implementation Complete
**Decision:** Shift from "MCP tools as primary interface" to "files as interface; MCP tools as helpers." LLMs edit task files natively (instant, no tool overhead). MCP tools reserved for read-only operations only: `keeli_next` (query index), `keeli_analyze` (TF-IDF), `keeli_digest` (context), `keeli_chain` (multi-step), `keeli_log` (safe append). Validation pushed to CLI boundaries (`keeli progress`, `keeli_complete`).

**Context:** ADR-010 (MCP-tool-heavy) was designed assuming tools are the primary interface. Empirical testing showed tool call latency compounds across workflows: call → wait → response → parse → continue = ~1-2s per mutation. With 4-6 mutations per task workflow, total latency 4-12 seconds — killing agent velocity.

**Key Insight:** LLMs are natively fast at file operations (read, edit, write). Pushing state mutations through tool calls adds unnecessary round-trip latency. File edits are instant; validation at CLI boundaries is deterministic and testable.

**Alternatives Considered:**
1. Keep ADR-010; optimize tool latency — rejected: fundamental overhead is structural.
2. Async tool calls (agent doesn't wait) — rejected: unauditable; agent cannot confirm success.
3. Hybrid: some mutations via tools, some via file edit — rejected: inconsistent model confuses agents.

**Consequences:**
- `keeli_complete()` validates handshakes locally (fast file read).
- Handshakes enforced via file edits + HATEOAS hints (no tool calls).
- Task templates include HATEOAS guidance for workflow.
- MCP tools reduced from 13 to 8 (delete 5 sign-off tools, keep 8 query/utility tools).
- Result: ~10-20x faster agent workflows (0.5s per task vs 4-12s with ADR-010).
- Full specification: `ADR-011_FILE_FIRST_LLM_NATIVE.md` (700+ lines, approved design).

---

### ADR-012 — Lean Instructions + Persona Hooks (On-Demand Loading)
**Date:** 2026-03-07
**Status:** ✅ Approved; Phases 1–2 Implementation Complete
**Decision:** Split bloated `.github/copilot-instructions.md` into lean core (~300 lines) + on-demand persona hooks. Personas load only when assigned to a task (via `**Persona:**` field). Task files include HATEOAS links to `docs/personas.md ## <persona>`.

**Context:** Copilot instructions were 2,000+ lines with all 5 persona definitions embedded. LLMs loaded every persona for every task, wasting 73% of tokens on irrelevant rules. @po rules were loaded even for @developer tasks (waste). Progressive disclosure principle: show only what's needed now.

**Design (File-First):**
- `.github/copilot-instructions.md`: ~300 lines, lean core framework + "Persona Activation Hook" section.
- `docs/personas.md`: Full persona definitions (unchanged); ONLY read when assigned.
- `keeli_next()` includes `"persona": "@developer"` field with hint to load that section.
- Task templates include HATEOAS comment explaining hook mechanism.

**Alternatives Considered:**
1. Keep all personas in copilot-instructions, compressed — rejected: pruning loses nuance; problem is presence, not verbosity.
2. Dynamic instruction generation per persona — rejected: adds latency and complexity; static hints are simpler.
3. Silence (no change) — rejected: token waste hurts agentic loop velocity.

**Consequences:**
- Copilot instructions trim from 2,000+ lines to ~300 lines.
- Base instruction size: 4,000 tokens → 600 tokens (85% reduction).
- Personas load on demand via file reference (no tool overhead).
- HATEOAS hints guide LLMs through activation mechanism.
- `keeli_next()` response includes `"persona"` and `"persona_hint"` fields.
- Task templates updated with persona hook comments.
- 8 new TDD tests; all passing.
- Scalable: adding 6th, 7th persona does NOT bloat base instructions.
- Implementation split into 3 phases: Phase 1 (CLI + templates), Phase 2 (documentation), Phase 3 (cleanup).

---

<!-- Add new decisions above this line -->

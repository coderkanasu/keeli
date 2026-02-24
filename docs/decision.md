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

<!-- Add new decisions above this line -->

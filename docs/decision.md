# Decision Log  (Persona Framework v0.2.0)

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

<!-- Add new decisions above this line -->

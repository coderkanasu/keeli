# Epic: Streaming MCP Responses

**Status:** Backlog
**Priority:** P2
**Created:** 2026-02-23T20:44:14Z
**Completed:** —
**Persona:** @architect

## Objective
**Goal:** Replace the current fire-and-forget MCP responses with progressive,
streaming-aware responses so that LLM agents and IDE integrations receive
live feedback during long-running Keeli operations.

**Why:** Today every MCP tool call blocks silently until completion. For fast
operations this is fine, but for `keeli_analyze` (TF-IDF corpus scan),
`keeli_digest` (token budget assembly), and future batch operations, agents
experience a dead wait with no indication of progress. Streaming lets agents
display incremental output, cancel early, and surface partial results —
improving perceived responsiveness and enabling richer agentic workflows.

**Success Criteria:**
- Agents receive at least one intermediate message before the final result
  for any operation taking >500 ms
- `keeli_analyze` emits a progress percentage as it scores each document
- `keeli_digest` streams each assembled section as it is built
- Cancellation via `CancelledNotification` stops work and returns what was
  built so far
- All existing sync tools continue to work unchanged (no regression)

**Out of Scope:**
- Streaming for instant operations (keeli_next, keeli_log, keeli_find)
- WebSocket transport — SSE + stdio only in this epic
- Client-side rendering / IDE plugin work

## Scope

**In scope:**
- `ProgressNotification` on `keeli_analyze` (document N of M, score emitted)
- Chunked `TextContent` streaming on `keeli_digest` (section-by-section)
- `LoggingMessageNotification` for verbose operation logs (replaces print stmts)
- Graceful cancellation handling in all streamed tool handlers
- Unit tests for progress emission using MCP SDK test helpers

**Out of scope:**
- New transport implementations (WebSocket, HTTP chunked)
- Streaming on CRUD tools (start, complete, archive, find, history)
- Client SDK changes or IDE-specific integration work
- Batching / parallelising the TF-IDF corpus scan itself

## Stories

### S-1: Progress notifications on keeli_analyze
**As a** developer using Copilot agent mode,
**I want** `keeli_analyze` to emit `ProgressNotification` messages as it scores
each document in the corpus,
**so that** I can see "Scoring doc 3/12 — skills.md" rather than waiting in silence.

**Acceptance Criteria:**
- [ ] `keeli_analyze` sends a `ProgressNotification` with `progress` (0–100) and
  `total` for each document scanned
- [ ] Progress token is taken from the MCP request's `_meta.progressToken` if present;
  silently skipped if absent
- [ ] Final `TextContent` result is unchanged from current format
- [ ] Test: mock corpus of 5 files → assert 5 progress notifications emitted

### S-2: Streaming section output on keeli_digest
**As an** LLM agent starting a new session,
**I want** `keeli_digest` to yield each assembled section (Active tasks, Project
overview, Backlog, Recent log) as it is built,
**so that** I can begin reading context before the full budget is assembled.

**Acceptance Criteria:**
- [ ] `keeli_digest` yields one `TextContent` chunk per section as it is appended
- [ ] Final chunk includes the token summary line (`~N tokens (budget: B)`)
- [ ] If `--budget` is exhausted mid-section the partial section is still emitted
- [ ] Behaviour is identical to current single-response output when reassembled
- [ ] Test: assert chunks arrive in order and concatenate to the same string as
  the current non-streaming output

### S-3: LoggingMessageNotification for verbose server logs
**As a** developer debugging the MCP server,
**I want** server-side log lines emitted as `LoggingMessageNotification` rather
than discarded,
**so that** I can see what Keeli is doing inside the MCP inspector / IDE log panel.

**Acceptance Criteria:**
- [ ] A `_mcp_log(level, message)` helper wraps `LoggingMessageNotification`
- [ ] `keeli_start`, `keeli_complete`, `keeli_archive_task` emit an INFO log on success
- [ ] Error paths emit ERROR level instead of (or in addition to) the error TextContent
- [ ] Log emission is conditional — no-op when there is no active session context
- [ ] Test: successful `keeli_start` call asserts exactly one INFO notification emitted

### S-4: Cancellation support for streaming tools
**As an** agent that has started a `keeli_analyze` or `keeli_digest` call,
**I want** to be able to cancel it mid-stream via `CancelledNotification`,
**so that** the server stops doing work and I can pivot without waiting.

**Acceptance Criteria:**
- [ ] Streamed handlers check for cancellation between each emitted chunk
- [ ] On cancellation: work stops, a final `TextContent` with "⚠️ Cancelled after
  N/M items" is returned
- [ ] Non-streamed tools are unaffected
- [ ] Test: send cancel after first progress notification → assert work halted

## Checklist
- [x] Objective and scope defined
- [x] User stories created (`keeli story --epic streaming-mcp-responses`)
- [x] Each story has acceptance criteria
- [ ] All linked stories completed
- [ ] @security sign-off
- [ ] @author docs updated
- [ ] Log completion in docs/ai_log.md

## Notes
**MCP SDK availability (verified 2026-02-24):**
- `ProgressNotification` / `ProgressNotificationParams` ✅ in `mcp.types`
- `TaskStatusNotification` / `TaskStatusNotificationParams` ✅ in `mcp.types`
- `LoggingMessageNotification` / `LoggingMessageNotificationParams` ✅ in `mcp.types`
- `CancelledNotification` ✅ in `mcp.types`

**Implementation order:** S-1 → S-3 → S-2 → S-4 (progress first, logging second,
digest streaming third, cancellation last — each story is independently shippable).

**Risk:** MCP SDK's async server context may require injecting the session/request
context into the tool handler to emit notifications. @architect to validate the
correct emission pattern (direct server.send vs request-scoped context) before S-1
implementation begins.

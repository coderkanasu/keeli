# Keeli AI Learning Log — Invisible State Machine Iterations

**Purpose:** Track lessons learned in each iteration toward invisible state management.  
**Format:** Each iteration: what was implemented, what failed, what worked, next steps.  
**Not Git-tracked:** This stays outside docs/ for rapid iteration.

---

## Iteration 1: Clean Template Reset (2026-03-11T03:35Z)

**Goal:** Establish baseline with honest templates (no hallucinations)

**What was implemented:**
- ✅ Deleted old 44KB bloated templates.py
- ✅ Created 12KB lean templates: Epic/Story/Task (no handshake tables, no aspirational sections)
- ✅ Regenerated fresh docs/, .github/ from clean templates
- ✅ Created demo Epic E-0001, Task T-0001 to verify flow

**What failed:**
- ❌ Old templates referenced `TASK_CHECKLISTS`, `STORY_TEMPLATE`, `EPIC_TEMPLATE` that didn't exist initially
- ❌ templates.py was missing `BUG_TEMPLATE`, `FEATURE_TEMPLATE`, `get_flavor_instructions()`, `STACK_PRESETS`
- ❌ `cmd_story()` still had interactive prompts (asking for role, goal, reason)

**What worked:**
- ✅ Simple Epic/Story/Task hierarchy flows naturally
- ✅ Lean markdown templates render cleanly
- ✅ `keeli list` shows tasks with epic/story relationships
- ✅ Task IDs auto-allocated (E-0001, T-0001, etc.)

**Key lesson:**
Templates must export ALL symbols that main.py imports, or keeli breaks on init.

**Next steps for Iteration 2:**
1. Implement `keeli_state.db` (SQLite backend) instead of MD files
2. Add git pre-commit hook validation
3. Remove interactive prompts from story/task creation
4. Auto-detect persona from git context (author → assigned persona)

---

## Iteration 2: SQLite State Foundation (2026-03-11T03:55Z)

**Goal:** Move Keeli toward invisible state management by making SQLite the live state source while keeping generated markdown as disposable views.

**What was implemented:**
- ✅ Added `keeli_state.db` initialization during `keeli init`
- ✅ Added SQLite tables for `state_meta`, `work_items`, and `audit_events`
- ✅ Synced `epic`, `story`, `task`, `bug`, and `feature` creation into SQLite
- ✅ Synced lifecycle transitions (`progress`, `review`, `complete`, `archive`, `reopen`) into SQLite
- ✅ Updated `keeli list` and `keeli status` to prefer SQLite-backed state
- ✅ Simplified `cmd_story()` to stop forcing interactive role/goal/reason prompts
- ✅ Replaced stale command tests with a lean suite that validates filesystem + SQLite state
- ✅ Replaced stale MCP tests with a lean async suite for `keeli_start`, `keeli_next`, `keeli_progress`, and `keeli_complete`
- ✅ Deleted `templates_old.py` to remove dead implementation baggage

**What failed:**
- ❌ The first SQLite upsert used `item_id` conflict handling only; forced overwrites hit a slug uniqueness error
- ❌ MCP server still used the old checklist/objective template contract after the CLI moved on
- ❌ Several old tests were asserting removed concepts: handshake tables, checklist ticking, five-persona instructions

**What worked:**
- ✅ A single task now exists in both markdown and SQLite without dual-entry friction
- ✅ Completion and reopen flows keep archive state and database state aligned
- ✅ Freshly generated projects now expose the new storage mode immediately via `keeli status`
- ✅ The learning loop is now preserved outside generated folders, so delete/reinit cycles are safe
- ✅ Forced reset verification passed: delete `.github`, `docs`, and `keeli_state.db`, run `keeli init --force`, then create epic → story → task and advance task state successfully

**Key lesson:**
Generated docs can be ephemeral, but the executable truth must be centralized. The moment the template contract changes, CLI, MCP, and tests all have to move together or the iteration collapses.

**Next steps for Iteration 3:**
1. Add git hook installation in `keeli init` for passive validation
2. Introduce automatic state transitions from commit/test signals
3. Add PII scanning/redaction before audit logging
4. Decide whether markdown tasks remain editable artifacts or become read-only projections from SQLite

---

## Iteration 3: Passive Validation Hook (2026-03-11T04:10Z)

**Goal:** Make the invisible-guardrail story true by installing a real pre-commit hook and enforcing basic passive validation through the CLI.

**What was implemented:**
- ✅ Added `.git/hooks/pre-commit` installation during `keeli init` when a git repo is present
- ✅ Added `keeli validate-task-state` command for hook-driven validation
- ✅ Validation now fails when leaf work exists but no task is active
- ✅ Validation now scans provided file paths for obvious email/secret patterns
- ✅ Added tests for hook installation, active-task validation, and PII scan failure

**What failed:**
- ❌ The first reset verification command used multi-word `story` flags incorrectly; reran with the simplified non-interactive story path
- ❌ Completing the passive-validation task surfaced an older in-progress task from a previous generated state, which means reset discipline still needs stronger cleanup semantics for active work

**What worked:**
- ✅ Full test suite stayed green after adding passive validation (`30 passed`)
- ✅ Delete/reinit loop recreated `.github`, `docs`, `keeli_state.db`, and `.git/hooks/pre-commit` successfully
- ✅ Happy-path validation passed on an active in-progress task
- ✅ Failure-path validation correctly rejected a sample file containing an email address

**Key lesson:**
Invisible state management needs two layers: a durable store and a policy entrypoint. The pre-commit hook is the first real policy edge, but reset safety also requires cleaning or reconciling leftover active tasks after regeneration.

**Next steps for Iteration 4:**
1. Reconcile or auto-close stale in-progress tasks after reset/reinit cycles
2. Add structured redaction before writing audit events, not just path-level scanning
3. Decide whether `validate-task-state` should auto-create a stub task when no active item exists
4. Begin replacing manual `progress` with passive state transitions driven by git/test signals

---

## Iteration 4: Stale Reconciliation + Audit PII Redaction (2026-03-11T04:30Z)

**Goal:** Close the ghost-task gap from Iteration 3 and add structured PII protection at the audit write path — no sensitive data should ever enter `audit_events` even if the caller doesn't sanitize.

**What was implemented:**
- ✅ Added `_db_reconcile_stale_items()`: after every `_db_sync_all_task_files()`, detect DB rows whose `source_path` no longer exists on disk and auto-archive them with `status='Archived'`
- ✅ Wired reconciliation into `cmd_init` via `_db_sync_all_task_files()` — runs transparently on every `keeli init --force`
- ✅ Added `_redact_pii(text)`: strips emails, AWS key IDs, and secret-like assignments from any string before it enters the audit trail
- ✅ Wired `_redact_pii()` directly into `_db_log_event()` — every audit write is automatically sanitized
- ✅ Fixed `cmd_init` output to print both `pre-commit` and `post-commit` alongside the one-liner: `Git hooks installed: .git/hooks/pre-commit, .git/hooks/post-commit`
- ✅ Added `TestStaleReconciliation` (2 tests): verifies ghost rows get archived and audit event is written
- ✅ Added `TestPiiRedaction` (3 tests): verifies email, AWS key, and secret-like values are redacted in `audit_events`

**What failed:**
- ❌ Nothing — all 3 new test classes passed on first run
- ❌ Minor: init output for hooks was cosmetically inconsistent before the fix (only showed `pre-commit`, not `post-commit`)

**What worked:**
- ✅ Full test suite: **38 passed** (up from 33)
- ✅ Stale row detection: deleting `docs/` then reinitting correctly archived the In Progress ghost row and wrote an `auto-archived` audit event
- ✅ PII redaction: `admin@example.com` → `[REDACTED-EMAIL]`, `AKIAIOSFODNN7EXAMPLE` → `[REDACTED-AWS-KEY]`, `token=supersecretvalue123` → `token=[REDACTED]`
- ✅ Forced delete/reinit cycle: both hooks installed, correct output message, validate + capture still worked

**Key lesson:**
The redaction layer belongs at the lowest common write point (`_db_log_event`), not at every call site. Any attempt to redact at individual callers will miss edge cases. Centralizing it means all future audit writes get it for free.

**Next steps for Iteration 5:**
1. Semantic commit→task linking: if commit message matches `closes T-XXXX` or `keeli:complete`, auto-advance the task to Review/Completed
2. `keeli sync` command: rebuild the full SQLite table from current markdown files (useful after manual edits)
3. Auto-stub creation in `validate-task-state`: when no active task exists but leaf work is present, offer a stub "Working on uncommitted changes" task
4. Test runner integration: hook into pytest post-run to flip active task from In Progress → Review when all tests pass

---

## Iteration 5: Passive Transitions (2026-03-11T12:45Z)

**Goal:** Convert passive guardrails into passive transitions so state can advance automatically from commit and test signals.

**What was implemented:**
- ✅ Added semantic transition parsing to `capture-commit-state`:
	- `keeli:complete` in commit subject auto-runs completion/archive on active task
	- `closes T-XXXX` matching the active item ID auto-moves active task to Review
- ✅ Added `keeli sync` command to rebuild `work_items` from markdown (`DELETE` + resync)
- ✅ Added `validate-task-state --auto-stub` to auto-create/restore `working-on-uncommitted-changes` and mark it In Progress when pending leaf work exists with no active item
- ✅ Added `keeli test [pytest args...]` command:
	- runs pytest
	- on pass, auto-moves first active In Progress leaf task to Review
	- exits with pytest's return code
- ✅ Parser updated to forward unknown CLI flags to `keeli test` (so `keeli test -q` works naturally)

**What failed:**
- ❌ First end-to-end run failed validation due to hierarchy mismatch (task linked to story without epic)
- ✅ Fixed by recreating the task with both `--story` and `--epic`, then reran pipeline successfully

**What worked:**
- ✅ Unit suite expanded from 38 → **43 passed**
- ✅ New tests cover: auto-stub creation, sync rebuild, commit semantic review/complete transitions, and test-pass auto-review
- ✅ Forced reset cycle passed with real workflow:
	- `keeli test -q --no-header` ran and auto-transitioned active task to Review
	- `keeli capture-commit-state` captured active commit metadata
	- `keeli sync` rebuilt DB and preserved expected 3-item hierarchy

**Key lesson:**
Passive state automation is now practical when transition semantics are explicit and deterministic. The only brittle edge remains intent detection from free-form commit text; this should evolve toward explicit structured markers.

**Next steps for Iteration 6:**
1. Add `keeli transition-from-commit --subject ...` as a pure evaluator for deterministic testing and CI usage
2. Support multi-item close markers in one commit (`closes T-0001, T-0002`) with safe fan-out rules
3. Add `--dry-run` to `keeli sync` and `keeli test` to preview transitions before mutation
4. Mirror transition events into MCP responses for AI-driven orchestration visibility

---

## Iteration 6: Deterministic Commit Evaluator + Dry-Run Controls (2026-03-11T13:05Z)

**Goal:** Make passive transitions predictable and CI-friendly by separating "evaluate" from "apply", then expose that transition intent to MCP clients.

**What was implemented:**
- ✅ Added pure evaluator command: `keeli transition-from-commit --subject "..."`
	- returns deterministic JSON with inferred actions and active item context
	- no state mutation unless `--apply` is passed
- ✅ Added multi-item closes parsing (`closes T-0001, T-0002`) and safe fan-out apply behavior
	- only non-archived leaf items currently `In Progress` are transitioned to `Review`
	- missing/archived/non-leaf/non-in-progress items are skipped with explicit reason
- ✅ Added `--dry-run` for `keeli sync`
	- previews rebuild item count without mutating SQLite
- ✅ Added `--dry-run` for `keeli test`
	- previews pytest command and potential transition target
	- exits 0 without running pytest
- ✅ Extended parser behavior so `keeli test -q` forwards flags naturally to pytest
- ✅ MCP visibility improvement:
	- `keeli_progress` / `keeli_complete` responses now include structured `Transition events` JSON block
	- new MCP tool `keeli_transition_from_commit` returns evaluation + applied transitions payload

**What failed:**
- ❌ One test initially failed due to mixed stdout (task creation output before JSON parse)
- ✅ Fixed by extracting JSON payload from first `{` in captured output before parsing

**What worked:**
- ✅ Full suite expanded from 43 → **48 passed**
- ✅ Forced reset verification succeeded end-to-end:
	- evaluator produced stable JSON without mutations
	- `--apply` transitioned both referenced tasks to Review via multi-ID closes marker
	- `sync --dry-run` and `test --dry-run` previewed behavior without side effects

**Key lesson:**
The evaluator/apply split removes ambiguity and makes transitions testable. Once transition intent is explicit JSON, both CLI and MCP automation become easier to reason about and safer to orchestrate.

**Next steps for Iteration 7:**
1. Add optional body/footer scanning for conventional commits (`Fixes:` / `Closes:` trailers) beyond subject line
2. Add per-item dry-run diff output (before/after status) for `transition-from-commit --apply --dry-run`
3. Expose transition events in `keeli capture-commit-state` as machine-readable JSON output mode
4. Add conflict handling when multiple active tasks exist and commit intent is ambiguous

---

## Iteration 7: Trailer Parsing + Ambiguity Guardrails (2026-03-11T13:20Z)

**Goal:** Make commit transitions robust under real commit formats and safe under ambiguous multi-active states.

**What was implemented:**
- ✅ Extended commit evaluator to read both subject and optional body/trailers
	- Supports `Fixes: T-0001`, `Closes: T-0002`, `Resolves: T-0003`
	- Keeps deterministic `evaluation.actions` output
- ✅ Added dry-run transition diff mode:
	- `keeli transition-from-commit --apply --dry-run`
	- Returns per-item preview entries with `before`, `after`, `would_apply`, and `reason`
- ✅ Added JSON output mode for commit capture:
	- `keeli capture-commit-state --json`
	- Emits structured payload including commit hash/subject/body, evaluation, and transition event lines
- ✅ Added ambiguity conflict handling when multiple active tasks exist:
	- If commit intent uses `keeli:complete` without explicit target and >1 active task, operation is blocked with a conflict message
	- Conflict details include active items; no transition is applied

**What failed:**
- ❌ Two new tests initially failed because stdout contained non-JSON lines before payloads
- ✅ Fixed by parsing from first JSON object boundary in captured output

**What worked:**
- ✅ Full test suite increased from 48 → **52 passed**
- ✅ Forced reset verification confirmed:
	- Trailer-based ID extraction (`Fixes:` body) works
	- `--apply --dry-run` previews correct per-item status diffs
	- Ambiguous `keeli:complete` with two active tasks is blocked safely
	- `capture-commit-state --json` returns structured machine-readable output

**Key lesson:**
Transition safety requires explicit intent under concurrency. Blocking ambiguous write transitions is better than guessing target state, especially once automation hooks are active.

**Next steps for Iteration 8:**
1. Add explicit target override support (e.g., `--target-id T-0001`) for `keeli:complete` in multi-active contexts
2. Add `--json` output modes for `transition-from-commit` and `test` parity consistency (currently already JSON for transition command; align full command metadata schema)
3. Include transition IDs/events in `docs/ai_log.md` entries for easier audit correlation
4. Add MCP tool for `capture-commit-state` to expose commit+transition payload remotely

---

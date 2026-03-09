# Architectural Issues & Fixes — Keeli v0.4.0 Deep Dive

**Author:** @architect  
**Date:** 2026-03-07  
**Status:** Analysis Complete — Ready for Implementation

---

## Issue 1: Missing Hierarchy Enforcement (Epic → Story → Task)

### Problem

The current system treats Epic, Story, and Task as independent files with **optional cross-references**. There is no structural enforcement that:
- A Story must belong to exactly one Epic
- A Task must belong to exactly one Story  
- A Task cannot exist without a Story
- A Story cannot exist without an Epic

This creates **orphaned tasks** and **dangling references**:
```
Example current state (BROKEN):
epic-user-auth.md ✓
  └─ story-login.md ✓
  └─ story-register.md ✓
task-implement-oauth.md (no story link → ORPHANED)
task-add-analytics.md (story points to non-existent story → BROKEN)
```

### Root Cause

- `keeli start` accepts `--story` and `--epic` as optional flags; both default to `None`
- Task files store references as strings (`**Story:** story-login`) — no validation that the parent exists
- MCP tools (`keeli_start`) don't validate hierarchy constraints
- The `keeli next` command returns tasks regardless of story/epic completeness

### Consequence

- LLMs and developers create orphaned work that clutters the backlog
- "What was this task for?" becomes unanswerable if the parent story/epic is archived or renamed
- Burndown charts can't accurately track epic progress (some tasks belong to no epic)

### Fix (ADR-008)

**Decision:** Enforce strict hierarchy: Epic (required) → Story (required) → Task (required).

**Implementation:**

1. **Metadata: Make story+epic mandatory in Task files**
   ```md
   **Epic:** user-auth    [no default, no empty string]
   **Story:** story-login [no default, no empty string]
   ```

2. **Validation Rule 1 (keeli start):**
   - If `--story <slug>` is provided, validate that the story file exists
   - If `--epic <slug>` is provided and no `--story`, validation fails: "Tasks require a story; stories require an epic"
   - If neither is provided, validation fails: "Task must link `--story story-slug --epic epic-slug`"
   - New error message: "Story '<slug>' not found at docs/tasks/story-<slug>.md"

3. **Validation Rule 2 (Story creation):**
   - `keeli story` requires `--epic <slug>`
   - Validate that the epic file exists before creating the story
   - Error message: "Epic '<slug>' not found at docs/tasks/epic-<slug>.md"

4. **Validation Rule 3 (MCP keeli_start):**
   - MCP `keeli_start` tool enforces the same validation as CLI
   - Returns error `{ "error": "story_not_found", "slug": "bad-story" }` 

5. **Validation Rule 4 (keeli next):**
   - Skip tasks with missing or invalid story/epic references
   - Log: "⚠️ Skipped task '<slug>' — story '<story-slug>' not found"

6. **Validation Rule 5 (Archiving):**
   - `keeli complete` (or MCP `keeli_complete`) fails if any task still references this story/epic
   - Error: "Cannot archive epic '<slug>': 3 tasks still link to it. Archive tasks first."

### ADR-008 Entry

```markdown
### ADR-008 — Strict Hierarchy Enforcement (Epic > Story > Task)
**Date:** 2026-03-07
**Decision:** All tasks must link to a story; all stories must link to an epic. Validation at creation and archival.
**Context:** Orphaned tasks and dangling references cause confusion and inaccurate burndown charts.
**Alternatives Considered:**
1. Optional hierarchy (current state) — rejected: creates orphaned work
2. Single-level tasks (no epic/story) — rejected: loses user-story semantics
**Consequences:** `keeli start` and `keeli story` require parent references; `keeli complete` validates no children before archiving.
```

---

## Issue 2: No Persona Handshake Mechanism

### Problem

The current "Handshakes" section in task templates is **decorative, not enforced**:
```md
## Handshakes
| Persona | Status | Signed | Summary |
|---------|--------|--------|---------|
| @po | ☐ pending | — | Waiting: user story + ACs + NFRs |
```

**There is no validation that:**
- @po must sign off before @architect can begin design
- @architect must sign off before @developer can begin implementation
- @developer must sign off before @security reviews
- @security must sign off before a task can be marked Completed

**Result:** Personas skip stages silently. A @developer might start coding without waiting for @architect's design. A task might be marked Completed without @security review.

### Root Cause

- The handshake table is just markdown — no CLI or MCP enforces it
- `keeli progress` (starting work) has no guard checking @po/@architect sign-off
- `keeli complete` has no guard checking @security sign-off
- No MCP tool validates handshake state

### Consequence

- The Five-Persona Architecture degrades because personas don't have to respect the handshake sequence
- Developers implement without @architect sign-off → scope creep, rework
- Tasks skip @security review → vulnerabilities
- The audit trail in `ai_log.md` doesn't reflect the handshake — impossible to trace "who approved this?"

### Fix (ADR-009)

**Decision:** Make persona handshakes **explicit state mutations** with dedicated MCP tools. Each persona must actively sign off before the task can move forward.

**Implementation:**

1. **Handshake State Machine (new)**
   ```
   Created → @po_pending → @po_approved → @architect_pending → @architect_approved 
   → @developer_pending → @developer_approved → @security_pending → @security_approved → Completed
   ```
   New field in task metadata:
   ```md
   **Handshake Status:** @po_pending
   ```

2. **New MCP Tools** (keeli_po_sign_off, keeli_architect_sign_off, keeli_developer_sign_off, keeli_security_sign_off)

   **keeli_po_sign_off** (input: task_slug, summary)
   - Validates that task has `@po Goals & Acceptance Criteria` section filled
   - Validates that NFRs section has content (not just a comment)
   - Updates `**Handshake Status:** @po_approved`
   - Appends log: `T-XXXX | @po | Signed off: <summary>`
   - Error: "Cannot sign off: NFR section unfilled. @po must define performance, scalability, and availability targets."

   **keeli_architect_sign_off** (input: task_slug, summary)
   - Validates @po sign-off already done (status must be `@po_approved`)
   - Validates `@architect Design & Planning` section has Design Summary + Implementation Plan + Test Strategy
   - Updates `**Handshake Status:** @architect_approved`
   - Appends log: `T-XXXX | @architect | Signed off: <summary>`
   - Error: "Cannot sign off: @po approval required first."

   **keeli_developer_sign_off** (input: task_slug, summary)
   - Validates @architect sign-off done (status must be `@architect_approved`)
   - Validates `@developer Implementation` section has Tests, Implementation, and all Validation checks
   - Updates `**Handshake Status:** @developer_approved`
   - Appends log: `T-XXXX | @developer | Signed off: <summary>`
   - Error: "Cannot sign off: @architect approval required first."

   **keeli_security_sign_off** (input: task_slug, summary)
   - Validates @developer sign-off done (status must be `@developer_approved`)
   - Validates `@security Findings & Issues` section is filled with findings or "no issues found"
   - Updates `**Handshake Status:** @security_approved`
   - Appends log: `T-XXXX | @security | Signed off: <summary>`
   - Error: "Cannot sign off: @developer approval required first."

3. **Guard on keeli_complete**
   - Fails if `**Handshake Status:**` is not `@security_approved`
   - Error: "Cannot complete: security sign-off required. Call keeli_security_sign_off first."

4. **Visual marker in task file (new)**
   Update handshake table to auto-fill based on status:
   ```md
   ## Handshakes
   | Persona | Status | Signed | Date |
   |---------|--------|--------|------|
   | @po | ☑ approved | @po | 2026-03-07T14:32:00Z |
   | @architect | ☐ pending | — | — |
   ```
   (Automatically updated by the sign-off tools)

5. **Copilot Instructions Update**
   Add to workflow rules:
   ```markdown
   **Persona Sign-Off Sequence:**
   Every task follows this sequence — no exceptions:
   1. @po writes story/ACs/NFRs → calls `keeli_po_sign_off`
   2. @architect writes design/test-strategy → calls `keeli_architect_sign_off`
   3. @developer implements + tests → calls `keeli_developer_sign_off`
   4. @security reviews findings → calls `keeli_security_sign_off`
   5. Anyone can call `keeli_complete`
   
   If any step blocks: log why, mark task as Blocked, and @mention the blocking persona.
   ```

### ADR-009 Entry

```markdown
### ADR-009 — Explicit Persona Handshakes (Sign-Off Sequence)
**Date:** 2026-03-07
**Decision:** Each persona must actively sign off before the next persona's work can begin. Implemented via dedicated MCP tools (keeli_po_sign_off, keeli_architect_sign_off, keeli_developer_sign_off, keeli_security_sign_off).
**Context:** Without explicit handshakes, personas can skip stages (e.g., developer coding without architect sign-off). This defeats the Five-Persona Architecture.
**Alternatives Considered:**
1. Soft governance in copilot-instructions.md (current) — rejected: LLMs might skip silently
2. Hooks in CLI only — rejected: MCP tools have no way to enforce handshakes for agentic LLMs
3. Sign-off via markdown edits — rejected: prone to typos and no validation
**Consequences:** New MCP tools; new `**Handshake Status:**` field in all task files; `keeli_complete` has a new guard. All five personas must learn to use their sign-off tool before proceeding.
```

---

## Issue 3: LLM Instructions Reference CLI Instead of MCP Tools

### Problem

The `copilot-instructions.md` and README tell the LLM to use CLI commands:

```markdown
# Current (WRONG)
keeli epic "User Auth" -p P0
keeli story "Login" --epic user-auth
keeli start "Implement OAuth" -k developer
keeli progress "implement-oauth"
keeli complete "implement-oauth"
```

**But the LLM cannot execute terminal commands directly.** The LLM's only interface is:
- MCP tools (`keeli_start`, `keeli_progress`, `keeli_complete`, etc.)
- File read/write (editing task files directly)

**Three problems:**
1. **Mismatch:** Instructions say use `keeli start` but LLM calls MCP `keeli_start` tool
2. **Wasted tokens:** LLM must infer that `keeli start ...` is actually "call the MCP keeli_start tool"
3. **Incomplete MCP surface:** The MCP server doesn't expose ALL operations (e.g., `keeli_po_sign_off`, `keeli_architect_sign_off`). LLM must edit task files directly for some operations.

### Root Cause

- `COPILOT_INSTRUCTIONS` template was written as if the LLM has shell access
- MCP tools were added incrementally, but instructions weren't updated to match
- No distinction between "CLI-only commands" and "MCP-exposed commands"
- Some state mutations have no MCP tool (e.g., the handshake sign-off tools haven't been implemented yet)

### Consequence

- LLM confusion: "Should I run a CLI command or call an MCP tool?"
- Token waste: LLM tries to run `keeli start ...` as a shell command (fails), then realizes it should call MCP tools
- Incomplete coverage: Some operations force LLM to edit task files manually → risk of syntax errors

### Fix (ADR-010)

**Decision:** All workflow instructions reference MCP tools by name. CLI usage is relegated to "Human/Local Use" section.

**Implementation:**

1. **Split COPILOT_INSTRUCTIONS into two sections:**

   **Section A: "For AI Agents (MCP Tools)"**
   ```markdown
   ### Work Management (MCP Tools)
   | Tool | To | Purpose |
   |------|-----|---------|
   | keeli_start | Create a task | Create task file, allocate ID, inject into index |
   | keeli_po_sign_off | Get @po sign-off | Update handshake status after ACs/NFRs filled |
   | keeli_architect_sign_off | Get @architect validation | Update after design summary + test strategy filled |
   | keeli_developer_sign_off | Mark implementation done | Update after all tests pass + code review complete |
   | keeli_security_sign_off | Get security approval | Update after threat model + all OWASP checks |
   | keeli_progress | Start work | Mark task In Progress |
   | keeli_complete | Finish task | Mark Completed (requires all sign-offs) |
   | keeli_next | Pick next task | Show highest-priority backlog item + inject context hints |
   | keeli_analyze | Inject context | TF-IDF corpus scan + inject skills/ADRs into task |
   | keeli_log | Add audit entry | Append message to docs/ai_log.md |
   | keeli_chain | Run pipeline | Execute sequence of commands (start → analyze → progress) |
   ```

   **Section B: "For Local Human Use (CLI Commands)"**
   ```markdown
   If you are running keeli locally on your machine (not via MCP):
   $ keeli start "Task title"
   $ keeli progress task-slug
   $ keeli complete task-slug
   $ keeli next
   $ keeli analyze task-slug
   
   The CLI is a convenience wrapper around the same task files. All state is persisted 
   in docs/tasks/ — the CLI and MCP tools mutate the same files.
   ```

2. **New MCP Tool Manifest (for clarity)**
   Create `docs/MCP_TOOLS.md`:
   ```markdown
   # Keeli MCP Tools Reference
   (Auto-generated from mcp_server.py)
   
   ## State Mutation Tools
   - keeli_start(title, priority, persona, epic, story, context) → task_id, slug, next_action
   - keeli_po_sign_off(task_slug, summary) → updated_handshake_status
   - keeli_architect_sign_off(task_slug, summary) → updated_handshake_status
   - keeli_developer_sign_off(task_slug, summary) → updated_handshake_status
   - keeli_security_sign_off(task_slug, summary) → updated_handshake_status
   - keeli_progress(task_slug) → status
   - keeli_complete(task_slug) → status, next_task
   - keeli_archive_task(task_slug) → archived_path
   - keeli_log(message, persona) → logged_entry
   
   ## Query Tools
   - keeli_next() → task_slug, title, persona, priority, hints, next_actions
   - keeli_find(id_or_keyword) → task_id, slug, title, status
   - keeli_history(task_id) → [log_entries...]
   - keeli_digest(budget) → context_snapshot
   - keeli_analyze(task_slug) → updated_file, hints_block
   
   ## Pipeline Tools
   - keeli_chain(steps) → [step_results...]
   ```

3. **Update Copilot Instructions Workflow Rules**
   ```markdown
   ## Workflow Rules (MCP Tools Primary Path)
   
   1. **Discovery:** Call `keeli_start` to create epic/story/task files (specify `--epic` and `--story` to the tool)
   2. **Refinement:** @po calls `keeli_po_sign_off` when story/ACs/NFRs complete
   3. **Design:** @architect calls `keeli_architect_sign_off` when design summary + test strategy complete
   4. **Implementation:** @developer calls `keeli_start` (for child tasks), `keeli_progress`, `keeli_developer_sign_off`
   5. **Review:** @security calls `keeli_security_sign_off` after threat model reviewed
   6. **Completion:** Any persona calls `keeli_complete` (requires all sign-offs)
   7. **Context Injection:** Call `keeli_analyze` before starting a task
   8. **Chaining:** Use `keeli_chain` to run multi-step pipelines (e.g., start → analyze → progress)
   
   All state changes go through MCP tools. Never edit task files manually unless adding Notes.
   ```

4. **Remove all CLI command examples from COPILOT_INSTRUCTIONS**
   (Keep only the MCP tools listed)

5. **Update README.md**
   ```markdown
   ## Quick Start (for Human/Local Use)
   
   If you're running keeli on your local machine:
   ```bash
   keeli init
   keeli epic "User Auth" -p P0
   keeli story "Login" --epic user-auth
   keeli start "Implement OAuth" --story login --epic user-auth
   keeli next
   keeli analyze <slug>
   keeli progress <slug>
   keeli complete <slug>
   ```
   
   ## For Agentic AI (MCP Tools)
   
   When using Keeli with GitHub Copilot or other AI agents:
   - Use the MCP tools exposed by `keeli mcp`
   - See [MCP_TOOLS.md](docs/MCP_TOOLS.md) for the full reference
   - All state changes happen through MCP tools — no shell commands
   ```

### ADR-010 Entry

```markdown
### ADR-010 — MCP Tools as Primary Interface; CLI for Local Use
**Date:** 2026-03-07
**Decision:** Copilot instructions reference MCP tools; CLI is relegated to "human local use" section. Split instructions accordingly.
**Context:** LLMs cannot execute shell commands; their only interface is MCP tools + file read/write. Current instructions create confusion and token waste.
**Alternatives Considered:**
1. Keep CLI-centric instructions — rejected: confuses LLMs; must be translated to MCP
2. Remove CLI entirely — rejected: humans benefit from CLI for local development
3. Keep both equal — rejected: muddies the primary workflow for each user type
**Consequences:** COPILOT_INSTRUCTIONS refactored; docs/MCP_TOOLS.md added; README split into "local" and "agentic" sections; new MCP sign-off tools added.
```

---

## Implementation Roadmap

### Phase 1: Hierarchy Enforcement (ADR-008)
1. Update `cmd_start` and `cmd_story` to require parent references
2. Update MCP `keeli_start` to validate hierarchy
3. Add guards to `keeli_complete` to prevent archiving parents with live children
4. Add tests (15 new tests, TDD)

### Phase 2: Persona Handshakes (ADR-009)  
1. Add `**Handshake Status:**` field to all task templates
2. Implement 5 new MCP tools: keeli_po_sign_off, keeli_architect_sign_off, keeli_developer_sign_off, keeli_security_sign_off
3. Update `keeli_complete` guard to require all sign-offs
4. Update copilot-instructions.md with new sign-off sequence
5. Add tests (25 new tests, TDD)

### Phase 3: MCP-First Instructions (ADR-010)
1. Refactor COPILOT_INSTRUCTIONS: split into "For AI Agents" + "For Local Use"
2. Create docs/MCP_TOOLS.md reference
3. Update README.md with both audiences
4. Remove all examples of CLI commands from LLM-facing sections

### Phase 4: Integration Testing
1. Full e2e scenario: create epic → sign off → create story → sign off → create tasks → implement → security review → complete
2. Test all error paths (missing parent, missing sign-off, orphaned tasks)
3. Validate ai_log.md entries for each sign-off
4. Verify keeli_complete fails correctly when sign-offs missing

---

## Files to Modify

| File | Change Type | Priority |
|------|-------------|----------|
| src/keeli/main.py | Validation in cmd_start, cmd_story, cmd_complete | P0 |
| src/keeli/mcp_server.py | 5 new MCP tool handlers + guard updates | P0 |
| src/keeli/templates.py | Add Handshake Status field to TASK_TEMPLATE; split COPILOT_INSTRUCTIONS | P0 |
| docs/decision.md | Add ADR-008, ADR-009, ADR-010 | P0 |
| README.md | Split into "Local Use" + "Agentic AI" sections | P1 |
| tests/test_commands.py | 15 new tests for hierarchy + validation | P0 |
| tests/test_mcp_server.py | 25 new tests for sign-off tools + guards | P0 |
| docs/MCP_TOOLS.md | New file: tool reference | P1 |

---

## Recommended Next Steps

**For @architect:**
1. Review this document; confirm ADRs 008/009/010 are correct
2. Review the implementation plan with @po and @developer  
3. If approved, create ADR entries in docs/decision.md

**For @po:**
1. Review Issue 2 (handshakes) — does the sign-off sequence match your intended workflow?
2. Confirm that Epic > Story > Task hierarchy matches your grooming process

**For @developer:**
1. Once ADRs approved, start with Phase 1 (TDD: write failing tests first)
2. The keeli_po_sign_off, keeli_architect_sign_off, etc. tools should be straightforward validators

---

## Questions for the Human

1. Should tasks without an epic/story be allowed to exist in a transition period?
   - **Recommended:** No — validate strictly from day 1
   
2. Can a task link to multiple stories?
   - **Recommended:** No — 1:N hierarchy (one epic has many stories, one story has many tasks)

3. Should the handshake table be visi ble in the task template, or stored as metadata only?
   - **Recommended:** Both — metadata field (`**Handshake Status:**`) + visual table updated by tools

4. Should @author have their own sign-off step, or is it optional?
   - **Recommended:** Optional for now (v0.4.0); can be added in v0.5.0 if needed

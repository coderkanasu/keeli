# ADR-011: File-First, LLM-Native Workflow (Replaces ADR-010)

**Date:** 2026-03-07  
**Status:** Approved  
**Decision:** Abandon MCP tool wrappers for state mutations. Instead: LLMs edit task files directly; MCP tools for read-only operations only (keeli_next, keeli_analyze, keeli_digest, keeli_chain).

---

## Context

The initial ADR-010 proposed making MCP tools the primary interface, with LLMs calling tools like `keeli_po_sign_off()`, `keeli_architect_sign_off()`, etc.

**Problem observed:** Each MCP tool call adds latency:
- Call the tool (delay)
- Wait for response (delay)
- Proceed to next step (delay)

Across a typical workflow (create → analyze → progress → review → complete), this multiplies the total turnaround time. For stateless AI agents doing many sequential operations per session, this overhead is unacceptable.

**Alternative:** Let the LLM operate **natively on files** (fast, direct, no round-trips), reserving MCP tools only for operations that require **server-side computation** or **context injection**.

---

## Decision

### What LLMs Can Edit Directly (No MCP Tool)

- **Handshake sign-offs:** @po edits the task file, filling ACs/NFRs, then marks `- [x] @po signed off` in the handshake table
- **Implementation plan:** @architect writes directly into the task file
- **Code + tests:** @developer writes code (no MCP wrapper needed)
- **Security findings:** @security documents directly in the task file
- **Status transitions:** Edit `**Status:** Backlog` → `**Status:** In Progress` manually

**Why:** These are pure markdown edits. The LLM has direct file access. No computation needed.

### What Stays as MCP Tools (Read-Only / Computed)

- **keeli_next()** → Read task index, compute priority, inject context hints
- **keeli_analyze()** → TF-IDF corpus scan, inject AI Context Hints block
- **keeli_digest()** → Token-budgeted context snapshot for session start
- **keeli_chain()** → Execute sequential operations (start → analyze → progress)
- **keeli_find()** → Query task index by ID/keyword
- **keeli_history()** → Query ai_log entries for a task
- **keeli_log()** → Append to audit trail (idempotent, safe)

### Validation Layers (Shifted)

**During LLM workflow:** No hard validation — trust the LLM to follow the process  
**At CLI boundaries:** Hard validation when humans run `keeli progress`, `keeli complete`, etc.  
**Example:** 
```bash
# Human runs this on their local machine before committing
keeli progress task-oauth

# CLI validates:
# - Does task file exist? ✓
# - Is the task still in Backlog status? ✓
# - Is the handshake status safe to transition? ✓
# - If story/epic links exist, are they valid? ✓
```

---

## Handshake Mechanism (Revised)

**Old Approach (ADR-009):** MCP tool calls `keeli_po_sign_off()`, `keeli_architect_sign_off()`, etc.  
**New Approach (ADR-011):** LLM edits task file directly + uses HATEOAS hints to understand the process.

### Handshake Marker (In Task File)

```markdown
## Handshakes
_Each persona signs off by checking the row and adding a summary._

| Persona | Signed | Date | Summary |
|---------|--------|------|---------|
| @po | ☐ | — | Waiting: ACs + NFRs filled |
| @architect | ☐ | — | Waiting: @po approval |
| @developer | ☐ | — | Waiting: @architect design |
| @security | ☐ | — | Waiting: @developer code + tests |

**Process:**
1. @po fills `## @po (Goals & Acceptance Criteria)` section → marks `[x]` + adds summary + saves file
2. @architect reviews, fills `## @architect (Design & Planning)` → marks `[x]` + saves
3. @developer implements, fills `## @developer (Implementation)` → marks `[x]` + saves
4. @security reviews, fills `## @security (Findings & Issues)` → marks `[x]` + saves
5. Any persona calls `keeli_complete` (CLI validates all boxes are checked)
```

**HATEOAS hints in task file (guide the LLM):**

```markdown
<!-- HATEOAS: Next Actions for LLM -->
<!-- 
If handshake_status is @po_pending:
  → Fill the @po section (ACs + NFRs)
  → Check the box: [x] @po signed off
  → Add ISO-8601 timestamp and summary in the table
  → Call keeli_log("T-XXXX | @po | Signed off: ...")
  → Next: ask @architect to review and fill design section

If handshake_status is @architect_pending:
  → @po approval must be done first (check handshake table)
  → Fill Design Summary + Implementation Plan + Test Strategy
  → Check the box: [x] @architect signed off
  → Call keeli_log("T-XXXX | @architect | Signed off: ...")
  → Next: ask @developer to implement

... etc for all 4 personas
-->
```

**Validation:** `keeli_complete` (CLI) checks:
```
✓ Task file exists
✓ All 4 handshake boxes are checked ([x])
✓ If story/epic links exist, are they valid?
✓ Status = In Progress or Review
→ Permits completion and archival
```

---

## Architecture Comparison

### Old: ADR-010 (MCP-Tool-Heavy)
```
LLM:
  Call MCP keeli_start(...)
    [wait for response]
  Call MCP keeli_po_sign_off(task_slug, summary)
    [wait for response]
  Call MCP keeli_architect_sign_off(...)
    [wait for response]
  ...
```
**Problem:** Many round-trips, compound latency.

### New: ADR-011 (File-First, HATEOAS-Guided)
```
LLM:
  1. Call keeli_next() [FAST: just read index, return priority task]
  2. Read task file [native file I/O, fast]
  3. Edit task file (fill sections, check handshake boxes) [fast, direct, no delay]
  4. Call keeli_log("...") [fast: just append]
  5. Call keeli_analyze(slug) [slow, but only when needed; TF-IDF corpus scan]
  6. Continue to next step
```

**Benefit:** Minimal MCP overhead. LLM drives workflow via file edits. MCP tools are *helpers*, not *gatekeepers*.

---

## Copilot Instructions (Revised for ADR-011)

```markdown
## Workflow Rules (File-First)

### How to Work on a Task

1. **Get next task:** Call `keeli_next()` → receive task slug + priority + HATEOAS hints
2. **Read task file:** `docs/tasks/<slug>.md` — understand what to do
3. **Follow handshake sequence:** Edit task file directly; no MCP tool calls for sign-offs
   - @po: Fill ACs + NFRs → check handshake box → call keeli_log()
   - @architect: Fill design + test-strategy → check handshake box → call keeli_log()
   - @developer: Implement + tests → check handshake → call keeli_log()
   - @security: Review threats + findings → check handshake → call keeli_log()
4. **Inject context hints:** Call `keeli_analyze(slug)` before starting implementation
5. **Build chains:** Use `keeli_chain()` to run multi-step operations (start → analyze → progress)
6. **Audit trail:** Call `keeli_log()` to append semtized entries to docs/ai_log.md
7. **Complete:** Ensure all handshake boxes are checked, then run `keeli_complete()` (or let human run CLI)

### When to Use MCP Tools

| Tool | When |
|------|------|
| keeli_next | At session start; after completing a task |
| keeli_analyze | Before implementing; refresh context |
| keeli_chain | Run multi-step workflows (start → analyze → progress) |
| keeli_log | Log significant milestones (sign-offs, blockers, completions) |
| keeli_digest | At session start; get full context snapshot (~2k tokens) |
| keeli_find / keeli_history | Look up task by ID or find audit trail |

### When to Edit Files Directly

| Operation | File | Action |
|-----------|------|--------|
| Sign off as @po | task-<slug>.md | Fill ACs + NFRs; mark [x] in handshake table; add timestamp + summary |
| Sign off as @architect | task-<slug>.md | Fill Design Summary + Impl Plan + Test Strategy; mark [x]; log |
| Sign off as @developer | task-<slug>.md | Write source code + tests; fill Validation checklist; mark [x]; log |
| Sign off as @security | task-<slug>.md | Document threat model + findings; mark [x]; log |
| Update status | task-<slug>.md | Edit `**Status:**` field directly |
| Add notes | task-<slug>.md | Append to ## Notes section |

### Never Use MCP Tools For

- Status transitions (edit task file instead)
- Handshake sign-offs (edit task file + keeli_log instead)
- Adding notes (edit task file directly)
- Updating task metadata (edit task file directly)

MCP tools are **read-only computation** only. Everything else is file I/O.
```

---

## Validation Rules (Boundary: CLI Only)

No MCP tool validates; instead, CLI `keeli` commands validate at the boundary:

```python
# src/keeli/main.py — cmd_progress
def cmd_progress(slug):
    task_path = _resolve_task_file(slug)
    content = task_path.read_text()
    
    # Guard 1: Task exists
    if not task_path.exists():
        raise TaskNotFoundError(...)
    
    # Guard 2: Can transition to In Progress
    status = _parse_task_field(content, "Status")
    if status not in ["Backlog"]:
        raise InvalidTransition(...)
    
    # Guard 3 (NEW): Hierarchy is valid (epic/story exist)
    epic = _parse_task_field(content, "Epic")
    story = _parse_task_field(content, "Story")
    if not epic or not story:
        raise HierarchyError("Task must link epic + story")
    
    if not (docs_tasks / f"epic-{epic}.md").exists():
        raise HierarchyError(f"Epic '{epic}' not found")
    
    if not (docs_tasks / f"story-{story}.md").exists():
        raise HierarchyError(f"Story '{story}' not found")
    
    # Update status + log + archive old logs
    _update_field(task_path, "Status", "In Progress")
    _append_log(f"T-XXXX | @developer | Task moved to In Progress")

# src/keeli/main.py — cmd_complete
def cmd_complete(slug):
    task_path = _resolve_task_file(slug)
    content = task_path.read_text()
    
    # Guard 1: Task exists
    if not task_path.exists():
        raise TaskNotFoundError(...)
    
    # Guard 2: All handshake boxes must be checked
    handshake_table = _extract_handshake_table(content)
    # [parse markdown table, check all "- [x]" are present]
    if not handshake_table.all_signed_off():
        raise HandshakeIncomplete(
            f"Not all personas signed off:\n{handshake_table.status()}"
        )
    
    # Guard 3: No live children (no tasks/stories link to this epic/story)
    _validate_no_children_on_complete(slug)
    
    # Archive + index update
    task_path.rename(docs_tasks / "archive" / task_path.name)
    _index_update_status(slug, "completed")
    _append_log(f"T-XXXX | @developer | Task completed")
```

**Result:** Validation happens at the human boundary (CLI), not in LLM workflows. LLMs can't bypass guards.

---

## Handshake Table Format (Standard)

Every task file includes:

```markdown
## Handshakes
| Persona | Signed | Date | Summary |
|---------|--------|------|---------|
| @po | ☐ | — | Waiting: ACs + NFRs filled |
| @architect | ☐ | — | Waiting: @po approval |
| @developer | ☐ | — | Waiting: @architect design |
| @security | ☐ | — | Waiting: @developer code |

<!-- HATEOAS Hints (guide LLM through the process) -->
<!-- 
If you are @po:
  1. Fill "## @po (Goals & Acceptance Criteria)" section
  2. Mark [x] in the table above: | @po | ☑ | 2026-03-07T... | Your summary here |
  3. Call: keeli_log("T-XXXX | @po | Signed off: <summary>")
  
If you are @architect:
  (... similar pattern ...)
-->
```

---

## Migration from ADR-010 to ADR-011

**What changes:**
1. Delete the 5 new MCP tools: `keeli_po_sign_off`, `keeli_architect_sign_off`, `keeli_developer_sign_off`, `keeli_security_sign_off`
2. Keep the 8 read-only/query tools: `keeli_next`, `keeli_analyze`, `keeli_digest`, `keeli_chain`, `keeli_log`, `keeli_find`, `keeli_history`
3. Shift validation from MCP to CLI boundary
4. Update COPILOT_INSTRUCTIONS: file-first workflow, HATEOAS hints for LLM guidance

**No changes to:**
- Task file schema (handshake table still exists, just managed by LLM directly)
- Hierarchy rules (epic > story > task still enforced, but at CLI boundaries)
- Audit logging (keeli_log still appends to ai_log.md)

---

## Summary

| Aspect | ADR-010 (Rejected) | ADR-011 (Approved) |
|--------|---|---|
| Handshake sign-offs | MCP tools (5 separate calls) | File edits + keeli_log (1-2 calls) |
| Status transitions | MCP tool wrappers | Edit task file directly |
| Validation | MCP tools (before state change) | CLI boundary (when human runs keeli) |
| LLM workflow speed | Slow (many round-trips) | Fast (minimal MCP overhead) |
| Agent experience | Blocked waiting for tool responses | Native file I/O + simple queries |

---

## Next Steps

1. **Update COPILOT_INSTRUCTIONS** to reflect file-first workflow
2. **Update task templates** to include HATEOAS hints for LLM guidance
3. **Remove 5 MCP sign-off tools** from mcp_server.py (keep 8 query tools)
4. **Shift validation** from MCP to CLI (cmd_progress, cmd_complete, etc.)
5. **Update README & docs** to show file-first workflow
6. **Keep ADR-008 (hierarchy)** — still needed for validation at CLI boundaries
7. **Keep ADR-009 handshake concept** — still enforced, but simpler (markdown table edits, not tool calls)

---

## Benefits

✅ **Agent speed:** 10x fewer round-trips per workflow  
✅ **Simplicity:** LLMs edit files natively; no tool call overhead  
✅ **Clarity:** HATEOAS hints in task files guide the LLM at every step  
✅ **Safety:** Validation still happens (at CLI boundaries), just not in LLM workflows  
✅ **Human control:** Humans validate & approve locally before changes are committed  

---

This is a significant simplification. Instead of trying to make MCP tools the primary interface, we embrace the LLM's native capabilities (file I/O) and use MCP tools only for what they're good at (computation + context injection).

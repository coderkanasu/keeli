# Implementation Roadmap — File-First Architecture (ADR-011)

**Status:** Ready for Development  
**Complexity:** Medium (simpler than ADR-010)  
**Timeline:** ~10-12 hours  
**Start:** Immediately after approval

---

## Three ADRs to Implement

| ADR | Focus | Change | Effort |
|-----|-------|--------|--------|
| **ADR-008** | Hierarchy (Epic > Story > Task) | Add validators at CLI boundaries | 2-3h |
| **ADR-009** | Handshakes (4-persona sign-off) | Simplify: file edits + HATEOAS (no MCP tools) | 2-3h |
| **ADR-011** | File-First Workflow | Update instructions + remove tool wrappers | 2-3h |
| **Integration** | Full e2e testing | Complete workflow validation | 2-3h |

---

## Phase 1: Core Architecture (ADR-008 + ADR-009)

### Goal
Enforce Epic > Story > Task hierarchy + 4-persona handshakes. All via file edits, validation at CLI boundaries.

### Tasks for @developer

#### Task 1.1: Add Hierarchy Validators (ADR-008)
**File:** `src/keeli/main.py`

**Changes:**
1. Add `_validate_hierarchy(task_slug)` helper
   ```python
   def _validate_hierarchy(task_slug):
       """Ensure task links to valid story + epic."""
       path = _resolve_task_file(task_slug)
       if not path.exists():
           raise TaskNotFoundError(...)
       
       content = path.read_text()
       epic = _parse_task_field(content, "Epic")
       story = _parse_task_field(content, "Story")
       
       if not epic or not story:
           raise HierarchyError("Task must link both --epic and --story")
       
       if not (docs_tasks / f"epic-{epic}.md").exists():
           raise HierarchyError(f"Epic '{epic}' not found")
       
       if not (docs_tasks / f"story-{story}.md").exists():
           raise HierarchyError(f"Story '{story}' not found")
   ```

2. Add `_validate_no_children_on_complete(task_slug)` helper
   ```python
   def _validate_no_children_on_complete(task_slug):
       """Prevent archiving epics/stories with live children."""
       if task_slug.startswith("epic-"):
           # Find all stories linking to this epic
           linked = [s for s in docs_tasks.glob("story-*.md") 
                    if _parse_task_field(s.read_text(), "Epic") == task_slug]
           if linked:
               raise ValidationError(f"Cannot archive: {len(linked)} stories still link here")
       
       elif task_slug.startswith("story-"):
           # Find all tasks linking to this story
           linked = [t for t in docs_tasks.glob("task-*.md")
                    if _parse_task_field(t.read_text(), "Story") == task_slug]
           if linked:
               raise ValidationError(f"Cannot archive: {len(linked)} tasks still link here")
   ```

3. Update `cmd_progress(slug)`
   - Add: `_validate_hierarchy(slug)` after status check
   - Error message: "Task must link both --epic and --story. Use keeli start with those flags."

4. Update `cmd_complete(slug)`
   - Add: `_validate_no_children_on_complete(slug)` before archival
   - Error message: "Cannot complete: <n> child tasks/stories still reference this. Archive them first."

5. Update `cmd_start(title, epic, story, ...)`
   - Current: `epic` and `story` are optional
   - New: Both required
   - Validation: Check both targets exist before creating task

6. Update `cmd_story(title, epic, ...)`
   - Current: `epic` is optional
   - New: Required
   - Validation: Check epic exists before creating story

**Tests:** 15 tests (TDD)
```
✓ cmd_start without epic → error
✓ cmd_start without story → error
✓ cmd_start with non-existent epic → error
✓ cmd_start with non-existent story → error
✓ cmd_start with both → success
✓ cmd_progress with invalid hierarchy → error
✓ cmd_complete with child tasks → error
✓ cmd_complete with all children archived → success
... (7 more variations)
```

**Effort:** 2-3 hours

---

#### Task 1.2: Simplify Handshakes (ADR-009)
**File:** `src/keeli/templates.py`

**Changes:**
1. Update `TASK_TEMPLATE`
   - Add `**Handshake Status:** backlog` field (new metadata)
   - Keep handshake table (already present)
   - Add HATEOAS hints comment block (guide LLM through the process)

2. HATEOAS hint example:
   ```markdown
   ## Handshakes
   | Persona | Signed | Date | Summary |
   |---------|--------|------|---------|
   | @po | ☐ | — | Waiting: ACs + NFRs filled |
   | @architect | ☐ | — | Waiting: @po approval |
   | @developer | ☐ | — | Waiting: @architect design |
   | @security | ☐ | — | Waiting: @developer code |
   
   <!-- HATEOAS: How to sign off (guide for LLM agents) -->
   <!--
   For @po:
     1. Fill the "## @po (Goals & Acceptance Criteria)" section
     2. Edit this table: mark [x] for @po, add timestamp, add summary
     3. Call: keeli_log("T-XXXX | @po | Signed off: <summary>")
     4. Next: ask @architect to fill design + test-strategy
   
   For @architect:
     1. Verify @po is already signed off (check table above)
     2. Fill "## @architect (Design & Planning)" section
     3. Edit table: mark [x] for @architect, add timestamp
     4. Call: keeli_log("T-XXXX | @architect | Signed off: <summary>")
     5. Next: ask @developer to implement
   
   ... (similar for @developer and @security)
   -->
   ```

**Tests:** 10 tests
```
✓ Task created with Handshake Status: backlog
✓ HATEOAS hints are present in template
✓ Handshake table has empty checkboxes initially
... (7 more)
```

**Effort:** 1-2 hours

---

#### Task 1.3: Update keeli_complete Guard (ADR-009)
**File:** `src/keeli/main.py`

**Changes:**
1. Add `_handshake_all_signed_off(content)` helper
   ```python
   def _handshake_all_signed_off(content):
       """Check if all 4 personas have signed off in the handshake table."""
       table = _extract_handshake_table(content)  # Parse markdown table
       return table.count("☑") == 4  # All boxes checked
   ```

2. Update `cmd_complete(slug)`
   - Add check: if not all handshakes signed, raise ValidationError
   - Clear error message listing which personas haven't signed off yet

**Tests:** 5 tests
```
✓ Complete fails if @po not signed
✓ Complete fails if @architect not signed
✓ Complete succeeds if all 4 signed
... (2 more)
```

**Effort:** 1 hour

---

### Total for Phase 1: 4-6 hours

**Deliverable:** 
- Hierarchy validated at CLI boundaries
- Handshakes enforced via file edits + HATEOAS guidance
- All path tests complete + passing
- No MCP tool wrappers added (reject ADR-010)

---

## Phase 2: Documentation & Instructions (ADR-011)

### Goal
Update COPILOT_INSTRUCTIONS and README to reflect file-first, LLM-native workflow.

### Tasks for @architect + @author

#### Task 2.1: Refactor COPILOT_INSTRUCTIONS (ADR-011)
**File:** `.github/copilot-instructions.md`

**Changes:**
1. **Remove ADR-010 section** (MCP tool wrappers)
2. **Add workflow section:**
   ```markdown
   ## Workflow — File-First, LLM-Native
   
   ### How to Work on a Task
   1. Call keeli_next() → get highest-priority task slug
   2. Read task file: docs/tasks/<slug>.md
   3. Follow the HATEOAS hints in the task file (they guide you through each persona's step)
   4. Edit sections directly:
      - @po: Fill ACs + NFRs → check handshake box → call keeli_log()
      - @architect: Fill design + test-strategy → check handshake box → call keeli_log()
      - @developer: Write code + tests → check handshake box → call keeli_log()
      - @security: Review threats → check handshake box → call keeli_log()
   5. Call keeli_analyze(slug) before implementing (context injection)
   6. Once all handshakes are complete, any persona can run keeli_complete (or have human run it)
   
   ### MCP Tools (Helpers Only)
   - keeli_next: Get priority task + hints
   - keeli_analyze: Inject AI context
   - keeli_chain: Run multi-step pipelines
   - keeli_log: Log audit entries
   - keeli_digest: Get full context
   
   ### Never Use MCP Tools For
   - State transitions (edit task file instead)
   - Handshake sign-offs (edit task file + keeli_log instead)
   - Metadata updates (edit task file directly)
   ```

3. Keep persona definitions (unchanged)
4. Keep scope guardrails (unchanged)

**Effort:** 2-3 hours

---

#### Task 2.2: Update README.md (ADR-011)
**File:** `README.md`

**Changes:**
1. Add section: "File-First Workflow"
   - Explain: LLMs edit files; MCP tools are helpers
   - Show example: @po signs off by editing file

2. Update "Quick Start" to show file-first approach
   - Emphasize: `keeli next` → read file → edit → `keeli log`

3. Keep CLI reference (for humans) in separate section

**Effort:** 1-2 hours

---

#### Task 2.3: Update Task Templates (ADR-009)
**File:** `src/keeli/templates.py`

**Changes:** (Already covered in Task 1.2)
- Add HATEOAS hints to TASK_TEMPLATE
- Add Handshake Status field

**Effort:** (Included in Task 1.2)

---

### Total for Phase 2: 3-5 hours

**Deliverable:**
- COPILOT_INSTRUCTIONS refactored for file-first workflow
- README updated with both audiences (CLI for humans, file-first for LLMs)
- Task template includes HATEOAS hints

---

## Phase 3: Delete ADR-010 Artifacts

### Goal
Clean up the rejected MCP sign-off tools.

### Tasks for @developer

#### Task 3.1: Remove Sign-Off Tools from mcp_server.py
**File:** `src/keeli/mcp_server.py`

**Changes:**
1. Delete: `handler_keeli_po_sign_off()`
2. Delete: `handler_keeli_architect_sign_off()`
3. Delete: `handler_keeli_developer_sign_off()`
4. Delete: `handler_keeli_security_sign_off()`
5. Remove these tools from `LIST_TOOLS` response

**Keep:**
- `keeli_next`, `keeli_analyze`, `keeli_digest`, `keeli_chain`, `keeli_log`, `keeli_find`, `keeli_history`
- All supporting helpers

**Tests:** Delete related tests; keep query tool tests

**Effort:** 1-2 hours

---

#### Task 3.2: Archive ADR-010 Document
**File:** `docs/decision.md`

**Changes:**
1. Update ADR-010 entry to mark as "Rejected in favor of ADR-011"
2. Add ADR-011 entry (new)

**Effort:** 30 min

---

### Total for Phase 3: 2 hours

**Deliverable:**
- No trace of rejected MCP sign-off tools
- ADR-011 formally recorded

---

## Phase 4: Integration Testing

### Goal
Validate the full workflow end-to-end.

### Tests: 20 scenarios (TDD)

```
✅ Epic Creation
  ✓ Create epic with POStatus=Backlog
  ✓ Epic appears in keeli_next output

✅ Story Creation
  ✓ Create story linked to epic
  ✓ story without epic → error
  ✓ Story appears under epic in keeli_next

✅ Task Creation
  ✓ Create task linked to story + epic
  ✓ Task without story → error
  ✓ Task without epic → error
  ✓ Task with non-existent story → error

✅ Handshakes (File-First)
  ✓ @po edits task file (fill ACs + NFRs) + checks handshake box + calls keeli_log
  ✓ @architect edits task file (fill design) + checks handshake box + calls keeli_log
  ✓ @developer edits task file (write code) + checks handshake box + calls keeli_log
  ✓ @security edits task file (findings) + checks handshake box + calls keeli_log
  ✓ All 4 handshakes logged in ai_log.md with timestamps

✅ Completion Guard
  ✓ keeli_complete fails if any handshake unchecked
  ✓ keeli_complete succeeds if all handshakes complete
  ✓ Task archived to docs/tasks/archive/
  ✓ Index updated

✅ Hierarchy Validation
  ✓ Archive epic with live stories → error
  ✓ Archive story with live tasks → error
  ✓ Archive epic with all children archived → success

✅ Cleanup
  ✓ No orphaned tasks after completion
```

**Effort:** 2-3 hours

---

## Summary: Implementation Schedule

| Phase | Tasks | Owner | Days | Start |
|-------|-------|-------|------|-------|
| **1** | ADR-008 + ADR-009 validators | @developer | 2 | Day 1 |
| **2** | ADR-011 docs + instructions | @architect + @author | 1 | Day 2 (parallel) |
| **3** | Delete ADR-010 artifacts | @developer | 1 | Day 3 |
| **4** | Integration testing | @developer | 1 | Day 3 (parallel) |
| **Total** | | | ~4-5 days | |

---

## Files Modified

```
IMPLEMENT (Changes Required):
├─ src/keeli/main.py
│  └─ Add: _validate_hierarchy(), _validate_no_children_on_complete()
│  └─ Update: cmd_start(), cmd_story(), cmd_progress(), cmd_complete()
│
├─ src/keeli/mcp_server.py
│  └─ Delete: 5 sign-off tool handlers
│  └─ Keep: 8 query tools
│
├─ src/keeli/templates.py
│  └─ Update: TASK_TEMPLATE (add Handshake Status + HATEOAS hints)
│  └─ Update: COPILOT_INSTRUCTIONS (file-first workflow)
│
├─ .github/copilot-instructions.md
│  └─ Refactor: Remove ADR-010; add workflow section
│
├─ README.md
│  └─ Update: Split CLI vs LLM audience; add file-first example
│
├─ docs/decision.md
│  └─ Add: ADR-011 entry
│  └─ Update: ADR-010 marked rejected
│
└─ tests/
   ├─ test_commands.py (add 15-20 hierarchy + handshake tests)
   └─ test_mcp_server.py (remove sign-off tool tests; keep query tests)

CREATE (New Files):
├─ ADR-011_FILE_FIRST_LLM_NATIVE.md ✅ (already created)
├─ ARCHITECTURAL_SHIFT_ADR_011.md ✅ (already created)
└─ This implementation roadmap ✅
```

---

## Success Criteria

✅ **Phase 1 Complete:**
- All hierarchy validators pass tests (15 tests)
- Handshake metadata + HATEOAS hints working
- No MCP tool wrappers added

✅ **Phase 2 Complete:**
- COPILOT_INSTRUCTIONS refactored for file-first
- README updated for both audiences
- Examples show LLM workflow (file edits, minimal MCP calls)

✅ **Phase 3 Complete:**
- No trace of rejected keeli_*_sign_off tools
- ADR-011 formally recorded in decision.md

✅ **Phase 4 Complete:**
- Full e2e workflow passes (epic → story → task → 4 sign-offs → complete)
- Hierarchy validation throughout
- All tests green (50+ new tests)

---

## Start Now

**@developer:** Begin Phase 1
- Create task: `keeli start "ADR-008: Implement hierarchy validators" -p P0 -k developer`
- Begin with tests (TDD)

**@architect + @author:** Begin Phase 2 (parallel)
- Create task: `keeli start "ADR-011: Refactor COPILOT_INSTRUCTIONS (file-first)" -p P0 -k architect`
- Create task: `keeli start "Update README for file-first workflow" -p P1 -k author`

**Expect:** ~4-5 days, all passing tests, significantly simpler than original plan.

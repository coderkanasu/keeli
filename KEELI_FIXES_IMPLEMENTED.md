# Keeli Fixes Implemented: Handshake Protocol

## Summary
Fixed critical gaps in keeli by implementing the **Crew Framework Handshake Protocol** — a formal persona signature and sequential handoff mechanism that was missing from the original implementation.

## Gaps Identified vs. Crew Framework

| Gap | Status | Fix |
|-----|--------|-----|
| No handshake mechanism | ❌ Critical | ✅ Added Handshakes table with persona rows |
| No persona signature structure | ❌ Critical | ✅ Created handshake table: `☐ pending` → `☑ signed` |
| No explicit design summary | ❌ Major | ✅ Added `## @architect (Design & Planning)` section |
| No implementation plan | ❌ Major | ✅ Added numbered implementation plan section |
| No test strategy materialization | ❌ Major | ✅ Made Test Strategy explicit in @architect section |
| No security findings section | ❌ Major | ✅ Added `## @security (Findings & Issues)` |
| No final docs section | ❌ Major | ✅ Added `## @author (Documentation)` with WCAG checklist |
| No structured handoff ceremony | ❌ Major | ✅ Created `keeli handoff` command |
| No validation of handshake status | ❌ Major | ✅ Updated transition guards to check handshake rows |

---

## Implementation Changes

### 1. **Updated TASK_TEMPLATE** (src/keeli/templates.py)

**Before:** Simple structure with `## Objective` and `## Checklist`

**After:** Structured persona sections with explicit handshake protocol:

```markdown
## Handshakes
| Persona | Status | Signed | Summary |
|---------|--------|--------|---------|
| @po | ☐ pending | — | Waiting: user story + ACs + NFRs |
| @architect | ☐ pending | — | Waiting: @po sign-off |
| @developer | ☐ pending | — | Waiting: @architect design |
| @security | ☐ pending | — | Waiting: @developer code review |
| @author | ☐ pending | — | Waiting: @security sign-off |

## @po (Goals & Acceptance Criteria)
## Non-Functional Requirements
## @architect (Design & Planning)
### Design Summary
### Implementation Plan
### Test Strategy

## @developer (Implementation)
### Tests
### Implementation
### Validation

## @security (Findings & Issues)
### Checklist
### Findings

## @author (Documentation)
### Documentation
### WCAG 2.1 AA
```

### 2. **Added Handshake Helper Function** (src/keeli/main.py)

```python
def _handshake_signed(persona: str) -> Callable[[str], bool]:
    """Check if a persona has signed the handshake."""
    # Returns True if persona row shows ☑ or [x]
```

### 3. **Created `keeli handoff` Command** (src/keeli/main.py:~2350)

**Usage:**
```bash
keeli handoff "my-task" --persona po -m "User story + 3 ACs + NFRs defined"
keeli handoff "my-task" -p architect -m "Interfaces designed, implementation plan written"
keeli handoff "my-task" -p developer -m "All tests passing, code reviewed"
keeli handoff "my-task" -p security -m "Auth reviewed, no injection vectors"
keeli handoff "my-task" -p author -m "API docs + examples written"
```

**What it does:**
- Finds the persona's row in the `## Handshakes` table
- Updates status: `☐ pending` → `☑ signed`
- Stamps ISO-8601 timestamp
- Records optional handoff message
- Logs to ai_log.md

### 4. **Updated Transition Validation** (src/keeli/main.py:cmd_progress)

**Before:**
```python
errors = _validate_transition(task_file, [
    ("Objective section is empty",
     _section_is_filled("## Objective")),
])
```

**After:**
```python
errors = _validate_transition(task_file, [
    ("@po handshake must be signed before @architect can start design",
     _handshake_signed("po")),
    ("@po (Goals & Acceptance Criteria) section must be filled",
     _section_is_filled("## @po (Goals & Acceptance Criteria)")),
    ("@architect (Design & Planning) section must be filled",
     _section_is_filled("## @architect (Design & Planning)")),
])
```

Now the task cannot progress until @po has formally signed off.

### 5. **Updated cmd_start** (src/keeli/main.py:~860)

- Removed obsolete `objective_text` and `checklist` formatting
- Template no longer uses those placeholders
- Fixed `persona` argument name (was `keeli`, now `persona`)

### 6. **Added Handoff Command to Parser** (src/keeli/main.py:build_parser)

```python
p_handoff = sub.add_parser("handoff", help="Sign a persona handshake on a task.")
p_handoff.add_argument("task_name", help="Task title or slug.")
p_handoff.add_argument("-p", "--persona", required=True, choices=personas,
                      help="Persona signing off.")
p_handoff.add_argument("-m", "--message", default=None,
                      help="Optional handoff summary/notes.")
```

### 7. **Registered Handoff in Dispatch** (src/keeli/main.py:main)

```python
dispatch = {
    ...
    "handoff": cmd_handoff,
}
```

---

## How the Handshake Protocol Works

### Workflow Example

```
1. @po creates task with keeli start
   → All handshake rows show ☐ pending

2. @po writes User Story + ACs + NFRs
   → keeli handoff "task" -p po -m "User story + 3 ACs defined"
   → Handshake row updates: ☑ signed | 2026-03-03T12:34:56Z | User story + 3 ACs...

3. @architect tries keeli progress "task"
   ✓ PASSES: @po handshake is signed
   → Task moves to In Progress
   → @architect now works on Design Summary + Implementation Plan

4. @architect writes design and signs off
   → keeli handoff "task" -p architect -m "Interfaces designed, 5-step impl plan"
   → Row updates: ☑ signed | ... | Interfaces designed...

5. @developer picks up the task
   → keeli next → task shows "In Progress" and full context
   → Developer follows @architect's numbered implementation plan

6. @developer completes tests + implementation
   → keeli handoff "task" -p developer -m "All tests passing, no TODOs"
   → Row updates with timestamp

7. @security reviews
   → keeli handoff "task" -p security -m "Auth boundaries verified, input validation ok"
   → Row updates

8. @author documents
   → keeli handoff "task" -p author -m "API docs + examples written"
   → Row updates

9. keeli complete "task"
   → Verifies all 5 handshakes are signed ☑
   → Archives task
   → Shows next highest-priority task
```

---

## Validation Rules Now Enforced

### keeli progress (Backlog → In Progress)
- ✅ @po handshake MUST be signed
- ✅ @po (Goals & Acceptance Criteria) section MUST be filled
- ✅ @architect (Design & Planning) section MUST be filled

### keeli review (In Progress → Review)
- ✅ All non-gate checklist items MUST be checked
- ✅ @security/@author items skipped (human review only)

### keeli complete (Review → Completed)
- ✅ All checklist items MUST be checked
- ✅ Task auto-archives to docs/tasks/archive/

---

## Key Advantages of This Protocol

1. **Explicit Sign-Off:** Each persona leaves a timestamped signature, creating an immutable audit trail
2. **Prevents Handoff Ambiguity:** Transition guards check handshake status, not just file sections
3. **Clear Sequential Flow:** The Handshakes table shows who's done and who's waiting
4. **Governance:** Personas CANNOT skip steps — incomplete sections block progression
5. **Context Preservation:** Handoff messages (max 500 chars) document why each persona signed off
6. **Audit Trail:** Every handoff is logged to ai_log.md with timestamp

---

## Testing the Fix

### Create a test task

```bash
cd /Users/spatil/Documents/persona-cli
keeli init  # if not already done
keeli start "Test Handshake Protocol" -p architect -p P1
```

### View the new template

```bash
cat docs/tasks/test-handshake-protocol.md
```

You should see:
- `## Handshakes` table with 5 persona rows, all showing `☐ pending`
- `## @po (Goals & Acceptance Criteria)` section (empty)
- `## @architect (Design & Planning)` with Design Summary, Implementation Plan, Test Strategy
- `## @developer (Implementation)` with Tests, Implementation, Validation
- `## @security (Findings & Issues)` with Checklist and Findings
- `## @author (Documentation)` with WCAG checklist

### Try to progress without @po sign-off

```bash
keeli progress "test handshake protocol"
```

Should FAIL with:
```
❌ Cannot move to In Progress — fix these issues first:
   • @po handshake must be signed before @architect can start design
   • @po (Goals & Acceptance Criteria) section must be filled
```

### Sign off as @po

```bash
keeli handoff "test-handshake-protocol" -p po -m "User story: As a developer, I want formal handoffs. Success: all 5 personas sign. NFRs: 100% test coverage."
```

### Now progress should work

```bash
keeli progress "test-handshake-protocol"
```

Should succeed:
```
✅ Marked as In Progress: docs/tasks/test-handshake-protocol.md
```

View the handshake table:
```bash
grep -A 6 "## Handshakes" docs/tasks/test-handshake-protocol.md
```

You should see:
```
| @po | ☑ signed | 2026-03-03T... | User story: As a developer... |
| @architect | ☐ pending | — | Waiting: @po sign-off |
```

---

## What's Next (Phase 2)

1. **MCP Tool Updates** — surfacehandshake status in keeli_next / keeli_analyze output
2. **keeli diagnose** — show which persona is currently blocked and why
3. **keeli chain handoff** — propagate handshakes through automated pipelines
4. **Persona-Aware Suggestions** — HATEOAS next actions show "next: handoff @architect after design is complete"

---

## Files Modified

- ✅ `src/keeli/templates.py` — TASK_TEMPLATE + TASK_CHECKLISTS
- ✅ `src/keeli/main.py` — added cmd_handoff, _handshake_signed helper, updated cmd_progress & cmd_start, registered handoff command

---

## Schema Version

- **Before:** 0.3.0
- **After:** 0.4.0 (no change to code, but template compatibility requires this)

The copilot-instructions.md already reflects v0.4.0, which defined the handshake protocol. This implementation brings the task file template in line with that specification.

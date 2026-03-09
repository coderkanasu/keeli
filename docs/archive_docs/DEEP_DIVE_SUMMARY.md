# Keeli Architectural Review Summary

## Three Critical Issues Identified & Fixed ✅

---

## ⚠️ ISSUE 1: No Hierarchy Enforcement
**Epic > Story > Task relationship is not validated**

### Current State (BROKEN)
```
epic-user-auth.md ✓
  └─ story-login.md ✓
     └─ task-oauth-setup.md ✓
  └─ story-register.md ✓
     
task-analytics.md  ❌ ORPHANED — no story
task-jwt-refresh.md ❌ BROKEN — references non-existent story
```

### Problem
- Tasks can be created without stories
- Stories can be created without epics
- No validation when parents are archived
- Impossible to query "what stories belong to this epic?"

### Solution (ADR-008)
✅ **Enforce strict 3-level hierarchy:**
- `keeli start` requires both `--story` and `--epic` 
- `keeli story` requires `--epic`
- `keeli complete` validates no children before archiving epic/story
- MCP tools validate same rules

---

## ⚠️ ISSUE 2: Persona Handshakes Are Decorative
**Sign-off table exists but is never enforced**

### Current State (BROKEN)
```md
## Handshakes
| Persona | Status | Signed | Summary |
|---------|--------|--------|---------|
| @po | ☐ pending | — | Waiting... |
| @architect | ☐ pending | — | Waiting... |
```

**No guards anywhere:**
- @developer can code without @architect sign-off ❌
- Task can be marked complete without @security review ❌
- Handshake table is just markdown — nobody checks it ❌

### Problem
- Five-Persona Architecture is non-binding
- Personas skip stages silently  
- No audit trail showing who approved what
- Impossible to prevent scope creep

### Solution (ADR-009)
✅ **Explicit state mutation tools with handshake validation:**

```
NEW MCP Tools (one per persona):
├─ keeli_po_sign_off(task_slug, summary)
├─ keeli_architect_sign_off(task_slug, summary)
├─ keeli_developer_sign_off(task_slug, summary)
└─ keeli_security_sign_off(task_slug, summary)
```

**Enforced sequence:**
1. @po fills ACs + NFRs → calls `keeli_po_sign_off`
2. @architect fills design + test-strategy → calls `keeli_architect_sign_off`
3. @developer implements + tests → calls `keeli_developer_sign_off`
4. @security reviews threat model → calls `keeli_security_sign_off`
5. `keeli_complete` fails if not all signed off

---

## ⚠️ ISSUE 3: LLM Instructions Reference CLI, Not MCP
**Tells LLMs to use shell commands they can't execute**

### Current State (WRONG)
```markdown
# COPILOT_INSTRUCTIONS (current)
keeli epic "User Auth" -p P0
keeli start "Implement OAuth" 
keeli progress oauth-setup
keeli complete oauth-setup
```

**Problem:**
- LLMs cannot execute shell commands
- Their only interface: MCP tools + file editing
- Instructions create confusion: "Use CLI" vs "Use MCP tools"
- Token waste: LLM tries CLI first, fails, realizes it needs MCP
- Incomplete coverage: No MCP tools for some operations

### Solution (ADR-010)
✅ **Split instructions by audience:**

**For AI Agents (MCP-only):**
```markdown
Call MCP tools:
├─ keeli_start(title, priority, epic, story)
├─ keeli_po_sign_off(slug, summary)
├─ keeli_architect_sign_off(slug, summary)
├─ keeli_developer_sign_off(slug, summary)
├─ keeli_security_sign_off(slug, summary)
├─ keeli_progress(slug)
├─ keeli_complete(slug)
├─ keeli_analyze(slug)
├─ keeli_next()
├─ keeli_chain(steps)
└─ keeli_log(message)
```

**For Local Humans (CLI):**
```bash
keeli epic "User Auth" -p P0
keeli start "Implement OAuth"
keeli progress oauth-setup
keeli analyze oauth-setup
keeli complete oauth-setup
```

---

## Implementation Roadmap

| Phase | ADR | Focus | Effort | Timeline |
|-------|-----|-------|--------|----------|
| **1** | ADR-008 | Hierarchy validation | 10 tests, 3 validators | 2-3 hours |
| **2** | ADR-009 | Handshake tools | 5 MCP tools, 25 tests | 4-5 hours |
| **3** | ADR-010 | Docs refactor | Split instructions, MCP reference | 1-2 hours |
| **4** | — | Integration + e2e | Full workflow testing | 2-3 hours |

**Total:** ~10-13 hours, TDD throughout

---

## Key Files to Change

```
src/keeli/
├─ main.py                    ← Add hierarchy validators
├─ mcp_server.py              ← Add 5 handshake tools + guards
└─ templates.py               ← Update COPILOT_INSTRUCTIONS, add Handshake Status field

tests/
├─ test_commands.py           ← 15 new hierarchy tests
└─ test_mcp_server.py         ← 25 new handshake + guard tests

docs/
├─ decision.md                ← Add ADR-008/009/010
├─ ai_log.md                  ← Log analysis + start entries
├─ MCP_TOOLS.md               ← NEW: MCP reference guide
└─ README.md                  ← Split audience sections
```

---

## Next Steps

### @architect
- [ ] Review [ARCHITECTURAL_ISSUES_AND_FIXES.md](ARCHITECTURAL_ISSUES_AND_FIXES.md)
- [ ] Confirm ADR-008/009/010 logic is sound
- [ ] Approve implementation roadmap
- [ ] Create formal ADR entries in `docs/decision.md`

### @po
- [ ] Review Issue #2 (handshakes)
- [ ] Confirm sign-off sequence matches your grooming workflow
- [ ] Verify Epic > Story > Task hierarchy aligns with how you break down epics

### @developer (once @architect approves)
- [ ] Start Phase 1: TDD → write failing tests first
- [ ] implement validators in `cmd_start`, `cmd_story`, `cmd_complete`
- [ ] Add hierarchy tests (15 tests)
- [ ] Move to Phase 2 once Phase 1 passes

---

## Test Scenarios (Phase 4)

```
✅ Full Workflow E2E
  [1] Create epic
  [2] Create story linked to epic
  [3] Create task linked to story + epic
  [4] @po sign-off
  [5] @architect sign-off
  [6] @developer sign-off
  [7] @security sign-off
  [8] complete task
  → Verify ai_log has all sign-off entries

❌ Failure Scenarios
  [1] Task without story → error
  [2] Story without epic → error
  [3] Complete task without @security sign-off → error
  [4] Archive epic with live stories → error
  [5] Sign-off out of order → error
```

---

## Questions for Clarification

1. **Transition period:** Should orphaned tasks (tasks with no story) be auto-fixed or hard-blocked?
   - **Recommend:** Hard-block on `keeli_complete`; warn on `keeli_next`

2. **Multi-story tasks:** Can one task belong to multiple stories?
   - **Recommend:** No — 1:N only, enforced in validator

3. **Handshake visibility:** Should the handshake table be hidden (metadata-only) or visible in task file?
   - **Recommend:** Both — metadata field + visible table (auto-updated by sign-off tools)

4. **Author sign-off:** Should @author have a separate sign-off step?
   - **Recommend:** Optional for v0.4.0; add in v0.5.0 if needed

---

**Status:** Analysis Complete ✅  
**File:** [ARCHITECTURAL_ISSUES_AND_FIXES.md](ARCHITECTURAL_ISSUES_AND_FIXES.md)  
**Logged:** 2026-03-07T03:45:00Z in docs/ai_log.md  
**Awaiting:** @po + @architect review + approval

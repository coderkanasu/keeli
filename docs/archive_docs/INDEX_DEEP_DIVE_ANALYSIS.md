# Keeli Architectural Analysis — Complete Deep Dive

**Status:** ✅ Analysis Complete  
**Date:** 2026-03-07  
**Prepared For:** @architect, @po, @developer  

---

## Documents Created

### 1. [DEEP_DIVE_SUMMARY.md](DEEP_DIVE_SUMMARY.md) ← **START HERE**
Executive summary with visual diagrams:
- **3 Issues Identified** — what's broken and why
- **3 Solutions Proposed** — how to fix each one
- **Implementation Roadmap** — 4 phases, ~10-13 hours
- **Quick reference** for all three personas

### 2. [ARCHITECTURAL_ISSUES_AND_FIXES.md](ARCHITECTURAL_ISSUES_AND_FIXES.md)
Comprehensive technical analysis:
- **Issue 1: Hierarchy Enforcement** (Epic > Story > Task)
  - Root cause analysis
  - Fix with ADR-008
  - Implementation details
  
- **Issue 2: Persona Handshakes** (Sign-off sequence)
  - State machine diagram
  - 4 new MCP tools (keeli_*_sign_off)
  - Validation rules
  - Fix with ADR-009
  
- **Issue 3: LLM Instructions** (CLI vs MCP)
  - Why it breaks LLM workflows
  - Audience split strategy
  - Docs refactor plan
  - Fix with ADR-010

- **Implementation Roadmap** with detailed phases
- **Questions for clarification**

### 3. [MCP_TOOLS_IMPLEMENTATION_SPEC.md](MCP_TOOLS_IMPLEMENTATION_SPEC.md)
Detailed technical specification:
- **ADR-008 validators** (hierarchy rules)
- **ADR-009 new MCP tools** (5 sign-off handlers)
  - keeli_po_sign_off
  - keeli_architect_sign_off
  - keeli_developer_sign_off
  - keeli_security_sign_off
  - keeli_complete (updated guard)
- **Error codes and responses** (structured for MCP clients)
- **Testing checklist** (30 test scenarios)
- **Return format examples** (JSON)

---

## Visual Diagrams

### Current State vs. Fixed State
![Current: Epic → Story → Task (no validation) → broken](DEEP_DIVE_SUMMARY.md)
![Fixed: Epic (enforce) → Story (enforce) → Task (enforce) → handshakes → Complete](DEEP_DIVE_SUMMARY.md)

---

## Three Issues at a Glance

| Issue | Problem | Root Cause | Fix |
|-------|---------|-----------|-----|
| **1. Hierarchy** | Tasks/Stories can be orphaned (no parent links) | Optional epic/story parameters; no validation | ADR-008: Make epic+story required; validate on create/archive |
| **2. Handshakes** | Sign-off table is decorative; personas skip stages | No enforcement mechanism; no state transitions | ADR-009: 4 new MCP tools; handshake status field; guards on keeli_complete |
| **3. MCP vs CLI** | LLM instructions say "use CLI" but LLMs can't execute shell | Instructions assume shell access; MCP tools weren't designed as primary interface | ADR-010: Split instructions by audience (LLM=MCP only); CLI for local humans |

---

## For Each Persona

### 👤 @po (Product Owner)

**Your Review Checklist:**
- [ ] Read [DEEP_DIVE_SUMMARY.md](DEEP_DIVE_SUMMARY.md) — Issue #2 (handshakes)
- [ ] Confirm the sign-off sequence matches your grooming workflow
- [ ] Verify Epic > Story > Task hierarchy aligns with how you break down epics
- [ ] Agree with ADR-009 (is @po sign-off the first gate for every task?)
- [ ] Approve starting implementation once @architect confirms

**Questions for you:**
1. Should a task ever exist without a story? → **Our recommendation:** No, hard-block it.
2. Does @po always sign off before @architect designs? → **Our recommendation:** Yes, ACs+NFRs are the contract.

### 🏗️ @architect (Architecture & Design)

**Your Review Checklist:**
- [ ] Read [ARCHITECTURAL_ISSUES_AND_FIXES.md](ARCHITECTURAL_ISSUES_AND_FIXES.md) — all 3 issues
- [ ] Review ADR-008/009/010 outlines (see issue sections)
- [ ] Confirm the implementation roadmap is sound
- [ ] Review [MCP_TOOLS_IMPLEMENTATION_SPEC.md](MCP_TOOLS_IMPLEMENTATION_SPEC.md) for technical details
- [ ] Formally add ADR-008/009/010 to `docs/decision.md` once approved
- [ ] Hand off to @developer for Phase 1 implementation (TDD)

**Questions for you:**
1. Should the handshake table be visible (markdown) or hidden (metadata-only)? → **Our recommendation:** Both — metadata + visual table auto-updated by tools.
2. Is the 4-persona sign-off sequence correct? → **Order we propose:** @po → @architect → @developer → @security.

### 💻 @developer (Implementation)

**Your Review Checklist:**
- [ ] Skim [DEEP_DIVE_SUMMARY.md](DEEP_DIVE_SUMMARY.md) to understand context
- [ ] Read [MCP_TOOLS_IMPLEMENTATION_SPEC.md](MCP_TOOLS_IMPLEMENTATION_SPEC.md) for exact requirements
- [ ] Plan Phase 1 (ADR-008): write failing tests first
  - Task 1: Validators for keeli_start (epic+story required)
  - Task 2: Validators for keeli_story (epic required)
  - Task 3: Guards on keeli_complete (no orphans)
  - ~15 tests, TDD throughout
- [ ] Once Phase 1 passes, move to Phase 2 (ADR-009): 5 new MCP tools
  - ~25 tests per tool

**Starting Point:** Once @architect approves, create 3 tasks in keeli:
1. `keeli start "Phase 1: Hierarchy Validators" -k developer -p P0`
2. `keeli start "Phase 2: Handshake Sign-Off Tools" -k developer -p P0`
3. `keeli start "Phase 3: Docs Refactor (MCP-first)" -k developer -p P0`

---

## Next Steps

### Immediate (Today)

**For @architect:**
1. ✅ Read DEEP_DIVE_SUMMARY.md (10 min)
2. ✅ Read ARCHITECTURAL_ISSUES_AND_FIXES.md (20 min)
3. → Confirm the 3 issues and 3 ADRs via Slack/channel
4. → If confirmed, formally add ADR-008/009/010 to `docs/decision.md`

**For @po:**
1. ✅ Read DEEP_DIVE_SUMMARY.md (10 min)
2. → Read Issue #2 (Handshakes) section in ARCHITECTURAL_ISSUES_AND_FIXES.md (10 min)
3. → Confirm the sign-off sequence is correct

### Phase 1 (Once @architect approves, ~2-3 hours)

@developer implements hierarchy validators (ADR-008):
- Validate epic+story required in keeli_start
- Validate epic required in keeli_story
- Guard against archiving parents with live children
- 15 new tests, all TDD

### Phase 2 (After Phase 1 passes, ~4-5 hours)

@developer implements handshake tools (ADR-009):
- 5 new MCP tools (keeli_*_sign_off)
- Add Handshake Status field to tasks
- Update keeli_complete guard
- 25 new tests

### Phase 3 (Parallel with Phase 2, ~1-2 hours)

@author refactors instructions (ADR-010):
- Split COPILOT_INSTRUCTIONS by audience
- Create docs/MCP_TOOLS.md reference
- Update README for both CLI + MCP users

### Phase 4 (After Phases 1-3, ~2-3 hours)

Integration & e2e testing:
- Full workflow: epic → @po sign-off → story → @architect sign-off → task → @developer sign-off → @security sign-off → complete
- Hierarchy validation throughout
- Error path testing

---

## Key Decision Points

| Question | Recommendation | Rationale |
|----------|---|---|
| Orphaned tasks allowed in transition? | No, hard-block from day 1 | Clean state prevents confusion; can be fixed manually later if needed |
| Multi-story tasks allowed? | No, 1:N only | Simplifies burndown; prevents ambiguity about which story a task belongs to |
| Handshake table visible or hidden? | Both — metadata + markdown | Metadata field for guards; visual table for human readability |
| @author sign-off step needed? | Optional for v0.4.0 | Can add in v0.5.0 if needed; not critical for Five-Persona flow |
| LLM instructions reference CLI or MCP? | MCP only (for LLM section) | LLMs can't execute shell; CLI is "local human use only" |

---

## File Dependencies

### Must read in this order:
```
DEEP_DIVE_SUMMARY.md  
  ↓ (issue overview)
ARCHITECTURAL_ISSUES_AND_FIXES.md
  ↓ (detailed technical analysis)
MCP_TOOLS_IMPLEMENTATION_SPEC.md
  ↓ (exact signatures, errors, tests)
```

### Changes to repository:
```
docs/
├─ decision.md        ← Add ADR-008/009/010
├─ ai_log.md          ← Already logged analysis completion
├─ MCP_TOOLS.md       ← Create (new)
└─ tasks/             ← Create 3 new implementation tasks

src/keeli/
├─ main.py            ← Add hierarchy validators
├─ mcp_server.py      ← Add 5 handshake tools + guards
└─ templates.py       ← Update COPILOT_INSTRUCTIONS, add Handshake Status

tests/
├─ test_commands.py   ← Add 15 hierarchy tests
└─ test_mcp_server.py ← Add 25 handshake tests

.github/
└─ copilot-instructions.md  ← Refactor (Split by audience)

ROOT (new artifacts)
├─ ARCHITECTURAL_ISSUES_AND_FIXES.md  ✅ Created
├─ DEEP_DIVE_SUMMARY.md               ✅ Created
└─ MCP_TOOLS_IMPLEMENTATION_SPEC.md    ✅ Created
```

---

## Rollout Timeline

| Phase | What | Owner | Days | Start |
|-------|------|-------|------|-------|
| Approval | Review docs, confirm ADRs | @architect + @po | 1 | Today |
| Phase 1 | Hierarchy validators | @developer | 1 | Tomorrow |
| Phase 2 | Handshake tools | @developer | 1-2 | Day 3 |
| Phase 3 | Docs refactor | @author | 1 | Day 3 (parallel) |
| Phase 4 | Integration testing | @developer | 1 | Day 5 |
| **Total** | | | ~5 days | |

---

## Success Criteria

✅ All three issues are fixed when:

**Issue 1 (Hierarchy):**
- [ ] Creating a task without epic/story fails with clear error
- [ ] Creating a story without epic fails with clear error
- [ ] keeli_complete rejects archiving parents with live children
- [ ] All 15 hierarchy tests pass

**Issue 2 (Handshakes):**
- [ ] Each persona has a sign-off tool (keeli_*_sign_off)
- [ ] Validation guards prevent skipping steps
- [ ] keeli_complete fails if not all signed off
- [ ] ai_log shows all 4 sign-off entries with personas
- [ ] All 25 handshake tests pass

**Issue 3 (MCP vs CLI):**
- [ ] COPILOT_INSTRUCTIONS split: "For AI Agents" (MCP only) + "For Local Use" (CLI)
- [ ] New docs/MCP_TOOLS.md documents all MCP tools
- [ ] README has both audiences clearly labeled
- [ ] Examples show MCP tools first (LLM-primary)
- [ ] No confusion in LLM workflow

---

## Contact & Questions

If you have questions about any part of this analysis:

1. **For Issue #1 (Hierarchy):** See [ARCHITECTURAL_ISSUES_AND_FIXES.md#issue-1](ARCHITECTURAL_ISSUES_AND_FIXES.md) + [MCP_TOOLS_IMPLEMENTATION_SPEC.md#adr-008](MCP_TOOLS_IMPLEMENTATION_SPEC.md)
2. **For Issue #2 (Handshakes):** See [ARCHITECTURAL_ISSUES_AND_FIXES.md#issue-2](ARCHITECTURAL_ISSUES_AND_FIXES.md) + [MCP_TOOLS_IMPLEMENTATION_SPEC.md#adr-009](MCP_TOOLS_IMPLEMENTATION_SPEC.md)
3. **For Issue #3 (MCP):** See [ARCHITECTURAL_ISSUES_AND_FIXES.md#issue-3](ARCHITECTURAL_ISSUES_AND_FIXES.md) + [DEEP_DIVE_SUMMARY.md#issue-3](DEEP_DIVE_SUMMARY.md)

---

## Acknowledgments

This deep dive addresses the feedback from the user:
- ✅ "Epics should have stories and stories should have tasks" → ADR-008
- ✅ "Each story/task should have a handshake where personas make sure they update this" → ADR-009
- ✅ "Keeli should not be directly embedded into LLM because there's no way for LLM to have a hook" → ADR-010

**All three issues now have:**
- Root cause analysis
- Detailed fix with ADR
- Implementation spec (signatures, errors, tests)
- Rollout plan

---

**Status:** Ready for @po + @architect review ✅

# ADR-012: Lean Instructions + Persona Hooks (On-Demand Loading)

**Date:** 2026-03-07  
**Status:** Approved  
**Decision:** Split bloated copilot-instructions into lean core + persona-specific hooks. Personas loaded on-demand based on task requirements.

---

## Context

**Problem with current approach:**
- `copilot-instructions.md` embeds **full Five-Persona Architecture** definition (2,000+ lines)
- All personas loaded for **every task**, regardless of relevance
- LLM must parse massive instruction set even if only working as @developer
- Violates **progressive disclosure** principle: show only what's needed now

**Result:** Token waste, cognitive overload for LLM, hard to maintain.

---

## Solution: Hook-Based Persona Loading

### New Structure

```
.github/
├─ copilot-instructions.md     [LEAN: Core framework only, ~300 lines]
│  └─ References docs/personas.md
│  └─ Provides hook mechanism
│
docs/
├─ personas.md                 [FULL: All 5 personas, ~1,200 lines]
│  ├─ ## po
│  ├─ ## architect
│  ├─ ## developer
│  ├─ ## security
│  └─ ## author
│
tasks/
└─ task-*.md                   [SPECIFIES: **Persona:** @developer]
   └─ MCP keeli_next() injects persona-specific rules
```

---

## Lean copilot-instructions.md (~300 lines)

```markdown
# GitHub Copilot Custom Instructions (Keeli Framework v0.5.0)

## Core Framework

You are operating under a **Five-Persona Architecture**. Each task specifies which persona(s) are responsible via the **Persona:** field.

- @po: Product ownership (requirements, user stories, acceptance criteria)
- @architect: System design (interfaces, decisions, test strategy)
- @developer: Implementation (code, tests, debugging)
- @security: Security review (threat model, OWASP checks, findings)
- @author: Documentation (user-facing docs, examples, WCAG compliance)

**Full persona definitions:** See [docs/personas.md](../../docs/personas.md)

---

## Session Start Protocol

At the beginning of **EVERY** conversation you **MUST**:

1. Read `docs/project.md` to understand the project context.
2. Scan `docs/tasks/` for any file whose status is **In Progress** or **Blocked**.
3. Read the **last 30 lines** of `docs/ai_log.md` to understand recent activity.
4. Read `docs/decision.md` to avoid re-litigating settled decisions.
5. Only **THEN** proceed with the user's request.

---

## Workflow: File-First, LLM-Native (ADR-011)

### How to Work on a Task

1. **Get next task:** Call `keeli_next()` 
   - Returns: task slug, priority, **persona assignment**, HATEOAS hints
   
2. **Read task file:** `docs/tasks/<slug>.md`
   - Look for: `**Persona:** @<role>`
   - Activate that persona's ruleset (below)
   
3. **Follow persona rules:** Edit task file directly based on your role
   - Fill your section (e.g., `## @developer (Implementation)`)
   - Update handshake table (mark box, add timestamp)
   - Call `keeli_log()` when done
   
4. **Inject context:** Call `keeli_analyze(slug)` before starting implementation
   
5. **Next steps:** Follow HATEOAS hints in the task file for what to do next

### MCP Tools (Read-Only / Safe)

```
keeli_next()          Get priority task + persona assignment
keeli_analyze()       Inject AI context hints
keeli_chain()         Run multi-step pipelines
keeli_log()           Append audit entries
keeli_digest()        Get context snapshot
keeli_find()          Query by ID/keyword
keeli_history()       Query audit trail
```

### Never Use Tools For

- Status transitions (edit task file)
- Handshake sign-offs (edit task file + keeli_log)
- Metadata updates (edit task file)

---

## Persona Activation Hook

**When you receive a task:**

```javascript
task = keeli_next()
// Output example:
// {
//   "slug": "task-oauth-setup",
//   "persona": "@developer",
//   "priority": "P0",
//   "next_actions": [...]
// }

// Load persona rules:
// 1. Open docs/personas.md
// 2. Find section: ## developer
// 3. Read: **Mindset**, **Core Skills**, **Flags immediately**, **NEVER**
// 4. Apply those rules for this task only
```

**In task file:**

```markdown
**Persona:** @developer

<!-- HATEOAS: Load persona rules from docs/personas.md ## developer -->
<!-- 
  You are @developer for this task.
  Rules:
  - Implement against @architect's interface (defined in Design Summary)
  - TDD: red → green → refactor
  - All tests must pass
  - No hardcoded values, TODOs, or debug code
  
  Full rules: See docs/personas.md ## developer
-->
```

---

## Task Lifecycle (Unchanged)

```
Backlog → In Progress → Review → Completed
       ↓                    ↓
    Blocked ← unblocked    Reopened → In Progress
```

**Handshakes (File-First):**
| Persona | Signed | Summary |
|---------|--------|---------|
| @po | ☑ | ACs defined |
| @architect | ☐ | Waiting for design |
| @developer | ☐ | Waiting for implementation |
| @security | ☐ | Waiting for review |

---

## Scope Guardrails

When **@developer** encounters ambiguity:
- Pause and ask the human or @po before proceeding
- Do NOT guess at requirements—confirm first

When **@architect** designs:
- Check `docs/skills.md` for tech stack assumptions
- If not recorded, ask before proceeding
- Define interfaces before @developer codes

---

## Bundled Skills

These are the specialization skills registered for this project. Personas **MUST** apply this expertise when writing or reviewing code.

<!-- KEELI_SKILLS_START -->
(no skills registered — run `keeli stack` to apply a preset, or `keeli skill add` for individual skills)
<!-- KEELI_SKILLS_END -->

---

## Files You Work With

| File | Owner | Purpose |
|------|-------|---------|
| `docs/project.md` | @architect | Project context, tech stack, high-level goals |
| `docs/decision.md` | @architect | Architectural decisions (ADRs) + rationale |
| `docs/personas.md` | @architect | Full persona definitions (load on demand) ← **NEW HOOK** |
| `docs/skills.md` | @architect | Tech stack + constraints (project-specific) |
| `docs/tasks/<slug>.md` | @po / @architect / @developer / @security / @author | Per-task tracking + handshakes |
| `docs/ai_log.md` | All | Timestamped audit trail |

---

## When to Read docs/personas.md

Read the full persona definition (`docs/personas.md`) when:
- You receive a task with `**Persona:** @<role>`
- You need to understand the **Flags immediately** section
- You need to check the **NEVER** rules for your role

**Don't read:** If the task doesn't apply to your persona (don't load @security rules if you're @developer).

---

## Summary

✅ **Lean instructions** (this file: ~300 lines)  
✅ **Persona hooks** (reference docs/personas.md on demand)  
✅ **On-demand loading** (task specifies Persona, load that persona only)  
✅ **File-first workflow** (edit task files, not tool calls)  
✅ **Progressive disclosure** (only show rules relevant to this task)

Result: Copilot instructions stay focused; personalities load only when needed.
```

---

## docs/personas.md (Unchanged Structure)

The file stays where it is (`docs/personas.md`), but now:
- **Copilot-instructions.md links to it** (not embedding full text)
- **Task files specify which persona is active** (via `**Persona:**` field)
- **LLM loads full rules only for that persona** (not all 5 at once)

---

## How keeli_next() Changes (Integration Point)

**Current:**
```json
{
  "slug": "task-oauth",
  "priority": "P0",
  "title": "Implement OAuth2 login"
}
```

**New (with persona hook):**
```json
{
  "slug": "task-oauth",
  "priority": "P0",
  "title": "Implement OAuth2 login",
  "persona": "@developer",
  "persona_hint": "See docs/personas.md ## developer for your ruleset",
  "next_actions": [...]
}
```

---

## HATEOAS Hints in Task Files

Each task file includes in-line persona guidance:

```markdown
**Persona:** @developer

<!-- HATEOAS: Persona Hook
  You are assigned as @developer for this task.
  Rules to follow:
  1. Implement per @architect's interface (defined above)
  2. TDD: failing test first → implementation → refactor
  3. No hardcoded values, TODOs, or debug code
  4. All tests pass before marking complete
  
  Full persona definition: docs/personas.md ## developer
  If you need the complete ruleset, read that file.
-->

## Objective
...
```

---

## Migration Path

### What Changes:
1. **Trim `copilot-instructions.md`** from 2,000+ lines to ~300 lines
   - Remove full persona definitions (move to hook)
   - Keep core framework + workflow
   - Add "Persona Activation Hook" section

2. **Update task templates** (`src/keeli/templates.py`)
   - Add HATEOAS persona hook comments
   - Example: `<!-- HATEOAS: You are @developer ... -->`

3. **Update `keeli_next()` response** (MCP)
   - Include `"persona": "@developer"` field
   - Include persona hint link

### What Stays:
- `docs/personas.md` (unchanged, just referenced instead of embedded)
- Task lifecycle (unchanged)
- Handshake mechanism (unchanged)
- All five personas (still all rules exist, just loaded on-demand)

---

## Benefits

✅ **Token efficiency:** Copilot instructions ~30% smaller  
✅ **Cognitive clarity:** LLM only sees relevant persona rules  
✅ **Scalability:** Easy to add personas (6th, 7th persona) without bloating instructions  
✅ **Maintainability:** Persona changes in one place (docs/personas.md)  
✅ **Progressive disclosure:** Show what's needed now, link to full definition  
✅ **Works with all LLM models:** Hooks don't require tool support  

---

## Example: @developer Workflow

1. **Session starts**
   ```
   Call keeli_next()
   ← Returns: slug="task-oauth", persona="@developer", ...
   ```

2. **Read task file**
   ```markdown
   **Persona:** @developer
   
   <!-- HATEOAS: As @developer, implement this per the interface
        defined in @architect's Design Summary section.
        Full rules: See docs/personas.md ## developer
   -->
   ```

3. **Quick check of persona rules**
   - Read section: `## developer` in docs/personas.md
   - Key rules: TDD, no TODOs, implement per interface
   - Apply those rules to this task

4. **Work**
   - Write failing test
   - Implement code
   - Check handshake box
   - Call `keeli_log()`

---

## Example: @architect Workflow

1. **Session starts**
   ```
   Call keeli_next()
   ← Returns: slug="epic-user-auth", persona="@architect", ...
   ```

2. **Read task file**
   ```markdown
   **Persona:** @architect
   
   <!-- HATEOAS: As @architect, define the interface + design
        before @developer starts coding.
        Full rules: See docs/personas.md ## architect
   -->
   ```

3. **Check rules**
   - Read: `## architect` in docs/personas.md
   - Key sections: Mindset, Core Skills, Flags immediately
   - Verify tech stack is recorded (STOP if not)

4. **Design**
   - Fill Design Summary
   - Fill Implementation Plan
   - Fill Test Strategy
   - Check handshake box

---

## Comparison: Before vs After

### Before (Bloated)
```
copilot-instructions.md (2,000+ lines)
├─ Core framework (50 lines)
├─ @po persona (300 lines)
├─ @architect persona (300 lines)
├─ @developer persona (300 lines)
├─ @security persona (300 lines)
└─ @author persona (300 lines)

Result: LLM loads everything, processes everything, wastes tokens
```

### After (Lean + Hooks)
```
copilot-instructions.md (300 lines)
├─ Core framework (50 lines)
├─ Workflow (100 lines)
├─ Persona Activation Hook (100 lines)
└─ MCP tools reference (50 lines)

docs/personas.md (1,200 lines)
├─ @po (250 lines)
├─ @architect (250 lines)
├─ @developer (250 lines)
├─ @security (250 lines)
└─ @author (250 lines)

Task file links to relevant persona only:
"See docs/personas.md ## developer for your ruleset"

Result: LLM loads base instructions + specific persona on-demand.
```

---

## Implementation

### Phase 1: Trim Copilot Instructions
1. Delete full persona definitions from `copilot-instructions.md`
2. Add "Persona Activation Hook" section
3. Add links to `docs/personas.md`
4. Keep workflow + scope guardrails

### Phase 2: Update Task Templates
1. Add HATEOAS persona hook comments
2. Include link to `docs/personas.md ## <persona>`

### Phase 3: Update keeli_next() (MCP)
1. Include `"persona"` field in response
2. Include `"persona_hint"` link

### Effort
- Phase 1: 1 hour
- Phase 2: 30 min
- Phase 3: 30 min
- **Total: 2 hours**

---

## Summary

**ADR-012 Decision:** Split bloated instructions into lean core + persona hooks.

**Result:**
- Copilot-instructions.md: ~300 lines (was 2,000+)
- Personas loaded on-demand (not for every task)
- File-first workflow, no tool overhead
- Each persona's rules live in one place (docs/personas.md)
- Task files link to relevant persona only

**Status:** Ready to implement (2-hour effort)

---

This keeps the system **lean, focused, and scalable** as you add more personas or refine rules.

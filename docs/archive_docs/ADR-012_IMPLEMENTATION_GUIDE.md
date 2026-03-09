# ADR-012 Implementation Guide: Lean Instructions + Persona Hooks

**Predecessor:** ADR-011 (File-First Architecture)  
**Effort:** ~2 hours  
**Owner:** @architect (trim instructions) + @author (personas) + @developer (keeli_next hook)  
**Status:** Ready to implement after ADR-011 Phase 1

---

## What This Achieves

✅ Reduce copilot-instructions.md from **2,000+ lines → 300 lines**  
✅ Load personas **on-demand only** (not for every task)  
✅ Prevent **"persona overload"** (LLM seeing all 5 rule sets when only 1 applies)  
✅ Keep **single source of truth** for each persona (docs/personas.md sections)  
✅ Progressive disclosure: **Show what's needed now, link to full docs**

---

## Implementation Tasks

### Task 1.1: Trim `.github/copilot-instructions.md` (45 min)

**Current state:**
- File: `.github/copilot-instructions.md` (~2,000 lines)
- Contains: Core framework (50 lines) + full persona definitions (1,950 lines)

**Changes:**

1. **Keep these sections:**
   - Core Philosophy (Core tenets)
   - Session Start Protocol (5 steps)
   - Task Lifecycle (state diagram) 
   - The Five Personas (👈 **CHANGE THIS SECTION**)
   - Workflow Rules  
   - Memory and Logging  
   - Scope Guardrails

2. **Replace "The Five Personas" section** with:
   ```markdown
   ## The Five Personas

   You are operating under a **Five-Persona Architecture**:

   - **@po (Product Owner):** User-first, value-driven. Owns the "what" and "why".
   - **@architect:** Design-first. Defines seams, interfaces, and decisions.
   - **@developer:** Disciplined craftsman. Implements per spec, TDD-focused.
   - **@security:** Sceptical by default. Validates auth, data, threat model.
   - **@author:** User-facing clarity. Docs, examples, WCAG 2.1 AA.

   ### Full Persona Definitions

   Each task specifies which persona is responsible via the `**Persona:**` field.

   **To load a persona's full ruleset:**
   1. Task file shows: `**Persona:** @developer` (or @po, @architect, etc.)
   2. Open [docs/personas.md](../../docs/personas.md)
   3. Find section: `## developer`
   4. Read: Mindset, Core Skills, MUST/MUST NOT, Flags Immediately
   5. Apply those rules to this task **only**

   → See [docs/personas.md](../../docs/personas.md) for complete persona definitions.
   ```

3. **DELETE entire sections:**
   - `### 1. @po (Product Owner)` — Full 100-line definition
   - `### 2. @architect` — Full 100-line definition
   - `### 3. @developer` — Full 100-line definition
   - `### 4. @security` — Full 100-line definition
   - `### 5. @author` — Full 100-line definition

4. **Add new section after "Workflow Rules":**
   ```markdown
   ## Persona Activation Hook

   When you receive a task assignment:

   ```javascript
   keeli_next()
   // Returns: {
   //   "slug": "task-oauth", 
   //   "persona": "@developer",     // ← Persona for this task
   //   "persona_hint": "See docs/personas.md ## developer",
   //   "title": "Implement OAuth2 login"
   // }
   ```

   **Action:** Open docs/personas.md and read only the section for your assigned persona.
   Don't load all 5 personas—load only the one that applies to this task.

   This keeps instructions lean and focused on what you need right now.
   ```

5. **Result:** File shrinks from 2,000 → ~300 lines. No function or workflow changes.

---

### Task 1.2: Update Task Templates in `src/keeli/templates.py` (45 min)

**Current state:**
```python
TASK_TEMPLATE = """
**ID:** {id}
**Status:** Backlog
**Priority:** {priority}
**Created:** {created}
**Epic:** 
**Story:** 
**Persona:** 

## Objective

(content)

## Handshake

| Persona | Signed | Timestamp | Notes |
|---------|--------|-----------|-------|
| @po | ☐ | |
| @architect | ☐ | |
| @developer | ☐ | |
| @security | ☐ | |
"""
```

**Change 1: Add HATEOAS persona hook comments**

```python
TASK_TEMPLATE = """
**ID:** {id}
**Status:** Backlog
**Priority:** {priority}
**Created:** {created}
**Epic:** 
**Story:** 
**Persona:** 

<!-- HATEOAS: Persona Hook
  The **Persona:** field above specifies who owns this task.
  
  When you are assigned this task:
  1. Note the Persona field (e.g., **Persona:** @developer)
  2. Open docs/personas.md
  3. Find the section for your persona (## developer)
  4. Read: Mindset, Core Skills, MUST/MUST NOT, Flags Immediately
  5. Apply those rules to this task
  
  Don't load personas not assigned to you.
  Don't process all 5 persona rule sets for every task.
  This keeps you focused and token-efficient.
-->

## Objective

(content)

## Handshake

| Persona | Signed | Timestamp | Notes |
|---------|--------|-----------|-------|
| @po | ☐ | |
| @architect | ☐ | |
| @developer | ☐ | |
| @security | ☐ | |
"""
```

**Change 2: Add example to COPILOT_INSTRUCTIONS reference**

In the same file, update the docstring above TEMPLATE_* constants:

```python
"""
Task templates with HATEOAS persona hook integration.
Each task specifies **Persona:** field. LLMs load only that persona's rules from docs/personas.md.
This keeps instructions lean (~300 lines) and prevents persona overload.
"""
```

---

### Task 1.3: Update `keeli_next()` MCP Response (30 min)

**File:** `src/keeli/mcp_server.py`  
**Function:** `handler_keeli_next()`

**Current response:**
```python
def handler_keeli_next():
    # ...
    task = {
        "slug": "task-oauth",
        "priority": "P0",
        "title": "Implement OAuth2 login",
        "status": "Backlog",
        # ... other fields
    }
    return ToolResult(content=[...], is_error=False)
```

**Updated response:**

```python
def handler_keeli_next():
    # ...
    # Parse task file to get Persona field
    persona = _parse_task_field(path, "Persona")
    
    task = {
        "slug": "task-oauth",
        "priority": "P0",
        "title": "Implement OAuth2 login",
        "status": "Backlog",
        "persona": persona or "@developer",  # fallback
        "persona_hint": f"Load persona rules from docs/personas.md ## {persona.lstrip('@')}" if persona else None,
        # ... other fields
    }
    return ToolResult(content=[...], is_error=False)
```

**Test case to add:**
```python
def test_keeli_next_includes_persona():
    # Create task file with **Persona:** @architect
    # Call keeli_next()
    # Assert response["persona"] == "@architect"
    # Assert "persona_hint" in response
```

---

## Migration Checklist

- [ ] **Task 1.1:** Trim `.github/copilot-instructions.md` (delete ~1,700 lines of persona definitions)
  - [ ] Keep core framework + workflow
  - [ ] Add "Persona Activation Hook" section
  - [ ] Link to docs/personas.md
  - [ ] Run: `wc -l .github/copilot-instructions.md` → should be ~300 lines

- [ ] **Task 1.2:** Update `src/keeli/templates.py`
  - [ ] Add HATEOAS persona hook comments to TASK_TEMPLATE
  - [ ] Update docstring to explain hook mechanism
  - [ ] Verify syntax (no markdown breaks)

- [ ] **Task 1.3:** Update `keeli_next()` in `src/keeli/mcp_server.py`
  - [ ] Add `persona` field extraction from task file
  - [ ] Add `persona_hint` field to response
  - [ ] Add test: `test_keeli_next_includes_persona`

- [ ] **Testing (1 hour):**
  - [ ] Call `keeli_next()` → verify persona field is populated
  - [ ] Read task file → verify HATEOAS comment is present
  - [ ] Run: `grep -r "@po\|@architect\|@developer" .github/copilot-instructions.md` → should show only "The Five Personas" section header

- [ ] **Documentation:**
  - [ ] Update `docs/project.md` → mention "Lean instructions + on-demand personas"
  - [ ] Update README.md → link to ADR-012 and explain copilot hook mechanism

---

## Code Changes Summary

### File: `.github/copilot-instructions.md`

**Before:**
```markdown
## The Five Personas

### 1. @po (Product Owner)
- **Mindset:** ...
- **MUST:** ...
[200 lines]

### 2. @architect
- **Mindset:** ...
[200 lines]

[... 3 more personas @ 200 lines each ...]

Total: 2,000+ lines
```

**After:**
```markdown
## The Five Personas

- **@po:** User-first, value-driven...
- **@architect:** Design-first...
- **@developer:** Disciplined craftsman...
- **@security:** Sceptical by default...
- **@author:** User-facing clarity...

### Full Persona Definitions

Each task specifies which persona is responsible via the `**Persona:**` field.

To load a persona's full ruleset:
1. Task shows: `**Persona:** @<role>`
2. Open docs/personas.md
3. Find section: `## <role>`
4. Read and apply that persona's rules to this task

→ See docs/personas.md for complete definitions.

## Persona Activation Hook

When you receive a keeli_next() response:
```javascript
{
  "persona": "@developer",
  "persona_hint": "See docs/personas.md ## developer"
}
```

Load only that persona's rules. Don't process all 5 for every task.

Total: ~300 lines
```

### File: `src/keeli/templates.py`

Add HATEOAS comment:
```python
TASK_TEMPLATE = """
...
**Persona:** 

<!-- HATEOAS: Persona Hook
  When assigned this task, load persona rules from docs/personas.md.
  Only load the persona specified in **Persona:** field.
  This keeps instructions lean and focused.
-->
...
"""
```

### File: `src/keeli/mcp_server.py`

Update `handler_keeli_next()`:
```python
def handler_keeli_next():
    # ... find next task ...
    
    persona = _parse_task_field(path, "Persona")  # NEW
    
    response = {
        "slug": task_slug,
        "persona": persona or "@developer",  # NEW
        "persona_hint": f"Load persona rules from docs/personas.md ## {persona.lstrip('@')}" if persona else None,  # NEW
        # ... existing fields ...
    }
    
    return ToolResult(content=[TextContent(type="text", text=json.dumps(response))])
```

---

## Testing Strategy

### Unit Tests (in `tests/test_mcp_server.py`)

```python
def test_keeli_next_includes_persona_field():
    """Verify keeli_next() returns persona field."""
    # Create task file: **Persona:** @developer
    response = handler_keeli_next()
    assert "persona" in response
    assert response["persona"] == "@developer"

def test_keeli_next_persona_hint_links_docs():
    """Verify persona_hint links to docs/personas.md."""
    response = handler_keeli_next()
    assert "persona_hint" in response
    assert "docs/personas.md" in response["persona_hint"]

def test_leaned_copilot_instructions_no_duplicate_persona_defs():
    """Verify instructions don't duplicate persona definitions elsewhere."""
    instructions = read_file(".github/copilot-instructions.md")
    # Count "### 1. @po" (should be 0, since it's deleted)
    assert "### 1. @po" not in instructions
    # Count "## The Five Personas" (should be 1)
    assert instructions.count("## The Five Personas") == 1
    # File size (should be ~300 lines)
    lines = len(instructions.split("\n"))
    assert lines < 500  # generous; target ~300

def test_task_template_includes_hateoas_persona_hook():
    """Verify task template includes HATEOAS hook."""
    template = TASK_TEMPLATE
    assert "<!-- HATEOAS: Persona Hook" in template
    assert "docs/personas.md" in template
```

### Integration Test

```python
def test_workflow_persona_hook_integration():
    """Full workflow: create task, call keeli_next, verify persona hook."""
    # 1. Create task with **Persona:** @developer
    cmd_start("Task", epic="epic-auth", story="story-oauth", persona="developer")
    
    # 2. Call keeli_next()
    response = handler_keeli_next()
    
    # 3. Check persona field
    assert response["persona"] == "@developer"
    assert "persona_hint" in response
    
    # 4. Verify docs/personas.md section exists
    personas_doc = read_file("docs/personas.md")
    assert "## developer" in personas_doc
```

---

## Success Criteria

✅ `.github/copilot-instructions.md` < 400 lines (currently 2,000+)  
✅ `keeli_next()` includes `"persona"` field  
✅ `keeli_next()` includes `"persona_hint"` field pointing to docs/personas.md  
✅ Task templates include HATEOAS persona hook comment  
✅ All tests pass (6+ new tests added)  
✅ No persona definitions duplicated in instructions  
✅ docs/personas.md remains unchanged (unchanged reference location)  

---

## Timeline

- **Phase:** Post ADR-011 Phase 1 (after hierarchy validators ship)
- **Effort:** ~2 hours
  - 45 min: Trim copilot-instructions.md
  - 45 min: Update TASK_TEMPLATE + keeli_next()
  - 30 min: Testing + verification
- **Blockers:** None (orthogonal to ADR-011 implementation)
- **Dependencies:** ADR-011 Phase 1 should be complete first (cleaner diff)

---

## Roll-Back Plan

If issues arise:
1. Restore `.github/copilot-instructions.md` from git
2. Remove persona field from keeli_next() response
3. Remove HATEOAS comment from TASK_TEMPLATE
4. Revert to ADR-011 baseline

Total roll-back time: 5 min.

---

## FAQ

### Q: Why not just delete personas from instructions entirely?
**A:** Personas must be defined somewhere. This approach keeps a reference + link mechanism, so LLMs know where to find the full definitions.

### Q: What if an LLM loads all 5 personas anyway (ignores the hook)?
**A:** Progressive disclosure is a suggestion, not a hard constraint. The benefit is:
- Instructions are lean (less tokens spent on preamble)
- Links are clear (if LLM chooses to expand, it knows exactly where)
- If LLM does load all 5 from docs/personas.md, it's still structured clearly

### Q: Will this slow down task execution?
**A:** No. The hook is metadata (read-only). No additional MCP calls or delays.

### Q: Can we remove the full persona definitions from docs/personas.md eventually?
**A:** Not yet. Teams may need full definitions for training/onboarding. This design preserves them; the copilot-instructions just doesn't embed them.

### Q: Do we need to update all existing task files?
**A:** No. Existing tasks are fine (persona field may be empty). New tasks will include HATEOAS hook automatically (from updated template).

---

## Next Steps

1. Await approval from @architect (this document)
2. Create keeli task for Phase 1.1 implementation (after ADR-011 Phase 1 ships)
3. @developer implements tasks in order (1.1 → 1.2 → 1.3)
4. Run test suite; verify copilot-instructions is now <400 lines
5. Merge and document in docs/decision.md

---

**Status:** ✅ Ready to implement. ADR-012 creates a lean, hook-based instruction set. No personas lost; they're just referenced on-demand, not embedded wholesale.

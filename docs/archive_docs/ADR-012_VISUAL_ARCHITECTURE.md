# ADR-012 Architecture: Lean Instructions + Persona Hooks (Visual)

## Before: Bloated Monolith

```
┌─────────────────────────────────────────────────────────────┐
│  .github/copilot-instructions.md (2,000+ lines)             │
│                                                             │
│  ✓ Core Framework (50 lines)                               │
│  ☗ BLOAT: @po persona full rules (300 lines)               │
│  ☗ BLOAT: @architect persona full rules (300 lines)        │
│  ☗ BLOAT: @developer persona full rules (300 lines)        │
│  ☗ BLOAT: @security persona full rules (300 lines)         │
│  ☗ BLOAT: @author persona full rules (300 lines)           │
│  ✓ Workflow + Scope Guardrails (200 lines)                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘

Problem: LLM loads ALL personas for EVERY task, wastes 1,500 lines
         when only 1 persona applies (e.g., @developer for this task).
```

## After: Lean + Hooks

```
┌────────────────────────────────────┐      ┌──────────────────────────┐
│  .github/copilot-instructions.md   │      │  docs/personas.md        │
│  (~300 lines)                      │      │  (~1,200 lines)          │
│                                    │      │                          │
│  ✓ Core Framework (50 lines)       │      │  ## @po (250 lines)      │
│  ✓ Workflow (100 lines)            │      │  ## @architect (250 lines)
│  ✓ Persona Activation Hook (100 ln) ◄────► ## @developer (250 lines) │
│  ✓ Scope Guardrails (50 lines)     │      │  ## @security (250 lines)
│                                    │      │  ## @author (250 lines)  │
└────────────────────────────────────┘      └──────────────────────────┘
         ↑                                            ↑
         │                                            │
         │ keeli_next() returns:                      │
         │ {                                          │
         │   "persona": "@developer",                 │
         │   "persona_hint": "See docs/personas.md" ──┘
         │ }                                          │

Task file links:
**Persona:** @developer

<!-- HATEOAS: Load only ## developer from docs/personas.md -->

Result: LLM loads ~300 lines of instructions + ONE persona definition
        (as needed). No bloat. Token-efficient.
```

## Workflow Sequence

### Old Approach (Monolithic)
```
┌──────────────┐
│ LLM Session  │
└──────────────┘
       │
       ├─→ Read copilot-instructions.md (2,000 lines)
       │   └─→ Parse @po rules (300 lines)
       │   └─→ Parse @architect rules (300 lines)
       │   └─→ Parse @developer rules (300 lines) ← only this applies!
       │   └─→ Parse @security rules (300 lines)
       │   └─→ Parse @author rules (300 lines)
       │
       └─→ Execute task
           Result: Token waste. Cognitive overload.
```

### New Approach (Hooks)
```
┌──────────────┐
│ LLM Session  │
└──────────────┘
       │
       ├─→ Call keeli_next()
       │   ← Returns: "persona": "@developer"
       │
       ├─→ Read copilot-instructions.md (~300 lines)
       │   └─→ See Hook: "Load @developer from docs/personas.md"
       │
       ├─→ Read docs/personas.md ## developer (~250 lines)
       │   └─→ Get only relevant rules
       │
       └─→ Execute task
           Result: Lean, focused, efficient.
```

## File Dependencies

```
copilot-instructions.md (LEAN: 300 lines)
      │
      └─→ links to ────→ docs/personas.md (1,200 lines)
                              │
                              ├─→ ## @po
                              ├─→ ## @architect
                              ├─→ ## @developer ← loaded only when needed
                              ├─→ ## @security
                              └─→ ## @author

Task file (.md):
  **Persona:** @developer
  └─→ Loads only ## @developer from docs/personas.md (via HATEOAS hook)

keeli_next() (MPC):
  Returns: "persona": "@developer"
  └─→ Guides LLM to correct section in docs/personas.md
```

## Integration Points

### 1. Task Creation
```
$ keeli start "Implement OAuth" -e epic-auth -s story-oauth -p @developer
                                                               ↑
                                         Sets **Persona:** @developer in file
```

### 2. Task Query
```
$ keeli_next()
  ↓
  Returns:
  {
    "slug": "task-oauth",
    "persona": "@developer",  ← MCP tool provides persona
    "persona_hint": "See docs/personas.md ## developer"
  }
```

### 3. Task File
```markdown
**Persona:** @developer

<!-- HATEOAS: Persona Hook
  Your assigned persona: @developer
  Load rules from: docs/personas.md ## developer
  Don't load other personas for this task.
-->
```

### 4. LLM Execution
```python
# Pseudo-code showing hook mechanism
persona = task["persona"]  # "@developer"
if persona:
    # Load ONLY this persona's rules
    persona_doc = read_file("docs/personas.md")
    persona_section = extract_section(persona_doc, f"## {persona.lstrip('@')}")
    # Execute task with only this persona's rules applied
else:
    # Fallback: use default rules from copilot-instructions.md
    pass
```

## Token Efficiency Comparison

### Before (Monolithic)
```
copilot-instructions.md: 2,000 lines = ~4,000 tokens
├─ Core framework: 100 tokens ✓ needed
├─ @po rules: 600 tokens ☗ not needed (only @developer assigned)
├─ @architect rules: 600 tokens ☗ not needed
├─ @developer rules: 600 tokens ✓ needed
├─ @security rules: 600 tokens ☗ not needed
├─ @author rules: 600 tokens ☗ not needed
└─ Workflow: 400 tokens ✓ needed

Total tokens in preamble: ~4,000
"Useful" tokens: ~1,100 (27% efficiency)
Waste: ~2,900 tokens (73% overhead)
```

### After (Hooks)
```
copilot-instructions.md: 300 lines = ~600 tokens
├─ Core framework: 100 tokens ✓ needed
├─ Persona Hook explanation: 150 tokens ✓ needed
├─ Link to docs/personas.md: 50 tokens ✓ needed
└─ Workflow: 300 tokens ✓ needed

docs/personas.md (on-demand load):
└─ ## @developer section: 250 lines = ~500 tokens (loaded only when needed)

Total tokens in preamble: ~600
"Useful" tokens: ~600 (100% efficiency)
Additional tokens only when persona is loaded: ~500

Result: 
- Baseline: 600 tokens (vs 4,000 before) = 85% reduction
- Full load (with persona): 1,100 tokens = 73% reduction
- Average (assuming persona load 4/5 times): ~800 tokens = 80% reduction
```

## Personas "Activated" = "Loaded"

```
Persona Activation States:

┌─────────────────────────┐
│ Task Assignment         │
│ **Persona:** @developer │
└─────────────────────────┘
          │
          ├─→ DEACTIVATED: @po (not assigned to this task)
          │   └─ Don't load docs/personas.md ## @po
          │
          ├─→ DEACTIVATED: @architect (not assigned)
          │   └─ Don't load docs/personas.md ## @architect
          │
          ├─→ ✓ ACTIVATED: @developer (assigned)
          │   └─ Load docs/personas.md ## @developer
          │
          ├─→ DEACTIVATED: @security (not assigned)
          │   └─ Don't load docs/personas.md ## @security
          │
          └─→ DEACTIVATED: @author (not assigned)
              └─ Don't load docs/personas.md ## @author
```

## Scalability: Adding More Personas

### With Old Monolithic Approach
```
If we add @qa persona:
copilot-instructions.md grows: 2,000 + 300 = 2,300 lines
Overhead grows even larger ☗
```

### With Hook-Based Approach
```
If we add @qa persona:
copilot-instructions.md stays: ~300 lines ✓
docs/personas.md grows: 1,200 + 250 = 1,450 lines
Hook mechanism stays the same: "Load docs/personas.md ## qa"
Efficient regardless of # personas ✓
```

## Summary Diagram

```
                    ┌─── BEFORE ───┐
                    │ Monolithic   │
                    └──────────────┘
                           │
                           ▼
            ┌──────────────────────────┐
            │ 2,000-line copilot-*.md  │
            │ ALL personas embedded    │
            │ 73% waste                │
            └──────────────────────────┘
                    │       │       │
                    │       │       └─→ Bloat
                    │       │
                    ▼       ▼
                 LLM token waste

                    ┌─── AFTER ───┐
                    │ Hook-Based  │
                    └─────────────┘
                           │
                ┌──────────┴──────────┐
                ▼                     ▼
        ┌──────────────┐      ┌────────────────┐
        │ ~300-line    │      │ docs/personas. │
        │ core         │      │ md (1,200 lines)
        │ instructions │      │ loaded on      │
        │              │      │ demand only    │
        └──────────────┘      └────────────────┘
             │                       │
             └───────────────────────┘
                      │
                      ▼
              Lean + Efficient
              (80% token savings)
```

---

**Key Insight:** Instead of embedding all personas in copilot-instructions, reference them. Load only what's needed. This follows the **ADR-011 File-First, LLM-Native** principle: files are the source of truth; instructions just provide hooks to find them.

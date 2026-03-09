# Custom Skill Template: How to Register New Project Skills

> **Purpose:** Blueprint for adding custom skills to `docs/skills.md` when integrating new technologies, patterns, or domains.
> **Usage:** Run `keeli skill scan` to auto-detect; run `keeli skill add` to manually register.
> **Governance:** Requires `@architect` approval before merging; enforced at `keeli start` via handshake.

---

## 1. What is a Skill?

A **skill** is a specific constraint or decision your project made about a technology, pattern, or domain.

**NOT:** Generic knowledge (everyone knows what Python is)
**YES:** Your project's specific use of it (Python 3.12+, strict type hints, async/await everywhere)

---

## 2. Skill Entry Template

Every skill is a **single row** in `docs/skills.md` with these columns:

```
| Type | Skill | Persona | Constraint |
|------|-------|---------|------------|
| lang | Python | developer | 3.12+; type hints on every function; cli-first, no framework overhead |
```

### Required Fields:

**Type** (one of):
- `lang` - Programming language
- `framework` - Framework or SDK
- `tool` - Development tool or library
- `domain` - Architectural pattern or domain expertise
- `pattern` - Code pattern or best practice

**Skill** (the technology/concept):
- Clear name (Python, FastAPI, pytest, TDD, etc.)
- Avoid generic terms ("coding", "testing")

**Persona** (primary owner):
- `developer`, `architect`, `security`, `po`, or `author`
- Who will primarily use/enforce this skill?

**Constraint** (the decision):
- Specific to YOUR project, not generic
- Format: semicolon-separated rules
- Examples:
  - ❌ Bad: "Use pytest" (everyone does)
  - ✅ Good: "TDD; unit tests before implementation; 100% coverage on critical paths"
  - ❌ Bad: "FastAPI"
  - ✅ Good: "Uvicorn ASGI server for SSE mode only; no web UI; minimal dependencies"

---

## 3. Sample Skill Entries (Real Examples)

```markdown
| Type | Skill | Persona | Constraint |
|------|-------|---------|------------|
| lang | Python | developer | 3.12+; type hints on every function; cli-first, no framework overhead |
| framework | FastAPI | developer | Uvicorn ASGI server for SSE mode only; no web UI; minimal dependencies |
| tool | pytest | developer | TDD; unit tests before implementation; 100% coverage on critical paths |
| tool | pathlib.Path | developer | all file I/O via pathlib; never os.path; _find_project_root() walks cwd() parents for docs/project.md |
| domain | Five-Persona Architecture | architect | @po (requirements/grooming), @architect (design/ADRs), @developer (TDD implementation), @security (governance/sign-off), @author (docs/copy) |
| domain | Immutable ID Ledger | architect | T/E/S/BUG/FEAT-NNNN per-type prefixes; allocated at creation via _allocate_id(); stored in docs/.keeli_index.json; survive rename/archive/reopen |
```

---

## 4. How to Add a New Skill

### Option A: Auto-Detect (Recommended for Languages/Frameworks)

```bash
keeli skill scan
```

Scans `pyproject.toml`, `requirements.txt`, `package.json`, `pom.xml`, `Cargo.toml` etc.
Shows detected packages and prompts for approval.

```bash
? Found pytest 7.4.0. Register as TDD tool? [y/n]: y
? Constraint for pytest: TDD; unit tests before implementation; 100% coverage on critical paths
✅ Added: tool | pytest | developer | TDD; unit tests before implementation; 100% coverage on critical paths
```

### Option B: Manual Registration

Edit `docs/skills.md` directly:

```markdown
| Type | Skill | Persona | Constraint |
|------|-------|---------|------------|
| tool | black | developer | Line length 100; format on save; skip long strings |
```

Then run:
```bash
keeli skill validate
```

Checks for duplicates, required fields, proper formatting.

### Option C: Via Task Creation (Embedded)

When creating a task:

```bash
keeli start "Add Redis caching layer"
```

Task file includes:

```markdown
## Skills Required
- [ ] Redis (caching layer, 10k req/s, TTL 5min)
- Type this skill: `tool | Redis | developer | async client; connection pooling; Lua scripts for atomic ops`
```

Register it:
```bash
keeli skill add "tool" "Redis" "developer" "async client; connection pooling; Lua scripts for atomic ops"
```

---

## 5. Skill Documentation: Full Example

Let's say you're adding **Pydantic** (data validation):

### Step 1: Create the skill entry

```
| tool | Pydantic | developer | v2; strict mode on all models; custom validators with @field_validator; no Config class |
```

### Step 2: Document it in a separate file (optional but recommended)

Create `docs/requirements/pydantic-strict-validation.md`:

```markdown
# Pydantic v2: Strict Mode Validation

## Skill Entry
```
| tool | Pydantic | developer | v2; strict mode on all models; custom validators with @field_validator; no Config class |
```

## Context
We use Pydantic for request/response validation in all APIs. Strict mode catches type mismatches early.

## Constraint Breakdown
- **v2 only:** No legacy v1 syntax. Use `pip install "pydantic>=2.0"`
- **strict mode:** All BaseModel subclasses must have `model_config = ConfigDict(strict=True)`
- **@field_validator:** Use new decorator signature; no @validator (v1 style)
- **no Config class:** Use ConfigDict in model_config; config classes are deprecated

## Example: Right ✅

```python
from pydantic import BaseModel, field_validator, ConfigDict

class User(BaseModel):
    model_config = ConfigDict(strict=True)
    
    username: str
    age: int
    
    @field_validator('age')
    @classmethod
    def age_positive(cls, v):
        if v < 0:
            raise ValueError('age must be positive')
        return v
```

## Example: Wrong ❌

```python
# DON'T: Using old Config class
class User(BaseModel):
    username: str
    age: int
    
    class Config:
        validate_assignment = True
```

## Related Skills
- [tool] pytest: TDD validation with Pydantic models
- [lang] Python: 3.12+ type hints work best with Pydantic v2
```

### Step 3: Register

```bash
keeli skill add "tool" "Pydantic" "developer" "v2; strict mode on all models; custom validators with @field_validator; no Config class"
```

### Step 4: Link from task template

Update base task template to mention it:

```markdown
## Skills Applied
See [pydantic-strict-validation.md](../requirements/pydantic-strict-validation.md) for validation patterns.
```

---

## 6. Governance: Skill Sign-Off

Before a skill is "live" in the project:

| Persona | Responsibility |
|---------|-----------------|
| **@architect** | Designs skill decision; creates ADR if >1 day impact |
| **@developer** | Implements examples; verifies skill works in code |
| **@security** | Validates no security holes (e.g., Pydantic injection attacks) |
| **@po** | Confirms skill aligns with product goals |
| **@author** | Documents skill clearly with examples |

Add to `docs/skills.md` with a sign-off section:

```markdown
## Sign-Off Checklist
- [x] @architect: Pydantic v2 strict mode approved (ADR-005)
- [x] @developer: Tested in 3 test files; validated type errors caught early
- [x] @security: Reviewed for injection/bypass risks; approved
- [ ] @po: (awaiting confirmation this aligns with data validation goals)
- [ ] @author: (documentation in progress)
```

---

## 7. Anti-Patterns: What NOT to Do

❌ **Too Generic:**
```
| tool | Git | developer | version control |
```

✅ **Specific to Your Project:**
```
| tool | Git | developer | squash-merge only; conventional commits (feat:, fix:, docs:); signed commits required |
```

---

❌ **No Implementation Guidance:**
```
| domain | TDD | developer | write tests |
```

✅ **Actionable Constraint:**
```
| domain | TDD | developer | pytest; unit tests BEFORE code; >90% coverage on critical paths; keeli analyze injection on all tasks |
```

---

❌ **Duplicate Skills:**
```
| tool | pytest | developer | testing framework |
| tool | pytest | developer | unit testing |
```

✅ **One Canonical Entry:**
```
| tool | pytest | developer | TDD; unit tests before implementation; 100% coverage on critical paths |
```

Run `keeli skill validate` to catch duplicates.

---

## 8. Skill Discovery: How LLMs Use Skills

When you create a task:

1. **Task Title:** "Add Redis caching"
2. **TF-IDF Scoring:** Matches "Redis" → pulls skill entry
3. **Context Injection:** `## AI Context Hints` block added to task:
   ```markdown
   ## AI Context Hints
   **Relevant Skills:**
   - [tool] Redis: async client; connection pooling; Lua scripts for atomic ops
   - [domain] TDD: unit tests before implementation; 100% coverage
   
   **Suggested Persona:** @developer (lead), @security (review)
   ```
4. **LLM Sees:** Skill constraints automatically in task file
5. **Compliance:** LLM is guided toward correct patterns without explicit instruction

---

## 9. Quick Checklist: Before Shipping a Skill

- [ ] Type, Skill, Persona, Constraint fields complete
- [ ] Constraint is specific to YOUR project (not generic)
- [ ] All 5 personas have signed off (or documented why N/A)
- [ ] Example code or test demonstrates the skill in action
- [ ] No duplicate entries in `docs/skills.md`
- [ ] Linked from relevant task templates
- [ ] Documented in `docs/requirements/` with worked examples
- [ ] Runs `keeli skill validate` with 0 errors

---

## 10. Skill Registry Structure

Your `docs/skills.md` should have:

```markdown
# Keeli Skills Registry (Keeli Framework v0.4.0)

<!-- Managed by `keeli skill` and `keeli stack`. Do not edit manually. -->
<!-- Format: Type | Skill | Persona | Constraint -->

## Languages
| Type | Skill | Persona | Constraint |

## Frameworks
| Type | Skill | Persona | Constraint |

## Tools
| Type | Skill | Persona | Constraint |

## Domains & Patterns
| Type | Skill | Persona | Constraint |
```

Keep it organized by category for clarity.

---

## Summary

A **well-formed skill**:
1. ✅ Specific to your project (not generic knowledge)
2. ✅ Actionable (LLM/developer knows exactly what to do)
3. ✅ Signed off by relevant personas
4. ✅ Documented with examples
5. ✅ Auto-discoverable by AI (TF-IDF injection)
6. ✅ Enforceable at task boundaries (handshake, hierarchy)

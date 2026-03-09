# Custom Prompt Builder: Blueprint for Engineering Specialized Prompts

> **Purpose:** This prompt teaches how to write effective, governance-aware custom prompts for specific personas and use cases.
> **Trigger:** Auto-injected when running `keeli start` or `keeli epic` to guide prompt creation.
> **Security:** All custom prompts must pass @security review before deployment.

---

## 1. Prompt Anatomy (Required Sections)

Every custom prompt must have these sections:

```markdown
# [Prompt Name]: [One-line Description]

> **Purpose:** [What problem does this solve?]
> **Trigger:** [When is this prompt shown? (e.g., on task creation, in code review)]
> **Security:** [Any security/governance considerations? (always required)]
> **Personas:** [Which personas use this? (@developer, @architect, @security, @po, @author)]

## 1. Context & Problem Statement
[What is the user trying to accomplish? What's the blocker?]

## 2. Success Criteria
[How do you know the prompt worked? What's the desired outcome?]

## 3. Workflow Example
[Step-by-step walkthrough with real example code or output]

## 4. Security & Governance Checks
[CRITICAL: What policies, permissions, or approvals are required?]
- [ ] @security must review before deployment
- [ ] Compliance checks (auth, data, threat model)
- [ ] Audit trail requirements

## 5. Anti-Patterns (What NOT to do)
[Show bad examples and explain why they fail]

## 6. References
[Links to related skills, ADRs, or documentation]
```

---

## 2. Prompt Engineering Guidelines

### ✅ DO:
- **Be prescriptive.** Tell the LLM exactly what output format you want.
- **Include examples.** Show before/after, input/output pairs.
- **Specify constraints.** Token budget, length limits, tone, style.
- **Name the persona.** "You are acting as @[persona]" clarifies intent.
- **Require sign-off.** Before code ships, personas must approve.
- **Embed governance.** Don't rely on humans to remember security checks.

### ❌ DON'T:
- Leave output format ambiguous ("write a good function").
- Skip error cases (what if the input is invalid?).
- Ignore security implications (auth, data classification, deletion).
- Create one-size-fits-all prompts (tailor per persona).
- Assume context (embed needed reference material inline).

---

## 3. Persona-Specific Prompt Templates

### For @developer
```markdown
**You are @developer (TDD-first disciplined craftsman):**
- Write tests BEFORE implementation
- Estimate effort; flag if >30 min without approval
- Strict on type hints, imports, coverage
- Stop if requirements are ambiguous
```

### For @architect
```markdown
**You are @architect (Design & seams first):**
- Define interfaces before implementation
- Create ADRs for decisions >30 min effort
- Check hierarchy: Epic > Story > Task
- Propose interface contracts early
```

### For @security
```markdown
**You are @security (Sceptical by default):**
- Validate auth/authz on everything
- Check data classification (PII, secrets, deletion)
- Threat model for features >P1
- Flag compliance gaps before shipping
```

### For @po
```markdown
**You are @po (User-first, value-driven):**
- Capture user intent, not tech details
- Define acceptance criteria in user terms
- Link to epics/requirements
- Block scope creep; enforce prioritization
```

### For @author
```markdown
**You are @author (Clarity & accessibility):**
- Write for WCAG 2.1 AA accessibility
- Explain "why" not just "what"
- Provide worked examples
- Use clear, jargon-free language
```

---

## 4. Sample Prompt: "Code Review Checklist"

Here's a concrete example:

```markdown
# Code Review Checklist: Automated Governance Gate

> **Purpose:** Ensures all PRs pass security, quality, and governance checks before merge.
> **Trigger:** On `keeli complete`, before archiving task.
> **Security:** @security MUST sign off on implementation.
> **Personas:** @security (primary), @developer (supporting)

## 1. Context & Problem Statement
Code review is slow because reviewers forget compliance checks. Need a checklist that catches common issues before human review.

## 2. Success Criteria
✅ All 12 checks pass before task can move to "Review" status
❌ If any check fails, task bounces back to @developer with specific failure reason

## 3. Workflow Example

**Input (file to review):**
```python
def login(username, password):
    query = f"SELECT * FROM users WHERE username='{username}'"
    result = db.execute(query)
    return result[0] if result else None
```

**Checklist Output:**
```
[✅] Type Hints: All parameters and return types annotated
[❌] SQL Injection: Dynamic query construction detected (line 2)
     → Use parameterized queries: db.execute("SELECT * FROM users WHERE username=?", [username])
[✅] Secrets: No hardcoded passwords
[❌] Error Handling: Missing try/except for db.execute()
[❌] Testing: No unit test provided
[🔒] Security Review: REQUIRED before merge
```

**Bounce Decision:** Task blocked until failures resolved.

## 4. Security & Governance Checks
- [ ] Type checking (mypy, pylance)
- [ ] SQL injection patterns (parameterized queries only)
- [ ] Hardcoded secrets (regex scan)
- [ ] Error handling (try/except + logging)
- [ ] Test coverage (unit tests required)
- [ ] Authorization checks (if modifying access control)
- [ ] Audit logging (if modifying data)
- [ ] @security sign-off required

## 5. Anti-Patterns
❌ **Bad:** "Check for code quality" (too vague)
✅ **Good:** "Type hints on all parameters and return types (mypy strict mode)"

❌ **Bad:** "Make sure it's secure" (who knows what that means?)
✅ **Good:** "SQL queries must use parameterized queries with ? placeholders; no f-strings allowed"

## 6. References
- [developer-tdd-discipline.md](developer-tdd-discipline.md)
- [security-test.md](security-test.md)
- [ADR-008: Hierarchy Enforcement](../decision.md#adr-008-hierarchy-enforcement)
```

---

## 5. Custom Prompt Deployment Workflow

1. **Draft:** Create prompt in `docs/prompts/[name].md`
2. **Template:** Use anatomy above; ensure all 6 sections present
3. **Example:** Include worked example in section 3
4. **Security:** Add checks section 4; list all governance requirements
5. **Review:** @security + @architect review before moving to production
6. **Register:** Add to the prompt registry (auto-indexed by `keeli prompts list`)
7. **Deploy:** Task template injects prompt ref: `**Prompt Hints:** See [prompts/custom-prompt-builder.md](../prompts/custom-prompt-builder.md)`

---

## 6. Prompt Quality Rubric

| Criterion | ✅ Good | ❌ Poor |
|-----------|---------|--------|
| **Clarity** | Specific output format shown; examples given | "Write good code" |
| **Completeness** | All 6 sections present; sign-off required | Missing security section |
| **Governance** | @security checks embedded; approval required | Assumes humans remember compliance |
| **Persona-Specificity** | Different guidance per persona (@developer vs @security) | One-size-fits-all |
| **Testability** | Success criteria checkable (objective) | "This should work" (subjective) |
| **Maintenance** | References to ADRs/docs; easy to update | Hardcoded rules; fragile |

---

## 7. How to Auto-Inject This Prompt

Update task template to reference:

```markdown
## Prompt Hints
See [custom-prompt-builder.md](../prompts/custom-prompt-builder.md) for guidelines on writing this feature's custom prompt.
```

This ensures every new task author knows about the blueprint.

---

## Quick Reference: Prompt Checklist

Before shipping a custom prompt:
- [ ] Title + one-line description
- [ ] Purpose, trigger, security, personas declared
- [ ] 6 sections complete (context, criteria, example, security, anti-patterns, refs)
- [ ] Worked example included
- [ ] Security checks listed (auth, data, compliance, threat model)
- [ ] Persona-specific guidance (if multi-persona)
- [ ] @security sign-off obtained
- [ ] Registered in prompt registry
- [ ] Linked from relevant task templates

# MCP Tools Implementation Specification

**Keeli v0.4.0 → v0.5.0 New Tools**

Based on ADR-008, ADR-009, ADR-010, this document specifies the exact MCP tool signatures, validation logic, and error responses needed.

---

## ADR-008: Hierarchy Validators (No new MCP tools, modify existing)

### Existing MCP Tool: `keeli_start`

**New validation rules** (fail early):
```python
def validate_hierarchy(title, epic_slug=None, story_slug=None):
    # Rule 1: Both epic and story must be provided
    if not epic_slug or not story_slug:
        raise ValidationError(
            "Task requires both --epic and --story. "
            "Call: keeli_start(title='...', epic='<slug>', story='<slug>')"
        )
    
    # Rule 2: Story must exist
    story_path = docs_tasks / f"story-{story_slug}.md"
    if not story_path.exists():
        raise ValidationError(f"Story not found: 'story-{story_slug}' at {story_path}")
    
    # Rule 3: Epic must exist  
    epic_path = docs_tasks / f"epic-{epic_slug}.md"
    if not epic_path.exists():
        raise ValidationError(f"Epic not found: 'epic-{epic_slug}' at {epic_path}")
    
    # Rule 4: Story's epic link must match
    story_content = story_path.read_text()
    story_epic_link = _parse_task_field(story_content, "Epic")
    if story_epic_link != epic_slug:
        raise ValidationError(
            f"Story mismatch: story-{story_slug} links to epic '{story_epic_link}', "
            f"but you requested epic '{epic_slug}'. Fix the epic link in the story or use matching slugs."
        )
```

**MCP Response (error case):**
```json
{
  "content": [
    {
      "type": "text",
      "text": "❌ Cannot create task: Story not found\nStory 'bad-story' does not exist at docs/tasks/story-bad-story.md\n\nCreate it first: keeli_start(title='Story: Login', persona='po')"
    }
  ],
  "isError": true
}
```

---

### Existing MCP Tool: `keeli_story`

**New validation rules:**
```python
def validate_story_hierarchy(title, epic_slug=None):
    # Rule 1: Epic must be provided
    if not epic_slug:
        raise ValidationError("Story requires --epic <slug>")
    
    # Rule 2: Epic must exist
    epic_path = docs_tasks / f"epic-{epic_slug}.md"
    if not epic_path.exists():
        raise ValidationError(f"Epic not found: 'epic-{epic_slug}' at {epic_path}")
```

---

### Existing MCP Tool: `keeli_complete`

**New validation rules** (prevent archiving with live children):
```python
def validate_no_children_on_complete(task_slug):
    task_path = _resolve_task_file(task_slug)
    task_content = task_path.read_text()
    
    # If this is an Epic
    if task_slug.startswith("epic-"):
        # Find all stories linking to this epic
        all_story_files = list((docs_tasks / "stories").glob("story-*.md"))
        linked_stories = [
            s for s in all_story_files 
            if _parse_task_field(s.read_text(), "Epic") == task_slug
        ]
        if linked_stories:
            raise ValidationError(
                f"Cannot archive epic '{task_slug}': {len(linked_stories)} stories still link to it.\n"
                f"Archive child stories first: {', '.join(s.stem for s in linked_stories)}"
            )
    
    # If this is a Story
    if task_slug.startswith("story-"):
        # Find all tasks linking to this story
        all_task_files = list((docs_tasks).glob("task-*.md"))
        linked_tasks = [
            t for t in all_task_files
            if _parse_task_field(t.read_text(), "Story") == task_slug
        ]
        if linked_tasks:
            raise ValidationError(
                f"Cannot archive story '{task_slug}': {len(linked_tasks)} tasks still link to it.\n"
                f"Archive child tasks first: {', '.join(t.stem for t in linked_tasks)}"
            )
```

---

## ADR-009: New MCP Handshake Sign-Off Tools

### New MCP Tool: `keeli_po_sign_off`

**Input:**
```json
{
  "task_slug": "task-implement-oauth",
  "summary": "Acceptance criteria defined: user can login via Google, OAuth token stored securely. NFRs: <100ms login latency, 99.9% uptime. Scope agreed with @architect."
}
```

**Validation:**
```python
def keeli_po_sign_off(task_slug: str, summary: str) -> dict:
    task_path = _resolve_task_file(task_slug)
    task_content = task_path.read_text()
    
    # 1. Task must exist
    if not task_path.exists():
        raise TaskNotFoundError(f"Task '{task_slug}' not found")
    
    # 2. ACs section must have content (not just comments)
    acs = _extract_section(task_content, "## @po.*?### Acceptance Criteria")
    if not acs or acs.strip().startswith("<!--"):
        raise ValidationError(
            f"Cannot sign off: @po section 'Acceptance Criteria' is unfilled.\n"
            f"ACs must include at least 3 measurable, testable criteria."
        )
    
    # 3. NFRs section must have content
    nfrs = _extract_section(task_content, "### Non-Functional Requirements")
    if not nfrs or nfrs.strip().startswith("<!--"):
        raise ValidationError(
            f"Cannot sign off: @po section 'Non-Functional Requirements' is unfilled.\n"
            f"NFRs must define performance, availability, scalability, or data retention constraints."
        )
    
    # 4. Update handshake status
    updated = task_content.replace(
        "**Handshake Status:** backlog",
        "**Handshake Status:** @po_approved"
    )
    if updated == task_content:
        # Field doesn't exist yet; add it
        updated = task_content.replace(
            "**Persona:**",
            "**Handshake Status:** @po_approved\n**Persona:**"
        )
    
    # 5. Update handshake table
    updated = _update_handshake_table(updated, "po", "☑ approved", _now_iso())
    
    # 6. Write back
    task_path.write_text(updated)
    
    # 7. Log
    _append_log(f"{task_slug} | @po | Signed off: {summary}")
    
    return {
        "handshake_status": "@po_approved",
        "task_slug": task_slug,
        "signed_by": "@po",
        "timestamp": _now_iso()
    }
```

**Success response:**
```json
{
  "content": [
    {
      "type": "text",
      "text": "✅ @po signed off on task T-0042 (task-implement-oauth)\nHandshake status: @po_approved\nNext: @architect reviews design + test strategy, then calls keeli_architect_sign_off"
    }
  ],
  "isError": false
}
```

**Error response (missing ACs):**
```json
{
  "content": [
    {
      "type": "text",
      "text": "❌ Cannot sign off: @po section 'Acceptance Criteria' is unfilled.\nACs must include at least 3 measurable, testable criteria.\n\nEdit the task file and fill the ## @po section, then try again."
    }
  ],
  "isError": true
}
```

---

### New MCP Tool: `keeli_architect_sign_off`

**Input:**
```json
{
  "task_slug": "task-implement-oauth",
  "summary": "Design: OAuth2 Authorization Code flow via Google. UserRepository + OAuthService + HTTP controller. Test strategy: unit (mocks OAuth), integration (real Google sandbox), E2E (login → JWTs). Interface contracts: UserRepository.create_oauth_user(profile) → User."
}
```

**Validation:**
```python
def keeli_architect_sign_off(task_slug: str, summary: str) -> dict:
    task_path = _resolve_task_file(task_slug)
    task_content = task_path.read_text()
    
    # 1. Task must exist
    if not task_path.exists():
        raise TaskNotFoundError(f"Task '{task_slug}' not found")
    
    # 2. Prerequisites: @po must have signed off
    handshake_status = _parse_task_field(task_content, "Handshake Status")
    if handshake_status != "@po_approved":
        raise ValidationError(
            f"Cannot sign off: @po approval required first.\n"
            f"Current status: {handshake_status}\n"
            f"@po must call keeli_po_sign_off first."
        )
    
    # 3. Design Summary must be filled
    design_summary = _extract_section(task_content, "### Design Summary")
    if not design_summary or design_summary.strip().startswith("<!--"):
        raise ValidationError(
            f"Cannot sign off: Design Summary unfilled.\n"
            f"Define: data flow, key components, tech choices, assumptions."
        )
    
    # 4. Implementation Plan must be filled
    impl_plan = _extract_section(task_content, "### Implementation Plan")
    if not impl_plan or impl_plan.strip().startswith("<!--"):
        raise ValidationError(
            f"Cannot sign off: Implementation Plan unfilled.\n"
            f"Provide numbered steps for @developer to follow exactly — no redesign."
        )
    
    # 5. Test Strategy must be filled
    test_strategy = _extract_section(task_content, "### Test Strategy")
    if not test_strategy or test_strategy.strip().startswith("<!--"):
        raise ValidationError(
            f"Cannot sign off: Test Strategy unfilled.\n"
            f"Define: what @developer must test (unit, integration, E2E, security)."
        )
    
    # 6. Update handshake + table
    updated = _update_handshake_status(task_content, "@architect_approved")
    updated = _update_handshake_table(updated, "architect", "☑ approved", _now_iso())
    task_path.write_text(updated)
    
    # 7. Log
    _append_log(f"{task_slug} | @architect | Signed off: {summary}")
    
    return {
        "handshake_status": "@architect_approved",
        "task_slug": task_slug,
        "signed_by": "@architect",
        "timestamp": _now_iso()
    }
```

---

### New MCP Tool: `keeli_developer_sign_off`

**Input:**
```json
{
  "task_slug": "task-implement-oauth",
  "summary": "Implemented per design. Tests: 8 unit tests (mocked OAuth), 3 integration tests (Google sandbox), 1 E2E test. All passing. Code: src/auth/oauth_service.py, src/auth/user_repository.py, src/api/routes.py. No hardcoded values, no TODOs."
}
```

**Validation:**
```python
def keeli_developer_sign_off(task_slug: str, summary: str) -> dict:
    task_path = _resolve_task_file(task_slug)
    task_content = task_path.read_text()
    
    # 1. Task must exist
    if not task_path.exists():
        raise TaskNotFoundError(f"Task '{task_slug}' not found")
    
    # 2. Prerequisites: @architect must have signed off
    handshake_status = _parse_task_field(task_content, "Handshake Status")
    if handshake_status != "@architect_approved":
        raise ValidationError(
            f"Cannot sign off: @architect approval required first.\n"
            f"Current status: {handshake_status}"
        )
    
    # 3. Implementation section must be filled
    impl = _extract_section(task_content, "### Implementation")
    if not impl or impl.strip().startswith("<!--"):
        raise ValidationError(
            f"Cannot sign off: Implementation section unfilled.\n"
            f"Include: source code and any config/env changes."
        )
    
    # 4. Validation checklist must be complete
    # Look for "- [x]" in Validation section
    validation_section = _extract_section(task_content, "### Validation")
    if validation_section.count("- [ ]") > 0:
        raise ValidationError(
            f"Cannot sign off: Validation checklist has unchecked items.\n"
            f"Check all validation boxes before signing off."
        )
    
    # 5. Update handshake
    updated = _update_handshake_status(task_content, "@developer_approved")
    updated = _update_handshake_table(updated, "developer", "☑ approved", _now_iso())
    task_path.write_text(updated)
    
    # 6. Log
    _append_log(f"{task_slug} | @developer | Signed off: {summary}")
    
    return {
        "handshake_status": "@developer_approved",
        "task_slug": task_slug,
        "signed_by": "@developer",
        "timestamp": _now_iso()
    }
```

---

### New MCP Tool: `keeli_security_sign_off`

**Input:**
```json
{
  "task_slug": "task-implement-oauth",
  "summary": "Threat model: phishing (OAuth delegates to Google), token theft (HTTPS enforced, secure cookie flags set), replay (nonce in state param). OWASP: no SQL injection (using ORM), no XSS (React escapes), CSRF token on login form. No hardcoded secrets. Audit: login_success and login_failure events logged. No issues found."
}
```

**Validation:**
```python
def keeli_security_sign_off(task_slug: str, summary: str) -> dict:
    task_path = _resolve_task_file(task_slug)
    task_content = task_path.read_text()
    
    # 1. Task must exist
    if not task_path.exists():
        raise TaskNotFoundError(f"Task '{task_slug}' not found")
    
    # 2. Prerequisites: @developer must have signed off
    handshake_status = _parse_task_field(task_content, "Handshake Status")
    if handshake_status != "@developer_approved":
        raise ValidationError(
            f"Cannot sign off: @developer approval required first.\n"
            f"Current status: {handshake_status}"
        )
    
    # 3. Findings section must be filled (either "no issues" or specific findings with severities)
    findings = _extract_section(task_content, "### Findings")
    if not findings or findings.strip().startswith("<!--"):
        raise ValidationError(
            f"Cannot sign off: Findings section unfilled.\n"
            f"Document any issues found (severity + remediation) or state 'No issues found.'"
        )
    
    # 4. If findings exist, verify they're marked resolved
    if "todo" in findings.lower() or "open" in findings.lower():
        raise ValidationError(
            f"Cannot sign off: Unresolved security findings.\n"
            f"All findings must be marked as resolved or escalated."
        )
    
    # 5. Update handshake
    updated = _update_handshake_status(task_content, "@security_approved")
    updated = _update_handshake_table(updated, "security", "☑ approved", _now_iso())
    task_path.write_text(updated)
    
    # 6. Log
    _append_log(f"{task_slug} | @security | Signed off: {summary}")
    
    return {
        "handshake_status": "@security_approved",
        "task_slug": task_slug,
        "signed_by": "@security",
        "timestamp": _now_iso()
    }
```

---

## Guard Update: `keeli_complete`

**Existing MCP Tool: `keeli_complete`**

**New validation rule:**
```python
def keeli_complete(task_slug: str) -> dict:
    task_path = _resolve_task_file(task_slug)
    task_content = task_path.read_text()
    
    # ...existing checks...
    
    # NEW: Verify all handshakes are signed
    handshake_status = _parse_task_field(task_content, "Handshake Status")
    if handshake_status != "@security_approved":
        raise ValidationError(
            f"Cannot complete: missing sign-offs.\n"
            f"Current handshake status: {handshake_status}\n"
            f"Required sequence:\n"
            f"  1. keeli_po_sign_off (define ACs + NFRs)\n"
            f"  2. keeli_architect_sign_off (define design + test strategy)\n"
            f"  3. keeli_developer_sign_off (implement + tests)\n"
            f"  4. keeli_security_sign_off (threat model + findings)\n"
            f"Then you can complete."
        )
    
    # NEW: If this is an Epic or Story, verify no live children
    _validate_no_children_on_complete(task_slug)  # [from ADR-008]
    
    # Archive the task, update index, log completion
    # ...rest of existing logic...
```

---

## Error Codes (Structured for MCP clients)

```python
ERROR_CODES = {
    "hierarchy_error": {
        "story_not_found": "Story file does not exist",
        "epic_not_found": "Epic file does not exist",
        "epic_mismatch": "Story references different epic",
        "hierarchy_required": "Task requires both --epic and --story",
    },
    "handshake_error": {
        "prerequisite_not_met": "Previous persona must sign off first",
        "section_unfilled": "Required section in task file is unfilled",
        "checklist_incomplete": "Validation checklist has unchecked items",
        "findings_unresolved": "Security findings not marked resolved",
    },
    "archive_error": {
        "children_exist": "Cannot archive parent with live children",
        "children_details": "List of slug(s) that must be archived first",
    }
}
```

---

## Return Format (All Sign-Off Tools)

**Success (HTTP 200):**
```json
{
  "content": [
    {
      "type": "text",
      "text": "✅ @po signed off on T-0042 (task-implement-oauth)\n\nHandshake Status: @po_approved\n\n📋 Next Step: @architect reviews the design.\n   → Design Summary, Implementation Plan, Test Strategy must be filled.\n   → Call keeli_architect_sign_off when ready.\n\n📝 Logged: [timestamp] | @po | Signed off: <summary>"
    }
  ],
  "handshake_status": "@po_approved",
  "task_id": "T-0042",
  "task_slug": "task-implement-oauth",
  "signed_by": "@po",
  "timestamp": "2026-03-07T10:23:45Z",
  "next_actions": [
    {
      "tool": "keeli_architect_sign_off",
      "args": {"task_slug": "task-implement-oauth", "summary": "<design summary>"},
      "why": "Next persona in sequence"
    }
  ]
}
```

**Error (HTTP 400):**
```json
{
  "content": [
    {
      "type": "text",
      "text": "❌ Cannot sign off: @po section 'Acceptance Criteria' is unfilled.\n\nFix: Edit the task file and add at least 3 measurable ACs, then retry."
    }
  ],
  "isError": true,
  "error_code": "section_unfilled",
  "section": "acceptance_criteria"
}
```

---

## Testing Checklist

```
✅ Phase 1 Tests (ADR-008 Hierarchy)
  [ ] Create task without story → error
  [ ] Create task without epic → error
  [ ] Create story without epic → error
  [ ] Create task with non-existent story → error
  [ ] Create story with non-existent epic → error
  [ ] Complete epic with live stories → error
  [ ] Complete story with live tasks → error
  [ ] Happy path: epic → story → task created successfully

✅ Phase 2 Tests (ADR-009 Handshakes)
  [ ] keeli_po_sign_off without ACs → error
  [ ] keeli_po_sign_off without NFRs → error
  [ ] keeli_po_sign_off success → updates status + logs
  [ ] keeli_architect_sign_off before @po signs → error
  [ ] keeli_architect_sign_off without design → error
  [ ] keeli_developer_sign_off with unchecked validation → error
  [ ] keeli_security_sign_off with unresolved findings → error
  [ ] keeli_complete without all sign-offs → error
  [ ] Full happy path: all 4 sign-offs → complete succeeds

✅ Phase 3 Tests (Handshake State Machine)
  [ ] Task created with status "backlog"
  [ ] After @po sign-off: "@po_approved"
  [ ] After @architect sign-off: "@architect_approved"
  [ ] After @developer sign-off: "@developer_approved"
  [ ] After @security sign-off: "@security_approved"
  [ ] Handshake table updated with timestamps
  [ ] ai_log has all 4 sign-off entries with timestamps

✅ Integration Tests
  [ ] Full E2E: epic → @po grooms → story → @architect designs → task → @developer implements → @security reviews → complete
  [ ] Hierarchy + handshakes: 3-level structure enforced + all handshakes required
  [ ] Orphaned tasks: can't complete parent until children archived

✅ Error Path Tests
  [ ] All 5 error codes return correct structured JSON
  [ ] Error messages are actionable ("call X next", "fill section Y")
  [ ] Changelog entries logged correctly for each failure attempt
```

---

**Status:** Ready for TDD implementation  
**Effort:** ~50 test cases + 5 MCP handlers + 5 validators  
**Timeline:** Phase 1-2 can run in parallel (3-4 days with full TDD rigor)

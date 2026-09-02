# T-0016: Phase 2 - Structured Intent Routing

**Status:** active
**Priority:** p0
**Created:** 2026-09-02T00:00:00Z
**Completed:** —
**Depends On:** T-0015
**Tags:** v7-upgrade, phase-2, llm-interface

## Description

Implement typed schema-based intent routing in `llm_interface.py`. Replace fragile heuristic NLP with a structured schema that enforces:
- Typed intent enums
- Confidence scoring
- Extracted parameters
- Missing field detection
- Validation and fallback loops

## Acceptance Criteria

- [ ] Implement ParsedIntent dataclass with required fields
- [ ] Replace heuristic parsing with schema-based parsing
- [ ] Add validation with confidence threshold (0.75)
- [ ] Implement fallback mechanism for low confidence
- [ ] Type hints throughout
- [ ] Backward compatibility maintained
- [ ] Tests pass

## Implementation Notes

**File Target:** `src/keeli/llm_interface.py`

**Key Changes:**
1. Create `ParsedIntent` dataclass matching spec
2. Refactor `_parse_intent()` to return typed structure
3. Add `_validate_intent()` with fallback logic
4. Update `ask()` to use structured routing
5. Add `_request_clarification()` for low-confidence intents

**Schema:**
```json
{
  "intent": "enum of supported actions",
  "confidence": 0.0-1.0,
  "parameters": {"key": "value"},
  "missing_fields": ["field1", "field2"],
  "evidence": "explanation"
}
```

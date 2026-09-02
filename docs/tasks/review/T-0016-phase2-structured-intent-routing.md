# T-0016: Phase 2 - Structured Intent Routing

**Status:** completed
**Priority:** p0
**Created:** 2026-09-02T00:00:00Z
**Completed:** 2026-09-02T02:30:00Z
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

- [x] Implement ParsedIntent dataclass with required fields
- [x] Replace heuristic parsing with schema-based parsing
- [x] Add validation with confidence threshold (0.75)
- [x] Implement fallback mechanism for low confidence
- [x] Type hints throughout
- [x] Backward compatibility maintained
- [x] Tests pass

## Implementation Notes

**File Target:** `src/keeli/llm_interface.py`

**Key Changes:**
1. Created `ParsedIntent` dataclass with typed fields ✅
2. Refactored `_parse_intent()` to return typed structure ✅
3. Added `_validate_intent()` with fallback logic ✅
4. Updated `ask()` to use structured routing ✅
5. Added `_request_clarification()` for low-confidence intents ✅

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

## Results

- **Commit:** 8d04176
- **Lines Changed:** 446 insertions, 134 deletions
- **Intent Types:** 12 (CREATE_TASK, GET_NEXT_TASK, LIST_TASKS, COMPLETE_TASK, GET_STATUS, STORE_CONTEXT, GET_CONTEXT, SEMANTIC_SEARCH, DISCOVER_PATTERNS, SUMMARIZE, HELP, UNKNOWN)
- **Validation Tests:** ✅ All passed
  - High confidence validation gate: PASS
  - Low confidence rejection: PASS  
  - Missing fields detection: PASS
  - Intent serialization: PASS
  - Clarification loop trigger: PASS
- **Intent Handlers:** 11 dedicated handler methods (one per non-unknown intent)
- **Circular Import Fix:** TYPE_CHECKING guard + deferred import in __init__
- **Telemetry Ready:** `_intent_log` field added for Phase 3

## Next: Phase 3

Will implement telemetry & learning loop to capture:
- Full request lifecycle logging
- Intent parsing confidence tracking
- Action execution outcomes
- Pattern detection for confidence calibration


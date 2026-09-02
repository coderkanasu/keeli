# T-0017: Phase 3 - Telemetry & Learning Loop

**Status:** active
**Priority:** p0
**Created:** 2026-09-02T02:35:00Z
**Completed:** —
**Depends On:** T-0016
**Tags:** v7-upgrade, phase-3, telemetry

## Description

Implement comprehensive telemetry system to capture the full request lifecycle:
- Original request text
- Parsed intent (schema from Phase 2)
- Extracted parameters
- Validation gate results
- Chosen action / route
- Action outcome (success/failure)
- Execution time

This enables Phase 4 benchmarking and helps calibrate confidence thresholds.

## Acceptance Criteria

- [ ] Create `telemetry.py` module with event schemas
- [ ] Add event logging to llm_interface.ask() full lifecycle
- [ ] Persist events to SQLite or JSON-lines
- [ ] Include timestamp, request, intent, parameters, outcome
- [ ] Calculate success rates per intent type
- [ ] Confidence threshold calibration data
- [ ] Event export for analysis
- [ ] Tests pass

## Implementation Plan

**File Targets:**
- Create: `src/keeli/telemetry.py`
- Modify: `src/keeli/llm_interface.py` (add event logging hooks)

**Event Schema:**
```python
@dataclass
class TelemetryEvent:
    timestamp: str  # ISO 8601
    request_text: str
    parsed_intent: ParsedIntent (as dict)
    validation_passed: bool
    route_chosen: str
    execution_time_ms: float
    outcome: str  # "success", "failure", "clarification_requested"
    error_message: Optional[str]
    metadata: Dict[str, Any]
```

**Key Features:**
1. Event logging at 5 checkpoints:
   - intent_parsed
   - validation_checked
   - route_chosen
   - action_executed
   - outcome_recorded

2. Per-intent statistics:
   - total_requests
   - success_rate
   - avg_confidence
   - avg_execution_time

3. Confidence calibration:
   - success_by_confidence_bucket (0.0-0.25, 0.25-0.50, etc.)
   - recommended_threshold

## Next: Phase 4

Phase 4 will use telemetry data to benchmark v7 against v6 and validate measurable improvements in understanding and execution accuracy.

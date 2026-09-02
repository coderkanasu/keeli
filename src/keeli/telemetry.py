"""
Keeli v7.0 - Telemetry & Learning Loop

Phase 3: Comprehensive event logging for the full request lifecycle.

This module captures:
- Original request text
- Parsed intent (with confidence and parameters)
- Validation gate results
- Route chosen / action executed
- Execution time and outcome
- Error messages (if any)

Events are persisted to SQLite for analysis, statistics calculation,
and confidence threshold calibration.
"""

import json
import sqlite3
import time
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional
from pathlib import Path
from enum import Enum


class OutcomeType(str, Enum):
    """Outcome types for telemetry events."""
    SUCCESS = "success"
    FAILURE = "failure"
    CLARIFICATION_REQUESTED = "clarification_requested"
    VALIDATION_REJECTED = "validation_rejected"


class CheckpointType(str, Enum):
    """Request processing checkpoints."""
    REQUEST_RECEIVED = "request_received"
    INTENT_PARSED = "intent_parsed"
    VALIDATION_CHECKED = "validation_checked"
    ROUTE_CHOSEN = "route_chosen"
    ACTION_EXECUTING = "action_executing"
    ACTION_EXECUTED = "action_executed"
    OUTCOME_RECORDED = "outcome_recorded"


@dataclass
class TelemetryEvent:
    """
    Structured event for telemetry logging.
    
    Captures all information about a single request's lifecycle.
    """
    timestamp: str  # ISO 8601 format
    checkpoint: CheckpointType
    request_text: str
    parsed_intent: Optional[Dict[str, Any]] = None
    intent_type: Optional[str] = None
    confidence: Optional[float] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    validation_passed: Optional[bool] = None
    route_chosen: Optional[str] = None
    execution_time_ms: float = 0.0
    outcome: Optional[OutcomeType] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert enums to strings
        if data.get("checkpoint"):
            data["checkpoint"] = data["checkpoint"].value
        if data.get("outcome"):
            data["outcome"] = data["outcome"].value
        return data


class TelemetryStore:
    """Persistent telemetry event storage with SQLite backend."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize telemetry store."""
        if db_path is None:
            db_path = Path.home() / ".keeli" / "telemetry.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    checkpoint TEXT NOT NULL,
                    request_text TEXT NOT NULL,
                    intent_type TEXT,
                    confidence REAL,
                    parameters TEXT,
                    missing_fields TEXT,
                    validation_passed INTEGER,
                    route_chosen TEXT,
                    execution_time_ms REAL,
                    outcome TEXT,
                    error_message TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON telemetry_events(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_intent ON telemetry_events(intent_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outcome ON telemetry_events(outcome)
            """)
            conn.commit()
    
    def log_event(self, event: TelemetryEvent) -> None:
        """Log a telemetry event."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO telemetry_events (
                    timestamp, checkpoint, request_text, intent_type, confidence,
                    parameters, missing_fields, validation_passed, route_chosen,
                    execution_time_ms, outcome, error_message, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.timestamp,
                event.checkpoint.value,
                event.request_text,
                event.intent_type,
                event.confidence,
                json.dumps(event.parameters),
                json.dumps(event.missing_fields),
                1 if event.validation_passed else 0 if event.validation_passed is not None else None,
                event.route_chosen,
                event.execution_time_ms,
                event.outcome.value if event.outcome else None,
                event.error_message,
                json.dumps(event.metadata)
            ))
            conn.commit()
    
    def get_stats(self, intent_type: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for intent type(s)."""
        with sqlite3.connect(self.db_path) as conn:
            if intent_type:
                # Stats for specific intent
                cursor = conn.execute("""
                    SELECT
                        COUNT(*) as total_requests,
                        SUM(CASE WHEN outcome = ? THEN 1 ELSE 0 END) as successes,
                        AVG(confidence) as avg_confidence,
                        AVG(execution_time_ms) as avg_execution_time_ms,
                        MIN(confidence) as min_confidence,
                        MAX(confidence) as max_confidence
                    FROM telemetry_events
                    WHERE intent_type = ? AND outcome IS NOT NULL
                """, (OutcomeType.SUCCESS.value, intent_type))
            else:
                # Overall stats
                cursor = conn.execute("""
                    SELECT
                        COUNT(*) as total_requests,
                        SUM(CASE WHEN outcome = ? THEN 1 ELSE 0 END) as successes,
                        AVG(confidence) as avg_confidence,
                        AVG(execution_time_ms) as avg_execution_time_ms
                    FROM telemetry_events
                    WHERE outcome IS NOT NULL
                """, (OutcomeType.SUCCESS.value,))
            
            row = cursor.fetchone()
            if not row or row[0] == 0:
                return {"total_requests": 0, "success_rate": 0.0}
            
            total, successes, avg_conf, avg_time = row
            success_rate = (successes / total) if total > 0 else 0.0
            
            return {
                "total_requests": total,
                "successes": successes or 0,
                "success_rate": round(success_rate, 3),
                "avg_confidence": round(avg_conf, 3) if avg_conf else None,
                "avg_execution_time_ms": round(avg_time, 1) if avg_time else None
            }
    
    def get_confidence_calibration(self, intent_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze success rate by confidence buckets.
        
        Returns success rates for ranges: [0-0.25), [0.25-0.5), [0.5-0.75), [0.75-1.0]
        """
        with sqlite3.connect(self.db_path) as conn:
            if intent_type:
                query = """
                    SELECT
                        CASE
                            WHEN confidence < 0.25 THEN '0.00-0.25'
                            WHEN confidence < 0.50 THEN '0.25-0.50'
                            WHEN confidence < 0.75 THEN '0.50-0.75'
                            ELSE '0.75-1.00'
                        END as bucket,
                        COUNT(*) as count,
                        SUM(CASE WHEN outcome = ? THEN 1 ELSE 0 END) as successes
                    FROM telemetry_events
                    WHERE intent_type = ? AND outcome IS NOT NULL AND confidence IS NOT NULL
                    GROUP BY bucket
                    ORDER BY bucket
                """
                cursor = conn.execute(query, (OutcomeType.SUCCESS.value, intent_type))
            else:
                query = """
                    SELECT
                        CASE
                            WHEN confidence < 0.25 THEN '0.00-0.25'
                            WHEN confidence < 0.50 THEN '0.25-0.50'
                            WHEN confidence < 0.75 THEN '0.50-0.75'
                            ELSE '0.75-1.00'
                        END as bucket,
                        COUNT(*) as count,
                        SUM(CASE WHEN outcome = ? THEN 1 ELSE 0 END) as successes
                    FROM telemetry_events
                    WHERE outcome IS NOT NULL AND confidence IS NOT NULL
                    GROUP BY bucket
                    ORDER BY bucket
                """
                cursor = conn.execute(query, (OutcomeType.SUCCESS.value,))
            
            calibration = {}
            for row in cursor.fetchall():
                bucket, count, successes = row
                success_rate = (successes / count) if count > 0 else 0.0
                calibration[bucket] = {
                    "count": count,
                    "successes": successes or 0,
                    "success_rate": round(success_rate, 3)
                }
            
            return calibration
    
    def get_intent_distribution(self) -> Dict[str, int]:
        """Get distribution of request intents."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT intent_type, COUNT(*) as count
                FROM telemetry_events
                WHERE intent_type IS NOT NULL
                GROUP BY intent_type
                ORDER BY count DESC
            """)
            
            return {row[0]: row[1] for row in cursor.fetchall()}
    
    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent telemetry events."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM telemetry_events
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def export_to_json(self, output_path: Path, intent_type: Optional[str] = None) -> None:
        """Export telemetry events to JSON."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if intent_type:
                cursor = conn.execute("""
                    SELECT * FROM telemetry_events
                    WHERE intent_type = ?
                    ORDER BY timestamp
                """, (intent_type,))
            else:
                cursor = conn.execute("""
                    SELECT * FROM telemetry_events
                    ORDER BY timestamp
                """)
            
            events = [dict(row) for row in cursor.fetchall()]
            
            with open(output_path, 'w') as f:
                json.dump(events, f, indent=2)


class TelemetryLogger:
    """High-level logger for telemetry events."""
    
    def __init__(self, store: TelemetryStore):
        """Initialize telemetry logger."""
        self.store = store
        self._request_start_time: Optional[float] = None
        self._checkpoint_times: Dict[str, float] = {}
    
    def start_request(self, request_text: str) -> None:
        """Mark start of request processing."""
        self._request_start_time = time.time()
        self._checkpoint_times = {
            CheckpointType.REQUEST_RECEIVED.value: self._request_start_time
        }
    
    def checkpoint(self, checkpoint_type: CheckpointType) -> None:
        """Record a checkpoint."""
        self._checkpoint_times[checkpoint_type.value] = time.time()
    
    def log_request_lifecycle(
        self,
        request_text: str,
        intent_type: Optional[str],
        confidence: Optional[float],
        parameters: Dict[str, Any],
        missing_fields: List[str],
        validation_passed: bool,
        route_chosen: str,
        outcome: OutcomeType,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log complete request lifecycle."""
        if self._request_start_time is None:
            self.start_request(request_text)
        
        execution_time_ms = (time.time() - self._request_start_time) * 1000.0
        
        event = TelemetryEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            checkpoint=CheckpointType.OUTCOME_RECORDED,
            request_text=request_text,
            intent_type=intent_type,
            confidence=confidence,
            parameters=parameters,
            missing_fields=missing_fields,
            validation_passed=validation_passed,
            route_chosen=route_chosen,
            execution_time_ms=round(execution_time_ms, 2),
            outcome=outcome,
            error_message=error_message,
            metadata=metadata or {}
        )
        
        self.store.log_event(event)

"""
Keeli v6.0 — Field-Level CRDT Engine (Production-Hardened)

Fixes applied:
  • LWWRegister: deterministic (timestamp, actor) tuple tiebreaker
  • ORSet: tag-aware observed-remove (only deletes observed tag instances)
  • VectorClock: defensive deep-copy semantics
  • Event: sqlite3 import fixed, made mutable to allow event_id assignment after DB insertion
"""

import json
import hashlib
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone


@dataclass
class Event:
    """CRDT event representing a single field mutation. event_id is set after DB insertion."""
    task_id: str
    field: str
    op: str
    value: Any
    timestamp: str
    actor: str
    branch: Optional[str] = None
    session_id: Optional[str] = None
    vector_clock: Dict[str, int] = field(default_factory=dict)
    event_id: Optional[int] = None

    def to_db_row(self) -> Tuple:
        return (
            self.task_id, self.field, self.op, json.dumps(self.value),
            self.timestamp, self.actor, self.branch, self.session_id,
            json.dumps(self.vector_clock, sort_keys=True)
        )

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> "Event":
        return cls(
            task_id=row["task_id"],
            field=row["field"],
            op=row["op"],
            value=json.loads(row["value"]),
            timestamp=row["timestamp"],
            actor=row["actor"],
            branch=row["branch"],
            session_id=row["session_id"],
            vector_clock=json.loads(row["vector_clock"]),
            event_id=row["event_id"]
        )


class VectorClock:
    """Lamport-style vector clock with defensive deep-copy semantics."""

    def __init__(self, clocks: Dict[str, int] = None):
        self.clocks = dict(clocks) if clocks else {}

    def increment(self, actor: str) -> "VectorClock":
        """Return a NEW clock with actor incremented. Never mutates self."""
        vc = VectorClock(self.clocks)
        vc.clocks[actor] = vc.clocks.get(actor, 0) + 1
        return vc

    def merge(self, other: "VectorClock") -> "VectorClock":
        """Return a NEW merged clock. Never mutates self or other."""
        merged = {}
        for k in set(self.clocks) | set(other.clocks):
            merged[k] = max(self.clocks.get(k, 0), other.clocks.get(k, 0))
        return VectorClock(merged)

    def compare(self, other: "VectorClock") -> str:
        """Returns: 'before', 'after', 'concurrent', 'equal'."""
        dominates = False
        dominated = False
        for k in set(self.clocks) | set(other.clocks):
            a = self.clocks.get(k, 0)
            b = other.clocks.get(k, 0)
            if a > b:
                dominates = True
            elif b > a:
                dominated = True
        if dominates and dominated:
            return "concurrent"
        if dominates:
            return "after"
        if dominated:
            return "before"
        return "equal"

    def to_json(self) -> str:
        return json.dumps(self.clocks, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "VectorClock":
        return cls(json.loads(s))

    def copy(self) -> "VectorClock":
        return VectorClock(self.clocks)

    def __repr__(self):
        return f"VC({self.clocks})"


class LWWRegister:
    """Last-Write-Wins Register with deterministic cross-replica ordering.

    Tiebreaker: (timestamp, actor) lexicographic tuple comparison.
    Guarantees identical convergence even with clock skew or identical timestamps.
    """

    def __init__(self, field: str):
        self.field = field
        self.value: Any = None
        self.timestamp: str = ""
        self.actor: str = ""
        self.vector_clock = VectorClock()

    def apply(self, event: Event) -> bool:
        if event.field != self.field:
            return False
        event_vc = VectorClock(event.vector_clock)
        comparison = self.vector_clock.compare(event_vc)

        changed = False
        if comparison in ("before", "equal"):
            self.value = event.value
            self.timestamp = event.timestamp
            self.actor = event.actor
            self.vector_clock = event_vc
            changed = True
        elif comparison == "concurrent":
            # Deterministic tiebreaker: (timestamp, actor) lexicographic ordering
            # This ensures all replicas converge to the same winner even with
            # clock skew or identical millisecond timestamps.
            self_tuple = (self.timestamp or "", self.actor or "")
            event_tuple = (event.timestamp or "", event.actor or "")
            if event_tuple > self_tuple:
                self.value = event.value
                self.timestamp = event.timestamp
                self.actor = event.actor
                self.vector_clock = self.vector_clock.merge(event_vc)
                changed = True
            elif event_tuple == self_tuple:
                # Perfect tie: keep existing (idempotent, no flip-flop)
                changed = False
            # else: event_tuple < self_tuple → keep existing
        return changed


class ORSet:
    """Observed-Remove Set with unique tag tracking.

    Each 'add' is tagged with a unique event_id. 'remove' MUST specify
    which observed tag IDs to delete, preserving concurrent adds from
    other agents that the remover had not yet observed.

    remove event value format: {"element": [tag_id1, tag_id2], ...}
    """

    def __init__(self, field: str):
        self.field = field
        # Map element -> set of unique tags (event_ids) that added it
        self.elements: Dict[str, Set[int]] = {}
        self.vector_clock = VectorClock()

    def apply(self, event: Event) -> bool:
        if event.field != self.field:
            return False

        changed = False
        event_vc = VectorClock(event.vector_clock)
        self.vector_clock = self.vector_clock.merge(event_vc)

        if event.op == "add":
            items = event.value if isinstance(event.value, list) else [event.value]
            unique_tag = event.event_id or self._tag_from_event(event)
            for item in items:
                item_str = str(item).strip().lower()
                if not item_str:
                    continue
                if item_str not in self.elements:
                    self.elements[item_str] = set()
                if unique_tag not in self.elements[item_str]:
                    self.elements[item_str].add(unique_tag)
                    changed = True

        elif event.op == "remove":
            # Tag-aware observed-remove: only delete specified tag instances
            if isinstance(event.value, dict):
                for item_str, tag_ids in event.value.items():
                    item_str = str(item_str).strip().lower()
                    if item_str not in self.elements:
                        continue
                    for tid in tag_ids:
                        self.elements[item_str].discard(tid)
                    if not self.elements[item_str]:
                        del self.elements[item_str]
                    changed = True
            else:
                # Legacy fallback: remove all observed instances of these elements
                # (used only for init/compat; engine always emits tag-aware removals)
                items = event.value if isinstance(event.value, list) else [event.value]
                for item in items:
                    item_str = str(item).strip().lower()
                    if item_str in self.elements:
                        del self.elements[item_str]
                        changed = True

        elif event.op == "set":
            # Full replacement: clear + add with new tag
            self.elements.clear()
            items = event.value if isinstance(event.value, list) else [event.value]
            unique_tag = event.event_id or self._tag_from_event(event)
            for item in items:
                item_str = str(item).strip().lower()
                if item_str:
                    self.elements[item_str] = {unique_tag}
            changed = True

        return changed

    def _tag_from_event(self, event: Event) -> int:
        payload = f"{event.task_id}:{event.field}:{event.timestamp}:{event.actor}"
        return int(hashlib.sha256(payload.encode()).hexdigest(), 16) % (2 ** 63)

    def value(self) -> List[str]:
        return sorted(self.elements.keys())

    def get_tags_for_removal(self, items: List[str]) -> Dict[str, List[int]]:
        """Return the current tag IDs for given items so the engine can
        emit a precise observed-remove event."""
        result = {}
        for item in items:
            item_str = str(item).strip().lower()
            if item_str in self.elements and self.elements[item_str]:
                result[item_str] = list(self.elements[item_str])
        return result


class TaskCRDT:
    """Aggregates LWW registers and OR-Sets into a unified Task state.

    Reconstructs state by replaying events. Field-level independence means
    Agent A editing 'status' never conflicts with Agent B editing 'priority'.
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.title = LWWRegister("title")
        self.status = LWWRegister("status")
        self.priority = LWWRegister("priority")
        self.description = LWWRegister("description")
        self.tags = ORSet("tags")
        self.depends_on = LWWRegister("depends_on")
        self.created = LWWRegister("created")
        self.completed = LWWRegister("completed")
        self.vector_clock = VectorClock()

    def apply(self, event: Event) -> bool:
        registers = [
            self.title, self.status, self.priority, self.description,
            self.depends_on, self.created, self.completed
        ]
        sets = [self.tags]

        changed = False
        for reg in registers:
            if reg.apply(event):
                changed = True
                self.vector_clock = self.vector_clock.merge(reg.vector_clock)

        for s in sets:
            if s.apply(event):
                changed = True
                self.vector_clock = self.vector_clock.merge(s.vector_clock)

        return changed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.task_id,
            "title": self.title.value or "Untitled Task",
            "status": (self.status.value or "backlog").lower(),
            "priority": (self.priority.value or "P2").upper(),
            "description": self.description.value or "No description provided.",
            "tags": ",".join(self.tags.value()),
            "depends_on": self.depends_on.value or "—",
            "created": self.created.value or "",
            "completed": self.completed.value or "—",
            "vector_clock": self.vector_clock.clocks,
        }

    @classmethod
    def from_events(cls, task_id: str, events: List[Event]) -> "TaskCRDT":
        task = cls(task_id)
        for event in sorted(events, key=lambda e: (e.timestamp, e.event_id or 0)):
            task.apply(event)
        return task

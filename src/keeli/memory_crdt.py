"""
Keeli v7.0 - Simplified In-Memory CRDT with Periodic Sync

This module provides a simplified CRDT implementation optimized for LLM workflows.
It operates primarily in memory with periodic filesystem synchronization, eliminating
the overhead of immediate file operations while maintaining persistence.

Core Philosophy: "Fast in-memory operations, lazy filesystem persistence"
"""

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from dataclasses import dataclass, field
from collections import defaultdict

from keeli.crdt import VectorClock, Event

if TYPE_CHECKING:
    from keeli.engine import KeeliEngine


@dataclass
class MemoryState:
    """In-memory state for a task."""
    task_id: str
    fields: Dict[str, Any] = field(default_factory=dict)
    vector_clock: VectorClock = field(default_factory=VectorClock)
    tags: Set[str] = field(default_factory=set)
    last_modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    pending_sync: bool = True


class MemoryCRDTStore:
    """
    Simplified in-memory CRDT store with periodic filesystem sync.
    
    This eliminates the complexity of immediate file operations while
    maintaining data persistence through periodic synchronization.
    """
    
    def __init__(self, sync_interval_seconds: int = 30, engine: Optional["KeeliEngine"] = None):
        self._state: Dict[str, MemoryState] = {}
        self._event_log: List[Event] = []
        self._sync_interval = sync_interval_seconds
        self._sync_thread: Optional[threading.Thread] = None
        self._stop_sync = threading.Event()
        self._lock = threading.RLock()
        self.engine = engine  # Optional KeeliEngine for persistence
        
        # Start background sync thread
        self._start_sync_thread()
    
    def _start_sync_thread(self) -> None:
        """Start background thread for periodic filesystem sync."""
        def sync_loop():
            while not self._stop_sync.wait(self._sync_interval):
                self.sync_to_filesystem()
        
        self._sync_thread = threading.Thread(target=sync_loop, daemon=True)
        self._sync_thread.start()
    
    def stop(self) -> None:
        """Stop the background sync thread and perform final sync."""
        self._stop_sync.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=5)
        self.sync_to_filesystem()
    
    # ── In-Memory Operations (Fast) ──
    
    def set_field(self, task_id: str, field: str, value: Any, actor: str) -> None:
        """Set a field value in memory (immediate, no file I/O)."""
        with self._lock:
            if task_id not in self._state:
                self._state[task_id] = MemoryState(task_id=task_id)
            
            state = self._state[task_id]
            state.fields[field] = value
            state.vector_clock = state.vector_clock.increment(actor)
            state.last_modified = datetime.now(timezone.utc)
            state.pending_sync = True
            
            # Log event for potential replay
            self._event_log.append(Event(
                task_id=task_id,
                field=field,
                op="set",
                value=value,
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor=actor,
                vector_clock=state.vector_clock.clocks
            ))
    
    def get_field(self, task_id: str, field: str, default: Any = None) -> Any:
        """Get a field value from memory (immediate, no file I/O)."""
        with self._lock:
            if task_id in self._state:
                return self._state[task_id].fields.get(field, default)
            return default
    
    def add_tags(self, task_id: str, tags: List[str], actor: str) -> None:
        """Add tags to a task in memory."""
        with self._lock:
            if task_id not in self._state:
                self._state[task_id] = MemoryState(task_id=task_id)

            state = self._state[task_id]
            cleaned = [tag.lower().strip() for tag in tags if str(tag).strip()]
            for tag in cleaned:
                state.tags.add(tag)
            state.vector_clock = state.vector_clock.increment(actor)
            state.last_modified = datetime.now(timezone.utc)
            state.pending_sync = True
            if cleaned:
                self._event_log.append(Event(
                    task_id=task_id,
                    field="tags",
                    op="add",
                    value=cleaned,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    actor=actor,
                    vector_clock=state.vector_clock.clocks,
                ))

    def remove_tags(self, task_id: str, tags: List[str], actor: str) -> None:
        """Remove tags from a task in memory."""
        with self._lock:
            if task_id in self._state:
                state = self._state[task_id]
                cleaned = [tag.lower().strip() for tag in tags if str(tag).strip()]
                for tag in cleaned:
                    state.tags.discard(tag)
                state.vector_clock = state.vector_clock.increment(actor)
                state.last_modified = datetime.now(timezone.utc)
                state.pending_sync = True
                if cleaned:
                    self._event_log.append(Event(
                        task_id=task_id,
                        field="tags",
                        op="remove",
                        value=cleaned,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        actor=actor,
                        vector_clock=state.vector_clock.clocks,
                    ))
    
    def get_tags(self, task_id: str) -> Set[str]:
        """Get tags for a task from memory."""
        with self._lock:
            if task_id in self._state:
                return self._state[task_id].tags.copy()
            return set()
    
    def get_task_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get complete task state from memory."""
        with self._lock:
            if task_id in self._state:
                state = self._state[task_id]
                return {
                    "id": task_id,
                    "fields": state.fields.copy(),
                    "tags": list(state.tags),
                    "vector_clock": state.vector_clock.clocks,
                    "last_modified": state.last_modified.isoformat()
                }
            return None
    
    def get_all_task_ids(self) -> List[str]:
        """Get all task IDs from memory."""
        with self._lock:
            return list(self._state.keys())
    
    def delete_task(self, task_id: str) -> None:
        """Delete a task from memory."""
        with self._lock:
            if task_id in self._state:
                del self._state[task_id]
    
    # ── Periodic Filesystem Sync (Lazy) ──
    
    def _task_exists_in_engine(self, task_id: str) -> bool:
        """Check whether the engine already materialized the task in SQLite."""
        if not self.engine:
            return False
        row = self.engine.conn.execute(
            "SELECT id FROM task_index WHERE id = ? OR slug = ?",
            (task_id, task_id),
        ).fetchone()
        return row is not None

    def _ensure_task_exists_in_engine(self, task_id: str, state: Optional[MemoryState] = None) -> None:
        """Create the base task record in the engine before replaying field events."""
        if not self.engine or self._task_exists_in_engine(task_id):
            return

        if state is None:
            state = self._state.get(task_id)
        if state is None:
            return

        title = str(state.fields.get("title", "Untitled Task") or "Untitled Task").strip() or "Untitled Task"
        description = str(state.fields.get("description", "No description provided.") or "No description provided.").strip()
        priority = str(state.fields.get("priority", "P1") or "P1").strip().upper()
        tags = [tag.strip().lower() for tag in state.tags if str(tag).strip()]

        self.engine.start(
            title=title,
            priority_raw=priority,
            tags=tags,
            description=description,
            actor="memory_store",
        )

    def sync_to_filesystem(self) -> Dict[str, int]:
        """
        Sync pending CRDT events to the SQLite engine.

        The source of truth is the event log, not materialized markdown.
        This replays the memory-store mutations into the engine so a reload
        reconstructs the same CRDT state from task_events.
        """
        with self._lock:
            if not self._event_log or not self.engine:
                return {"synced": 0, "skipped": 0}

            synced_count = 0
            skipped_count = len(self._event_log)

            try:
                for event in list(self._event_log):
                    state = self._state.get(event.task_id)
                    self._ensure_task_exists_in_engine(event.task_id, state)

                    if event.op == "set":
                        self.engine.edit_task_field(
                            task_id=event.task_id,
                            field=event.field,
                            value=event.value,
                            op="set",
                            actor=event.actor,
                        )
                    elif event.field == "tags" and event.op == "add":
                        payload = event.value if isinstance(event.value, list) else [event.value]
                        self.engine.add_tags(
                            task_id=event.task_id,
                            tags=payload,
                            actor=event.actor,
                        )
                    elif event.field == "tags" and event.op == "remove":
                        payload = event.value if isinstance(event.value, list) else [event.value]
                        self.engine.remove_tags(
                            task_id=event.task_id,
                            tags=payload,
                            actor=event.actor,
                        )
                    else:
                        self.engine.edit_task_field(
                            task_id=event.task_id,
                            field=event.field,
                            value=event.value,
                            op=event.op,
                            actor=event.actor,
                        )

                    synced_count += 1
                    skipped_count -= 1

                self._event_log.clear()
                for state in self._state.values():
                    state.pending_sync = False

            except Exception as e:
                print(f"Warning: Failed to sync CRDT events to engine: {e}")
                return {"synced": 0, "skipped": skipped_count or len(self._event_log)}

            return {"synced": synced_count, "skipped": 0}
    
    def force_sync(self) -> Dict[str, int]:
        """Force immediate sync of all pending changes."""
        return self.sync_to_filesystem()
    
    # ── Query Operations ──
    
    def query_tasks(self, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Query tasks from memory with optional filters."""
        with self._lock:
            results = []
            
            for task_id, state in self._state.items():
                task_data = {
                    "id": task_id,
                    **state.fields,
                    "tags": list(state.tags),
                    "vector_clock": state.vector_clock.clocks,
                    "last_modified": state.last_modified.isoformat()
                }
                
                # Apply filters
                if filters:
                    if not self._matches_filters(task_data, filters):
                        continue
                
                results.append(task_data)
            
            return results
    
    def _matches_filters(self, task_data: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if task data matches filters."""
        for key, value in filters.items():
            if key not in task_data:
                return False
            if task_data[key] != value:
                return False
        return True
    
    # ── Statistics and Monitoring ──
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the memory store."""
        with self._lock:
            pending_sync = sum(1 for state in self._state.values() if state.pending_sync)
            total_events = len(self._event_log)
            
            return {
                "total_tasks": len(self._state),
                "pending_sync": pending_sync,
                "total_events": total_events,
                "sync_interval": self._sync_interval,
                "memory_usage_approx": len(json.dumps(self._state, default=str))
            }
    
    def get_pending_changes(self) -> List[str]:
        """Get list of task IDs with pending changes."""
        with self._lock:
            return [task_id for task_id, state in self._state.items() if state.pending_sync]


class PredictiveCache:
    """
    Predictive caching system that learns LLM access patterns.
    
    This predicts what the LLM might need next and pre-loads it into memory.
    """
    
    def __init__(self, max_cache_size: int = 100):
        self._cache: Dict[str, Any] = {}
        self._access_patterns: Dict[str, List[datetime]] = defaultdict(list)
        self._max_cache_size = max_cache_size
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache and record access pattern."""
        with self._lock:
            if key in self._cache:
                self._access_patterns[key].append(datetime.now(timezone.utc))
                # Keep only last 10 access times
                if len(self._access_patterns[key]) > 10:
                    self._access_patterns[key] = self._access_patterns[key][-10:]
                return self._cache[key]
            return None
    
    def set(self, key: str, value: Any) -> None:
        """Set item in cache with size management."""
        with self._lock:
            # Evict if cache is full
            if len(self._cache) >= self._max_cache_size and key not in self._cache:
                self._evict_least_recently_used()
            
            self._cache[key] = value
            self._access_patterns[key].append(datetime.now(timezone.utc))
    
    def _evict_least_recently_used(self) -> None:
        """Evict the least recently used item from cache."""
        if not self._cache:
            return
        
        # Find item with oldest access
        oldest_key = None
        oldest_time = datetime.now(timezone.utc)
        
        for key, access_times in self._access_patterns.items():
            if access_times:
                latest_access = max(access_times)
                if latest_access < oldest_time:
                    oldest_time = latest_access
                    oldest_key = key
        
        if oldest_key and oldest_key in self._cache:
            del self._cache[oldest_key]
            del self._access_patterns[oldest_key]
    
    def predict_next_access(self, recent_keys: List[str]) -> List[str]:
        """Predict what might be accessed next based on patterns."""
        with self._lock:
            predictions = []
            
            # Simple pattern: if keys A and B are accessed together often,
            # predict that when A is accessed, B might be next
            
            for key in recent_keys:
                if key in self._access_patterns:
                    # This is a simplified prediction - in a real implementation,
                    # you'd use more sophisticated pattern recognition
                    predictions.append(key)
            
            return predictions[:5]  # Return top 5 predictions
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_accesses = sum(len(times) for times in self._access_patterns.values())
            
            return {
                "cache_size": len(self._cache),
                "max_cache_size": self._max_cache_size,
                "total_accesses": total_accesses,
                "unique_keys": len(self._access_patterns),
                "hit_rate": self._calculate_hit_rate()
            }
    
    def _calculate_hit_rate(self) -> float:
        """Calculate cache hit rate (simplified)."""
        # This is a placeholder - real implementation would track hits vs misses
        return 0.0
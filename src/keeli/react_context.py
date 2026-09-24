"""
Keeli ReAct Loop - Dynamic State Context Injection

This module implements the dynamic state context injection system that prepends
current branch name, session ID, and context digest into the system prompt.
"""

import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timezone

from keeli.engine import KeeliEngine
from keeli.react_prompt import format_dynamic_context

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DynamicContextInjector:
    """
    Manages dynamic state context injection for the ReAct loop.
    
    This class:
    - Gathers current workspace state (branch, session, task info)
    - Generates context digests
    - Formats context for system prompt injection
    - Updates context dynamically during execution
    """
    
    def __init__(self, root_dir: Optional[Path] = None):
        """
        Initialize the dynamic context injector.
        
        Args:
            root_dir: Project root directory
        """
        self.root_dir = root_dir
        self._engine = None
        self._cached_context: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 30  # Cache context for 30 seconds
    
    @property
    def engine(self) -> KeeliEngine:
        """Lazy-load the Keeli engine."""
        if self._engine is None:
            self._engine = KeeliEngine(root_dir=self.root_dir)
        return self._engine
    
    def get_current_state(self) -> Dict[str, Any]:
        """
        Get the current workspace state.
        
        Returns:
            Dictionary containing current branch, session, task info
        """
        # Check cache
        if self._cached_context and self._is_cache_valid():
            return self._cached_context
        
        try:
            # Get project context from engine
            project_context = self.engine.get_project_context()
            
            # Build state dictionary
            state = {
                "branch": project_context.get("branch", "unknown"),
                "session_id": project_context.get("active_session"),
                "session_goal": project_context.get("session_goal"),
                "focus_task_id": project_context.get("focus_task_id"),
                "focus_task": project_context.get("focus_task"),
                "project_root": str(project_context.get("project_root", "")),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Cache the result
            self._cached_context = state
            self._cache_timestamp = datetime.now(timezone.utc)
            
            return state
        
        except Exception as e:
            logger.error(f"Failed to get current state: {e}")
            return {
                "branch": "unknown",
                "session_id": None,
                "session_goal": None,
                "focus_task_id": None,
                "focus_task": None,
                "project_root": str(self.root_dir) if self.root_dir else "",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }
    
    def _is_cache_valid(self) -> bool:
        """Check if the cached context is still valid."""
        if not self._cache_timestamp:
            return False
        
        age = (datetime.now(timezone.utc) - self._cache_timestamp).total_seconds()
        return age < self._cache_ttl_seconds
    
    def invalidate_cache(self) -> None:
        """Invalidate the cached context."""
        self._cached_context = None
        self._cache_timestamp = None
    
    def get_context_digest(
        self,
        session_id: Optional[str] = None,
        tier: str = "brief",
        budget: int = 1200
    ) -> str:
        """
        Get a context digest for the current state.
        
        Args:
            session_id: Session ID to scope digest to
            tier: Detail level (nano, brief, standard, full)
            budget: Token budget for digest
        
        Returns:
            Context digest string
        """
        try:
            state = self.get_current_state()
            effective_session_id = session_id or state.get("session_id")
            branch = state.get("branch")
            
            digest = self.engine.digest(
                tier=tier,
                budget=budget,
                session_id=effective_session_id,
                branch=branch,
                include_working_memory=True,
                include_knowledge=False
            )
            
            return digest
        
        except Exception as e:
            logger.error(f"Failed to get context digest: {e}")
            return f"Context digest unavailable: {str(e)}"
    
    def format_for_system_prompt(
        self,
        session_id: Optional[str] = None,
        include_digest: bool = True,
        digest_tier: str = "brief",
        digest_budget: int = 1200
    ) -> str:
        """
        Format the current state for injection into the system prompt.
        
        Args:
            session_id: Session ID to scope context to
            include_digest: Whether to include context digest
            digest_tier: Detail level for digest
            digest_budget: Token budget for digest
        
        Returns:
            Formatted context string
        """
        state = self.get_current_state()
        
        # Build context components
        context_parts = []
        
        # Add branch info
        if state.get("branch"):
            context_parts.append(f"**Current Branch**: {state['branch']}")
        
        # Add session info
        if state.get("session_id"):
            context_parts.append(f"**Session ID**: {state['session_id']}")
            if state.get("session_goal"):
                context_parts.append(f"**Session Goal**: {state['session_goal']}")
        
        # Add focus task info
        if state.get("focus_task_id"):
            context_parts.append(f"**Focus Task**: {state['focus_task_id']}")
            if state.get("focus_task"):
                task = state['focus_task']
                context_parts.append(f"  - Title: {task.get('title', 'N/A')}")
                context_parts.append(f"  - Status: {task.get('status', 'N/A')}")
                context_parts.append(f"  - Priority: {task.get('priority', 'N/A')}")
        
        # Add context digest if requested
        if include_digest:
            digest = self.get_context_digest(
                session_id=session_id,
                tier=digest_tier,
                budget=digest_budget
            )
            if digest and digest != "Context digest unavailable":
                context_parts.append(f"**Context Digest**:")
                context_parts.append(f"```\n{digest}\n```")
        
        # Add timestamp
        context_parts.append(f"**Last Updated**: {state.get('timestamp', 'N/A')}")
        
        return "\n".join(context_parts)
    
    def update_session_state(
        self,
        session_id: Optional[str] = None,
        focus_task_id: Optional[str] = None
    ) -> None:
        """
        Update the current session state.
        
        Args:
            session_id: New session ID
            focus_task_id: New focus task ID
        """
        # Invalidate cache to force refresh
        self.invalidate_cache()
        
        # Update internal state tracking
        if session_id is not None:
            # The cache will be refreshed on next get_current_state call
            pass
        
        if focus_task_id is not None:
            # Same - let the cache refresh handle it
            pass
    
    def get_task_context(self, task_id: str) -> Dict[str, Any]:
        """
        Get detailed context for a specific task.
        
        Args:
            task_id: Task identifier
        
        Returns:
            Task context dictionary
        """
        try:
            task_state = self.engine.get_task_state(task_id)
            task_markdown = self.engine.get_task(task_id)
            conflicts = self.engine.detect_conflicts(task_id)
            
            return {
                "task_id": task_id,
                "state": task_state,
                "markdown": task_markdown,
                "conflicts": conflicts,
                "conflict_count": len(conflicts)
            }
        
        except Exception as e:
            logger.error(f"Failed to get task context for {task_id}: {e}")
            return {
                "task_id": task_id,
                "error": str(e)
            }
    
    def get_recent_activity(self, limit: int = 5) -> list:
        """
        Get recent activity from the audit log.
        
        Args:
            limit: Maximum number of activity entries to return
        
        Returns:
            List of recent activity entries
        """
        try:
            rows = self.engine.conn.execute(
                """SELECT created, actor, action, details, item_id 
                   FROM audit 
                   ORDER BY event_id DESC 
                   LIMIT ?""",
                (limit,)
            ).fetchall()
            
            return [dict(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Failed to get recent activity: {e}")
            return []
    
    def get_status_summary(self) -> Dict[str, Any]:
        """
        Get a summary of current task statuses.
        
        Returns:
            Status summary dictionary
        """
        try:
            stats = self.engine.conn.execute(
                "SELECT status, COUNT(*) as count FROM task_index GROUP BY status"
            ).fetchall()
            
            summary = {row["status"]: row["count"] for row in stats}
            summary["total"] = sum(summary.values())
            
            return summary
        
        except Exception as e:
            logger.error(f"Failed to get status summary: {e}")
            return {"error": str(e)}
    
    def format_state_update(self, previous_state: Dict[str, Any], current_state: Dict[str, Any]) -> str:
        """
        Format a state update message showing what changed.
        
        Args:
            previous_state: Previous state dictionary
            current_state: Current state dictionary
        
        Returns:
            Formatted state update message
        """
        changes = []
        
        # Check for session changes
        if previous_state.get("session_id") != current_state.get("session_id"):
            old_session = previous_state.get("session_id") or "None"
            new_session = current_state.get("session_id") or "None"
            changes.append(f"Session changed: {old_session} → {new_session}")
        
        # Check for focus task changes
        if previous_state.get("focus_task_id") != current_state.get("focus_task_id"):
            old_task = previous_state.get("focus_task_id") or "None"
            new_task = current_state.get("focus_task_id") or "None"
            changes.append(f"Focus task changed: {old_task} → {new_task}")
        
        # Check for branch changes
        if previous_state.get("branch") != current_state.get("branch"):
            old_branch = previous_state.get("branch") or "unknown"
            new_branch = current_state.get("branch") or "unknown"
            changes.append(f"Branch changed: {old_branch} → {new_branch}")
        
        if changes:
            return "State changes:\n" + "\n".join(f"  - {change}" for change in changes)
        else:
            return "No state changes detected"
    
    def export_state(self) -> Dict[str, Any]:
        """
        Export the complete current state for debugging or persistence.
        
        Returns:
            Complete state dictionary
        """
        state = self.get_current_state()
        
        # Add additional context
        state["recent_activity"] = self.get_recent_activity(limit=3)
        state["status_summary"] = self.get_status_summary()
        state["context_digest"] = self.get_context_digest(tier="nano", budget=500)
        
        return state
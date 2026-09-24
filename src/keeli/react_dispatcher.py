"""
Keeli ReAct Loop - Tool Dispatcher

This module implements the dispatcher that maps LLM tool calls to actual Keeli Python functions.
It includes argument validation and error handling for LLM hallucinations.
"""

import json
import logging
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from keeli.engine import KeeliEngine
from keeli.react_schemas import validate_tool_arguments, VALIDATION_RULES

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ToolDispatcher:
    """
    Dispatcher that maps LLM tool calls to Keeli engine functions.
    
    This class handles:
    - Tool name to function mapping
    - Argument validation
    - Error handling and recovery
    - Response formatting
    """
    
    def __init__(self, root_dir: Optional[Path] = None):
        """
        Initialize the tool dispatcher.
        
        Args:
            root_dir: Project root directory
        """
        self.root_dir = root_dir
        self._engine = None
    
    @property
    def engine(self) -> KeeliEngine:
        """Lazy-load the Keeli engine."""
        if self._engine is None:
            self._engine = KeeliEngine(root_dir=self.root_dir)
        return self._engine
    
    def dispatch(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch a tool call from the LLM to the appropriate Keeli function.
        
        Args:
            tool_call: Dictionary containing tool name and arguments
                {
                    "name": "keeli_tasks",
                    "arguments": {"operation": "create", "title": "..."}
                }
        
        Returns:
            Response dictionary with result or error
        """
        tool_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})
        
        # Validate tool name
        if not tool_name:
            return self._error_response("missing_tool_name", "Tool name is required")
        
        if not isinstance(arguments, dict):
            return self._error_response("invalid_arguments", "Arguments must be a dictionary")
        
        # Extract operation from arguments
        operation = arguments.get("operation")
        if not operation:
            return self._error_response("missing_operation", "Operation is required")
        
        # Validate arguments against schema
        is_valid, error_msg = validate_tool_arguments(tool_name, operation, arguments)
        if not is_valid:
            return self._error_response("validation_error", error_msg)
        
        # Dispatch to appropriate handler
        try:
            if tool_name == "keeli_tasks":
                return self._dispatch_tasks(operation, arguments)
            elif tool_name == "keeli_context":
                return self._dispatch_context(operation, arguments)
            elif tool_name == "keeli_sessions":
                return self._dispatch_sessions(operation, arguments)
            elif tool_name == "keeli_memory":
                return self._dispatch_memory(operation, arguments)
            elif tool_name == "keeli_knowledge":
                return self._dispatch_knowledge(operation, arguments)
            elif tool_name == "keeli_system":
                return self._dispatch_system(operation, arguments)
            else:
                return self._error_response("unknown_tool", f"Unknown tool: {tool_name}")
        
        except ValueError as e:
            logger.error(f"Value error in {tool_name}.{operation}: {e}")
            return self._error_response("value_error", str(e))
        except KeyError as e:
            logger.error(f"Key error in {tool_name}.{operation}: {e}")
            return self._error_response("missing_key", f"Missing required key: {e}")
        except TypeError as e:
            logger.error(f"Type error in {tool_name}.{operation}: {e}")
            return self._error_response("type_error", f"Type mismatch: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in {tool_name}.{operation}: {e}")
            return self._error_response("internal_error", f"Internal error: {str(e)}")
    
    def _dispatch_tasks(self, operation: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch keeli_tasks operations."""
        engine = self.engine
        task_id = args.get("task_id")
        session_id = args.get("session_id")
        branch = args.get("branch")
        actor = args.get("actor")
        
        if operation == "create":
            tid = engine.start(
                title=args["title"],
                priority_raw=args.get("priority", "p2"),
                tags=args.get("tags"),
                description=args.get("description", ""),
                depends_on=args.get("depends_on"),
                actor=actor,
                branch=branch,
                session_id=session_id
            )
            task_state = engine.get_task_state(tid)
            return self._success_response({
                "task_id": tid,
                "task": task_state,
                "message": f"Created task {tid}"
            })
        
        elif operation == "query":
            filters = args.get("filters", {})
            tasks = engine.list_tasks(
                status=filters.get("status") or args.get("status"),
                branch=filters.get("branch") or branch,
                tags=filters.get("tags"),
                tag_match=filters.get("tag_match", "any")
            )
            return self._success_response({
                "count": len(tasks),
                "tasks": tasks,
                "message": f"Found {len(tasks)} tasks"
            })
        
        elif operation == "get":
            if not task_id:
                return self._error_response("missing_task_id", "task_id required for get operation")
            markdown = engine.get_task(task_id)
            state = engine.get_task_state(task_id)
            return self._success_response({
                "task_id": task_id,
                "state": state,
                "markdown": markdown,
                "message": f"Retrieved task {task_id}"
            })
        
        elif operation == "get_state":
            if not task_id:
                return self._error_response("missing_task_id", "task_id required for get_state operation")
            state = engine.get_task_state(task_id)
            return self._success_response({
                "task_id": task_id,
                "state": state,
                "message": f"Retrieved state for task {task_id}"
            })
        
        elif operation == "next":
            task = engine.next_task(session_id=session_id, branch=branch)
            if task:
                return self._success_response({
                    "task": task,
                    "has_pending": True,
                    "message": f"Next task: {task['id']} - {task['title']}"
                })
            return self._success_response({
                "task": None,
                "has_pending": False,
                "message": "No pending tasks"
            })
        
        elif operation == "update_status":
            if not task_id or not args.get("status"):
                return self._error_response("missing_fields", "task_id and status required")
            engine.move_task(
                task_id, args["status"],
                actor=actor, branch=branch, session_id=session_id,
                rationale=args.get("rationale")
            )
            if args["status"] == "active" and session_id:
                engine.session_focus(task_id, session_id=session_id)
            state = engine.get_task_state(task_id)
            return self._success_response({
                "task_id": task_id,
                "status": args["status"],
                "state": state,
                "message": f"Updated task {task_id} to {args['status']}"
            })
        
        elif operation == "update_field":
            if not task_id or not args.get("field") or not args.get("value"):
                return self._error_response("missing_fields", "task_id, field, and value required")
            engine.edit_task_field(
                task_id, args["field"], args["value"],
                actor=actor, branch=branch, session_id=session_id
            )
            state = engine.get_task_state(task_id)
            return self._success_response({
                "task_id": task_id,
                "field": args["field"],
                "value": args["value"],
                "state": state,
                "message": f"Updated {args['field']} for task {task_id}"
            })
        
        elif operation == "update_tags":
            if not task_id or not args.get("tags"):
                return self._error_response("missing_fields", "task_id and tags required")
            tag_op = args.get("tag_operation", "add")
            if tag_op == "add":
                engine.add_tags(task_id, args["tags"], actor=actor, branch=branch, session_id=session_id)
            elif tag_op == "remove":
                engine.remove_tags(task_id, args["tags"], actor=actor, branch=branch, session_id=session_id)
            else:
                return self._error_response("invalid_tag_operation", "tag_operation must be 'add' or 'remove'")
            state = engine.get_task_state(task_id)
            return self._success_response({
                "task_id": task_id,
                "tag_operation": tag_op,
                "tags": args["tags"],
                "state": state,
                "message": f"Updated tags for task {task_id}"
            })
        
        elif operation == "conflicts":
            if not task_id:
                return self._error_response("missing_task_id", "task_id required for conflicts operation")
            conflicts = engine.detect_conflicts(task_id, args.get("lookback_seconds", 300))
            return self._success_response({
                "task_id": task_id,
                "conflicts": conflicts,
                "count": len(conflicts),
                "message": f"Found {len(conflicts)} conflicts for task {task_id}"
            })
        
        else:
            return self._error_response("unknown_operation", f"Unknown operation: {operation}")
    
    def _dispatch_context(self, operation: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch keeli_context operations."""
        engine = self.engine
        session_id = args.get("session_id")
        branch = args.get("branch")
        
        if operation == "get":
            if not args.get("key"):
                return self._error_response("missing_key", "key required for get operation")
            effective_scope_id = args.get("scope_id")
            if args.get("scope") == "session" and not effective_scope_id:
                effective_scope_id = session_id
            elif args.get("scope") == "branch" and not effective_scope_id:
                effective_scope_id = branch
            
            data = engine.context_get(
                key=args["key"],
                session_id=effective_scope_id if args.get("scope") == "session" else None,
                branch=effective_scope_id if args.get("scope") == "branch" else None
            )
            return self._success_response({
                "key": args["key"],
                "value": data.get("value"),
                "scope": data.get("scope"),
                "message": f"Retrieved context for {args['key']}"
            })
        
        elif operation == "set":
            if not args.get("key") or not args.get("value"):
                return self._error_response("missing_key_value", "key and value required for set operation")
            effective_scope_id = args.get("scope_id")
            if args.get("scope") == "session" and not effective_scope_id:
                effective_scope_id = session_id
            elif args.get("scope") == "branch" and not effective_scope_id:
                effective_scope_id = branch
            
            engine.context_set(
                key=args["key"],
                value=args["value"],
                scope=args.get("scope", "session"),
                scope_id=effective_scope_id,
                source=args.get("source", "agent_override")
            )
            return self._success_response({
                "key": args["key"],
                "scope": args.get("scope"),
                "scope_id": effective_scope_id,
                "message": f"Set context for {args['key']}"
            })
        
        elif operation == "digest":
            result = engine.digest(
                tier=args.get("tier", "standard"),
                budget=args.get("budget", 2000),
                session_id=session_id,
                branch=branch,
                include_working_memory=args.get("include_working_memory", True),
                include_knowledge=args.get("include_knowledge", False)
            )
            return self._success_response({
                "tier": args.get("tier", "standard"),
                "budget": args.get("budget", 2000),
                "digest": result,
                "message": "Generated context digest"
            })
        
        elif operation == "fastcontext":
            result = engine.digest(
                tier=args.get("tier", "brief"),
                budget=args.get("budget", 1200),
                session_id=session_id,
                branch=branch,
                include_working_memory=True,
                include_knowledge=True
            )
            return self._success_response({
                "tier": args.get("tier", "brief"),
                "budget": args.get("budget", 1200),
                "digest": result,
                "message": "Generated fast context"
            })
        
        else:
            return self._error_response("unknown_operation", f"Unknown operation: {operation}")
    
    def _dispatch_sessions(self, operation: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch keeli_sessions operations."""
        engine = self.engine
        
        if operation == "start":
            sid = engine.session_start(
                name=args.get("name", "Investigation"),
                branch=args.get("branch"),
                focus_task_id=args.get("focus_task_id")
            )
            return self._success_response({
                "session_id": sid,
                "name": args.get("name", "Investigation"),
                "branch": args.get("branch"),
                "focus_task_id": args.get("focus_task_id"),
                "message": f"Started session {sid}"
            })
        
        elif operation == "focus":
            if not args.get("session_id") or not args.get("focus_task_id"):
                return self._error_response("missing_fields", "session_id and focus_task_id required")
            engine.session_focus(
                task_id=args["focus_task_id"],
                session_id=args["session_id"]
            )
            return self._success_response({
                "session_id": args["session_id"],
                "focus_task_id": args["focus_task_id"],
                "message": f"Focused session on task {args['focus_task_id']}"
            })
        
        elif operation == "checkpoint":
            if not args.get("session_id"):
                return self._error_response("missing_session_id", "session_id required for checkpoint")
            engine.session_checkpoint(
                note=args.get("note", "Sync"),
                session_id=args["session_id"],
                pending_decisions=args.get("pending_decisions")
            )
            return self._success_response({
                "session_id": args["session_id"],
                "note": args.get("note", "Sync"),
                "pending_decisions": args.get("pending_decisions", []),
                "message": f"Created checkpoint for session {args['session_id']}"
            })
        
        elif operation == "list":
            sessions = engine.session_list()
            return self._success_response({
                "count": len(sessions),
                "sessions": sessions,
                "message": f"Found {len(sessions)} sessions"
            })
        
        else:
            return self._error_response("unknown_operation", f"Unknown operation: {operation}")
    
    def _dispatch_memory(self, operation: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch keeli_memory operations."""
        engine = self.engine
        session_id = args.get("session_id")
        branch = args.get("branch")
        
        if operation == "set":
            if not args.get("key") or not args.get("value") or not session_id:
                return self._error_response("missing_fields", "key, value, and session_id required")
            engine.working_memory_set(
                key=args["key"],
                value=args["value"],
                session_id=session_id,
                ttl_minutes=args.get("ttl_minutes", 60)
            )
            return self._success_response({
                "key": args["key"],
                "ttl_minutes": args.get("ttl_minutes", 60),
                "message": f"Stored memory item {args['key']}"
            })
        
        elif operation == "get":
            if not args.get("key") or not session_id:
                return self._error_response("missing_fields", "key and session_id required")
            result = engine.working_memory_get(args["key"], session_id)
            return self._success_response({
                "key": args["key"],
                "value": result,
                "message": f"Retrieved memory item {args['key']}"
            })
        
        elif operation == "delete":
            if not args.get("key") or not session_id:
                return self._error_response("missing_fields", "key and session_id required")
            engine.working_memory_delete(args["key"], session_id)
            return self._success_response({
                "key": args["key"],
                "message": f"Deleted memory item {args['key']}"
            })
        
        elif operation == "list":
            if not session_id:
                return self._error_response("missing_session_id", "session_id required")
            items = engine.working_memory_list(session_id)
            return self._success_response({
                "count": len(items),
                "items": items,
                "message": f"Found {len(items)} memory items"
            })
        
        elif operation == "clear_expired":
            cleared = engine.working_memory_clear_expired(session_id)
            return self._success_response({
                "cleared": cleared,
                "message": f"Cleared {cleared} expired memory items"
            })
        
        elif operation == "save_analysis":
            if not args.get("analysis_type") or not args.get("analysis_content"):
                return self._error_response("missing_fields", "analysis_type and analysis_content required")
            result = engine.save_project_analysis(
                analysis_type=args["analysis_type"],
                analysis_content=args["analysis_content"],
                session_id=session_id,
                branch=branch
            )
            return self._success_response({
                "analysis_type": args["analysis_type"],
                "result": result,
                "message": f"Saved analysis {args['analysis_type']}"
            })
        
        elif operation == "get_analysis":
            if not args.get("analysis_type"):
                return self._error_response("missing_analysis_type", "analysis_type required")
            result = engine.get_project_analysis(
                analysis_type=args["analysis_type"],
                session_id=session_id,
                branch=branch
            )
            return self._success_response({
                "analysis_type": args["analysis_type"],
                "value": result,
                "message": f"Retrieved analysis {args['analysis_type']}"
            })
        
        elif operation == "get_context":
            context = engine.get_project_context()
            return self._success_response({
                "context": context,
                "message": "Retrieved project context"
            })
        
        else:
            return self._error_response("unknown_operation", f"Unknown operation: {operation}")
    
    def _dispatch_knowledge(self, operation: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch keeli_knowledge operations."""
        engine = self.engine
        session_id = args.get("session_id")
        branch = args.get("branch")
        
        if operation == "save":
            if not args.get("knowledge_type") or not args.get("content"):
                return self._error_response("missing_fields", "knowledge_type and content required")
            result = engine.save_project_knowledge(
                knowledge_type=args["knowledge_type"],
                content=args["content"],
                source_session=args.get("source_session"),
                tags=args.get("tags"),
                branch=branch
            )
            return self._success_response({
                "knowledge_type": args["knowledge_type"],
                "result": result,
                "message": f"Saved knowledge {args['knowledge_type']}"
            })
        
        elif operation == "get":
            knowledge = engine.get_project_knowledge(args.get("knowledge_type"))
            return self._success_response({
                "knowledge_type": args.get("knowledge_type"),
                "count": len(knowledge),
                "knowledge": knowledge,
                "message": f"Retrieved {len(knowledge)} knowledge items"
            })
        
        elif operation == "extract":
            if not session_id:
                return self._error_response("missing_session_id", "session_id required for extract")
            knowledge = engine.extract_knowledge_from_session(session_id)
            return self._success_response({
                "session_id": session_id,
                "knowledge": knowledge,
                "message": f"Extracted knowledge from session {session_id}"
            })
        
        elif operation == "list":
            knowledge = engine.get_project_knowledge()
            return self._success_response({
                "count": len(knowledge),
                "types": [k["type"] for k in knowledge],
                "knowledge": knowledge,
                "message": f"Found {len(knowledge)} knowledge types"
            })
        
        else:
            return self._error_response("unknown_operation", f"Unknown operation: {operation}")
    
    def _dispatch_system(self, operation: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch keeli_system operations."""
        engine = self.engine
        
        if operation == "sync":
            count, corrected = engine.sync()
            return self._success_response({
                "count": count,
                "corrected": corrected,
                "message": f"Synced {count} tasks, corrected {corrected}"
            })
        
        elif operation == "doctor":
            status_lines = [
                f"Root: {engine.root_dir}",
                f"Workspace: {engine.workspace_dir} ({'OK' if engine.workspace_dir.exists() else 'MISSING'})",
                f"DB: {engine.db_path} ({'OK' if engine.db_path.exists() else 'Missing'})"
            ]
            for status, directory in engine.status_dirs.items():
                status_lines.append(f"Folder {status}: {'OK' if directory.exists() else 'MISSING'}")
            
            count, corrected = engine.sync()
            status_lines.append(f"Indexing: {count} tasks found, {corrected} corrected.")
            
            return self._success_response({
                "report": status_lines,
                "message": "Health check completed"
            })
        
        else:
            return self._error_response("unknown_operation", f"Unknown operation: {operation}")
    
    def _success_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format a successful response."""
        return {
            "success": True,
            "data": data,
            "error": None
        }
    
    def _error_response(self, code: str, message: str) -> Dict[str, Any]:
        """Format an error response."""
        return {
            "success": False,
            "data": None,
            "error": {
                "code": code,
                "message": message
            }
        }
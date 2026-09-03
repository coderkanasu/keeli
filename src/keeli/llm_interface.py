"""
Keeli v7.0 - LLM-Centric Unified Interface with Structured Intent Routing & Telemetry

Phase 2: Structured Intent Routing
Phase 3: Telemetry & Learning Loop

This module provides a simplified, natural language interface designed specifically
for LLM workflows. It eliminates the complexity of multiple tools and parameters
by providing intelligent defaults and automatic session management.

Core Philosophy: "I understand how you work, let me help automatically"
"""

import re
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum

from keeli.engine import KeeliEngine
from keeli.memory_crdt import MemoryCRDTStore, PredictiveCache
from keeli.semantic_search import SemanticSearchInterface
from keeli.workflow_templates import WorkflowTemplateLibrary
from keeli.context_optimizer import IntelligentContextBuilder
from keeli.telemetry import TelemetryStore, TelemetryLogger, OutcomeType, CheckpointType

if TYPE_CHECKING:
    from keeli.workflow_orchestrator import WorkflowOrchestrator, WorkflowType
else:
    WorkflowOrchestrator = None
    WorkflowType = None


# ── Intent Schema ──

class IntentType(str, Enum):
    """Enumeration of all supported intents."""
    CREATE_TASK = "create_task"
    GET_NEXT_TASK = "get_next_task"
    LIST_TASKS = "list_tasks"
    COMPLETE_TASK = "complete_task"
    GET_STATUS = "get_status"
    STORE_CONTEXT = "store_context"
    GET_CONTEXT = "get_context"
    SEMANTIC_SEARCH = "semantic_search"
    DISCOVER_PATTERNS = "discover_patterns"
    SUMMARIZE = "summarize"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class ParsedIntent:
    """Structured intent with explainable routing information."""
    intent: IntentType
    confidence: float  # 0.0 to 1.0
    parameters: Dict[str, Any] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    evidence: str = ""
    
    def is_valid(self, confidence_threshold: float = 0.75) -> bool:
        """Check if intent passes validation gates."""
        if self.confidence < confidence_threshold:
            return False
        if self.missing_fields:
            return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "intent": self.intent.value,
            "confidence": round(self.confidence, 3),
            "parameters": self.parameters,
            "missing_fields": self.missing_fields,
            "evidence": self.evidence
        }


class LLMInterface:
    """
    Unified LLM-friendly interface with structured intent routing.
    
    This class provides a single entry point for all Keeli operations with:
    - Automatic session management
    - Typed schema-based intent routing (replaces fragile NLP)
    - Validation and fallback mechanisms
    - Natural language UX with structured internal processing
    - Context-aware responses
    - Roundtrip reduction
    """
    
    def __init__(self, root_dir: Optional[Path] = None):
        self.engine = KeeliEngine(root_dir)
        self._auto_session_id: Optional[str] = None
        self._session_start_time: Optional[datetime] = None
        self._activity_log: List[Dict[str, Any]] = []
        self._context_cache: Dict[str, Any] = {}
        self._intent_log: List[ParsedIntent] = []  # For telemetry
        
        # Phase 3: Telemetry & Learning Loop
        self.telemetry_store = TelemetryStore()
        self.telemetry_logger = TelemetryLogger(self.telemetry_store)
        
        # Deferred import to avoid circular dependency
        from keeli.workflow_orchestrator import WorkflowOrchestrator
        self.workflow_orchestrator = WorkflowOrchestrator(self)
        
        # New v7.0 components
        self.memory_store = MemoryCRDTStore(sync_interval_seconds=30, engine=self.engine)
        self.predictive_cache = PredictiveCache(max_cache_size=100)
        self.semantic_search = SemanticSearchInterface(self)
        self.template_library = WorkflowTemplateLibrary()
        self.context_builder = IntelligentContextBuilder(max_tokens=4000)
        
    # ── Auto-Session Management ──
    
    def _ensure_session(self, goal: str = "LLM Work Session") -> str:
        """Automatically ensure an active session exists."""
        if self._auto_session_id:
            # Check if session is still valid (within last hour)
            if self._session_start_time and \
               datetime.now(timezone.utc) - self._session_start_time < timedelta(hours=1):
                return self._auto_session_id
        
        # Create new session
        self._auto_session_id = self.engine.session_start(
            name=goal,
            branch=self.engine._get_current_branch()
        )
        self._session_start_time = datetime.now(timezone.utc)
        self._log_activity("session_start", {"goal": goal})
        return self._auto_session_id
    
    def _log_activity(self, activity_type: str, details: Dict[str, Any]) -> None:
        """Log activity for pattern detection and optimization."""
        self._activity_log.append({
            "type": activity_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details
        })
        # Keep only last 100 activities
        if len(self._activity_log) > 100:
            self._activity_log = self._activity_log[-100:]
    
    # ── Structured Intent Routing ──
    
    def _parse_intent(self, natural_request: str) -> ParsedIntent:
        """
        Parse natural language request into structured intent with validation.
        
        Returns a ParsedIntent with typed fields, confidence score,
        extracted parameters, and evidence for the classification.
        """
        request_lower = natural_request.lower().strip()
        
        # ── Task Creation Intent ──
        if any(word in request_lower for word in ["create", "add", "new", "make"]):
            details = self._extract_task_details(natural_request)
            return ParsedIntent(
                intent=IntentType.CREATE_TASK,
                confidence=0.95 if details["title"] else 0.7,
                parameters=details,
                missing_fields=[] if details["title"] else ["title"],
                evidence="Request contains task creation keywords (create/add/new/make) and extracted task details"
            )
        
        # ── Get Next Task Intent ──
        if any(word in request_lower for word in ["next", "what's next", "what should i", "upcoming", "what do i"]):
            return ParsedIntent(
                intent=IntentType.GET_NEXT_TASK,
                confidence=0.95,
                parameters={},
                missing_fields=[],
                evidence="Request contains next-task keywords (next/upcoming/what should i)"
            )
        
        # ── List Tasks Intent ──
        if any(word in request_lower for word in ["show", "list", "what are", "tell me", "all tasks"]):
            return ParsedIntent(
                intent=IntentType.LIST_TASKS,
                confidence=0.90,
                parameters={},
                missing_fields=[],
                evidence="Request contains listing keywords (show/list/what are/tell me)"
            )
        
        # ── Complete Task Intent ──
        if any(word in request_lower for word in ["complete", "done", "finish", "archive", "mark complete"]):
            task_id = self._extract_task_id(natural_request)
            return ParsedIntent(
                intent=IntentType.COMPLETE_TASK,
                confidence=0.9 if task_id else 0.6,
                parameters={"task_id": task_id},
                missing_fields=[] if task_id else ["task_id"],
                evidence=f"Request contains completion keywords; task_id {'found' if task_id else 'not found in request'}"
            )
        
        # ── Get Status Intent ──
        if any(word in request_lower for word in ["status", "progress", "how's", "current state", "what's happening"]):
            return ParsedIntent(
                intent=IntentType.GET_STATUS,
                confidence=0.90,
                parameters={},
                missing_fields=[],
                evidence="Request contains status keywords (status/progress/how's/current)"
            )
        
        # ── Store Context Intent ──
        if any(word in request_lower for word in ["remember", "save", "store", "cache", "note that"]):
            content = self._extract_context_content(natural_request, ["remember", "save", "store", "cache", "note that"])
            return ParsedIntent(
                intent=IntentType.STORE_CONTEXT,
                confidence=0.95 if content else 0.7,
                parameters={"content": content},
                missing_fields=[] if content else ["content"],
                evidence=f"Request contains context storage keywords; content {'extracted' if content else 'not found'}"
            )
        
        # ── Get Context Intent ──
        if any(word in request_lower for word in ["recall", "get", "retrieve", "what did", "what do you remember", "remind me"]):
            return ParsedIntent(
                intent=IntentType.GET_CONTEXT,
                confidence=0.90,
                parameters={},
                missing_fields=[],
                evidence="Request contains retrieval keywords (recall/retrieve/what did/remind me)"
            )
        
        # ── Semantic Search Intent ──
        if any(word in request_lower for word in ["search", "find", "look for", "related to", "similar to"]):
            return ParsedIntent(
                intent=IntentType.SEMANTIC_SEARCH,
                confidence=0.92,
                parameters={"query": natural_request},
                missing_fields=[],
                evidence="Request contains search keywords (search/find/look for/related to)"
            )
        
        # ── Discover Patterns Intent ──
        if any(word in request_lower for word in ["patterns", "discover", "analyze", "insights", "trends", "concepts"]):
            return ParsedIntent(
                intent=IntentType.DISCOVER_PATTERNS,
                confidence=0.90,
                parameters={},
                missing_fields=[],
                evidence="Request contains analysis keywords (patterns/discover/analyze/insights)"
            )
        
        # ── Summarize Intent ──
        if any(word in request_lower for word in ["summarize", "summary", "wrap up", "recap", "tldr"]):
            return ParsedIntent(
                intent=IntentType.SUMMARIZE,
                confidence=0.95,
                parameters={},
                missing_fields=[],
                evidence="Request contains summarization keywords (summarize/summary/wrap up/recap)"
            )
        
        # ── Help Intent ──
        if any(word in request_lower for word in ["help", "how do i", "what can you", "guide", "teach"]):
            return ParsedIntent(
                intent=IntentType.HELP,
                confidence=0.90,
                parameters={},
                missing_fields=[],
                evidence="Request contains help keywords (help/how do i/what can you)"
            )
        
        # ── Unknown Intent (Low Confidence Default) ──
        return ParsedIntent(
            intent=IntentType.UNKNOWN,
            confidence=0.4,
            parameters={"request": natural_request},
            missing_fields=["intent"],
            evidence="Request did not match any known intent patterns"
        )
    
    def _validate_intent(self, parsed: ParsedIntent, confidence_threshold: float = 0.75) -> tuple[bool, Optional[str]]:
        """
        Validate parsed intent and determine if clarification is needed.
        
        Returns: (is_valid, clarification_prompt)
        """
        # Check confidence threshold
        if parsed.confidence < confidence_threshold:
            return False, f"I'm not sure what you mean (confidence: {parsed.confidence:.1%}). Could you clarify?"
        
        # Check for missing required fields
        if parsed.missing_fields:
            fields_str = ", ".join(parsed.missing_fields)
            return False, f"I need more information to proceed. Missing: {fields_str}. Could you provide details?"
        
        # Intent is valid
        return True, None
    
    def _request_clarification(self, parsed: ParsedIntent, original_request: str, clarification_prompt: str, session_id: str) -> str:
        """
        Handle low-confidence or incomplete intents with clarification loop.
        
        Returns response asking user for more information.
        """
        self._log_activity("clarification_requested", {
            "intent": parsed.intent.value,
            "confidence": parsed.confidence,
            "missing_fields": parsed.missing_fields
        })
        
        return f"❓ {clarification_prompt}\n\nYour request: \"{original_request}\"\nMy analysis: {parsed.evidence}"
    
    def _extract_task_details(self, natural_request: str) -> Dict[str, Any]:
        """Extract task details from natural language."""
        details = {"title": "", "priority": "p1", "tags": [], "description": ""}
        request_lower = natural_request.lower()
        
        # Extract priority
        if "urgent" in request_lower or "critical" in request_lower:
            details["priority"] = "p0"
        elif "important" in request_lower:
            details["priority"] = "p1"
        elif "low" in request_lower or "minor" in request_lower:
            details["priority"] = "p2"
        
        # Extract title (remove common task-related words)
        title = natural_request
        for word in ["create", "add", "new", "task", "make", "urgent", "critical", "important", "low", "minor"]:
            title = re.sub(rf"\b{word}\b", "", title, flags=re.IGNORECASE)
        details["title"] = title.strip() or ""

        # Extract schema-based tags from intent keywords
        details["tags"] = self._extract_tags_from_request(request_lower)
        
        # Extract description (anything after "because" or "to")
        if "because" in request_lower:
            parts = request_lower.split("because")
            if len(parts) > 1:
                details["description"] = parts[1].strip()
        elif " to " in request_lower:
            parts = request_lower.split(" to ", 1)
            if len(parts) > 1:
                details["description"] = "To " + parts[1].strip()
        
        return details

    def _extract_tags_from_request(self, request_lower: str) -> List[str]:
        """Extract structured tags using the enforced schema prefix:value."""
        tag_set = set()

        domain_map = {
            "frontend": ["ui", "frontend", "dashboard", "streamlit"],
            "backend": ["backend", "api", "server", "database", "db", "mcp"],
            "data": ["data", "ingestion", "analytics", "sector", "integrity"],
            "testing": ["test", "tests", "coverage", "benchmark"],
            "security": ["auth", "authentication", "security", "vulnerability", "cve"],
            "devops": ["deploy", "deployment", "infra", "docker", "kubernetes"],
        }

        area_map = {
            "auth": ["auth", "authentication", "jwt"],
            "dashboard": ["dashboard", "ui", "streamlit"],
            "state-management": ["state", "session", "context", "memory", "crdt"],
            "data-integrity": ["sector", "unknown", "missing", "integrity", "reconcile"],
            "telemetry": ["telemetry", "metrics", "observability", "monitoring"],
            "performance": ["performance", "optimize", "latency", "speed"],
            "mcp": ["mcp", "tool", "agent"],
        }

        risk_map = {
            "critical": ["critical", "urgent", "prod", "production", "outage", "sev1"],
            "high": ["high", "blocking", "blocker", "sev2"],
            "medium": ["important", "sev3"],
            "low": ["minor", "low", "nice to have"],
        }

        state_map = {
            "blocked": ["blocked", "waiting", "stuck"],
            "review": ["review", "qa", "verify", "validation"],
            "active": ["active", "in progress", "working on"],
            "planned": ["plan", "planning", "todo", "backlog"],
        }

        def add_from_map(prefix: str, mapping: Dict[str, List[str]]) -> None:
            for value, keywords in mapping.items():
                if any(keyword in request_lower for keyword in keywords):
                    tag_set.add(f"{prefix}:{value}")

        add_from_map("domain", domain_map)
        add_from_map("area", area_map)
        add_from_map("risk", risk_map)
        add_from_map("state", state_map)

        return sorted(tag_set)
    
    def _extract_task_id(self, text: str) -> Optional[str]:
        """Extract task ID from text."""
        match = re.search(r'[Tt]-?\d+', text)
        if match:
            task_id = match.group(0).upper()
            if not task_id.startswith("T-"):
                task_id = f"T-{task_id[2:]}"
            return task_id
        return None
    
    def _extract_context_content(self, text: str, trigger_words: List[str]) -> str:
        """Extract context content after trigger words."""
        for word in trigger_words:
            pattern = rf"{word}\s+(.*?)(?:\.|$)"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""
    
    # ── Unified Public Interface ──
    
    def ask(self, request: str) -> str:
        """
        Main entry point - natural language interface with structured intent routing.
        
        This method:
        1. Parses request into typed ParsedIntent
        2. Validates intent (confidence threshold, missing fields)
        3. Falls back to clarification if needed
        4. Routes to appropriate handler
        5. Logs all actions for telemetry (Phase 3)
        """
        # ── Store request for telemetry ──
        self._current_request_text = request
        
        # ── Telemetry: Start Request ──
        self.telemetry_logger.start_request(request)
        
        session_id = self._ensure_session(f"Natural language request: {request[:50]}")
        
        # ── Phase 1: Parse Intent ──
        parsed_intent = self._parse_intent(request)
        self._intent_log.append(parsed_intent)
        self.telemetry_logger.checkpoint(CheckpointType.INTENT_PARSED)
        
        # ── Phase 2: Validate Intent ──
        is_valid, clarification_prompt = self._validate_intent(parsed_intent)
        self.telemetry_logger.checkpoint(CheckpointType.VALIDATION_CHECKED)
        
        if not is_valid:
            # Log clarification request
            self.telemetry_logger.log_request_lifecycle(
                request_text=request,
                intent_type=parsed_intent.intent.value,
                confidence=parsed_intent.confidence,
                parameters=parsed_intent.parameters,
                missing_fields=parsed_intent.missing_fields,
                validation_passed=False,
                route_chosen="clarification_request",
                outcome=OutcomeType.CLARIFICATION_REQUESTED,
                metadata={"evidence": parsed_intent.evidence}
            )
            return self._request_clarification(parsed_intent, request, clarification_prompt, session_id)
        
        # ── Phase 3: Check Workflow Triggers ──
        workflow_type = self.workflow_orchestrator.detect_workflow(request)
        if workflow_type and not self.workflow_orchestrator._active_workflow:
            matching_template = self.template_library.find_matching_template(request)
            if matching_template:
                template_info = self.template_library.format_template_for_display(matching_template)
                workflow_start = self.workflow_orchestrator.start_workflow(workflow_type, request)
                self._log_activity("workflow_started", {"workflow_type": workflow_type.value})
                # Log workflow start
                self.telemetry_logger.log_request_lifecycle(
                    request_text=request,
                    intent_type=parsed_intent.intent.value,
                    confidence=parsed_intent.confidence,
                    parameters=parsed_intent.parameters,
                    missing_fields=[],
                    validation_passed=True,
                    route_chosen="workflow_template",
                    outcome=OutcomeType.SUCCESS
                )
                return f"{workflow_start}\n\n📋 **Suggested Template:**\n{template_info}"
            workflow_start = self.workflow_orchestrator.start_workflow(workflow_type, request)
            self._log_activity("workflow_started", {"workflow_type": workflow_type.value})
            self.telemetry_logger.log_request_lifecycle(
                request_text=request,
                intent_type=parsed_intent.intent.value,
                confidence=parsed_intent.confidence,
                parameters=parsed_intent.parameters,
                missing_fields=[],
                validation_passed=True,
                route_chosen="workflow",
                outcome=OutcomeType.SUCCESS
            )
            return workflow_start
        
        # ── Phase 4: Handle Workflow Continuation ──
        if self.workflow_orchestrator._active_workflow:
            if "next" in request.lower() or "continue" in request.lower():
                return self.workflow_orchestrator.advance_stage()
            elif "complete" in request.lower() or "finish" in request.lower():
                return self.workflow_orchestrator._complete_workflow()
            elif "status" in request.lower() or "where" in request.lower():
                return self.workflow_orchestrator.get_workflow_status()
            elif "templates" in request.lower() or "workflows" in request.lower():
                return self.workflow_orchestrator.get_workflow_templates()
        
        # ── Phase 5: Route to Handler ──
        try:
            self.telemetry_logger.checkpoint(CheckpointType.ROUTE_CHOSEN)
            
            if parsed_intent.intent == IntentType.CREATE_TASK:
                return self._handle_create_task(parsed_intent, session_id, request)
            
            elif parsed_intent.intent == IntentType.GET_NEXT_TASK:
                return self._handle_get_next_task(parsed_intent, session_id, request)
            
            elif parsed_intent.intent == IntentType.LIST_TASKS:
                return self._handle_list_tasks(parsed_intent, session_id, request)
            
            elif parsed_intent.intent == IntentType.COMPLETE_TASK:
                return self._handle_complete_task(parsed_intent, session_id, request)
            
            elif parsed_intent.intent == IntentType.GET_STATUS:
                return self._handle_get_status(parsed_intent, session_id, request)
            
            elif parsed_intent.intent == IntentType.STORE_CONTEXT:
                return self._handle_store_context(parsed_intent, session_id, request)
            
            elif parsed_intent.intent == IntentType.GET_CONTEXT:
                return self._handle_get_context(parsed_intent, session_id, request)
            
            elif parsed_intent.intent == IntentType.SEMANTIC_SEARCH:
                return self._handle_semantic_search(parsed_intent, session_id, request)
            
            elif parsed_intent.intent == IntentType.DISCOVER_PATTERNS:
                return self._handle_discover_patterns(parsed_intent, session_id, request)
            
            elif parsed_intent.intent == IntentType.SUMMARIZE:
                return self._handle_summarize(parsed_intent, session_id, request)
            
            elif parsed_intent.intent == IntentType.HELP:
                return self._handle_help(parsed_intent, session_id, request)
            
            else:  # UNKNOWN
                return self._handle_unknown(parsed_intent, session_id, request)
        
        except Exception as e:
            self._log_activity("execution_error", {"intent": parsed_intent.intent.value, "error": str(e)})
            # Log error to telemetry
            self.telemetry_logger.log_request_lifecycle(
                request_text=request,
                intent_type=parsed_intent.intent.value,
                confidence=parsed_intent.confidence,
                parameters=parsed_intent.parameters,
                missing_fields=parsed_intent.missing_fields,
                validation_passed=True,
                route_chosen=parsed_intent.intent.value,
                outcome=OutcomeType.FAILURE,
                error_message=str(e)
            )
            return f"❌ Error executing intent '{parsed_intent.intent.value}': {str(e)}"
    
    def _log_telemetry_success(self, parsed: ParsedIntent, route: str, request_text: str = "") -> None:
        """Helper to log successful intent execution to telemetry."""
        self.telemetry_logger.log_request_lifecycle(
            request_text=request_text,
            intent_type=parsed.intent.value,
            confidence=parsed.confidence,
            parameters=parsed.parameters,
            missing_fields=[],
            validation_passed=True,
            route_chosen=route,
            outcome=OutcomeType.SUCCESS
        )
    
    # ── Intent Handlers (Structured Execution) ──
    
    def _task_decomposition_gate(self, title: str, description: str) -> Optional[str]:
        """Reject incomplete task definitions before mutating state."""
        normalized = (description or "").strip()
        if not normalized:
            return (
                f"⚠️ **Task Definition Incomplete for '{title or 'Untitled Task'}**\n\n"
                "To prevent assumptions, you must break down this task before I can create it.\n"
                "Provide a revised request that includes:\n"
                "1. Specific acceptance criteria.\n"
                "2. At least two concrete subtasks or dependencies.\n"
                "3. The exact files or modules affected."
            )

        description_lower = normalized.lower()
        has_criteria = any(term in description_lower for term in [
            "acceptance criteria",
            "acceptance",
            "criteria",
            "must",
            "expected result",
            "done when",
            "outcome",
        ])
        has_subtasks = any(term in description_lower for term in [
            "step 1",
            "step 2",
            "subtask",
            "subtasks",
            "dependency",
            "dependencies",
            "phase",
            "workflow",
            "1.",
            "2.",
            "then",
            "after",
        ])
        word_count = len(re.findall(r"\b\w+\b", normalized))

        if word_count < 15 or not (has_criteria and has_subtasks):
            return (
                f"⚠️ **Task Definition Incomplete for '{title or 'Untitled Task'}**\n\n"
                "To prevent assumptions, you must break down this task before I can create it.\n"
                "Respond with a revised request that explicitly includes:\n"
                "1. Specific acceptance criteria.\n"
                "2. At least two concrete subtasks or dependencies.\n"
                "3. The exact files or modules affected."
            )
        return None

    def _handle_create_task(self, parsed: ParsedIntent, session_id: str, request: str = "") -> str:
        """Handle task creation with extracted parameters."""
        title = parsed.parameters.get("title", "").strip()
        if not title:
            return "❓ I need a task title to create a task. What should I create?"

        description = str(parsed.parameters.get("description", "") or "").strip()
        gate_message = self._task_decomposition_gate(title, description)
        if gate_message:
            self._log_telemetry_success(parsed, "create_task_rejected_hallucination", request)
            return gate_message

        priority = parsed.parameters.get("priority", "p1")
        tags = parsed.parameters.get("tags", []) or []
        actor = "llm_agent"

        if getattr(self, "engine", None) is not None:
            task_id = self.engine.start(
                title=title,
                priority_raw=priority,
                tags=tags,
                description=description,
                session_id=session_id,
                actor=actor,
            )
        else:
            task_id = f"T-{uuid.uuid4().hex[:6].upper()}"

        if getattr(self, "memory_store", None) is not None:
            self.memory_store.set_field(task_id, "title", title, actor)
            self.memory_store.set_field(task_id, "description", description, actor)
            self.memory_store.set_field(task_id, "priority", priority, actor)
            self.memory_store.set_field(task_id, "status", "backlog", actor)
            if tags:
                self.memory_store.add_tags(task_id, tags, actor)

        self._log_activity("task_created", {
            "task_id": task_id,
            "intent": parsed.intent.value,
            "confidence": parsed.confidence
        })
        self._log_telemetry_success(parsed, "create_task", request)
        return f"✅ Created task {task_id}: {title} (Pending disk sync)"
    
    def _handle_get_next_task(self, parsed: ParsedIntent, session_id: str, request: str = "") -> str:
        """Handle next task retrieval."""
        task = self.engine.next_task(session_id=session_id)
        if task:
            self.engine.session_focus(task["id"], session_id=session_id)
            self._log_activity("task_focused", {"task_id": task["id"], "intent": parsed.intent.value})
            self._log_telemetry_success(parsed, "get_next_task", request)
            return f"🎯 Next task: {task['id']} - {task['title']} (Priority: {task['priority']}, Status: {task['status']})"
        self._log_telemetry_success(parsed, "get_next_task_empty", request)
        return "📭 No pending tasks. Good job!"
    
    def _handle_list_tasks(self, parsed: ParsedIntent, session_id: str, request: str = "") -> str:
        """Handle task listing."""
        tasks = self.engine.list_tasks()
        if not tasks:
            self._log_telemetry_success(parsed, "list_tasks_empty", request)
            return "📭 No tasks found."
        response = "📋 Current tasks:\n"
        for task in tasks[:10]:
            response += f"  • {task['id']}: {task['title']} ({task['status']}, {task['priority']})\n"
        if len(tasks) > 10:
            response += f"  ... and {len(tasks) - 10} more"
        self._log_activity("tasks_listed", {"count": len(tasks), "intent": parsed.intent.value})
        self._log_telemetry_success(parsed, "list_tasks", request)
        return response
    
    def _handle_complete_task(self, parsed: ParsedIntent, session_id: str, request: str = "") -> str:
        """Handle task completion."""
        task_id = parsed.parameters.get("task_id")
        if not task_id:
            return "❓ Which task? Please specify the task ID (e.g., T-0001)"

        actor = "llm_agent"
        if getattr(self, "memory_store", None) is not None:
            self.memory_store.set_field(task_id, "status", "archive", actor)
            self.memory_store.set_field(task_id, "completed", datetime.now(timezone.utc).isoformat(), actor)
        elif getattr(self, "engine", None) is not None:
            self.engine.move_task(task_id, "archive", session_id=session_id, actor=actor)

        self._log_activity("task_completed", {"task_id": task_id, "intent": parsed.intent.value})
        self._log_telemetry_success(parsed, "complete_task", request)
        return f"✅ Completed task {task_id} (Pending disk sync)"
    
    def _handle_get_status(self, parsed: ParsedIntent, session_id: str, request: str = "") -> str:
        """Handle status request."""
        context = self.engine.get_project_context()
        tasks = self.engine.list_tasks()
        
        response = f"📊 **Project Status**\n"
        response += f"📍 Branch: {context['branch']}\n"
        
        active_tasks = [t for t in tasks if t['status'] == 'active']
        if active_tasks:
            response += f"🔥 **Active ({len(active_tasks)}):**\n"
            for task in active_tasks[:3]:
                response += f"  • {task['id']}: {task['title']}\n"
        
        pending_tasks = [t for t in tasks if t['status'] in ['backlog', 'review']]
        if pending_tasks:
            response += f"📋 **Pending ({len(pending_tasks)}):**\n"
            for task in pending_tasks[:3]:
                response += f"  • {task['id']}: {task['title']}\n"
        
        self._log_activity("status_requested", {"intent": parsed.intent.value})
        self._log_telemetry_success(parsed, "get_status", request)
        return response
    
    def _handle_store_context(self, parsed: ParsedIntent, session_id: str, request: str = "") -> str:
        """Handle context storage."""
        content = parsed.parameters.get("content", "").strip()
        if not content:
            return "❓ What should I remember? Please provide content to store."
        
        key = self._generate_semantic_key(content)
        self.engine.working_memory_set(key, content, session_id, ttl_minutes=120)
        self.predictive_cache.set(f"context:{key}", content)
        
        self._log_activity("context_stored", {
            "key": key,
            "intent": parsed.intent.value,
            "confidence": parsed.confidence
        })
        self._log_telemetry_success(parsed, "store_context", request)
        return f"🧠 Remembered: {content[:50]}..."
    
    def _handle_get_context(self, parsed: ParsedIntent, session_id: str, request: str = "") -> str:
        """Handle context retrieval."""
        items = self.engine.working_memory_list(session_id)
        
        if not items:
            self._log_telemetry_success(parsed, "get_context_empty", request)
            return "🧠 Nothing remembered yet. Tell me what to remember!"
        
        response = "🧠 **What I remember:**\n"
        for item in items:
            response += f"  • {item['key']}: {item['value'][:80]}...\n"
        
        self._log_activity("context_retrieved", {"count": len(items), "intent": parsed.intent.value})
        self._log_telemetry_success(parsed, "get_context", request)
        return response
    
    def _handle_semantic_search(self, parsed: ParsedIntent, session_id: str, request: str = "") -> str:
        """Handle semantic search."""
        query = parsed.parameters.get("query", "")
        result = self.semantic_search.search(query)
        self._log_activity("semantic_search", {
            "query": query,
            "intent": parsed.intent.value,
            "confidence": parsed.confidence
        })
        self._log_telemetry_success(parsed, "semantic_search", request)
        return result
    
    def _handle_discover_patterns(self, parsed: ParsedIntent, session_id: str, request: str = "") -> str:
        """Handle pattern discovery."""
        result = self.semantic_search.discover_patterns()
        self._log_activity("patterns_discovered", {"intent": parsed.intent.value})
        self._log_telemetry_success(parsed, "discover_patterns", request)
        return result
    
    def _handle_summarize(self, parsed: ParsedIntent, session_id: str, request: str = "") -> str:
        """Handle session summarization."""
        recent_activity = [a for a in self._activity_log if a["type"] in ["task_created", "task_completed", "task_focused"]]
        
        summary = f"📝 **Session Summary**\n"
        summary += f"⏱️ Session duration: {self._get_session_duration()}\n"
        
        if recent_activity:
            summary += f"🎯 **Recent activity:**\n"
            for activity in recent_activity[-5:]:
                summary += f"  • {activity['type']}: {activity['details']}\n"
        
        memory_items = self.engine.working_memory_list(session_id)
        if memory_items:
            summary += f"🧠 **Key insights remembered:**\n"
            for item in memory_items:
                summary += f"  • {item['key']}\n"
        
        self.engine.session_checkpoint(
            note="Auto-generated summary",
            session_id=session_id,
            pending_decisions=[]
        )
        
        self._log_activity("session_summarized", {"intent": parsed.intent.value})
        self._log_telemetry_success(parsed, "summarize", request)
        return summary
    
    def _handle_help(self, parsed: ParsedIntent, session_id: str, request: str = "") -> str:
        """Handle help request."""
        self._log_activity("help_requested", {"intent": parsed.intent.value})
        self._log_telemetry_success(parsed, "help", request)
        return self._get_help()
    
    def _handle_unknown(self, parsed: ParsedIntent, session_id: str, original_request: str) -> str:
        """Handle unknown intent."""
        self._log_activity("unknown_intent", {
            "request": original_request,
            "confidence": parsed.confidence,
            "evidence": parsed.evidence
        })
        self._log_telemetry_success(parsed, "unknown", original_request)
        return f"🤔 I didn't understand '{original_request}'. Try asking for help with 'help' or rephrase your request."

    
    def _generate_semantic_key(self, content: str) -> str:
        """Generate a semantic key from content."""
        # Simple approach: use first few words
        words = content.split()[:3]
        return "_".join(words).lower()
    
    def _get_session_duration(self) -> str:
        """Get human-readable session duration."""
        if not self._session_start_time:
            return "Unknown"
        
        duration = datetime.now(timezone.utc) - self._session_start_time
        minutes = int(duration.total_seconds() / 60)
        
        if minutes < 1:
            return "Just started"
        elif minutes < 60:
            return f"{minutes} minutes"
        else:
            hours = minutes // 60
            return f"{hours}h {minutes % 60}m"
    
    def _get_help(self) -> str:
        """Provide helpful guidance."""
        return """
🤖 **Keeli LLM Interface** - Just tell me what you need!

**Task Management:**
• "Create a task to fix the authentication bug" 
• "What should I work on next?"
• "Show me all tasks"
• "Complete task T-0001"
• "What's the current status?"

**Context & Memory:**
• "Remember that the API endpoint is /api/v1/users"
• "What do you remember?"
• "Summarize what we've done"

**Semantic Search & Discovery:**
• "Search for authentication related tasks"
• "Find items related to user management"
• "Discover patterns in my work"
• "What concepts appear frequently?"

**Workflows (I'll guide you step-by-step):**
• "Implement a new feature" → I'll guide through development
• "Fix the authentication bug" → I'll guide through debugging
• "Review the code changes" → I'll guide through code review
• "Refactor the user module" → I'll guide through refactoring
• "Document the API" → I'll guide through documentation

**Workflow Commands:**
• "next" → Advance to next stage
• "status" → See current workflow progress
• "complete" → Finish workflow early
• "templates" → See available workflow types

**I automatically:**
• Manage your work session
• Detect workflows and guide you
• Track your activity
• Store important context
• Understand semantic relationships
• Suggest next steps

Just ask naturally!
"""
    
    # ── Smart Predictive Features ──
    
    def suggest_next_action(self) -> Optional[str]:
        """Suggest next action based on patterns."""
        # Check workflow status first
        if self.workflow_orchestrator._active_workflow:
            return f"Workflow in progress: {self.workflow_orchestrator._active_workflow.value.replace('_', ' ').title()}. Say 'next' to advance or 'status' for details."
        
        if not self._activity_log:
            return "Start by telling me what you'd like to work on, and I'll guide you through the optimal workflow."
        
        recent_activities = self._activity_log[-5:]
        activity_types = [a["type"] for a in recent_activities]
        
        # Pattern: just created a task -> suggest focusing on it
        if "task_created" in activity_types and "task_focused" not in activity_types:
            return "You just created a task. Would you like to focus on it or create another?"
        
        # Pattern: completed tasks -> suggest getting next task
        if "task_completed" in activity_types:
            return "Great progress! Would you like to see what's next?"
        
        # Pattern: lots of context storage -> suggest summarization
        context_stores = sum(1 for a in recent_activities if a["type"] == "context_stored")
        if context_stores >= 3:
            return "You've stored several insights. Would you like me to summarize what we've accomplished?"
        
        return None
    
    def get_context_digest(self, max_tokens: int = 2000) -> str:
        """Get optimized context digest for LLM consumption."""
        session_id = self._ensure_session("Context digest request")
        
        # Gather available context
        available_context = {}
        
        # Add task context
        tasks = self.engine.list_tasks()
        if tasks:
            task_summary = "Current tasks:\n" + "\n".join([
                f"- {t['id']}: {t['title']} ({t['status']}, {t['priority']})" 
                for t in tasks[:10]
            ])
            available_context["tasks"] = task_summary
        
        # Add working memory
        if session_id:
            memory_items = self.engine.working_memory_list(session_id)
            if memory_items:
                memory_summary = "Working memory:\n" + "\n".join([
                    f"- {item['key']}: {item['value'][:100]}..." 
                    for item in memory_items
                ])
                available_context["working_memory"] = memory_summary
        
        # Add project context
        project_context = self.engine.get_project_context()
        available_context["project"] = f"Project context: {json.dumps(project_context, indent=2)}"
        
        # Use intelligent context builder
        optimized_digest, metadata = self.context_builder.build_context_for_request(
            "context digest request",
            available_context
        )
        
        # Add metadata info
        digest = f"""# OPTIMIZED CONTEXT DIGEST
**Tokens:** {metadata['tokens']} / {max_tokens}
**Components:** {metadata['components']}/{metadata['total_available']}
**Quality Score:** {metadata['quality_score']:.2f}
**Compression:** {metadata['compression_ratio']:.2f}x

{optimized_digest}
"""
        
        # Add predictive suggestion
        suggestion = self.suggest_next_action()
        if suggestion:
            digest += f"\n\n💡 **Suggestion:** {suggestion}"
        
        return digest
    
    # ── Telemetry & Learning Loop ──
    
    def get_telemetry_stats(self, intent_type: Optional[str] = None) -> Dict[str, Any]:
        """Get telemetry statistics for v7.0 validation."""
        return self.telemetry_store.get_stats(intent_type)
    
    def get_confidence_calibration(self, intent_type: Optional[str] = None) -> Dict[str, Any]:
        """Get confidence calibration analysis."""
        return self.telemetry_store.get_confidence_calibration(intent_type)
    
    def get_intent_distribution(self) -> Dict[str, int]:
        """Get distribution of intents across all requests."""
        return self.telemetry_store.get_intent_distribution()
    
    def export_telemetry(self, output_path: Path, intent_type: Optional[str] = None) -> None:
        """Export telemetry events to JSON for analysis."""
        self.telemetry_store.export_to_json(output_path, intent_type)
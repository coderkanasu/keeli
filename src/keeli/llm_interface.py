"""
Keeli v7.0 - LLM-Centric Unified Interface

This module provides a simplified, natural language interface designed specifically
for LLM workflows. It eliminates the complexity of multiple tools and parameters
by providing intelligent defaults and automatic session management.

Core Philosophy: "I understand how you work, let me help automatically"
"""

import re
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from keeli.engine import KeeliEngine
from keeli.workflow_orchestrator import WorkflowOrchestrator, WorkflowType
from keeli.memory_crdt import MemoryCRDTStore, PredictiveCache
from keeli.semantic_search import SemanticSearchInterface
from keeli.workflow_templates import WorkflowTemplateLibrary
from keeli.context_optimizer import IntelligentContextBuilder


class LLMInterface:
    """
    Unified LLM-friendly interface that handles complexity automatically.
    
    This class provides a single entry point for all Keeli operations with:
    - Automatic session management
    - Intelligent defaults
    - Natural language processing
    - Context-aware responses
    - Roundtrip reduction
    """
    
    def __init__(self, root_dir: Optional[Path] = None):
        self.engine = KeeliEngine(root_dir)
        self._auto_session_id: Optional[str] = None
        self._session_start_time: Optional[datetime] = None
        self._activity_log: List[Dict[str, Any]] = []
        self._context_cache: Dict[str, Any] = {}
        self.workflow_orchestrator = WorkflowOrchestrator(self)
        
        # New v7.0 components
        self.memory_store = MemoryCRDTStore(sync_interval_seconds=30)
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
    
    # ── Natural Language Processing ──
    
    def _parse_intent(self, natural_request: str) -> Dict[str, Any]:
        """Parse natural language request into structured intent."""
        request_lower = natural_request.lower().strip()
        
        # Task-related intents
        if any(word in request_lower for word in ["create", "add", "new", "make"]):
            return {"intent": "create_task", "confidence": 0.9}
        
        if any(word in request_lower for word in ["next", "what's next", "what should i"]):
            return {"intent": "get_next_task", "confidence": 0.95}
        
        if any(word in request_lower for word in ["show", "list", "what are", "tell me"]):
            return {"intent": "list_tasks", "confidence": 0.85}
        
        if any(word in request_lower for word in ["complete", "done", "finish", "archive"]):
            return {"intent": "complete_task", "confidence": 0.9}
        
        if any(word in request_lower for word in ["status", "progress", "how's"]):
            return {"intent": "get_status", "confidence": 0.85}
        
        # Context-related intents
        if any(word in request_lower for word in ["remember", "save", "store", "cache"]):
            return {"intent": "store_context", "confidence": 0.9}
        
        if any(word in request_lower for word in ["recall", "get", "retrieve", "what did"]):
            return {"intent": "get_context", "confidence": 0.85}
        
        # Search-related intents
        if any(word in request_lower for word in ["search", "find", "look for", "related to", "similar"]):
            return {"intent": "semantic_search", "confidence": 0.9}
        
        if any(word in request_lower for word in ["patterns", "discover", "analyze", "insights"]):
            return {"intent": "discover_patterns", "confidence": 0.85}
        
        if any(word in request_lower for word in ["summarize", "summary", "wrap up"]):
            return {"intent": "summarize", "confidence": 0.95}
        
        # Default to general help
        return {"intent": "help", "confidence": 0.5}
    
    def _extract_task_details(self, natural_request: str) -> Dict[str, Any]:
        """Extract task details from natural language."""
        details = {"title": "", "priority": "p1", "tags": [], "description": ""}
        
        # Extract priority
        if "urgent" in natural_request.lower() or "critical" in natural_request.lower():
            details["priority"] = "p0"
        elif "important" in natural_request.lower():
            details["priority"] = "p1"
        elif "low" in natural_request.lower() or "minor" in natural_request.lower():
            details["priority"] = "p2"
        
        # Extract title (remove common task-related words)
        title = natural_request
        for word in ["create", "add", "new", "task", "make", "urgent", "critical", "important", "low", "minor"]:
            title = re.sub(rf"\b{word}\b", "", title, flags=re.IGNORECASE)
        details["title"] = title.strip() or "Untitled Task"
        
        # Extract description (anything after "because" or "to")
        if "because" in natural_request.lower():
            parts = natural_request.lower().split("because")
            if len(parts) > 1:
                details["description"] = parts[1].strip()
        elif "to" in natural_request.lower():
            parts = natural_request.lower().split("to", 1)
            if len(parts) > 1:
                details["description"] = "To " + parts[1].strip()
        
        return details
    
    # ── Unified Public Interface ──
    
    def ask(self, request: str) -> str:
        """
        Main entry point - natural language interface.
        
        This is the primary method LLMs should use. It automatically:
        - Manages sessions
        - Parses intent
        - Detects workflows
        - Executes appropriate actions
        - Provides context-aware responses
        """
        session_id = self._ensure_session(f"Natural language request: {request[:50]}")
        intent = self._parse_intent(request)
        
        # Check for workflow triggers
        workflow_type = self.workflow_orchestrator.detect_workflow(request)
        if workflow_type and not self.workflow_orchestrator._active_workflow:
            # First, check if there's a matching template
            matching_template = self.template_library.find_matching_template(request)
            if matching_template:
                template_info = self.template_library.format_template_for_display(matching_template)
                workflow_start = self.workflow_orchestrator.start_workflow(workflow_type, request)
                return f"{workflow_start}\n\n📋 **Suggested Template:**\n{template_info}"
            return self.workflow_orchestrator.start_workflow(workflow_type, request)
        
        # Handle workflow continuation
        if self.workflow_orchestrator._active_workflow:
            if "next" in request.lower() or "continue" in request.lower():
                return self.workflow_orchestrator.advance_stage()
            elif "complete" in request.lower() or "finish" in request.lower():
                return self.workflow_orchestrator._complete_workflow()
            elif "status" in request.lower() or "where" in request.lower():
                return self.workflow_orchestrator.get_workflow_status()
            elif "templates" in request.lower() or "workflows" in request.lower():
                return self.workflow_orchestrator.get_workflow_templates()
        
        try:
            if intent["intent"] == "create_task":
                details = self._extract_task_details(request)
                task_id = self.engine.start(
                    title=details["title"],
                    priority_raw=details["priority"],
                    description=details["description"],
                    session_id=session_id
                )
                self._log_activity("task_created", {"task_id": task_id, "request": request})
                return f"✅ Created task {task_id}: {details['title']}"
            
            elif intent["intent"] == "get_next_task":
                task = self.engine.next_task(session_id=session_id)
                if task:
                    # Auto-focus on this task
                    self.engine.session_focus(task["id"], session_id=session_id)
                    self._log_activity("task_focused", {"task_id": task["id"]})
                    return f"🎯 Next task: {task['id']} - {task['title']} (Priority: {task['priority']}, Status: {task['status']})"
                return "📭 No pending tasks. Good job!"
            
            elif intent["intent"] == "list_tasks":
                tasks = self.engine.list_tasks()
                if not tasks:
                    return "📭 No tasks found."
                response = "📋 Current tasks:\n"
                for task in tasks[:10]:  # Limit to 10 for brevity
                    response += f"  • {task['id']}: {task['title']} ({task['status']}, {task['priority']})\n"
                if len(tasks) > 10:
                    response += f"  ... and {len(tasks) - 10} more"
                return response
            
            elif intent["intent"] == "complete_task":
                # Try to extract task ID from request
                task_match = re.search(r'[Tt]-?\d+', request)
                if task_match:
                    task_id = task_match.group(0).upper()
                    if not task_id.startswith("T-"):
                        task_id = f"T-{task_id[2:]}"
                    self.engine.move_task(task_id, "archive", session_id=session_id)
                    self._log_activity("task_completed", {"task_id": task_id})
                    return f"✅ Completed task {task_id}"
                return "❓ Which task? Please specify the task ID (e.g., T-0001)"
            
            elif intent["intent"] == "get_status":
                return self._get_smart_status(session_id)
            
            elif intent["intent"] == "store_context":
                return self._smart_store_context(request, session_id)
            
            elif intent["intent"] == "get_context":
                return self._smart_get_context(request, session_id)
            
            elif intent["intent"] == "summarize":
                return self._auto_summarize(session_id)
            
            elif intent["intent"] == "semantic_search":
                return self.semantic_search.search(request)
            
            elif intent["intent"] == "discover_patterns":
                return self.semantic_search.discover_patterns()
            
            else:  # help
                return self._get_help()
        
        except Exception as e:
            return f"❌ Error: {str(e)}. Try rephrasing your request."
    
    def _get_smart_status(self, session_id: str) -> str:
        """Provide intelligent status overview."""
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
        
        return response
    
    def _smart_store_context(self, request: str, session_id: str) -> str:
        """Intelligently store context based on request."""
        # Extract what to remember
        content = request.replace("remember", "").replace("save", "").replace("store", "").strip()
        
        # Generate a semantic key
        key = self._generate_semantic_key(content)
        
        # Store in both engine working memory and predictive cache
        self.engine.working_memory_set(key, content, session_id, ttl_minutes=120)
        self.predictive_cache.set(f"context:{key}", content)
        
        self._log_activity("context_stored", {"key": key})
        return f"🧠 Remembered: {content[:50]}..."
    
    def _smart_get_context(self, request: str, session_id: str) -> str:
        """Intelligently retrieve context based on request."""
        # Check predictive cache first
        search_key = request.lower().replace("what do you remember about ", "").replace("?", "").strip()
        cache_key = f"context:{search_key}"
        cached_result = self.predictive_cache.get(cache_key)
        
        if cached_result:
            return f"🧠 **From cache:** {cached_result}"
        
        # Fall back to working memory
        items = self.engine.working_memory_list(session_id)
        
        if not items:
            return "🧠 Nothing remembered yet. Tell me what to remember!"
        
        response = "🧠 **What I remember:**\n"
        for item in items:
            response += f"  • {item['key']}: {item['value'][:80]}...\n"
        
        return response
    
    def _auto_summarize(self, session_id: str) -> str:
        """Automatically generate session summary."""
        # Get session activity
        recent_activity = [a for a in self._activity_log if a["type"] in ["task_created", "task_completed", "task_focused"]]
        
        summary = f"📝 **Session Summary**\n"
        summary += f"⏱️ Session duration: {self._get_session_duration()}\n"
        
        if recent_activity:
            summary += f"🎯 **Recent activity:**\n"
            for activity in recent_activity[-5:]:
                summary += f"  • {activity['type']}: {activity['details']}\n"
        
        # Get working memory
        memory_items = self.engine.working_memory_list(session_id)
        if memory_items:
            summary += f"🧠 **Key insights remembered:**\n"
            for item in memory_items:
                summary += f"  • {item['key']}\n"
        
        # Auto-save as checkpoint
        self.engine.session_checkpoint(
            note="Auto-generated summary",
            session_id=session_id,
            pending_decisions=[]
        )
        
        return summary
    
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
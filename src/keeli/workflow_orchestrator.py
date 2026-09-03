"""
Keeli v7.0 - Workflow Orchestrator

This module provides intelligent workflow orchestration for common LLM tasks.
It guides LLMs through optimal patterns rather than providing raw tools.

Core Philosophy: "I know the best way to do this, let me guide you"
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from keeli.llm_interface import LLMInterface


class WorkflowType(Enum):
    """Common LLM workflow types."""
    FEATURE_DEVELOPMENT = "feature_development"
    BUG_FIXING = "bug_fixing"
    CODE_REVIEW = "code_review"
    REFACTORING = "refactoring"
    DOCUMENTATION = "documentation"
    DEBUGGING = "debugging"
    TESTING = "testing"
    PLANNING = "planning"


class WorkflowStage(Enum):
    """Stages in a workflow."""
    CONTEXT_GATHERING = "context_gathering"
    ANALYSIS = "analysis"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    DOCUMENTATION = "documentation"
    COMPLETION = "completion"


class WorkflowOrchestrator:
    """
    Intelligent workflow orchestration that guides LLMs through optimal patterns.
    """
    
    def __init__(self, interface: LLMInterface):
        self.interface = interface
        self._active_workflow: Optional[WorkflowType] = None
        self._current_stage: Optional[WorkflowStage] = None
        self._workflow_context: Dict[str, Any] = {}
        self._stage_history: List[Dict[str, Any]] = []
        
    # ── Workflow Detection ──
    
    def detect_workflow(self, natural_request: str) -> Optional[WorkflowType]:
        """Detect the type of workflow from natural language."""
        request_lower = natural_request.lower()
        
        # Feature development patterns
        if any(word in request_lower for word in ["implement", "add feature", "build", "create functionality"]):
            return WorkflowType.FEATURE_DEVELOPMENT
        
        # Bug fixing patterns
        if any(word in request_lower for word in ["fix", "bug", "error", "issue", "problem"]):
            return WorkflowType.BUG_FIXING
        
        # Code review patterns
        if any(word in request_lower for word in ["review", "check", "audit", "examine"]):
            return WorkflowType.CODE_REVIEW
        
        # Refactoring patterns
        if any(word in request_lower for word in ["refactor", "clean up", "improve", "optimize"]):
            return WorkflowType.REFACTORING
        
        # Documentation patterns
        if any(word in request_lower for word in ["document", "write docs", "explain", "readme"]):
            return WorkflowType.DOCUMENTATION
        
        # Debugging patterns
        if any(word in request_lower for word in ["debug", "investigate", "troubleshoot", "why"]):
            return WorkflowType.DEBUGGING
        
        # Testing patterns
        if any(word in request_lower for word in ["test", "coverage", "spec", "verify"]):
            return WorkflowType.TESTING
        
        # Planning patterns
        if any(word in request_lower for word in ["plan", "design", "architecture", "structure"]):
            return WorkflowType.PLANNING
        
        return None
    
    # ── Workflow Execution ──
    
    def start_workflow(self, workflow_type: WorkflowType, context: str = "") -> str:
        """Start a guided workflow with step-by-step guidance."""
        self._active_workflow = workflow_type
        self._current_stage = WorkflowStage.CONTEXT_GATHERING
        self._workflow_context = {"initial_request": context, "start_time": datetime.now(timezone.utc).isoformat()}
        
        guidance = self._get_workflow_guidance(workflow_type, WorkflowStage.CONTEXT_GATHERING)
        self._record_stage_transition(WorkflowStage.CONTEXT_GATHERING, guidance)
        
        return f"🎯 **Starting {workflow_type.value.replace('_', ' ').title()} Workflow**\n\n{guidance}"
    
    def advance_stage(self, user_input: str = "") -> str:
        """Advance to the next stage in the workflow."""
        if not self._active_workflow:
            return "No active workflow. Start one with a clear request like 'implement X' or 'fix Y bug'."
        
        next_stage = self._get_next_stage(self._current_stage)
        if not next_stage:
            return self._complete_workflow()
        
        self._current_stage = next_stage
        guidance = self._get_workflow_guidance(self._active_workflow, next_stage)
        self._record_stage_transition(next_stage, guidance)
        
        return f"📍 **Stage: {next_stage.value.replace('_', ' ').title()}**\n\n{guidance}"
    
    def _get_next_stage(self, current_stage: WorkflowStage) -> Optional[WorkflowStage]:
        """Get the next stage in the workflow sequence."""
        stage_order = [
            WorkflowStage.CONTEXT_GATHERING,
            WorkflowStage.ANALYSIS,
            WorkflowStage.IMPLEMENTATION,
            WorkflowStage.VALIDATION,
            WorkflowStage.DOCUMENTATION,
            WorkflowStage.COMPLETION
        ]
        
        try:
            current_index = stage_order.index(current_stage)
            if current_index < len(stage_order) - 1:
                return stage_order[current_index + 1]
        except ValueError:
            pass
        
        return None
    
    def _get_workflow_guidance(self, workflow_type: WorkflowType, stage: WorkflowStage) -> str:
        """Get specific guidance for a workflow type and stage."""
        guidance_map = {
            WorkflowType.FEATURE_DEVELOPMENT: self._feature_development_guidance,
            WorkflowType.BUG_FIXING: self._bug_fixing_guidance,
            WorkflowType.CODE_REVIEW: self._code_review_guidance,
            WorkflowType.REFACTORING: self._refactoring_guidance,
            WorkflowType.DOCUMENTATION: self._documentation_guidance,
            WorkflowType.DEBUGGING: self._debugging_guidance,
            WorkflowType.TESTING: self._testing_guidance,
            WorkflowType.PLANNING: self._planning_guidance,
        }
        
        guidance_func = guidance_map.get(workflow_type, self._default_guidance)
        return guidance_func(stage)
    
    # ── Specific Workflow Guidances ──
    
    def _feature_development_guidance(self, stage: WorkflowStage) -> str:
        guidance = {
            WorkflowStage.CONTEXT_GATHERING: """
**Step 1: Gather Context**
• Ask me to show relevant tasks and current project status
• Review existing code related to the feature
• Check for similar implementations in the codebase
• Identify dependencies and integration points

*Say "show context" or "what's related" to proceed.*
""",
            WorkflowStage.ANALYSIS: """
**Step 2: Analyze Requirements**
• Break down the feature into smaller components
• Identify edge cases and error conditions
• Consider performance and security implications
• Plan the implementation approach

*Say "analyze" or "break it down" when ready.*
""",
            WorkflowStage.IMPLEMENTATION: """
**Step 3: Implement Feature**
• Start with the core functionality
• Write clean, maintainable code
• Follow existing code patterns and conventions
• Add appropriate error handling

*Say "implement" or "start coding" to begin.*
""",
            WorkflowStage.VALIDATION: """
**Step 4: Validate Implementation**
• Test the feature thoroughly
• Check for edge cases
• Verify integration with existing code
• Ensure no regressions

*Say "validate" or "test it" when ready.*
""",
            WorkflowStage.DOCUMENTATION: """
**Step 5: Document Changes**
• Update relevant documentation
• Add code comments where needed
• Update README or API docs
• Record lessons learned

*Say "document" to complete documentation.*
""",
            WorkflowStage.COMPLETION: """
**Step 6: Complete Feature**
• Mark the task as complete
• Summarize what was accomplished
• Identify any follow-up work
• Clean up temporary files or notes

*Say "complete" to finish this workflow.*
"""
        }
        return guidance.get(stage, "")
    
    def _bug_fixing_guidance(self, stage: WorkflowStage) -> str:
        guidance = {
            WorkflowStage.CONTEXT_GATHERING: """
**Step 1: Baseline the Problem (Evidence First)**
• Reproduce with one deterministic check and capture before-state metrics
• Save baseline snapshot in session memory (`keeli_memory set`)
• Start/confirm scoped session and branch context (`keeli_sessions start`, `keeli_context digest`)
• Define expected vs actual outcome in one measurable sentence

*Say "show context" to proceed with baseline evidence.*
""",
            WorkflowStage.ANALYSIS: """
**Step 2: Isolate Root Cause**
• Drill from aggregate symptoms into specific defective records/inputs
• Validate each hypothesis with direct evidence (queries, logs, traces)
• Record key findings as working memory for cross-model continuity
• Prefer minimal-scope root cause over broad speculative rewrites

*Say "analyze" when root-cause evidence is concrete.*
""",
            WorkflowStage.IMPLEMENTATION: """
**Step 3: Apply Minimal Patch**
• Update only the defective state/logic required to resolve the issue
• Log per-item mutation outcomes and decisions
• Checkpoint immediately after mutation (`keeli_sessions checkpoint`)
• Add a regression test or invariant check when feasible

*Say "implement" to apply and checkpoint the patch.*
""",
            WorkflowStage.VALIDATION: """
**Step 4: Re-Verify End-to-End**
• Re-run the original baseline check and compare before/after metrics
• Validate downstream outputs or consumers, not just the local fix path
• Confirm zero remaining unknown/missing/error states for this defect class
• Run relevant tests to guard against regressions

*Say "validate" to prove the fix is complete.*
""",
            WorkflowStage.DOCUMENTATION: """
**Step 5: Instrument and Document Prevention**
• Add warning/monitoring hooks for recurrence signals
• Update runbook with checker command, defect signature, and fix pattern
• Save durable insight to project knowledge (`keeli_knowledge save`)
• Document what changed in behavior and why

*Say "document" to store prevention guidance.*
""",
            WorkflowStage.COMPLETION: """
**Step 6: Close with State Integrity**
• Mark the task complete only after evidence is stored
• Summarize baseline, patch, and verified outcome in one closure note
• Capture any follow-up tasks discovered during remediation
• Keep session state clean for handoff across Devin/Claude/GPT

*Say "complete" to finalize the remediation loop.*
"""
        }
        return guidance.get(stage, "")
    
    def _code_review_guidance(self, stage: WorkflowStage) -> str:
        guidance = {
            WorkflowStage.CONTEXT_GATHERING: """
**Step 1: Review Context**
• Ask me to show the code to review
• Understand the purpose of the changes
• Check related files and dependencies
• Review the task or PR description

*Say "show context" to begin.*
""",
            WorkflowStage.ANALYSIS: """
**Step 2: Analyze Code Quality**
• Check for bugs and logic errors
• Review code style and conventions
• Assess performance implications
• Consider security and edge cases

*Say "analyze" to examine the code.*
""",
            WorkflowStage.IMPLEMENTATION: """
**Step 3: Provide Feedback**
• Give specific, actionable feedback
• Suggest improvements with examples
• Highlight both strengths and weaknesses
• Prioritize issues by severity

*Say "feedback" to provide review comments.*
""",
            WorkflowStage.VALIDATION: """
**Step 4: Validate Changes**
• Confirm suggested changes are correct
• Verify the code works as expected
• Check that feedback is clear
• Ensure no new issues introduced

*Say "validate" to confirm feedback.*
""",
            WorkflowStage.DOCUMENTATION: """
**Step 5: Document Review**
• Summarize key findings
• Document approved changes
• Note any unresolved issues
• Record review outcome

*Say "document" to complete.*
""",
            WorkflowStage.COMPLETION: """
**Step 6: Complete Review**
• Mark the review as complete
• Provide overall assessment
• Follow up on any action items
• Archive review materials

*Say "complete" to finish.*
"""
        }
        return guidance.get(stage, "")
    
    def _refactoring_guidance(self, stage: WorkflowStage) -> str:
        return f"""
**Refactoring - {stage.value.replace('_', ' ').title()}**
• Start with understanding current code structure
• Identify improvement opportunities
• Make small, incremental changes
• Test thoroughly after each change
• Ensure no behavior changes

*Say "next" to proceed to the next stage.*
"""
    
    def _documentation_guidance(self, stage: WorkflowStage) -> str:
        return f"""
**Documentation - {stage.value.replace('_', ' ').title()}**
• Understand the audience and purpose
• Gather necessary information
• Write clear, concise documentation
• Include examples and use cases
• Review and refine

*Say "next" to proceed.*
"""
    
    def _debugging_guidance(self, stage: WorkflowStage) -> str:
        return f"""
**Debugging - {stage.value.replace('_', ' ').title()}**
• Reproduce the issue consistently
• Gather relevant logs and context
• Formulate hypotheses about root cause
• Test hypotheses systematically
• Implement and verify fix

*Say "next" to proceed.*
"""
    
    def _testing_guidance(self, stage: WorkflowStage) -> str:
        return f"""
**Testing - {stage.value.replace('_', ' ').title()}**
• Understand what needs testing
• Design comprehensive test cases
• Implement tests systematically
• Run and analyze results
• Document coverage and gaps

*Say "next" to proceed.*
"""
    
    def _planning_guidance(self, stage: WorkflowStage) -> str:
        return f"""
**Planning - {stage.value.replace('_', ' ').title()}**
• Define clear objectives
• Research and gather requirements
• Create detailed implementation plan
• Identify risks and dependencies
• Set milestones and success criteria

*Say "next" to proceed.*
"""
    
    def _default_guidance(self, stage: WorkflowStage) -> str:
        return f"""
**Workflow Stage: {stage.value.replace('_', ' ').title()}**
• Proceed systematically through this stage
• Ask for clarification if needed
• Document important decisions
• Validate assumptions before proceeding

*Say "next" to advance to the next stage.*
"""
    
    def _record_stage_transition(self, stage: WorkflowStage, guidance: str) -> None:
        """Record a stage transition for history and learning."""
        self._stage_history.append({
            "stage": stage.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "guidance": guidance[:200],  # Store truncated guidance
            "workflow_type": self._active_workflow.value if self._active_workflow else None
        })
    
    def _complete_workflow(self) -> str:
        """Complete the current workflow and provide summary."""
        if not self._active_workflow:
            return "No active workflow to complete."
        
        workflow_type = self._active_workflow
        duration = self._get_workflow_duration()
        
        summary = f"""
🎉 **Workflow Complete: {workflow_type.value.replace('_', ' ').title()}**

**Duration:** {duration}
**Stages Completed:** {len(self._stage_history)}

**Summary:**
You've successfully completed the {workflow_type.value.replace('_', ' ').title()} workflow.
Key stages were executed with guidance at each step.

**Next Steps:**
• Consider creating follow-up tasks if needed
• Document any lessons learned
• Share results with team if applicable

*Start a new workflow anytime by asking for help with a new task.*
"""
        
        # Reset workflow state
        self._active_workflow = None
        self._current_stage = None
        self._workflow_context = {}
        
        return summary
    
    def _get_workflow_duration(self) -> str:
        """Get human-readable workflow duration."""
        if not self._stage_history:
            return "Unknown"
        
        start_time = self._workflow_context.get("start_time")
        if not start_time:
            return "Unknown"
        
        start = datetime.fromisoformat(start_time)
        duration = datetime.now(timezone.utc) - start
        minutes = int(duration.total_seconds() / 60)
        
        if minutes < 1:
            return "Less than a minute"
        elif minutes < 60:
            return f"{minutes} minutes"
        else:
            hours = minutes // 60
            return f"{hours}h {minutes % 60}m"
    
    def get_workflow_status(self) -> str:
        """Get current workflow status."""
        if not self._active_workflow:
            return "No active workflow. Start one with a clear request."
        
        return f"""
📍 **Current Workflow:** {self._active_workflow.value.replace('_', ' ').title()}
📍 **Current Stage:** {self._current_stage.value.replace('_', ' ').title()}
📍 **Progress:** {len(self._stage_history)} stages completed

*Say "next" to advance to the next stage, or "complete" to finish early.*
"""
    
    def get_workflow_templates(self) -> str:
        """Get available workflow templates."""
        templates = """
📋 **Available Workflow Templates:**

**1. Feature Development**
• "Implement a new feature"
• "Add X functionality"
• "Build Y component"

**2. Bug Fixing**
• "Fix the authentication bug"
• "Resolve the error in module X"
• "Debug the issue with Y"

**3. Code Review**
• "Review the changes in PR #123"
• "Check the code for issues"
• "Audit the implementation"

**4. Refactoring**
• "Refactor the user module"
• "Clean up the authentication code"
• "Improve the database queries"

**5. Documentation**
• "Document the API"
• "Write README for X"
• "Explain how Y works"

**6. Debugging**
• "Debug why X fails"
• "Investigate the performance issue"
• "Troubleshoot the error"

**7. Testing**
• "Test the new feature"
• "Add test coverage for X"
• "Verify the implementation"

**8. Planning**
• "Plan the implementation of X"
• "Design the architecture for Y"
• "Structure the approach"

*Simply describe what you want to do, and I'll guide you through the optimal workflow.*
"""
        return templates
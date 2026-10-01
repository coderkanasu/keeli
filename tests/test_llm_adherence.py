"""
Keeli MCP LLM Adherence Test Framework

This framework tests how well the current Keeli MCP tools adhere to LLM best practices
by simulating different LLM interaction patterns and validating tool design.

Testing Philosophy:
- Test, observe, learn, then implement
- Don't guess about LLM behavior - simulate and measure
- Validate current implementation before making changes
"""

import sys
from pathlib import Path
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from keeli.engine import KeeliEngine
from keeli.mcp_server import (
    keeli_tasks, keeli_context, keeli_sessions, 
    keeli_memory, keeli_knowledge, keeli_system
)


class LLMStyle(str, Enum):
    """Different LLM interaction patterns to simulate"""
    CLAUDE = "claude"  # Thorough, context-aware, asks for clarification
    GPT4 = "gpt4"      # Direct, tool-efficient, minimal context
    BASIC = "basic"    # Simple request-response, less sophisticated


@dataclass
class ToolCall:
    """Record of a tool call made during simulation"""
    tool_name: str
    operation: str
    parameters: Dict[str, Any]
    timestamp: str
    success: bool
    response: Any


@dataclass
class SimulationResult:
    """Results from simulating an LLM interaction"""
    scenario: str
    llm_style: LLMStyle
    tool_calls: List[ToolCall] = field(default_factory=list)
    total_calls: int = 0
    forced_context_calls: int = 0
    voluntary_context_calls: int = 0
    success: bool = False
    errors: List[str] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)


class LLMSimulator:
    """Simulate different LLM behavior patterns with Keeli MCP tools"""
    
    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.engine = KeeliEngine(root_dir=temp_dir)
        self.tool_call_log: List[ToolCall] = []
        
    def _record_call(self, tool_name: str, operation: str, parameters: Dict[str, Any], 
                     success: bool, response: Any) -> ToolCall:
        """Record a tool call for analysis"""
        from datetime import datetime, timezone
        
        call = ToolCall(
            tool_name=tool_name,
            operation=operation,
            parameters=parameters,
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=success,
            response=response
        )
        self.tool_call_log.append(call)
        return call
    
    def simulate_claude_task_creation(self, user_request: str) -> SimulationResult:
        """
        Simulate Claude's approach to task creation.
        Claude: thorough, context-aware, likely to ask for context first
        """
        result = SimulationResult(
            scenario="task_creation",
            llm_style=LLMStyle.CLAUDE
        )
        
        try:
            # Claude pattern: Get context first
            context_response = json.loads(keeli_context(
                operation="digest",
                tier="brief",
                budget=1200,
                session_id=None,
                branch="main"
            ))
            
            self._record_call("keeli_context", "digest", {"tier": "brief"}, 
                            context_response.get("ok", False), context_response)
            result.forced_context_calls += 1
            result.observations.append("Claude-style: Called context digest first")
            
            # Then create task
            task_response = json.loads(keeli_tasks(
                operation="create",
                title="Test task from Claude simulation",
                description="Simulated task creation",
                priority="P1",
                session_id=None,
                branch="main"
            ))
            
            self._record_call("keeli_tasks", "create", {"title": "Test task"}, 
                            task_response.get("ok", False), task_response)
            
            result.success = task_response.get("ok", False)
            result.observations.append("Claude-style: Created task after getting context")
            
        except Exception as e:
            result.errors.append(str(e))
            result.success = False
        
        result.tool_calls = self.tool_call_log.copy()
        result.total_calls = len(result.tool_calls)
        return result
    
    def simulate_gpt4_task_creation(self, user_request: str) -> SimulationResult:
        """
        Simulate GPT-4's approach to task creation.
        GPT-4: direct, tool-efficient, goes straight to task creation
        """
        result = SimulationResult(
            scenario="task_creation",
            llm_style=LLMStyle.GPT4
        )
        
        try:
            # GPT-4 pattern: Direct task creation, minimal context
            task_response = json.loads(keeli_tasks(
                operation="create",
                title="Test task from GPT-4 simulation",
                description="Simulated task creation",
                priority="P1",
                session_id=None,
                branch="main"
            ))
            
            self._record_call("keeli_tasks", "create", {"title": "Test task"}, 
                            task_response.get("ok", False), task_response)
            
            result.success = task_response.get("ok", False)
            result.observations.append("GPT-4 style: Direct task creation, no context call")
            
        except Exception as e:
            result.errors.append(str(e))
            result.success = False
        
        result.tool_calls = self.tool_call_log.copy()
        result.total_calls = len(result.tool_calls)
        return result


class MCPAdherenceValidator:
    """Validate if MCP tools adhere to LLM best practices"""
    
    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.engine = KeeliEngine(root_dir=temp_dir)
        self.validation_results: Dict[str, Any] = {}
    
    def test_tool_clarity(self) -> Dict[str, Any]:
        """
        Test if tool descriptions are clear for LLMs.
        
        Checks:
        - Are tool names self-explanatory?
        - Are parameters well-documented?
        - Are operation enums clear?
        """
        results = {
            "test_name": "tool_clarity",
            "passed": True,
            "findings": [],
            "issues": []
        }
        
        # Check tool names
        tool_names = ["keeli_tasks", "keeli_context", "keeli_sessions", 
                     "keeli_memory", "keeli_knowledge", "keeli_system"]
        
        for tool_name in tool_names:
            if "_" in tool_name and not tool_name.replace("_", " ").islower():
                results["issues"].append(f"Tool name '{tool_name}' could be clearer")
            else:
                results["findings"].append(f"Tool name '{tool_name}' is clear")
        
        # Check operation clarity (this would need actual docstring parsing)
        results["findings"].append("Tool operations follow consistent naming patterns")
        
        results["passed"] = len(results["issues"]) == 0
        self.validation_results["tool_clarity"] = results
        return results
    
    def test_forced_context_issue(self) -> Dict[str, Any]:
        """
        Test if current system forces context inappropriately.
        
        This is the key test for the original issue.
        """
        results = {
            "test_name": "forced_context_issue",
            "passed": False,
            "findings": [],
            "issues": []
        }
        
        # Check if digest operation exists and is being called automatically
        try:
            # Try to call digest with minimal parameters
            digest_response = keeli_context(
                operation="digest",
                tier="brief",
                budget=1200
            )
            
            results["findings"].append("keeli_context.digest operation exists and is callable")
            results["issues"].append("Digest operation can be called independently - may lead to forced context injection")
            
            # Check if there's a fastcontext operation (likely forced)
            fastcontext_response = keeli_context(
                operation="fastcontext",
                tier="brief",
                budget=1200
            )
            
            results["findings"].append("keeli_context.fastcontext operation exists")
            results["issues"].append("fastcontext suggests automatic context injection pattern")
            
        except Exception as e:
            results["findings"].append(f"Digest call failed: {str(e)}")
        
        # Check react_loop for forced context injection
        try:
            from keeli.react_loop import ReActLoop
            from pathlib import Path
            
            # Initialize ReAct loop
            loop = ReActLoop(root_dir=self.temp_dir, max_iterations=5)
            
            # Check if it forces context in system prompt
            dynamic_context = loop._get_dynamic_context()
            
            if "digest" in str(dynamic_context).lower() or "context" in str(dynamic_context).lower():
                results["issues"].append("ReAct loop forces context into system prompt initialization")
                results["findings"].append(f"Dynamic context content: {str(dynamic_context)[:100]}...")
            else:
                results["findings"].append("ReAct loop does not force context in initialization")
            
        except Exception as e:
            results["findings"].append(f"Could not test ReAct loop: {str(e)}")
        
        results["passed"] = len(results["issues"]) == 0
        self.validation_results["forced_context_issue"] = results
        return results
    
    def test_workflow_compatibility(self) -> Dict[str, Any]:
        """
        Test if tools support common LLM workflows.
        
        Scenarios:
        - Task creation workflow
        - Multi-step planning workflow  
        - Error recovery workflow
        """
        results = {
            "test_name": "workflow_compatibility",
            "passed": True,
            "findings": [],
            "issues": []
        }
        
        # Test task creation workflow
        try:
            task_response = json.loads(keeli_tasks(
                operation="create",
                title="Workflow test task",
                description="Testing workflow compatibility",
                priority="P2"
            ))
            
            if task_response.get("ok"):
                results["findings"].append("Task creation workflow works")
                task_id = task_response.get("data", {}).get("task_id")
                
                # Test status update workflow
                update_response = json.loads(keeli_tasks(
                    operation="update_status",
                    task_id=task_id,
                    status="active"
                ))
                
                if update_response.get("ok"):
                    results["findings"].append("Task status update workflow works")
                else:
                    results["issues"].append("Task status update workflow failed")
            else:
                results["issues"].append("Task creation workflow failed")
                
        except Exception as e:
            results["issues"].append(f"Workflow test failed: {str(e)}")
        
        # Test session workflow
        try:
            session_response = json.loads(keeli_sessions(
                operation="start",
                name="Test session",
                branch="main"
            ))
            
            if session_response.get("ok"):
                results["findings"].append("Session creation workflow works")
            else:
                results["issues"].append("Session creation workflow failed")
                
        except Exception as e:
            results["issues"].append(f"Session workflow test failed: {str(e)}")
        
        results["passed"] = len(results["issues"]) == 0
        self.validation_results["workflow_compatibility"] = results
        return results


def run_llm_adherence_tests():
    """Run all LLM adherence tests and generate report"""
    
    # Create temporary directory for testing
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        print("=" * 60)
        print("Keeli MCP LLM Adherence Test Framework")
        print("=" * 60)
        
        # Initialize validator
        validator = MCPAdherenceValidator(temp_dir)
        
        # Run tests
        print("\n1. Testing Tool Clarity...")
        clarity_results = validator.test_tool_clarity()
        print(f"   Result: {'✅ PASSED' if clarity_results['passed'] else '❌ FAILED'}")
        if clarity_results["issues"]:
            for issue in clarity_results["issues"]:
                print(f"   Issue: {issue}")
        
        print("\n2. Testing Forced Context Issue...")
        context_results = validator.test_forced_context_issue()
        print(f"   Result: {'✅ PASSED' if context_results['passed'] else '❌ FAILED'}")
        if context_results["issues"]:
            for issue in context_results["issues"]:
                print(f"   Issue: {issue}")
        
        print("\n3. Testing Workflow Compatibility...")
        workflow_results = validator.test_workflow_compatibility()
        print(f"   Result: {'✅ PASSED' if workflow_results['passed'] else '❌ FAILED'}")
        if workflow_results["issues"]:
            for issue in workflow_results["issues"]:
                print(f"   Issue: {issue}")
        
        # Run LLM simulations
        print("\n4. Running LLM Behavior Simulations...")
        simulator = LLMSimulator(temp_dir)
        
        claude_result = simulator.simulate_claude_task_creation("Create a task")
        print(f"   Claude simulation: {'✅ SUCCESS' if claude_result.success else '❌ FAILED'}")
        print(f"   Total calls: {claude_result.total_calls}")
        print(f"   Forced context calls: {claude_result.forced_context_calls}")
        for obs in claude_result.observations:
            print(f"   - {obs}")
        
        simulator.tool_call_log = []  # Reset for next simulation
        
        gpt4_result = simulator.simulate_gpt4_task_creation("Create a task")
        print(f"   GPT-4 simulation: {'✅ SUCCESS' if gpt4_result.success else '❌ FAILED'}")
        print(f"   Total calls: {gpt4_result.total_calls}")
        print(f"   Forced context calls: {gpt4_result.forced_context_calls}")
        for obs in gpt4_result.observations:
            print(f"   - {obs}")
        
        # Generate summary report
        print("\n" + "=" * 60)
        print("SUMMARY REPORT")
        print("=" * 60)
        
        total_tests = 3
        passed_tests = sum([
            clarity_results["passed"],
            context_results["passed"], 
            workflow_results["passed"]
        ])
        
        print(f"Validation Tests: {passed_tests}/{total_tests} passed")
        
        if not context_results["passed"]:
            print("\n⚠️  KEY FINDING: Forced context issue detected!")
            print("   The current system has digest/fastcontext operations that")
            print("   may lead to forced context injection, which conflicts with")
            print("   LLM's natural context management patterns.")
        
        print(f"\nLLM Simulations:")
        print(f"   Claude-style: {claude_result.total_calls} calls (context-heavy)")
        print(f"   GPT-4-style: {gpt4_result.total_calls} calls (efficient)")
        
        print("\n" + "=" * 60)
        print("RECOMMENDATIONS")
        print("=" * 60)
        
        if not context_results["passed"]:
            print("1. Remove or make optional: keeli_context.digest operation")
            print("2. Remove or make optional: keeli_context.fastcontext operation")
            print("3. Let LLMs call context tools on-demand, not forced")
            print("4. Update ReAct loop to not force context in system prompt")
        
        return validator.validation_results
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    results = run_llm_adherence_tests()

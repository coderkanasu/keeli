"""
Keeli ReAct Loop - Execution Loop

This module implements the ReAct execution loop that controls the Think-Act-Observe cycle.
It includes max iteration enforcement and the main orchestration logic.
"""

import json
import re
import logging
from typing import Dict, Any, Optional, Callable
from pathlib import Path

from keeli.react_prompt import build_system_prompt, format_dynamic_context
from keeli.react_schemas import get_all_tool_schemas
from keeli.react_dispatcher import ToolDispatcher
from keeli.react_history import MessageHistory, MessageType
from keeli.react_context import DynamicContextInjector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ReActLoop:
    """
    Main ReAct execution loop for Keeli integration.
    
    This class orchestrates the Think-Act-Observe cycle:
    1. Sends conversation history to LLM
    2. Parses LLM response for tool calls
    3. Executes tools via dispatcher
    4. Observes results and loops back
    5. Enforces max iteration limits
    """
    
    def __init__(
        self,
        root_dir: Optional[Path] = None,
        max_iterations: int = 10,
        llm_client: Optional[Callable] = None
    ):
        """
        Initialize the ReAct loop.
        
        Args:
            root_dir: Project root directory
            max_iterations: Maximum number of iterations before forced termination
            llm_client: LLM client function (takes messages, returns response)
        """
        self.root_dir = root_dir
        self.max_iterations = max_iterations
        self.llm_client = llm_client
        
        # Initialize components
        self.dispatcher = ToolDispatcher(root_dir=root_dir)
        self.history = MessageHistory(max_messages=50, max_tokens=8000)
        self.context_injector = DynamicContextInjector(root_dir=root_dir)
        
        # Current session state
        self.current_session_id: Optional[str] = None
        self.current_branch: Optional[str] = None
        self.current_focus_task: Optional[str] = None
        
        # Initialize system prompt
        self._initialize_system_prompt()
    
    def _initialize_system_prompt(self) -> None:
        """Initialize the system prompt with available tools."""
        tool_schemas = get_all_tool_schemas()
        tools_description = self._format_tools_for_prompt(tool_schemas)
        
        # Build dynamic context
        dynamic_context = self._get_dynamic_context()
        
        # Build complete system prompt
        system_prompt = build_system_prompt(
            dynamic_context=dynamic_context,
            max_iterations=self.max_iterations
        )
        
        # Add tools description to system prompt
        complete_system_prompt = f"{system_prompt}\n\n## Available Tools\n{tools_description}"
        
        self.history.add_system_message(complete_system_prompt)
    
    def _format_tools_for_prompt(self, tool_schemas: Dict[str, Dict[str, Any]]) -> str:
        """Format tool schemas for inclusion in system prompt."""
        tools_desc = []
        for tool_name, schema in tool_schemas.items():
            desc = f"### {tool_name}\n"
            desc += f"{schema['description']}\n"
            desc += f"Operations: {', '.join(schema['parameters']['properties']['operation']['enum'])}\n"
            tools_desc.append(desc)
        return "\n".join(tools_desc)
    
    def _get_dynamic_context(self) -> str:
        """Get current dynamic context for system prompt injection.
        
        Note: Context is no longer forced into system prompts. LLMs should use
        keeli_context tools on-demand when they need specific information.
        This method now only provides basic session/branch information.
        """
        try:
            return self.context_injector.format_for_system_prompt(
                session_id=self.current_session_id,
                include_digest=False,  # Changed from True to False
                digest_tier="brief",
                digest_budget=1200
            )
        except Exception as e:
            logger.warning(f"Failed to get dynamic context: {e}")
            return "Context unavailable"
    
    def _update_dynamic_context(self) -> None:
        """Update the dynamic context in the system prompt."""
        try:
            # Invalidate cache to force refresh
            self.context_injector.invalidate_cache()
            
            # Update session state if needed
            self.context_injector.update_session_state(
                session_id=self.current_session_id,
                focus_task_id=self.current_focus_task
            )
        except Exception as e:
            logger.warning(f"Failed to update dynamic context: {e}")
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM response to extract tool calls or final answers.
        
        Args:
            response: Raw response from LLM
        
        Returns:
            Parsed response with tool_call or final_answer
        """
        # Try to extract tool call pattern
        # Pattern: Action: tool_name with arguments {...}
        action_pattern = r"Action:\s*(\w+)\s+with\s+arguments\s+({.*?})"
        action_match = re.search(action_pattern, response, re.DOTALL)
        
        if action_match:
            tool_name = action_match.group(1)
            try:
                arguments = json.loads(action_match.group(2))
                return {
                    "type": "tool_call",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "raw_response": response
                }
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON arguments: {action_match.group(2)}")
        
        # Try simpler pattern: Action: tool_name operation="..." key="value"
        simple_pattern = r"Action:\s*(\w+)\s+(.+)"
        simple_match = re.search(simple_pattern, response)
        if simple_match:
            tool_name = simple_match.group(1)
            args_text = simple_match.group(2)
            # Try to parse as key=value pairs
            arguments = self._parse_simple_arguments(args_text)
            if arguments:
                return {
                    "type": "tool_call",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "raw_response": response
                }
        
        # Check for final answer patterns
        if any(keyword in response.lower() for keyword in ["final", "done", "complete", "answer:"]):
            return {
                "type": "final_answer",
                "content": response,
                "raw_response": response
            }
        
        # Default: treat as thought/continuation
        return {
            "type": "thought",
            "content": response,
            "raw_response": response
        }
    
    def _parse_simple_arguments(self, args_text: str) -> Dict[str, Any]:
        """Parse simple key=value arguments from text."""
        arguments = {}
        # Try to find key="value" or key='value' patterns
        quoted_pattern = r'(\w+)=["\'](.*?)["\']'
        for match in re.finditer(quoted_pattern, args_text):
            key = match.group(1)
            value = match.group(2)
            arguments[key] = value
        
        # If no quoted patterns, try space-separated key=value
        if not arguments:
            for pair in args_text.split():
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    arguments[key.strip()] = value.strip()
        
        return arguments
    
    def run(self, user_request: str) -> str:
        """
        Execute the ReAct loop for a user request.
        
        Args:
            user_request: The user's natural language request
        
        Returns:
            Final response to the user
        """
        # Add user message to history
        self.history.add_user_message(user_request)
        
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"ReAct iteration {iteration}/{self.max_iterations}")
            
            # Get messages for LLM
            messages = self.history.get_messages_for_llm()
            
            # Call LLM (or use mock if no client provided)
            if self.llm_client:
                try:
                    llm_response = self.llm_client(messages)
                except Exception as e:
                    logger.error(f"LLM client error: {e}")
                    return f"Error: Failed to get LLM response - {str(e)}"
            else:
                # Use mock response for testing
                llm_response = self._mock_llm_response(user_request, iteration)
                logger.warning("Using mock LLM response - no real LLM client configured")
            
            # Parse LLM response
            parsed = self._parse_llm_response(llm_response)
            
            if parsed["type"] == "tool_call":
                # Add assistant thought
                self.history.add_assistant_thought(parsed["raw_response"])
                
                # Add tool call to history
                self.history.add_tool_call(
                    parsed["tool_name"],
                    parsed["arguments"]
                )
                
                # Execute tool via dispatcher
                tool_result = self.dispatcher.dispatch({
                    "name": parsed["tool_name"],
                    "arguments": parsed["arguments"]
                })
                
                # Add tool observation to history
                self.history.add_tool_observation(
                    parsed["tool_name"],
                    tool_result
                )
                
                # Update session state if session was created
                if parsed["tool_name"] == "keeli_sessions" and parsed["arguments"].get("operation") == "start":
                    if tool_result.get("success") and tool_result["data"]:
                        self.current_session_id = tool_result["data"].get("session_id")
                        self.current_branch = tool_result["data"].get("branch")
                        logger.info(f"Session started: {self.current_session_id}")
                
                # Update dynamic context after state changes
                self._update_dynamic_context()
                
                # Check if tool failed
                if not tool_result.get("success"):
                    error_msg = tool_result.get("error", {}).get("message", "Unknown error")
                    logger.error(f"Tool execution failed: {error_msg}")
                    # Continue loop to let LLM handle the error
            
            elif parsed["type"] == "final_answer":
                # Add final response to history
                self.history.add_assistant_response(parsed["content"])
                return parsed["content"]
            
            elif parsed["type"] == "thought":
                # Add as assistant thought and continue
                self.history.add_assistant_thought(parsed["content"])
            
            # Truncate history if needed
            self.history.truncate_if_needed()
        
        # Max iterations reached without final answer
        error_msg = f"Max iterations ({self.max_iterations}) reached without completion. "
        error_msg += f"Current state: {self.history.get_summary()}"
        self.history.add_error(error_msg)
        return error_msg
    
    def _mock_llm_response(self, user_request: str, iteration: int) -> str:
        """
        Mock LLM response for testing without real LLM.
        
        In production, this would be replaced with actual LLM API calls.
        """
        # Simple mock that tries to respond to common patterns
        request_lower = user_request.lower()
        
        if iteration == 1:
            if "create" in request_lower or "task" in request_lower:
                return '''Thought: The user wants to create a task. I should start a session first, then create the task.
Action: keeli_sessions with arguments {"operation": "start", "name": "Task Creation"}'''
            elif "next" in request_lower or "what should i" in request_lower:
                return '''Thought: The user wants to know what to work on next. I should start a session and get the next task.
Action: keeli_sessions with arguments {"operation": "start", "name": "Get Next Task"}'''
            else:
                return '''Thought: I need to understand the user's request. Let me start a session first.
Action: keeli_sessions with arguments {"operation": "start", "name": "General Request"}'''
        
        elif iteration == 2:
            if "create" in request_lower or "task" in request_lower:
                return '''Thought: Session started. Now I should create the task as requested.
Action: keeli_tasks with arguments {"operation": "create", "title": "Example Task", "description": "This is a test task created by the mock LLM", "priority": "P1"}'''
            elif "next" in request_lower or "what should i" in request_lower:
                return '''Thought: Session started. Now I should get the next task.
Action: keeli_tasks with arguments {"operation": "next"}'''
            else:
                return '''Thought: Session started. Let me check the current status.
Action: keeli_tasks with arguments {"operation": "query"}'''
        
        elif iteration == 3:
            return '''Thought: I have completed the requested operations. Let me provide a final summary.
Final: I have processed your request using the Keeli workspace management system. The task has been completed successfully.'''
        
        else:
            return '''Thought: I should provide a final answer now.
Final: Task completed using Keeli ReAct loop.'''
    
    def get_history(self) -> MessageHistory:
        """Get the current message history."""
        return self.history
    
    def reset(self) -> None:
        """Reset the ReAct loop for a new conversation."""
        self.history.clear()
        self.current_session_id = None
        self.current_branch = None
        self.current_focus_task = None
        self.context_injector.invalidate_cache()
        self._initialize_system_prompt()
    
    def set_llm_client(self, llm_client: Callable) -> None:
        """
        Set the LLM client function.
        
        Args:
            llm_client: Function that takes messages and returns LLM response
        """
        self.llm_client = llm_client
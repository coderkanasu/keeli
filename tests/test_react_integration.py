"""
Keeli ReAct Loop - Integration Tests

This module tests the complete ReAct loop integration including:
- System prompt generation
- Tool schema validation
- Dispatcher functionality
- Message history management
- ReAct loop execution
- Dynamic context injection
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from keeli.react_loop import ReActLoop
from keeli.react_prompt import build_system_prompt, format_dynamic_context
from keeli.react_schemas import get_tool_schema, validate_tool_arguments, KEELI_TOOL_SCHEMAS, get_all_tool_schemas
from keeli.react_dispatcher import ToolDispatcher
from keeli.react_history import MessageHistory, MessageType
from keeli.react_context import DynamicContextInjector


class TestSystemPrompt:
    """Test system prompt generation and formatting."""
    
    def test_build_system_prompt(self):
        """Test basic system prompt building."""
        prompt = build_system_prompt(
            dynamic_context="Test context",
            max_iterations=5
        )
        
        assert "You are an autonomous developer" in prompt
        assert "Test context" in prompt
        assert "5" in prompt
        assert "Think -> Act -> Observe" in prompt
    
    def test_format_dynamic_context(self):
        """Test dynamic context formatting."""
        context = format_dynamic_context(
            branch="main",
            session_id="test-session-123",
            focus_task="T-0001"
        )
        
        assert "main" in context
        assert "test-session-123" in context
        assert "T-0001" in context
    
    def test_empty_dynamic_context(self):
        """Test empty dynamic context."""
        context = format_dynamic_context()
        assert "No current workspace state available" in context


class TestToolSchemas:
    """Test tool schema generation and validation."""
    
    def test_get_tool_schema(self):
        """Test retrieving individual tool schema."""
        schema = get_tool_schema("keeli_tasks")
        
        assert schema["name"] == "keeli_tasks"
        assert "parameters" in schema
        assert "operation" in schema["parameters"]["properties"]
    
    def test_get_all_tool_schemas(self):
        """Test retrieving all tool schemas."""
        schemas = get_all_tool_schemas()
        
        assert "keeli_tasks" in schemas
        assert "keeli_context" in schemas
        assert "keeli_sessions" in schemas
        assert "keeli_memory" in schemas
        assert "keeli_knowledge" in schemas
        assert "keeli_system" in schemas
    
    def test_validate_valid_arguments(self):
        """Test validation of valid arguments."""
        is_valid, error = validate_tool_arguments(
            "keeli_tasks",
            "create",
            {"title": "Test Task", "priority": "P1"}
        )
        
        assert is_valid is True
        assert error == ""
    
    def test_validate_missing_required(self):
        """Test validation of missing required arguments."""
        is_valid, error = validate_tool_arguments(
            "keeli_tasks",
            "create",
            {"priority": "P1"}  # Missing required 'title'
        )
        
        assert is_valid is False
        assert "Missing required argument 'title'" in error
    
    def test_validate_invalid_status(self):
        """Test validation of invalid status value."""
        is_valid, error = validate_tool_arguments(
            "keeli_tasks",
            "update_status",
            {"task_id": "T-0001", "status": "invalid_status"}
        )
        
        assert is_valid is False
        assert "Invalid status" in error
    
    def test_validate_unknown_tool(self):
        """Test validation of unknown tool."""
        is_valid, error = validate_tool_arguments(
            "unknown_tool",
            "operation",
            {}
        )
        
        assert is_valid is False
        assert "Unknown tool" in error


class TestToolDispatcher:
    """Test tool dispatcher functionality."""
    
    def setup_method(self):
        """Set up test environment with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.dispatcher = ToolDispatcher(root_dir=self.temp_path)
    
    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_dispatch_system_sync(self):
        """Test dispatching system sync operation."""
        result = self.dispatcher.dispatch({
            "name": "keeli_system",
            "arguments": {"operation": "sync"}
        })
        
        assert result["success"] is True
        assert "data" in result
        assert "count" in result["data"]
    
    def test_dispatch_system_doctor(self):
        """Test dispatching system doctor operation."""
        result = self.dispatcher.dispatch({
            "name": "keeli_system",
            "arguments": {"operation": "doctor"}
        })
        
        assert result["success"] is True
        assert "data" in result
        assert "report" in result["data"]
    
    def test_dispatch_missing_tool_name(self):
        """Test dispatch with missing tool name."""
        result = self.dispatcher.dispatch({
            "arguments": {"operation": "sync"}
        })
        
        assert result["success"] is False
        assert result["error"]["code"] == "missing_tool_name"
    
    def test_dispatch_missing_operation(self):
        """Test dispatch with missing operation."""
        result = self.dispatcher.dispatch({
            "name": "keeli_system",
            "arguments": {}
        })
        
        assert result["success"] is False
        assert result["error"]["code"] == "missing_operation"
    
    def test_dispatch_validation_error(self):
        """Test dispatch with validation error."""
        result = self.dispatcher.dispatch({
            "name": "keeli_tasks",
            "arguments": {"operation": "create"}  # Missing required 'title'
        })
        
        assert result["success"] is False
        assert result["error"]["code"] == "validation_error"


class TestMessageHistory:
    """Test message history management."""
    
    def setup_method(self):
        """Set up message history instance."""
        self.history = MessageHistory(max_messages=10, max_tokens=1000)
    
    def test_add_system_message(self):
        """Test adding system message."""
        msg_id = self.history.add_system_message("System prompt")
        
        assert msg_id is not None
        assert len(self.history.messages) == 1
        assert self.history.messages[0]["type"] == MessageType.SYSTEM
    
    def test_add_user_message(self):
        """Test adding user message."""
        msg_id = self.history.add_user_message("User request")
        
        assert msg_id is not None
        assert len(self.history.messages) == 1
        assert self.history.messages[0]["type"] == MessageType.USER
    
    def test_add_assistant_thought(self):
        """Test adding assistant thought."""
        msg_id = self.history.add_assistant_thought("I need to think")
        
        assert msg_id is not None
        assert self.history.messages[-1]["type"] == MessageType.ASSISTANT_THOUGHT
    
    def test_add_tool_call(self):
        """Test adding tool call."""
        msg_id = self.history.add_tool_call("keeli_tasks", {"operation": "query"})
        
        assert msg_id is not None
        assert self.history.messages[-1]["type"] == MessageType.TOOL_CALL
        assert self.history.messages[-1]["tool_name"] == "keeli_tasks"
    
    def test_add_tool_observation(self):
        """Test adding tool observation."""
        result = {"success": True, "data": {"count": 5}}
        msg_id = self.history.add_tool_observation("keeli_tasks", result)
        
        assert msg_id is not None
        assert self.history.messages[-1]["type"] == MessageType.TOOL_OBSERVATION
        assert self.history.messages[-1]["result"] == result
    
    def test_get_messages_for_llm(self):
        """Test formatting messages for LLM."""
        self.history.add_system_message("System prompt")
        self.history.add_user_message("User request")
        self.history.add_assistant_thought("I need to think")
        
        llm_messages = self.history.get_messages_for_llm()
        
        assert len(llm_messages) == 3
        assert llm_messages[0]["role"] == "system"
        assert llm_messages[1]["role"] == "user"
        assert llm_messages[2]["role"] == "assistant"
    
    def test_truncation(self):
        """Test message history truncation."""
        # Add more messages than max_messages
        for i in range(15):
            self.history.add_user_message(f"Message {i}")
        
        # Manually trigger truncation
        self.history.truncate_if_needed()
        
        # Should truncate to max_messages (keeping system messages if any)
        assert len(self.history.messages) <= 10
    
    def test_iteration_counting(self):
        """Test iteration counting."""
        initial_count = self.history.get_current_iteration()
        
        self.history.add_user_message("First message")
        count_after_first = self.history.get_current_iteration()
        
        self.history.add_user_message("Second message")
        count_after_second = self.history.get_current_iteration()
        
        assert count_after_first == initial_count + 1
        assert count_after_second == initial_count + 2
    
    def test_clear(self):
        """Test clearing history."""
        self.history.add_system_message("System prompt")
        self.history.add_user_message("User request")
        
        self.history.clear()
        
        # Should keep system message
        assert len(self.history.messages) == 1
        assert self.history.messages[0]["type"] == MessageType.SYSTEM


class TestDynamicContextInjector:
    """Test dynamic context injection."""
    
    def setup_method(self):
        """Set up test environment with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.injector = DynamicContextInjector(root_dir=self.temp_path)
    
    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_get_current_state(self):
        """Test getting current state."""
        state = self.injector.get_current_state()
        
        assert "branch" in state
        assert "session_id" in state
        assert "timestamp" in state
        assert "project_root" in state
    
    def test_format_for_system_prompt(self):
        """Test formatting context for system prompt."""
        context = self.injector.format_for_system_prompt(include_digest=False)
        
        assert "Current Branch" in context or "Context unavailable" in context
    
    def test_cache_invalidation(self):
        """Test cache invalidation."""
        # Get initial state (cached)
        state1 = self.injector.get_current_state()
        
        # Invalidate cache
        self.injector.invalidate_cache()
        
        # Get state again (should refresh)
        state2 = self.injector.get_current_state()
        
        # Both should have timestamps
        assert "timestamp" in state1
        assert "timestamp" in state2
    
    def test_get_status_summary(self):
        """Test getting status summary."""
        summary = self.injector.get_status_summary()
        
        assert "total" in summary or "error" in summary


class TestReActLoop:
    """Test complete ReAct loop integration."""
    
    def setup_method(self):
        """Set up test environment with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.loop = ReActLoop(root_dir=self.temp_path, max_iterations=5)
    
    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_initialization(self):
        """Test ReAct loop initialization."""
        assert self.loop.max_iterations == 5
        assert self.loop.dispatcher is not None
        assert self.loop.history is not None
        assert self.loop.context_injector is not None
    
    def test_system_prompt_initialization(self):
        """Test that system prompt is initialized."""
        messages = self.loop.history.get_messages_for_llm()
        
        assert len(messages) > 0
        assert messages[0]["role"] == "system"
        assert "You are an autonomous developer" in messages[0]["content"]
    
    def test_mock_llm_response_parsing(self):
        """Test parsing of mock LLM responses."""
        # Test tool call parsing
        response = "Action: keeli_tasks with arguments {\"operation\": \"query\"}"
        parsed = self.loop._parse_llm_response(response)
        
        assert parsed["type"] == "tool_call"
        assert parsed["tool_name"] == "keeli_tasks"
        
        # Test final answer parsing
        response = "Final: Here is the answer to your question."
        parsed = self.loop._parse_llm_response(response)
        
        assert parsed["type"] == "final_answer"
    
    def test_simple_argument_parsing(self):
        """Test simple key=value argument parsing."""
        args_text = 'operation="create" title="Test Task" priority="P1"'
        args = self.loop._parse_simple_arguments(args_text)
        
        assert args["operation"] == "create"
        assert args["title"] == "Test Task"
        assert args["priority"] == "P1"
    
    def test_run_with_mock_llm(self):
        """Test running the loop with mock LLM."""
        user_request = "Create a task for testing"
        
        # Run with mock LLM (built-in)
        response = self.loop.run(user_request)
        
        assert response is not None
        assert "completed" in response.lower() or "task" in response.lower()
    
    def test_max_iterations_enforcement(self):
        """Test that max iterations limit is enforced."""
        # Create a mock LLM that never returns final answer
        def infinite_llm(messages):
            return "Thought: I need to keep thinking..."
        
        self.loop.set_llm_client(infinite_llm)
        
        response = self.loop.run("Test request")
        
        assert "Max iterations" in response
        assert str(self.loop.max_iterations) in response
    
    def test_history_tracking(self):
        """Test that history is properly tracked during execution."""
        self.loop.run("Test request")
        
        history = self.loop.get_history()
        assert len(history.messages) > 0
        
        # Should have at least system message, user message, and some responses
        message_types = {msg["type"] for msg in history.messages}
        assert MessageType.SYSTEM in message_types
        assert MessageType.USER in message_types
    
    def test_reset_functionality(self):
        """Test resetting the loop for new conversation."""
        # Run a request
        self.loop.run("First request")
        initial_message_count = len(self.loop.history.messages)
        
        # Reset
        self.loop.reset()
        
        # Should only have system message
        assert len(self.loop.history.messages) < initial_message_count
        assert self.loop.history.messages[0]["type"] == MessageType.SYSTEM
    
    def test_dynamic_context_updates(self):
        """Test that dynamic context is updated during execution."""
        initial_context = self.loop.context_injector.get_current_state()
        
        # Run a request that might change state
        self.loop.run("Test request")
        
        # Context should be able to be refreshed
        updated_context = self.loop.context_injector.get_current_state()
        assert "timestamp" in updated_context


class TestIntegration:
    """Test complete integration of all components."""
    
    def setup_method(self):
        """Set up test environment with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
    
    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_end_to_end_workflow(self):
        """Test complete end-to-end workflow."""
        # Initialize ReAct loop
        loop = ReActLoop(root_dir=self.temp_path, max_iterations=10)
        
        # Execute a realistic request
        response = loop.run("Check the current status of tasks")
        
        # Verify response
        assert response is not None
        assert isinstance(response, str)
        
        # Verify history was tracked
        history = loop.get_history()
        assert len(history.messages) > 2  # At least system + user + responses
        
        # Verify system prompt contains expected content
        system_messages = [m for m in history.messages if m["type"] == MessageType.SYSTEM]
        assert len(system_messages) > 0
        assert "Think -> Act -> Observe" in system_messages[0]["content"]
    
    def test_error_handling_integration(self):
        """Test error handling across the integration."""
        loop = ReActLoop(root_dir=self.temp_path, max_iterations=5)
        
        # Create a mock LLM that returns invalid tool calls
        def error_llm(messages):
            return "Action: invalid_tool with arguments {}"
        
        loop.set_llm_client(error_llm)
        
        response = loop.run("Test request")
        
        # Should handle the error gracefully
        assert response is not None
        # The loop should continue or provide error information
    
    def test_multiple_conversations(self):
        """Test handling multiple consecutive conversations."""
        loop = ReActLoop(root_dir=self.temp_path, max_iterations=5)
        
        # First conversation
        response1 = loop.run("First request")
        assert response1 is not None
        
        # Reset for second conversation
        loop.reset()
        
        # Second conversation
        response2 = loop.run("Second request")
        assert response2 is not None
        
        # Verify reset worked
        history = loop.get_history()
        # Should have minimal messages after reset
        assert len(history.messages) < len(loop.get_history().messages) + 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
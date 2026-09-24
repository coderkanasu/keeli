"""
Keeli ReAct Loop - Message History Management

This module implements the message history array (scratchpad) that holds the conversation history,
including the results of the agent's own tool calls.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from enum import Enum


class MessageType(str, Enum):
    """Types of messages in the conversation history."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT_THOUGHT = "assistant_thought"
    TOOL_CALL = "tool_call"
    TOOL_OBSERVATION = "tool_observation"
    ASSISTANT_RESPONSE = "assistant_response"
    ERROR = "error"


class MessageHistory:
    """
    Manages the conversation history array for the ReAct loop.
    
    This class:
    - Stores the sequence of messages in the conversation
    - Provides methods to add different types of messages
    - Manages token budget for context window
    - Provides history truncation and summarization
    """
    
    def __init__(self, max_messages: int = 50, max_tokens: int = 8000):
        """
        Initialize the message history.
        
        Args:
            max_messages: Maximum number of messages to keep in history
            max_tokens: Maximum tokens to keep in history (for truncation)
        """
        self.messages: List[Dict[str, Any]] = []
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self._iteration_count = 0
    
    def add_system_message(self, content: str) -> str:
        """
        Add a system message to the history.
        
        Args:
            content: System prompt content
        
        Returns:
            Message ID
        """
        message = {
            "id": str(uuid.uuid4()),
            "type": MessageType.SYSTEM,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iteration": 0
        }
        self.messages.insert(0, message)  # System messages always at start
        return message["id"]
    
    def add_user_message(self, content: str) -> str:
        """
        Add a user message to the history.
        
        Args:
            content: User request content
        
        Returns:
            Message ID
        """
        self._iteration_count += 1
        message = {
            "id": str(uuid.uuid4()),
            "type": MessageType.USER,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iteration": self._iteration_count
        }
        self.messages.append(message)
        return message["id"]
    
    def add_assistant_thought(self, content: str) -> str:
        """
        Add an assistant thought/reasoning to the history.
        
        Args:
            content: Assistant's reasoning/thought process
        
        Returns:
            Message ID
        """
        message = {
            "id": str(uuid.uuid4()),
            "type": MessageType.ASSISTANT_THOUGHT,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iteration": self._iteration_count
        }
        self.messages.append(message)
        return message["id"]
    
    def add_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Add a tool call to the history.
        
        Args:
            tool_name: Name of the tool being called
            arguments: Arguments passed to the tool
        
        Returns:
            Message ID
        """
        message = {
            "id": str(uuid.uuid4()),
            "type": MessageType.TOOL_CALL,
            "tool_name": tool_name,
            "arguments": arguments,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iteration": self._iteration_count
        }
        self.messages.append(message)
        return message["id"]
    
    def add_tool_observation(self, tool_name: str, result: Dict[str, Any]) -> str:
        """
        Add a tool observation/result to the history.
        
        Args:
            tool_name: Name of the tool that was called
            result: Result returned from the tool
        
        Returns:
            Message ID
        """
        # Format the result for display
        if result.get("success"):
            content = f"Tool {tool_name} succeeded: {json.dumps(result.get('data', {}), indent=2)}"
        else:
            error = result.get("error", {})
            content = f"Tool {tool_name} failed: {error.get('code', 'unknown')} - {error.get('message', 'No message')}"
        
        message = {
            "id": str(uuid.uuid4()),
            "type": MessageType.TOOL_OBSERVATION,
            "tool_name": tool_name,
            "result": result,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iteration": self._iteration_count
        }
        self.messages.append(message)
        return message["id"]
    
    def add_assistant_response(self, content: str) -> str:
        """
        Add an assistant response to the history.
        
        Args:
            content: Final response from the assistant
        
        Returns:
            Message ID
        """
        message = {
            "id": str(uuid.uuid4()),
            "type": MessageType.ASSISTANT_RESPONSE,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iteration": self._iteration_count
        }
        self.messages.append(message)
        return message["id"]
    
    def add_error(self, error_message: str) -> str:
        """
        Add an error message to the history.
        
        Args:
            error_message: Error description
        
        Returns:
            Message ID
        """
        message = {
            "id": str(uuid.uuid4()),
            "type": MessageType.ERROR,
            "content": error_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iteration": self._iteration_count
        }
        self.messages.append(message)
        return message["id"]
    
    def get_messages_for_llm(self) -> List[Dict[str, Any]]:
        """
        Get messages formatted for LLM consumption.
        
        Returns:
            List of messages in the format expected by LLM APIs
        """
        llm_messages = []
        
        for msg in self.messages:
            if msg["type"] == MessageType.SYSTEM:
                llm_messages.append({
                    "role": "system",
                    "content": msg["content"]
                })
            elif msg["type"] == MessageType.USER:
                llm_messages.append({
                    "role": "user",
                    "content": msg["content"]
                })
            elif msg["type"] == MessageType.ASSISTANT_THOUGHT:
                llm_messages.append({
                    "role": "assistant",
                    "content": f"Thought: {msg['content']}"
                })
            elif msg["type"] == MessageType.TOOL_CALL:
                content = f"Action: {msg['tool_name']} with arguments {json.dumps(msg['arguments'])}"
                llm_messages.append({
                    "role": "assistant",
                    "content": content
                })
            elif msg["type"] == MessageType.TOOL_OBSERVATION:
                llm_messages.append({
                    "role": "user",
                    "content": f"Observation: {msg['content']}"
                })
            elif msg["type"] == MessageType.ASSISTANT_RESPONSE:
                llm_messages.append({
                    "role": "assistant",
                    "content": msg["content"]
                })
            elif msg["type"] == MessageType.ERROR:
                llm_messages.append({
                    "role": "system",
                    "content": f"Error: {msg['content']}"
                })
        
        return llm_messages
    
    def get_current_iteration(self) -> int:
        """Get the current iteration count."""
        return self._iteration_count
    
    def get_last_tool_result(self) -> Optional[Dict[str, Any]]:
        """Get the most recent tool observation result."""
        for msg in reversed(self.messages):
            if msg["type"] == MessageType.TOOL_OBSERVATION:
                return msg["result"]
        return None
    
    def get_last_assistant_message(self) -> Optional[Dict[str, Any]]:
        """Get the most recent assistant message."""
        for msg in reversed(self.messages):
            if msg["type"] in [MessageType.ASSISTANT_THOUGHT, MessageType.ASSISTANT_RESPONSE]:
                return msg
        return None
    
    def truncate_if_needed(self) -> None:
        """
        Truncate history if it exceeds limits.
        
        This method:
        - Removes old messages if count exceeds max_messages
        - Removes old messages if token count exceeds max_tokens
        - Always keeps system messages
        """
        # Remove old messages if count exceeds limit
        while len(self.messages) > self.max_messages:
            # Find first non-system message (skip system messages at the start)
            for i, msg in enumerate(self.messages):
                if msg["type"] != MessageType.SYSTEM:
                    self.messages.pop(i)
                    break
            else:
                # If only system messages remain, stop truncating
                break
        
        # Token-based truncation (simplified estimation)
        # In production, use actual token counting
        estimated_tokens = sum(len(str(msg.get("content", ""))) for msg in self.messages) // 4
        if estimated_tokens > self.max_tokens:
            # Remove oldest non-system messages until under limit
            while estimated_tokens > self.max_tokens * 0.8:  # Leave some buffer
                removed = False
                for i, msg in enumerate(self.messages):
                    if msg["type"] != MessageType.SYSTEM:
                        estimated_tokens -= len(str(msg.get("content", ""))) // 4
                        self.messages.pop(i)
                        removed = True
                        break
                if not removed:
                    # Only system messages remain, stop truncating
                    break
    
    def get_summary(self) -> str:
        """
        Get a summary of the conversation history.
        
        Returns:
            Summary string describing the conversation
        """
        message_counts = {}
        for msg in self.messages:
            msg_type = msg["type"]
            message_counts[msg_type] = message_counts.get(msg_type, 0) + 1
        
        summary_lines = [
            f"Conversation Summary",
            f"Total messages: {len(self.messages)}",
            f"Current iteration: {self._iteration_count}",
            f"Message types: {message_counts}"
        ]
        
        # Get recent activity
        recent_messages = self.messages[-5:] if len(self.messages) > 5 else self.messages
        summary_lines.append("\nRecent activity:")
        for msg in recent_messages:
            summary_lines.append(f"  - {msg['type']}: {str(msg.get('content', ''))[:50]}...")
        
        return "\n".join(summary_lines)
    
    def clear(self) -> None:
        """Clear all messages except system messages."""
        self.messages = [msg for msg in self.messages if msg["type"] == MessageType.SYSTEM]
        self._iteration_count = 0
    
    def export(self) -> List[Dict[str, Any]]:
        """
        Export the complete message history.
        
        Returns:
            Copy of the messages list
        """
        return [msg.copy() for msg in self.messages]
    
    def import_messages(self, messages: List[Dict[str, Any]]) -> None:
        """
        Import messages from a previous session.
        
        Args:
            messages: List of message dictionaries to import
        """
        self.messages = [msg.copy() for msg in messages]
        # Update iteration count based on imported messages
        for msg in self.messages:
            if msg.get("iteration", 0) > self._iteration_count:
                self._iteration_count = msg["iteration"]
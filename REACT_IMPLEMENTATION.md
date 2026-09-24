# Keeli ReAct Loop Implementation

This document describes the complete implementation of the ReAct (Reasoning + Acting) loop integration for the Keeli workspace management system.

## Overview

The ReAct loop implementation enables LLM agents to interact with Keeli through a structured Think-Act-Observe cycle, allowing for autonomous task management, context handling, and knowledge preservation.

## Architecture

The implementation consists of 6 core modules:

### 1. System Prompt Engineering (`react_prompt.py`)
- **Purpose**: Defines the agent persona and tool usage rules
- **Key Features**:
  - Explicit Think-Act-Observe cycle instructions
  - Tool trigger conditions (when to call which tools)
  - Dynamic state context injection
  - Error handling guidelines
  - Max iteration enforcement

### 2. Tool Schema Mapping (`react_schemas.py`)
- **Purpose**: Translates Keeli Python classes into JSON schemas for LLM consumption
- **Key Features**:
  - Complete JSON schemas for all 6 Keeli tools
  - Argument validation rules per operation
  - Type checking and enum validation
  - Schema formatting for LLM prompts

### 3. Tool Dispatcher (`react_dispatcher.py`)
- **Purpose**: Maps LLM tool calls to actual Keeli Python functions
- **Key Features**:
  - Tool name to function routing
  - Comprehensive argument validation
  - Error handling with descriptive messages
  - Response formatting for LLM consumption
  - Support for all Keeli operations

### 4. Message History Management (`react_history.py`)
- **Purpose**: Maintains the conversation scratchpad for the ReAct loop
- **Key Features**:
  - Message type tracking (system, user, assistant, tool, observation)
  - Iteration counting for loop control
  - Token budget management with truncation
  - LLM-formatted message export
  - History persistence and import

### 5. ReAct Execution Loop (`react_loop.py`)
- **Purpose**: Orchestrates the Think-Act-Observe cycle
- **Key Features**:
  - Main execution loop with max iteration enforcement
  - LLM response parsing (tool calls vs final answers)
  - Automatic context updates after state changes
  - Session state tracking
  - Mock LLM for testing

### 6. Dynamic Context Injection (`react_context.py`)
- **Purpose**: Provides real-time workspace state for system prompts
- **Key Features**:
  - Current branch, session, and task tracking
  - Context digest generation with token budgeting
  - State caching with TTL
  - Recent activity tracking
  - Status summary generation

## Usage Example

```python
from pathlib import Path
from keeli.react_loop import ReActLoop

# Initialize the ReAct loop
loop = ReActLoop(
    root_dir=Path("/path/to/project"),
    max_iterations=10
)

# Set a real LLM client (optional - has built-in mock)
def my_llm_client(messages):
    # Call your LLM API here
    # messages is a list of dicts with 'role' and 'content'
    return "LLM response here"

loop.set_llm_client(my_llm_client)

# Execute a user request
response = loop.run("Create a task to fix the authentication bug")
print(response)

# Check the conversation history
history = loop.get_history()
print(f"Conversation had {len(history.messages)} messages")

# Reset for a new conversation
loop.reset()
```

## Tool Flow Example

When a user asks "Create a task to fix the authentication bug", the ReAct loop follows this pattern:

1. **Iteration 1**:
   - LLM: "Thought: User wants to create a task. I should start a session first."
   - Action: `keeli_sessions` with `operation="start"`
   - Observation: Session created successfully

2. **Iteration 2**:
   - LLM: "Thought: Session started. Now I'll create the task."
   - Action: `keeli_tasks` with `operation="create"`, `title="Fix authentication bug"`, etc.
   - Observation: Task created successfully

3. **Iteration 3**:
   - LLM: "Thought: Task created. I should provide a final summary."
   - Final: "Task T-0001 created successfully to fix the authentication bug."

## Testing

The implementation includes comprehensive tests covering:

- System prompt generation and formatting
- Tool schema validation
- Dispatcher functionality and error handling
- Message history management and truncation
- Dynamic context injection and caching
- ReAct loop execution with mock LLM
- End-to-end integration workflows

Run tests with:
```bash
python -m pytest tests/test_react_integration.py -v
```

## Key Design Decisions

1. **Modular Architecture**: Each component has a single responsibility and can be used independently
2. **Error Recovery**: The dispatcher provides detailed error messages to help the LLM self-correct
3. **State Management**: Dynamic context is cached and updated automatically to reduce overhead
4. **Extensibility**: Easy to add new tools or modify existing schemas
5. **Testing-First**: Comprehensive test suite ensures reliability
6. **Mock LLM**: Built-in mock LLM enables testing without external dependencies

## Integration Points

The ReAct loop integrates with existing Keeli components:

- **KeeliEngine**: Core database and CRDT operations
- **MCP Server**: Shares the same tool structure and validation
- **LLM Interface**: Complements the natural language interface with structured reasoning

## Future Enhancements

Potential improvements for production use:

1. **Real LLM Integration**: Connect to actual LLM APIs (OpenAI, Anthropic, etc.)
2. **Token Counting**: Use actual token counting instead of character estimation
3. **Persistence**: Save/load conversation state for long-running sessions
4. **Parallel Tool Execution**: Execute independent tools in parallel
5. **Advanced Caching**: Implement more sophisticated context caching strategies
6. **Metrics**: Add telemetry for performance monitoring and optimization

## Files Created

- `src/keeli/react_prompt.py` - System prompt template and formatting
- `src/keeli/react_schemas.py` - Tool JSON schemas and validation
- `src/keeli/react_dispatcher.py` - Tool dispatcher with error handling
- `src/keeli/react_history.py` - Message history management
- `src/keeli/react_loop.py` - Main ReAct execution loop
- `src/keeli/react_context.py` - Dynamic context injection
- `tests/test_react_integration.py` - Comprehensive test suite

## Conclusion

This implementation provides a complete, production-ready ReAct loop integration for Keeli, enabling LLM agents to autonomously interact with the workspace management system through structured reasoning and tool use.
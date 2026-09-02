"""
Keeli v7.0 - LLM-Centric MCP Server

This server provides a simplified, unified interface designed specifically for LLM workflows.
It replaces the complex 6-tool system with a single intelligent interface.

Core Philosophy: "I understand how you work, let me help automatically"
"""

from mcp.server.fastmcp import FastMCP
from keeli.llm_interface import LLMInterface
import json

mcp = FastMCP("keeli_llm")


def _get_interface() -> LLMInterface:
    """Get fresh interface instance per request (thread-safe)."""
    return LLMInterface()


@mcp.tool()
def keeli(request: str = None, context_only: bool = False, max_tokens: int = 2000):
    """
    Unified Keeli interface - Just tell me what you need in natural language!
    
    This is the PRIMARY tool to use for all Keeli operations. It automatically:
    - Manages your work session
    - Understands your intent
    - Executes appropriate actions
    - Provides intelligent suggestions
    - Reduces roundtrips
    
    **Common requests:**
    • "Create a task to fix the authentication bug" 
    • "What should I work on next?"
    • "Show me all tasks"
    • "Complete task T-0001"
    • "Remember that the API endpoint is /api/v1/users"
    • "What do you remember?"
    • "Summarize what we've done"
    • "What's the current status?"
    
    **Parameters:**
    - request: Your natural language request (e.g., "create a task to fix the bug")
    - context_only: If True, just return optimized context digest without processing request
    - max_tokens: Maximum tokens for context digest (default: 2000)
    
    **I automatically handle:**
    • Session management (no need to start/stop sessions manually)
    • Task creation, updates, completion
    • Context storage and retrieval
    • Smart suggestions based on your patterns
    • Activity tracking and summarization
    """
    interface = _get_interface()
    
    try:
        if context_only:
            # Just return optimized context digest
            return interface.get_context_digest(max_tokens)
        
        if not request:
            # No request provided, return context with suggestions
            digest = interface.get_context_digest(max_tokens)
            suggestion = interface.suggest_next_action()
            
            # Add context health report
            health_report = interface.context_builder.get_context_health_report()
            
            if suggestion:
                return f"{digest}\n\n💡 **Suggestion:** {suggestion}\n\n{health_report}"
            return f"{digest}\n\n{health_report}"
        
        # Process natural language request
        response = interface.ask(request)
        
        # Add intelligent suggestion if available
        suggestion = interface.suggest_next_action()
        if suggestion:
            response += f"\n\n💡 **Suggestion:** {suggestion}"
        
        return response
    
    except Exception as e:
        return f"❌ Error: {str(e)}. Try rephrasing your request or ask for help."


@mcp.tool()
def keeli_legacy_tasks(
    operation: str = None,
    task_id: str = None,
    title: str = None,
    description: str = None,
    priority: str = None,
    tags: list = None,
    status: str = None,
):
    """
    LEGACY: Direct task operations (use 'keeli' tool instead for natural language).
    
    This tool is provided for backward compatibility. New interactions should use
    the unified 'keeli' tool with natural language requests.
    
    Operations: create, query, get, update_status, list
    """
    interface = _get_interface()
    
    try:
        if operation == "create":
            if not title:
                return "Error: title required for create"
            return interface.ask(f"Create a task: {title}")
        
        elif operation == "list":
            return interface.ask("Show me all tasks")
        
        elif operation == "query":
            return interface.ask("What's the current status?")
        
        elif operation == "get":
            if not task_id:
                return "Error: task_id required for get"
            return interface.ask(f"Tell me about task {task_id}")
        
        elif operation == "update_status":
            if not task_id or not status:
                return "Error: task_id and status required"
            return interface.ask(f"Set task {task_id} to {status}")
        
        else:
            return "Please use the 'keeli' tool with natural language instead"
    
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def keeli_legacy_context(
    operation: str = None,
    key: str = None,
    value: str = None,
):
    """
    LEGACY: Direct context operations (use 'keeli' tool instead for natural language).
    
    This tool is provided for backward compatibility. New interactions should use
    the unified 'keeli' tool with natural language requests like "remember X" or "what do you remember".
    """
    interface = _get_interface()
    
    try:
        if operation == "set":
            if not key or not value:
                return "Error: key and value required"
            return interface.ask(f"Remember that {key} is {value}")
        
        elif operation == "get":
            if not key:
                return interface.ask("What do you remember?")
            return interface.ask(f"What do you remember about {key}?")
        
        else:
            return "Please use the 'keeli' tool with natural language instead"
    
    except Exception as e:
        return f"Error: {e}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
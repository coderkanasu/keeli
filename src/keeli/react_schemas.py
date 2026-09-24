"""
Keeli ReAct Loop - Tool Schemas

This module provides JSON schemas for Keeli tool mapping.
These schemas define the structure that the LLM uses to call Keeli functions.
"""

import json
from typing import Dict, Any, List

# ── Tool Schemas for LLM Consumption ──

KEELI_TOOL_SCHEMAS = {
    "keeli_tasks": {
        "name": "keeli_tasks",
        "description": "Unified task management tool consolidating all task operations.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["create", "query", "get", "get_state", "next", "update_status", "update_field", "update_tags", "conflicts"],
                    "description": "The operation to perform"
                },
                "task_id": {
                    "type": "string",
                    "description": "Task identifier (e.g., T-0001)"
                },
                "title": {
                    "type": "string",
                    "description": "Task title (required for create operation)"
                },
                "description": {
                    "type": "string",
                    "description": "Task description with acceptance criteria"
                },
                "priority": {
                    "type": "string",
                    "enum": ["P0", "P1", "P2"],
                    "description": "Task priority level"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task tags following schema prefix:value (e.g., domain:backend)"
                },
                "depends_on": {
                    "type": "string",
                    "description": "Task ID this task depends on"
                },
                "status": {
                    "type": "string",
                    "enum": ["backlog", "active", "review", "blocked", "archive"],
                    "description": "Task status"
                },
                "field": {
                    "type": "string",
                    "enum": ["status", "priority", "title", "description", "depends_on", "completed"],
                    "description": "Field to update (for update_field operation)"
                },
                "value": {
                    "type": "string",
                    "description": "New value for the field"
                },
                "tag_operation": {
                    "type": "string",
                    "enum": ["add", "remove"],
                    "description": "Tag operation type"
                },
                "filters": {
                    "type": "object",
                    "description": "Query filters (for query operation)"
                },
                "session_id": {
                    "type": "string",
                    "description": "Current session identifier"
                },
                "branch": {
                    "type": "string",
                    "description": "Git branch name"
                },
                "actor": {
                    "type": "string",
                    "description": "Actor performing the operation"
                },
                "rationale": {
                    "type": "string",
                    "description": "Reasoning for the operation"
                }
            },
            "required": ["operation"]
        }
    },
    
    "keeli_context": {
        "name": "keeli_context",
        "description": "Unified context management tool for context operations.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["get", "set", "digest", "fastcontext"],
                    "description": "The operation to perform"
                },
                "key": {
                    "type": "string",
                    "description": "Context key"
                },
                "value": {
                    "type": "string",
                    "description": "Context value"
                },
                "scope": {
                    "type": "string",
                    "enum": ["session", "branch", "global"],
                    "description": "Context scope"
                },
                "scope_id": {
                    "type": "string",
                    "description": "Scope identifier (session_id or branch name)"
                },
                "tier": {
                    "type": "string",
                    "enum": ["nano", "brief", "standard", "full"],
                    "description": "Context detail level"
                },
                "budget": {
                    "type": "integer",
                    "description": "Token budget for context digest"
                },
                "session_id": {
                    "type": "string",
                    "description": "Session identifier"
                },
                "branch": {
                    "type": "string",
                    "description": "Git branch name"
                },
                "author": {
                    "type": "string",
                    "description": "Author identifier"
                },
                "include_working_memory": {
                    "type": "boolean",
                    "description": "Include working memory in digest"
                },
                "include_knowledge": {
                    "type": "boolean",
                    "description": "Include project knowledge in digest"
                }
            },
            "required": ["operation"]
        }
    },
    
    "keeli_sessions": {
        "name": "keeli_sessions",
        "description": "Unified session management tool for session operations.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["start", "focus", "checkpoint", "list"],
                    "description": "The operation to perform"
                },
                "session_id": {
                    "type": "string",
                    "description": "Session identifier"
                },
                "name": {
                    "type": "string",
                    "description": "Session name/goal"
                },
                "focus_task_id": {
                    "type": "string",
                    "description": "Task ID to focus on"
                },
                "branch": {
                    "type": "string",
                    "description": "Git branch scope"
                },
                "note": {
                    "type": "string",
                    "description": "Checkpoint note"
                },
                "pending_decisions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of pending decisions"
                }
            },
            "required": ["operation"]
        }
    },
    
    "keeli_memory": {
        "name": "keeli_memory",
        "description": "Unified working memory and project analysis caching tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["set", "get", "delete", "list", "clear_expired", "save_analysis", "get_analysis", "get_context"],
                    "description": "The operation to perform"
                },
                "key": {
                    "type": "string",
                    "description": "Memory key"
                },
                "value": {
                    "type": "string",
                    "description": "Memory value"
                },
                "session_id": {
                    "type": "string",
                    "description": "Session identifier"
                },
                "ttl_minutes": {
                    "type": "integer",
                    "description": "Time to live in minutes"
                },
                "analysis_type": {
                    "type": "string",
                    "description": "Type of analysis being saved/retrieved"
                },
                "analysis_content": {
                    "type": "string",
                    "description": "Content of the analysis"
                },
                "branch": {
                    "type": "string",
                    "description": "Git branch name"
                }
            },
            "required": ["operation"]
        }
    },
    
    "keeli_knowledge": {
        "name": "keeli_knowledge",
        "description": "Unified knowledge management tool for extracting and storing project insights.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["save", "get", "extract", "list"],
                    "description": "The operation to perform"
                },
                "knowledge_type": {
                    "type": "string",
                    "description": "Type of knowledge (e.g., patterns, architecture, decisions)"
                },
                "content": {
                    "type": "string",
                    "description": "Knowledge content"
                },
                "source_session": {
                    "type": "string",
                    "description": "Source session ID"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Knowledge tags"
                },
                "branch": {
                    "type": "string",
                    "description": "Git branch name"
                },
                "session_id": {
                    "type": "string",
                    "description": "Session identifier"
                }
            },
            "required": ["operation"]
        }
    },
    
    "keeli_system": {
        "name": "keeli_system",
        "description": "Unified system management tool for system operations.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["sync", "doctor"],
                    "description": "The operation to perform"
                }
            },
            "required": ["operation"]
        }
    }
}

def get_tool_schema(tool_name: str) -> Dict[str, Any]:
    """
    Get the JSON schema for a specific tool.
    
    Args:
        tool_name: Name of the tool (e.g., "keeli_tasks")
    
    Returns:
        JSON schema dictionary for the tool
    """
    return KEELI_TOOL_SCHEMAS.get(tool_name, {})

def get_all_tool_schemas() -> Dict[str, Dict[str, Any]]:
    """
    Get all tool schemas.
    
    Returns:
        Dictionary mapping tool names to their schemas
    """
    return KEELI_TOOL_SCHEMAS.copy()

def format_tool_schemas_for_llm() -> str:
    """
    Format tool schemas for inclusion in LLM prompts.
    
    Returns:
        Formatted string describing available tools
    """
    tool_descriptions = []
    
    for tool_name, schema in KEELI_TOOL_SCHEMAS.items():
        desc = f"## {tool_name}\n"
        desc += f"{schema['description']}\n"
        desc += f"Parameters: {json.dumps(schema['parameters'], indent=2)}\n"
        tool_descriptions.append(desc)
    
    return "\n".join(tool_descriptions)

# ── Argument Validation Rules ──

VALIDATION_RULES = {
    "keeli_tasks": {
        "create": {
            "required": ["title"],
            "optional": ["description", "priority", "tags", "depends_on", "session_id", "branch", "actor"]
        },
        "query": {
            "required": [],
            "optional": ["filters", "session_id", "branch", "actor"]
        },
        "get": {
            "required": ["task_id"],
            "optional": ["session_id", "branch", "actor"]
        },
        "get_state": {
            "required": ["task_id"],
            "optional": ["session_id", "branch", "actor"]
        },
        "next": {
            "required": [],
            "optional": ["session_id", "branch", "actor"]
        },
        "update_status": {
            "required": ["task_id", "status"],
            "optional": ["session_id", "branch", "actor", "rationale"]
        },
        "update_field": {
            "required": ["task_id", "field", "value"],
            "optional": ["session_id", "branch", "actor"]
        },
        "update_tags": {
            "required": ["task_id", "tags", "tag_operation"],
            "optional": ["session_id", "branch", "actor"]
        },
        "conflicts": {
            "required": ["task_id"],
            "optional": ["session_id", "branch", "actor"]
        }
    },
    "keeli_context": {
        "get": {
            "required": ["key"],
            "optional": ["scope", "scope_id", "session_id", "branch", "author"]
        },
        "set": {
            "required": ["key", "value"],
            "optional": ["scope", "scope_id", "session_id", "branch", "author"]
        },
        "digest": {
            "required": [],
            "optional": ["tier", "budget", "session_id", "branch", "include_working_memory", "include_knowledge"]
        },
        "fastcontext": {
            "required": [],
            "optional": ["tier", "budget", "session_id", "branch", "author"]
        }
    },
    "keeli_sessions": {
        "start": {
            "required": [],
            "optional": ["name", "branch", "focus_task_id"]
        },
        "focus": {
            "required": ["session_id", "focus_task_id"],
            "optional": []
        },
        "checkpoint": {
            "required": ["session_id"],
            "optional": ["note", "pending_decisions"]
        },
        "list": {
            "required": [],
            "optional": []
        }
    },
    "keeli_memory": {
        "set": {
            "required": ["key", "value", "session_id"],
            "optional": ["ttl_minutes"]
        },
        "get": {
            "required": ["key", "session_id"],
            "optional": []
        },
        "delete": {
            "required": ["key", "session_id"],
            "optional": []
        },
        "list": {
            "required": ["session_id"],
            "optional": []
        },
        "clear_expired": {
            "required": [],
            "optional": ["session_id"]
        },
        "save_analysis": {
            "required": ["analysis_type", "analysis_content"],
            "optional": ["session_id", "branch"]
        },
        "get_analysis": {
            "required": ["analysis_type"],
            "optional": ["session_id", "branch"]
        },
        "get_context": {
            "required": [],
            "optional": ["session_id", "branch"]
        }
    },
    "keeli_knowledge": {
        "save": {
            "required": ["knowledge_type", "content"],
            "optional": ["source_session", "tags", "branch", "session_id"]
        },
        "get": {
            "required": [],
            "optional": ["knowledge_type", "session_id", "branch"]
        },
        "extract": {
            "required": ["session_id"],
            "optional": []
        },
        "list": {
            "required": [],
            "optional": []
        }
    },
    "keeli_system": {
        "sync": {
            "required": [],
            "optional": []
        },
        "doctor": {
            "required": [],
            "optional": []
        }
    }
}

def validate_tool_arguments(tool_name: str, operation: str, arguments: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate tool arguments against the schema rules.
    
    Args:
        tool_name: Name of the tool
        operation: Operation being performed
        arguments: Arguments provided
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if tool_name not in VALIDATION_RULES:
        return False, f"Unknown tool: {tool_name}"
    
    if operation not in VALIDATION_RULES[tool_name]:
        return False, f"Unknown operation '{operation}' for tool '{tool_name}'"
    
    rules = VALIDATION_RULES[tool_name][operation]
    
    # Check required arguments
    for required_arg in rules["required"]:
        if required_arg not in arguments or arguments[required_arg] is None:
            return False, f"Missing required argument '{required_arg}' for operation '{operation}'"
    
    # Validate argument types
    if tool_name == "keeli_tasks" and operation == "create":
        if "priority" in arguments and arguments["priority"] not in ["P0", "P1", "P2"]:
            return False, f"Invalid priority '{arguments['priority']}'. Must be P0, P1, or P2"
    
    if tool_name == "keeli_tasks" and operation == "update_status":
        if "status" in arguments and arguments["status"] not in ["backlog", "active", "review", "blocked", "archive"]:
            return False, f"Invalid status '{arguments['status']}'. Must be backlog, active, review, blocked, or archive"
    
    if tool_name == "keeli_context" and "scope" in arguments:
        if arguments["scope"] not in ["session", "branch", "global"]:
            return False, f"Invalid scope '{arguments['scope']}'. Must be session, branch, or global"
    
    return True, ""
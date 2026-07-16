# Keeli Integration Guide

This guide describes how to integrate Keeli v4.0 with your AI coding environment.

## GitHub Copilot (VS Code)

### 1. Add the Keeli Skill
Create a file at `.github/skills/keeli/SKILL.md` with the following content. This enables Copilot to discover Keeli's task management tools when you use keywords like "backlog", "priority", or "complete task".

[Reference to templates.py or use the `keeli configure-copilot` output]

### 2. Configure the MCP Server
Create or update `.vscode/mcp.json` to include the Keeli MCP server. This allows Copilot to actually execute the task management tools.

```json
{
  "mcpServers": {
    "keeli": {
      "type": "stdio",
      "command": "python3",
      "args": ["/absolute/path/to/src/keeli/mcp_server.py"],
      "env": {
        "PYTHONPATH": "."
      }
    }
  }
}
```

## Cursor / Clade Desktop

For other clients, follow the standard MCP configuration process for your tool, pointing to the `src/keeli/mcp_server.py` file.

## Verification
Run `keeli doctor` to ensure your local environment is correctly structured.
In your LLM chat, try asking "What is my next task?". If configured correctly, the LLM will use the `keeli_next` tool.

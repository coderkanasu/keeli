# Task: Build Keeli MCP Server

**Status:** Completed
**Created:** 2026-02-22T10:00:00Z
**Completed:** 2026-02-22T10:15:00Z
**Depends On:** 

## Objective
Build a Model Context Protocol (MCP) server for Keeli to allow AI assistants (like Claude Desktop, Cursor, Copilot) to natively interact with the Keeli task board and framework.

## Requirements
- Expose Keeli commands (`next`, `list`, `complete`, `archive`) as MCP tools.
- Expose Keeli context (e.g., `project.md`, `decision.md`, `ai_log.md`) as MCP resources.
- Add a `keeli mcp` command to start the server over `stdio`.
- Update `setup.py` with the `mcp` dependency.
- Document how to configure Claude Desktop to use the Keeli MCP server.

## Checklist
- [x] Add `mcp` dependency to `setup.py`.
- [x] Create `src/keeli/mcp_server.py` with the MCP server implementation.
- [x] Register MCP tools for Keeli commands.
- [x] Register MCP resources for Keeli documentation.
- [x] Add `cmd_mcp` to `src/keeli/main.py` to launch the server.
- [x] Update `README.md` with MCP configuration instructions.
- [x] Test the MCP server locally.

## Notes
- The MCP server will communicate over `stdio`, which is the standard for local MCP integrations.
- We will use the official `mcp` Python SDK.
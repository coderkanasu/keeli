"""
Keeli MCP Server — Thin wrapper around Keeli CLI.
Provides task management tools to LLM agents.
"""

import os
import subprocess
import sys
import json
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("keeli")

def run_keeli(args):
    """Run keeli CLI and return output."""
    try:
        # Resolve project root for consistent behavior
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Use sys.executable to ensure we use the same python environment
        cmd = [sys.executable, "-m", "keeli.main"] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            cwd=project_root,
            env={**os.environ, "PYTHONPATH": f"{project_root}/src", "KEELI_ROOT": project_root}
        )
        if result.returncode != 0:
            return f"Error: {result.stderr or result.stdout}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds."
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def keeli_list(status: str = None):
    """List tasks, optionally filtered by status (backlog, active, review, blocked, archive)."""
    cmd = ["list"]
    if status:
        cmd.extend(["--status", status])
    return run_keeli(cmd)

@mcp.tool()
def keeli_get(task_id: str):
    """Retrieve the full content of a specific task."""
    return run_keeli(["get", task_id])

@mcp.tool()
def keeli_next():
    """Get the next recommended task to work on based on priority and age."""
    return run_keeli(["next"])

@mcp.tool()
def keeli_start(title: str, description: str = "", priority: str = "p2", tags: list = None):
    """Create a new task in the backlog. Use one priority: 'p0', 'p1', 'p2', 'high', 'medium', or 'low'."""
    cmd = ["start", title, "--priority", priority]
    if description:
        cmd.extend(["--description", description])
    if tags:
        # CLI expects space-separated tags or repeated flags
        for t in tags:
            cmd.extend(["--tags", t])
    return run_keeli(cmd)

@mcp.tool()
def keeli_active(task_id: str):
    """Mark a task as Active (In Progress)."""
    return run_keeli(["active", task_id])

@mcp.tool()
def keeli_complete(task_id: str):
    """Mark a task as completed (moves to archive)."""
    return run_keeli(["complete", task_id])

@mcp.tool()
def keeli_block(task_id: str):
    """Mark a task as blocked."""
    return run_keeli(["block", task_id])

@mcp.tool()
def keeli_unblock(task_id: str):
    """Unblock a task (moves back to backlog)."""
    return run_keeli(["unblock", task_id])

@mcp.tool()
def keeli_review(task_id: str):
    """Move a task to review status."""
    return run_keeli(["review", task_id])

@mcp.tool()
def keeli_digest(tier: str = "standard", budget: int = 2000):
    """Get a token-budgeted context snapshot. Use 'nano', 'brief', 'standard', or 'full'."""
    return run_keeli(["digest", "--tier", tier, "--budget", str(budget)])

@mcp.tool()
def keeli_insights():
    """Get velocity insights and team activity stats."""
    return run_keeli(["insights"])

@mcp.tool()
def keeli_sync():
    """Manually reconcile filesystem tasks with the index."""
    return run_keeli(["sync"])

@mcp.tool()
def keeli_history(task_id: str):
    """View the audit trail for a specific task."""
    return run_keeli(["history", task_id])

def main():
    mcp.run()

if __name__ == "__main__":
    main()


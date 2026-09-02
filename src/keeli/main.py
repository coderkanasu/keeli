#!/usr/bin/env python3
"""
Keeli v6.0 - Legacy CLI Interface (DEPRECATED)

This CLI interface is disabled by default. Keeli is designed to be used
primarily through the MCP (Model Context Protocol) server for AI integration.

To enable the CLI, set the environment variable: KEELI_ENABLE_CLI=1

For MCP integration, use: python -m keeli.mcp_server
"""

import os
import sys

# Check if CLI is explicitly enabled
if not os.getenv("KEELI_ENABLE_CLI"):
    print("Keeli CLI is disabled by default.", file=sys.stderr)
    print("Keeli is designed for MCP (Model Context Protocol) integration with AI tools.", file=sys.stderr)
    print("", file=sys.stderr)
    print("To use Keeli:", file=sys.stderr)
    print("1. Configure MCP server in your AI tool (Cursor, GitHub Copilot, etc.)", file=sys.stderr)
    print("2. Use the MCP tools: keeli_tasks, keeli_context, keeli_sessions, keeli_memory, keeli_knowledge, keeli_system", file=sys.stderr)
    print("", file=sys.stderr)
    print("To enable this legacy CLI, set: KEELI_ENABLE_CLI=1", file=sys.stderr)
    sys.exit(1)

# Legacy CLI implementation (only runs if KEELI_ENABLE_CLI=1)
import argparse
import re
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from keeli.schema import init_db
from keeli.templates import TASK_TEMPLATE, CLAUDE_MD, SKILL_TEMPLATE, MCP_TEMPLATE
from keeli.engine import KeeliEngine

VERSION = "6.0.0"

# --- Legacy CLI Wrappers ---
engine = KeeliEngine()

def start(args):
    tid = engine.start(
        title=args.title,
        priority_raw=args.priority,
        tags=args.tags,
        description=args.description,
        depends_on=args.depends_on
    )
    print(f"Created task {tid}")

def sync(args):
    count, corrected = engine.sync()
    print(f"Synced {count} tasks. {corrected} corrected.")

def next_task(args):
    task = engine.next_task()
    if task:
        print(f"{task['id']}: {task['title']} ({task['status'].upper()}, {task['priority']})")
    else:
        print("No tasks pending.")

def list_tasks(args):
    tasks = engine.list_tasks(status=args.status)
    if args.json:
        print(json.dumps(tasks, indent=2))
        return
    for r in tasks:
        print(f"[{r['status'].upper()}] {r['id']}: {r['title']} ({r['priority']})")

def get_task(args):
    try:
        print(engine.get_task(args.task_id))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

def digest(args):
    content = engine.digest(tier=args.tier, budget=args.budget)
    if args.json:
        print(json.dumps({"content": content, "tier": args.tier, "budget": args.budget}))
    else:
        print(content)
        # Tiktoken aware approx
        tokens = len(content.split()) * 1.3
        print(f"\n📊 ~{int(tokens)} tokens (budget: {args.budget})", file=sys.stderr)

def session_start(args):
    sid = engine.session_start(name=args.name)
    print(f"Session started: {sid}")

def session_focus(args):
    engine.session_focus(task_id=args.task_id)
    print(f"Focused on task: {args.task_id}")

def session_checkpoint(args):
    cid = engine.session_checkpoint(note=args.note)
    print(f"Checkpoint created: {cid}")

def session_list(args):
    sessions = engine.conn.execute("SELECT id, name, created, focus_task_id FROM sessions ORDER BY created DESC").fetchall()
    for s in sessions:
        focus = f" [FOCUS: {s['focus_task_id']}]" if s['focus_task_id'] else ""
        print(f"{s['id']} | {s['name']} | {s['created']}{focus}")

def history(args):
    rows = engine.conn.execute("SELECT created, action, actor, details FROM audit WHERE item_id = ? ORDER BY event_id DESC", (args.task_id,)).fetchall()
    for r in rows:
        print(f"{r['created']} | {r['action'].upper()} | {r['actor']} | {r['details']}")

def insights(args):
    print("## Keeli Velocity Insights")
    completions = engine.conn.execute("""
        SELECT a1.item_id, a1.created as start_time, a2.created as end_time, t.title
        FROM audit a1
        JOIN audit a2 ON a1.item_id = a2.item_id
        JOIN task_index t ON a1.item_id = t.id
        WHERE a1.action = 'active' AND a2.action = 'archive'
        AND a1.event_id < a2.event_id
    """).fetchall()
    
    if completions:
        print("\n### ⏱ Average Completion (Cycle Time)")
        total_seconds = 0
        for c in completions:
            start_ts = datetime.fromisoformat(c['start_time'].replace("Z", "+00:00"))
            end_ts = datetime.fromisoformat(c['end_time'].replace("Z", "+00:00"))
            duration = (end_ts - start_ts).total_seconds()
            total_seconds += duration
            print(f"- {c['item_id']}: {duration/60:.1f} mins ({c['title']})")
        print(f"\n**Avg Cycle Time:** {(total_seconds / len(completions))/60:.1f} minutes")
    else:
        print("\nNo completion data yet.")

    actors = engine.conn.execute("SELECT actor, COUNT(*) as count FROM audit GROUP BY actor ORDER BY count DESC").fetchall()
    for a in actors:
        print(f"- {a['actor']}: {a['count']} events")

def validate(args):
    errors = []
    tasks = engine.conn.execute("SELECT id, title, tags FROM task_index").fetchall()
    all_ids = {t['id'] for t in tasks}
    for t in tasks:
        deps = re.findall(r"(T-\d{4})", t['tags'])
        for d in deps:
            if d not in all_ids:
                errors.append(f"{t['id']}: Broken dependency '{d}'")
    if errors:
        for e in errors: print(f"❌ {e}")
        sys.exit(1)
    print("✅ Validation passed.")

def doctor(args):
    print("🔍 Keeli Health Check")
    print(f"  Root: {engine.root_dir}")
    print(f"  DB:   {engine.db_path} ({'OK' if engine.db_path.exists() else 'Missing - will be created on sync'})")
    
    for s, d in engine.status_dirs.items():
        status = 'OK' if d.exists() else 'MISSING'
        print(f"  Folder {s:10}: {status}")
    
    count, corrected = engine.sync()
    print(f"✅ Indexing: {count} tasks found, {corrected} corrected.")
    
    # MCP Check
    mcp_config_path = engine.root_dir / ".vscode" / "mcp.json"
    if mcp_config_path.exists():
        print(f"✅ MCP Configuration: Found at {mcp_config_path}")
    else:
        print("💡 Configure MCP integration for AI tool usage.")

def mcp_config(args):
    py_path = sys.executable
    config = {
        "mcpServers": {
            "keeli": {
                "command": py_path,
                "args": ["-m", "keeli.mcp_server"],
                "env": {
                    "PYTHONPATH": str(engine.root_dir / "src")
                },
                "type": "stdio"
            }
        }
    }
    print("\n--- MCP CONFIGURATION (Add to .vscode/mcp.json) ---")
    print(json.dumps(config, indent=2))
    print("---------------------------------------------------\n")

def main():
    parser = argparse.ArgumentParser(description="Keeli v6.0 Legacy CLI (DEPRECATED - Use MCP instead)")
    parser.add_argument("--version", action="version", version=f"Keeli {VERSION}")
    subparsers = parser.add_subparsers(dest="command")

    p_start = subparsers.add_parser("start", aliases=["create"])
    p_start.add_argument("title", nargs="?", default="Untitled Task")
    p_start.add_argument("--priority", default="p2")
    p_start.add_argument("--tags", nargs="*", default=[])
    p_start.add_argument("--description")
    p_start.add_argument("--depends-on")

    subparsers.add_parser("active", aliases=["progress"]).add_argument("task_id")
    subparsers.add_parser("complete", aliases=["archive"]).add_argument("task_id")
    subparsers.add_parser("review").add_argument("task_id")
    subparsers.add_parser("block").add_argument("task_id")
    subparsers.add_parser("unblock").add_argument("task_id")
    subparsers.add_parser("reopen").add_argument("task_id")

    p_list = subparsers.add_parser("list")
    p_list.add_argument("--status")
    p_list.add_argument("--json", action="store_true")
    
    subparsers.add_parser("next")
    subparsers.add_parser("get").add_argument("task_id")
    subparsers.add_parser("history").add_argument("task_id")
    subparsers.add_parser("insights")
    
    p_digest = subparsers.add_parser("digest")
    p_digest.add_argument("--tier", choices=["nano", "brief", "standard", "full"], default="standard")
    p_digest.add_argument("--budget", type=int, default=2000)
    p_digest.add_argument("--json", action="store_true")

    # Session Management
    p_sess = subparsers.add_parser("session")
    s_sub = p_sess.add_subparsers(dest="session_cmd")
    s_start = s_sub.add_parser("start")
    s_start.add_argument("name", nargs="?", default="default")
    s_focus = s_sub.add_parser("focus")
    s_focus.add_argument("task_id")
    s_check = s_sub.add_parser("checkpoint")
    s_check.add_argument("--note")
    s_sub.add_parser("list")

    subparsers.add_parser("mcp")
    subparsers.add_parser("mcp-config")
    subparsers.add_parser("sync")
    subparsers.add_parser("validate")
    subparsers.add_parser("doctor")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cmd = args.command
    if cmd in ["start", "create"]: start(args)
    elif cmd in ["active", "progress"]: engine.move_task(args.task_id, "active")
    elif cmd in ["complete", "archive"]: engine.move_task(args.task_id, "archive")
    elif cmd == "review": engine.move_task(args.task_id, "review")
    elif cmd == "block": engine.move_task(args.task_id, "blocked")
    elif cmd == "unblock": engine.move_task(args.task_id, "backlog")
    elif cmd == "reopen": engine.move_task(args.task_id, "backlog")
    elif cmd == "sync": sync(args)
    elif cmd == "next": next_task(args)
    elif cmd == "list": list_tasks(args)
    elif cmd == "get": get_task(args)
    elif cmd == "digest": digest(args)
    elif cmd == "session":
        if args.session_cmd == "start": session_start(args)
        elif args.session_cmd == "focus": session_focus(args)
        elif args.session_cmd == "checkpoint": session_checkpoint(args)
        elif args.session_cmd == "list": session_list(args)
    elif cmd == "insights": insights(args)
    elif cmd == "history": history(args)
    elif cmd == "validate": validate(args)
    elif cmd == "mcp":
        from keeli.mcp_server import main as mcp_main
        mcp_main()
    elif cmd == "mcp-config": mcp_config(args)
    elif cmd == "doctor": doctor(args)

if __name__ == "__main__":
    main()

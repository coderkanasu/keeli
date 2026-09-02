#!/usr/bin/env python3
"""
Keeli v6.0 CLI — LEGACY INTERFACE (DEPRECATED)

This CLI is disabled by default. Keeli is designed for MCP integration with AI tools.
To enable this CLI, set environment variable: KEELI_ENABLE_CLI=1

For MCP integration, use: python -m keeli.mcp_server

Critical fixes applied:
  • Input validation on field mutations
  • No expected_hash parameters (replaced by CRDT auto-merge)
  • Explicit --actor, --branch, --session on all commands
  • doctor command verifies .gitignore isolation
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

import argparse
import json
import os
import sys
from pathlib import Path

from keeli.engine import KeeliEngine
from keeli.version import get_version

engine = KeeliEngine()

_VALID_FIELDS = {"status", "priority", "title", "description", "depends_on", "completed"}

def _validate_field(field: str) -> None:
    if field not in _VALID_FIELDS and field != "tags":
        raise ValueError(f"Invalid field '{field}'. Allowed: {_VALID_FIELDS} or tags")

def _coerce_value(value, field: str):
    if field == "status":
        v = str(value).strip().lower()
        if v not in {"backlog", "active", "review", "blocked", "archive"}:
            raise ValueError(f"Invalid status '{v}'")
        return v
    if field == "priority":
        v = str(value).strip().upper()
        if v not in {"P0", "P1", "P2"}:
            raise ValueError(f"Invalid priority '{v}'")
        return v
    return str(value).strip()


def start(args):
    tid = engine.start(
        title=args.title,
        priority_raw=args.priority,
        tags=args.tags,
        description=args.description,
        depends_on=args.depends_on,
        actor=args.actor,
        branch=args.branch,
        session_id=args.session,
    )
    print(f"Created task {tid}")


def sync(args):
    count, corrected = engine.sync()
    print(f"Synced {count} tasks. {corrected} metadata corrections applied.")


def next_task(args):
    task = engine.next_task(session_id=args.session, branch=args.branch)
    if task:
        vc = json.loads(task.get("vector_clock", "{}"))
        print(f"{task['id']}: {task['title']} ({task['status'].upper()}, {task['priority']}) [VC: {vc}]")
    else:
        print("No tasks pending.")


def list_tasks(args):
    tasks = engine.list_tasks(status=args.status, branch=args.branch)
    if args.json:
        print(json.dumps(tasks, indent=2))
        return
    for r in tasks:
        vc = json.loads(r.get("vector_clock", "{}"))
        print(f"[{r['status'].upper()}] {r['id']}: {r['title']} ({r['priority']}) [VC: {vc}]")


def get_task(args):
    try:
        print(engine.get_task(args.task_id))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def get_state(args):
    try:
        state = engine.get_task_state(args.task_id)
        print(json.dumps(state, indent=2))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def digest(args):
    content = engine.digest(tier=args.tier, budget=args.budget, session_id=args.session, branch=args.branch)
    if args.json:
        print(json.dumps({"content": content, "tier": args.tier, "budget": args.budget}))
    else:
        print(content)
        tokens = int(len(content.split()) * 1.3)
        print(f"\n📊 ~{tokens} tokens (budget: {args.budget})", file=sys.stderr)


def session_start(args):
    sid = engine.session_start(name=args.name, branch=args.branch, focus_task_id=args.focus)
    print(f"Session started: {sid}")


def session_focus(args):
    try:
        engine.session_focus(task_id=args.task_id, session_id=args.session)
        print(f"Focused on task: {args.task_id}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def session_checkpoint(args):
    try:
        cid = engine.session_checkpoint(note=args.note, session_id=args.session, pending_decisions=args.pending)
        print(f"Checkpoint created: {cid}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def session_list(args):
    sessions = engine.session_list()
    for s in sessions:
        focus = f" [FOCUS: {s['focus_task_id']}]" if s['focus_task_id'] else ""
        print(f"{s['session_id']} | {s['goal']} | {s['branch_name'] or 'unspecified'} | {s['created']}{focus}")


def history(args):
    rows = engine.history(args.task_id)
    for r in rows:
        print(f"{r['created']} | {r['actor']} | {r['action'].upper()} | {r.get('field', '')}={r.get('value', '')}")


def edit_field(args):
    try:
        _validate_field(args.field)
        coerced = _coerce_value(args.value, args.field)
        engine.edit_task_field(
            args.task_id, args.field, coerced,
            actor=args.actor, branch=args.branch, session_id=args.session,
        )
        print(f"Updated {args.field} on {args.task_id} to '{coerced}'")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def add_tags(args):
    try:
        engine.add_tags(args.task_id, args.tags, actor=args.actor, branch=args.branch, session_id=args.session)
        print(f"Tags added to {args.task_id}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def remove_tags(args):
    try:
        engine.remove_tags(args.task_id, args.tags, actor=args.actor, branch=args.branch, session_id=args.session)
        print(f"Tags removed from {args.task_id}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def detect_conflicts(args):
    conflicts = engine.detect_conflicts(args.task_id, args.lookback)
    if not conflicts:
        print(f"No conflicts detected for {args.task_id} in last {args.lookback}s.")
        return
    for c in conflicts:
        print(f"⚠️  {c['field']}: concurrent edit by {c['actors']} (resolved via {c['resolution']})")


def doctor(args):
    print("🔍 Keeli v6.0 Health Check")
    print(f"  Root:      {engine.root_dir}")
    print(f"  Workspace: {engine.workspace_dir} ({'OK' if engine.workspace_dir.exists() else 'MISSING'})")
    print(f"  DB:        {engine.db_path} ({'OK' if engine.db_path.exists() else 'Missing - will initialize'})")

    for s, d in engine.status_dirs.items():
        print(f"  Folder {s:10}: {'OK' if d.exists() else 'MISSING'}")

    count, corrected = engine.sync()
    print(f"✅ Indexing: {count} tasks found, {corrected} corrected.")

    gitignore = engine.root_dir / ".gitignore"
    if gitignore.exists() and ".keeli/" in gitignore.read_text():
        print("✅ .gitignore: .keeli/ is excluded from code indexing")
    else:
        print("⚠️  .gitignore: .keeli/ not found — LLM tools may index task noise")


def main():
    parser = argparse.ArgumentParser(description="Keeli v6.0 Task Engine (CRDT Architecture)")
    parser.add_argument("--version", action="version", version=f"Keeli {get_version()}")
    parser.add_argument("--actor", default=os.getenv("KEELI_ACTOR", os.getenv("USER", "agent")), help="Agent actor identity")
    parser.add_argument("--branch", default=None, help="Git branch scope")
    parser.add_argument("--session", default=None, help="Session ID for scoped operations")

    subparsers = parser.add_subparsers(dest="command")

    # ── Task Lifecycle ──
    p_start = subparsers.add_parser("start", aliases=["create"])
    p_start.add_argument("title", nargs="?", default="Untitled Task")
    p_start.add_argument("--priority", default="p2")
    p_start.add_argument("--tags", nargs="*", default=[])
    p_start.add_argument("--description")
    p_start.add_argument("--depends-on")

    p_active = subparsers.add_parser("active", aliases=["progress"])
    p_active.add_argument("task_id")

    p_comp = subparsers.add_parser("complete", aliases=["archive"])
    p_comp.add_argument("task_id")
    p_comp.add_argument("--rationale", default="")

    p_block = subparsers.add_parser("block")
    p_block.add_argument("task_id")
    p_block.add_argument("--reason", default="")

    subparsers.add_parser("unblock").add_argument("task_id")
    subparsers.add_parser("reopen").add_argument("task_id")
    subparsers.add_parser("sync")

    # ── Query ──
    p_next = subparsers.add_parser("next")
    p_list = subparsers.add_parser("list")
    p_list.add_argument("--status")
    p_list.add_argument("--json", action="store_true")

    subparsers.add_parser("get").add_argument("task_id")
    p_state = subparsers.add_parser("state")
    p_state.add_argument("task_id")
    p_state.add_argument("--json", action="store_true")

    subparsers.add_parser("history").add_argument("task_id")

    # ── Field Editing (CRDT-native) ──
    p_edit = subparsers.add_parser("edit")
    p_edit.add_argument("task_id")
    p_edit.add_argument("--field", required=True, help="Field name: status, priority, title, description, depends_on, completed")
    p_edit.add_argument("--value", required=True, help="New value")

    p_tag_add = subparsers.add_parser("tag-add")
    p_tag_add.add_argument("task_id")
    p_tag_add.add_argument("tags", nargs="+")

    p_tag_rm = subparsers.add_parser("tag-rm")
    p_tag_rm.add_argument("task_id")
    p_tag_rm.add_argument("tags", nargs="+")

    p_conflicts = subparsers.add_parser("conflicts")
    p_conflicts.add_argument("task_id")
    p_conflicts.add_argument("--lookback", type=int, default=300, help="Seconds to look back")

    # ── Digest ──
    p_digest = subparsers.add_parser("digest")
    p_digest.add_argument("--tier", choices=["nano", "brief", "standard", "full"], default="standard")
    p_digest.add_argument("--budget", type=int, default=2000)
    p_digest.add_argument("--json", action="store_true")

    # ── Session Management ──
    p_sess = subparsers.add_parser("session")
    s_sub = p_sess.add_subparsers(dest="session_cmd")
    s_start = s_sub.add_parser("start")
    s_start.add_argument("name", nargs="?", default="Investigation")
    s_start.add_argument("--focus")
    s_focus = s_sub.add_parser("focus")
    s_focus.add_argument("task_id")
    s_check = s_sub.add_parser("checkpoint")
    s_check.add_argument("--note", default="Sync point")
    s_check.add_argument("--pending", nargs="*", default=[])
    s_sub.add_parser("list")

    subparsers.add_parser("doctor")
    subparsers.add_parser("mcp")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cmd = args.command
    try:
        if cmd in ["start", "create"]: start(args)
        elif cmd in ["active", "progress"]: engine.move_task(args.task_id, "active", actor=args.actor, branch=args.branch, session_id=args.session)
        elif cmd in ["complete", "archive"]: engine.move_task(args.task_id, "archive", actor=args.actor, branch=args.branch, session_id=args.session, rationale=args.rationale)
        elif cmd == "block": engine.move_task(args.task_id, "blocked", actor=args.actor, branch=args.branch, session_id=args.session, rationale=args.reason)
        elif cmd in ["unblock", "reopen"]: engine.move_task(args.task_id, "backlog", actor=args.actor, branch=args.branch, session_id=args.session)
        elif cmd == "sync": sync(args)
        elif cmd == "next": next_task(args)
        elif cmd == "list": list_tasks(args)
        elif cmd == "get": get_task(args)
        elif cmd == "state": get_state(args)
        elif cmd == "digest": digest(args)
        elif cmd == "history": history(args)
        elif cmd == "edit": edit_field(args)
        elif cmd == "tag-add": add_tags(args)
        elif cmd == "tag-rm": remove_tags(args)
        elif cmd == "conflicts": detect_conflicts(args)
        elif cmd == "session":
            if args.session_cmd == "start": session_start(args)
            elif args.session_cmd == "focus": session_focus(args)
            elif args.session_cmd == "checkpoint": session_checkpoint(args)
            elif args.session_cmd == "list": session_list(args)
        elif cmd == "doctor": doctor(args)
        elif cmd == "mcp":
            from keeli.mcp_server import main as mcp_main
            mcp_main()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

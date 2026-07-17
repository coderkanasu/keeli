#!/usr/bin/env python3
"""
Keeli v4.0.1 CLI — Source of truth is the filesystem.
Directory = Status.
Index = Performance.
Audit = Integrity.
"""

import argparse
import os
import re
import sqlite3
import sys
import json
import string
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from keeli.schema import init_db
from keeli.templates import TASK_TEMPLATE, CLAUDE_MD, SKILL_TEMPLATE, MCP_TEMPLATE

VERSION = "4.0.1"

# --- Constants ---
def find_project_root(start_path: Path) -> Path:
    """Walk up from start_path to find project root (containing .git or docs/tasks)."""
    # Check environment override first
    if os.getenv("KEELI_ROOT"):
        return Path(os.getenv("KEELI_ROOT")).absolute()

    curr = start_path.absolute()
    for _ in range(20):
        # Prefer .git as a stronger root signal
        if (curr / ".git").exists():
            return curr
        if (curr / "docs" / "tasks").exists():
            return curr
        if curr.parent == curr:
            break
        curr = curr.parent
    return start_path.absolute()

ROOT_DIR = find_project_root(Path.cwd())
DOCS_DIR = ROOT_DIR / "docs"
TASKS_DIR = DOCS_DIR / "tasks"
VALID_STATUSES = ["backlog", "active", "review", "blocked", "archive"]
STATUS_DIRS = {s: TASKS_DIR / s for s in VALID_STATUSES}
DB_PATH = ROOT_DIR / "keeli_state.db"

# --- Helpers ---
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")

def parse_task_file(content: str, path: Path) -> Dict[str, Any]:
    """Extract metadata with robust patterns and fallback."""
    try:
        # Match ID and Title specifically at start of file
        match = re.search(r"^# (T-\d{4})[:\s]+(.+)$", content, re.MULTILINE)
        if not match:
            match = re.search(r"^# \[(T-\d{4})\]\s+(.+)$", content, re.MULTILINE)
            
        if match:
            task_id = match.group(1)
            title = match.group(2).strip()
        else:
            id_match = re.search(r"(T-\d{4})", content[:200])
            task_id = id_match.group(1) if id_match else None
            title = "Untitled Task"

        status_match = re.search(r"^\*\*Status:\*\* (.+)$", content, re.MULTILINE)
        priority_match = re.search(r"^\*\*Priority:\*\* (.+)$", content, re.MULTILINE)
        created_match = re.search(r"^\*\*Created:\*\* (.+)$", content, re.MULTILINE)
        
        tags = []
        tags_match = re.search(r"^\*\*Tags:\*\* (.+)$", content, re.MULTILINE)
        if tags_match:
            tags_line = tags_match.group(1)
            tags = re.findall(r"([a-z0-9-]+:[a-z0-9-]+)", tags_line, re.IGNORECASE)

        # Better directory inference: find which status dir it is under
        inferred_status = "backlog"
        for s, d in STATUS_DIRS.items():
            if str(path.absolute()).startswith(str(d.absolute())):
                inferred_status = s
                break

        return {
            "id": task_id,
            "title": title,
            "slug": path.stem.replace(f"{task_id}-", "") if task_id else path.stem,
            "status": status_match.group(1).strip().lower() if status_match else inferred_status,
            "priority": (priority_match.group(1).strip().upper() if priority_match else "P1"),
            "created": created_match.group(1).strip() if created_match else "",
            "tags": ",".join(tags),
            "path": str(path)
        }
    except Exception as e:
        print(f"Error parsing {path}: {e}", file=sys.stderr)
        return {}

def ensure_synced() -> sqlite3.Connection:
    """Check if index is fresh; auto-sync if not. Returns connection."""
    conn = init_db(DB_PATH)
    if not DB_PATH.exists() or not TASKS_DIR.exists():
        return conn
    
    try:
        last_sync_row = conn.execute("SELECT MAX(updated) FROM task_index").fetchone()
        last_sync_ts = 0
        if last_sync_row and last_sync_row[0]:
            last_sync_ts = datetime.fromisoformat(last_sync_row[0].replace("Z", "+00:00")).timestamp()
    except sqlite3.OperationalError:
        sync(None, conn)
        return conn

    # Optimized check: only directory mtimes for top-level status folders
    latest_mtime = 0
    for folder in STATUS_DIRS.values():
        if folder.exists():
            latest_mtime = max(latest_mtime, folder.stat().st_mtime)
    
    if latest_mtime > last_sync_ts + 0.5: # tighter buffer
        sync(None, conn)
        
    return conn

def log_event(conn: sqlite3.Connection, item_id: Optional[str], action: str, actor: str, details: str):
    conn.execute(
        "INSERT INTO audit (item_id, action, actor, details, created) VALUES (?, ?, ?, ?, ?)",
        (item_id, action, actor, details, _now_iso())
    )
    conn.commit()

def _git_commit(message: str, file_path: Optional[Path] = None):
    """Attempt to commit task changes to git, scoped to file or TASKS_DIR."""
    try:
        target = str(file_path) if file_path else str(TASKS_DIR)
        check = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True)
        if check.returncode != 0: return

        subprocess.run(["git", "add", target], check=True, capture_output=True)
        # Check if something is staged
        diff = subprocess.run(["git", "diff", "--cached", "--quiet", "--", target])
        if diff.returncode == 0: return # Nothing to commit
        
        subprocess.run(["git", "commit", "-m", message, "--", target], check=True, capture_output=True)
    except Exception as e:
        print(f"⚠️ Git commit failed: {e}", file=sys.stderr)

# --- Commands ---
def start(args):
    conn = ensure_synced()
    
    # Map friendly priority names
    p_map = {
        "high": "P0", "medium": "P1", "low": "P2",
        "p0": "P0", "p1": "P1", "p2": "P2"
    }
    priority = p_map.get(args.priority.lower(), "P2")

    ids = []
    for f in TASKS_DIR.rglob("T-*.md"):
        m = re.search(r"T-(\d{4})", f.name)
        if m: ids.append(int(m.group(1)))
    
    next_num = (max(ids) + 1) if ids else 1
    next_id = f"T-{next_num:04d}"

    slug = _slugify(args.title or "untitled")
    filename = f"{next_id}-{slug}.md"
    filepath = STATUS_DIRS['backlog'] / filename

    # Safety: injection-proof template filling
    template = string.Template(TASK_TEMPLATE)
    content = template.safe_substitute(
        task_id=next_id,
        title=args.title or "Untitled Task",
        status="Backlog",
        priority=priority,
        timestamp=_now_iso(),
        depends_on=args.depends_on or "—",
        tags=", ".join(args.tags) if args.tags else "—",
        description=args.description or "No description provided."
    )

    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)
    
    with conn:
        conn.execute(
            "INSERT INTO task_index (id, slug, title, status, priority, created, tags, path, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (next_id, slug, args.title, "backlog", priority, _now_iso(), ",".join(args.tags) if args.tags else "", str(filepath), _now_iso())
        )
        log_event(conn, next_id, "start", os.getenv("USER", "developer"), f"Created task: {args.title}")
    
    _git_commit(f"keeli start {next_id}: {args.title}", filepath)
    print(f"Created task {next_id} at {filepath}")

def sync(args, conn=None):
    if not conn:
        conn = init_db(DB_PATH)
    
    try:
        seen_ids = {}
        count = 0
        corrected = 0
        
        # Collect data first to minimize transaction time
        rows = []
        files_to_update = []
        
        for status, folder in STATUS_DIRS.items():
            if not folder.exists(): continue
            for md_file in folder.glob("*.md"):
                content = md_file.read_text()
                data = parse_task_file(content, md_file)
                if not data or not data.get('id'): continue
                
                tid = data['id']
                if tid in seen_ids:
                    print(f"⚠️  Ignoring duplicate ID {tid} at {md_file}", file=sys.stderr)
                    continue
                seen_ids[tid] = md_file

                if data['status'].lower() != status.lower():
                    # Non-destructive correction: update data but only warn unless fix requested
                    new_status_str = status.capitalize()
                    new_content = re.sub(r"^\*\*Status:\*\* .+$", f"**Status:** {new_status_str}", content, flags=re.MULTILINE)
                    if "**Status:**" not in new_content:
                        if "---" in new_content:
                            new_content = new_content.replace("---", f"**Status:** {new_status_str}\n---", 1)
                    
                    if new_content != content:
                        files_to_update.append((md_file, new_content))
                        data['status'] = status
                        corrected += 1

                rows.append((data['id'], data['slug'], data['title'], status, data['priority'], data['created'], data['tags'], data['path'], _now_iso()))
                count += 1

        with conn:
            conn.execute("DELETE FROM task_index")
            conn.executemany(
                "INSERT INTO task_index (id, slug, title, status, priority, created, tags, path, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows
            )
            for f, c in files_to_update:
                f.write_text(c)
            
            log_event(conn, None, "sync", "system", f"Rebuilt index: {count} tasks, {corrected} corrected")
        
        if args:
            print(f"Synced {count} tasks. {corrected} corrected.")
    except Exception as e:
        print(f"❌ Sync failed: {e}", file=sys.stderr)
        sys.exit(1)

def _move_task(task_id: str, target_status: str, conn: sqlite3.Connection):
    if target_status not in STATUS_DIRS:
        print(f"Error: Invalid status {target_status}", file=sys.stderr)
        sys.exit(1)

    row = conn.execute("SELECT id, path, title FROM task_index WHERE id = ? OR slug = ?", (task_id, task_id)).fetchone()
    if not row:
        print(f"Error: Task {task_id} not found.", file=sys.stderr)
        sys.exit(1)
    
    tid, current_path, title = row['id'], Path(row['path']), row['title']
    if not current_path.exists():
        print(f"Error: File {current_path} missing.", file=sys.stderr)
        sys.exit(1)

    new_path = STATUS_DIRS[target_status] / current_path.name
    STATUS_DIRS[target_status].mkdir(parents=True, exist_ok=True)
    os.rename(current_path, new_path)
    
    content = new_path.read_text()
    new_content = re.sub(r"^\*\*Status:\*\* .+$", f"**Status:** {target_status.capitalize()}", content, flags=re.MULTILINE)
    
    if target_status == "archive":
        ts = _now_iso()
        if "**Completed:**" in new_content:
            new_content = re.sub(r"^\*\*Completed:\*\* .+$", f"**Completed:** {ts}", new_content, flags=re.MULTILINE)
        else:
            new_content = re.sub(r"^(\*\*Priority:\*\* .+)$", f"\\1\n**Completed:** {ts}", new_content, flags=re.MULTILINE)
    else:
        # Clear completed date if moving away from archive
        new_content = re.sub(r"^\*\*Completed:\*\* .+$", "**Completed:** —", new_content, flags=re.MULTILINE)
    
    new_path.write_text(new_content)
    
    with conn:
        conn.execute(
            "UPDATE task_index SET status = ?, path = ?, updated = ? WHERE id = ?",
            (target_status, str(new_path), _now_iso(), tid)
        )
        log_event(conn, tid, target_status, os.getenv("USER", "developer"), f"Moved to {target_status}")
    
    _git_commit(f"keeli {target_status} {tid}: {title}", new_path)
    print(f"Moved {tid} to {target_status}")

def next_task(args):
    conn = ensure_synced()
    query = """
    SELECT * FROM task_index 
    WHERE status IN ('backlog', 'active') 
    ORDER BY 
        CASE WHEN priority = 'P0' THEN 0 WHEN priority = 'P1' THEN 1 WHEN priority = 'P2' THEN 2 ELSE 3 END ASC,
        CASE WHEN (created IS NULL OR created = '') THEN '9999' ELSE created END ASC
    LIMIT 1;
    """
    row = conn.execute(query).fetchone()
    if row:
        print(f"{row['id']}: {row['title']} ({row['status'].upper()}, {row['priority']})")
    else:
        print("No tasks pending.")

def list_tasks(args):
    conn = ensure_synced()
    query = "SELECT id, title, status, priority FROM task_index"
    params = []
    if args.status:
        query += " WHERE status = ? COLLATE NOCASE"
        params.append(args.status.lower())
    
    rows = conn.execute(query, params).fetchall()
    if args.json:
        print(json.dumps([dict(r) for r in rows], indent=2))
        return

    for r in rows:
        print(f"[{r['status'].upper()}] {r['id']}: {r['title']} ({r['priority']})")

def get_task(args):
    conn = ensure_synced()
    row = conn.execute("SELECT path FROM task_index WHERE id = ? OR slug = ?", (args.task_id, args.task_id)).fetchone()
    if row:
        path = Path(row['path'])
        if path.exists():
            print(path.read_text())
        else:
            print(f"Error: File {path} missing.", file=sys.stderr); sys.exit(1)
    else:
        print(f"Task {args.task_id} not found.", file=sys.stderr); sys.exit(1)

def digest(args):
    conn = ensure_synced()
    budget = args.budget
    output = []
    
    tier = getattr(args, 'tier', 'standard').lower()
    
    # Stats
    stats = conn.execute("SELECT status, COUNT(*) as count FROM task_index GROUP BY status").fetchall()
    if stats:
        output.append("## Status Summary")
        stat_line = " | ".join([f"{s['status'].upper()}: {s['count']}" for s in stats])
        output.append(stat_line)
        output.append("")

    active = conn.execute("SELECT id, title, priority FROM task_index WHERE status = 'active'").fetchall()
    if active:
        output.append("## Active Tasks")
        for a in active:
            output.append(f"- {a['id']}: {a['title']} ({a['priority']})")
        output.append("")
    
    if tier == 'nano' and active:
        print("\n".join(output))
        return

    if tier != 'brief':
        limit = 10 if tier == 'full' else 5
        backlog = conn.execute(f"SELECT id, title, priority FROM task_index WHERE status = 'backlog' ORDER BY 1 ASC LIMIT {limit}").fetchall()
        if backlog:
            output.append(f"## Backlog (Top {len(backlog)})")
            for b in backlog:
                output.append(f"- {b['id']}: {b['title']} ({b['priority']})")
            output.append("")

    if tier in ['standard', 'full']:
        # Fallback to README if CLAUDE.md is missing
        overview_file = ROOT_DIR / "CLAUDE.md"
        if not overview_file.exists():
            overview_file = ROOT_DIR / "README.md"
            
        if overview_file.exists():
            output.append(f"## Project Overview ({overview_file.name})")
            lines = overview_file.read_text().splitlines()
            output.extend(lines[:15] if tier == 'standard' else lines)
            output.append("")

    logs = conn.execute("SELECT created, item_id, actor, action, details FROM audit ORDER BY event_id DESC LIMIT 5").fetchall()
    if logs:
        output.append("## Recent Log")
        for l in logs:
            item = l['item_id'] or "SYS"
            output.append(f"- {l['created']} | {l['actor']} | {l['action'].upper()} | {l['details']}")

    final_text = "\n".join(output)
    if args.json:
        print(json.dumps({"content": final_text, "tier": tier, "budget": budget}))
    else:
        print(final_text)
        tokens = int(len(final_text.split()) * 1.35)
        print(f"\n📊 ~{tokens} tokens (budget: {budget})", file=sys.stderr)

def history(args):
    conn = ensure_synced()
    rows = conn.execute("SELECT created, action, actor, details FROM audit WHERE item_id = ? ORDER BY event_id DESC", (args.task_id,)).fetchall()
    for r in rows:
        print(f"{r['created']} | {r['action'].upper()} | {r['actor']} | {r['details']}")

def insights(args):
    conn = ensure_synced()
    print("## Keeli Velocity Insights")
    
    # Task completion time
    completions = conn.execute("""
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
            start = datetime.fromisoformat(c['start_time'].replace("Z", "+00:00"))
            end = datetime.fromisoformat(c['end_time'].replace("Z", "+00:00"))
            duration = (end - start).total_seconds()
            total_seconds += duration
            print(f"- {c['item_id']}: {duration/60:.1f} mins ({c['title']})")
        
        avg = total_seconds / len(completions)
        print(f"\n**Avg Cycle Time:** {avg/60:.1f} minutes")
    else:
        print("\nNo completion data yet.")

    # Top Actors
    actors = conn.execute("SELECT actor, COUNT(*) as count FROM audit GROUP BY actor ORDER BY count DESC").fetchall()
    if actors:
        print("\n### 👤 Most Active Contributors")
        for a in actors:
            print(f"- {a['actor']}: {a['count']} events")

def validate(args):
    conn = ensure_synced()
    errors = []
    tasks = conn.execute("SELECT id, title, tags FROM task_index").fetchall()
    all_ids = {t['id'] for t in tasks}
    
    for t in tasks:
        deps = re.findall(r"(T-\d{4})", t['tags'])
        for d in deps:
            if d not in all_ids:
                errors.append(f"{t['id']}: Broken dependency '{d}'")

    if errors:
        for e in errors: print(f"❌ {e}")
        sys.exit(1)
    else:
        print("✅ Validation passed.")

def doctor(args):
    conn = ensure_synced()
    print("🔍 Keeli Health Check")
    for s, d in STATUS_DIRS.items():
        exists = "OK" if d.exists() else "MISSING"
        print(f"  Folder {s:10}: {exists}")

    all_files = list(TASKS_DIR.rglob("*.md"))
    db_paths = {r['path'] for r in conn.execute("SELECT path FROM task_index").fetchall()}
    orphans = [f for f in all_files if str(f.absolute()) not in {str(Path(p).absolute()) for p in db_paths}]
    if orphans:
        print(f"⚠️  {len(orphans)} untracked files found. Run 'keeli sync'?")
    print("✅ Index health: OK")

def main():
    parser = argparse.ArgumentParser(description="Keeli v4.0.1 Task Manager")
    parser.add_argument("--version", action="version", version=f"Keeli {VERSION}")
    subparsers = parser.add_subparsers(dest="command")

    p_start = subparsers.add_parser("start", aliases=["create"])
    p_start.add_argument("title", nargs="?", default="Untitled Task")
    p_start.add_argument("--priority", choices=["p0", "p1", "p2", "high", "medium", "low"], default="p2", help="Priority: p0/high, p1/medium, p2/low")
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

    subparsers.add_parser("mcp", help="Start the MCP server")
    subparsers.add_parser("sync")
    subparsers.add_parser("validate")
    subparsers.add_parser("doctor")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cmd = args.command
    if cmd in ["start", "create"]: start(args)
    elif cmd in ["active", "progress"]: _move_task(args.task_id, "active", ensure_synced())
    elif cmd in ["complete", "archive"]: _move_task(args.task_id, "archive", ensure_synced())
    elif cmd == "review": _move_task(args.task_id, "review", ensure_synced())
    elif cmd == "block": _move_task(args.task_id, "blocked", ensure_synced())
    elif cmd == "unblock": _move_task(args.task_id, "backlog", ensure_synced())
    elif cmd == "reopen": _move_task(args.task_id, "backlog", ensure_synced())
    elif cmd == "sync": sync(args)
    elif cmd == "next": next_task(args)
    elif cmd == "list": list_tasks(args)
    elif cmd == "get": get_task(args)
    elif cmd == "digest": digest(args)
    elif cmd == "insights": insights(args)
    elif cmd == "history": history(args)
    elif cmd == "validate": validate(args)
    elif cmd == "mcp":
        from keeli.mcp_server import main as mcp_main
        mcp_main()
    elif cmd == "doctor": doctor(args)

if __name__ == "__main__":
    main()

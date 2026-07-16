#!/usr/bin/env python3
"""
Keeli v4.0 CLI — Source of truth is the filesystem.
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from keeli.schema import init_db
from keeli.templates import TASK_TEMPLATE, CLAUDE_MD, SKILL_TEMPLATE, MCP_TEMPLATE

# --- Constants ---
DOCS_DIR = Path("docs")
TASKS_DIR = DOCS_DIR / "tasks"
STATUS_DIRS = {
    "backlog": TASKS_DIR / "backlog",
    "active": TASKS_DIR / "active",
    "archive": TASKS_DIR / "archive",
    "blocked": TASKS_DIR / "blocked",
    "review": TASKS_DIR / "review",
}
DB_PATH = Path("keeli_state.db")

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
        # Pattern 1: # T-0001: Title (standard)
        match = re.search(r"# (T-\d{4}): (.+)", content)
        
        # Pattern 2: # T-0001 Title (no colon)
        if not match:
            match = re.search(r"# (T-\d{4})\s+(.+)", content)
            
        # Pattern 3: # [T-0001] Title (brackets)
        if not match:
            match = re.search(r"# \[(T-\d{4})\]\s+(.+)", content)
            
        if match:
            task_id = match.group(1)
            title = match.group(2).strip()
        else:
            # Fallback for unparseable but still identifiable IDs
            id_match = re.search(r"(T-\d{4})", content[:100])
            task_id = id_match.group(1) if id_match else "T-0000"
            title = "Untitled Task"

        status_match = re.search(r"\*\*Status:\*\* (.+)", content)
        priority_match = re.search(r"\*\*Priority:\*\* (.+)", content)
        created_match = re.search(r"\*\*Created:\*\* (.+)", content)
        tags = re.findall(r"([a-z0-9-]+:[a-z0-9-]+)", content)

        # Infer status from directory name if metadata is missing or wrong
        inferred_status = path.parent.name.capitalize()

        return {
            "id": task_id,
            "title": title,
            "slug": path.stem.replace(f"{task_id}-", ""),
            "status": status_match.group(1).strip() if status_match else inferred_status,
            "priority": priority_match.group(1).strip() if priority_match else "P1",
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
    
    # Check for index existence/health
    try:
        last_sync_row = conn.execute("SELECT MAX(updated) FROM \"index\"").fetchone()
        last_sync_ts = 0
        if last_sync_row and last_sync_row[0]:
            last_sync_ts = datetime.fromisoformat(last_sync_row[0].replace("Z", "+00:00")).timestamp()
    except sqlite3.OperationalError:
        sync(None, conn) # Force sync if table missing
        return conn

    # Check filesystem for newer files or directory changes
    latest_mtime = 0
    for folder in STATUS_DIRS.values():
        if folder.exists():
            # Directory mtime changes when files are added/removed/renamed
            dir_mtime = folder.stat().st_mtime
            if dir_mtime > latest_mtime:
                latest_mtime = dir_mtime
                
            for f in folder.glob("*.md"):
                mtime = f.stat().st_mtime
                if mtime > latest_mtime:
                    latest_mtime = mtime
    
    if latest_mtime > last_sync_ts + 1: # 1s buffer
        print("⚠️ Index out of sync. Auto-syncing...", file=sys.stderr)
        sync(None, conn)
        
    return conn

def log_event(conn: sqlite3.Connection, item_id: Optional[str], action: str, actor: str, details: str):
    conn.execute(
        "INSERT INTO audit (item_id, action, actor, details, created) VALUES (?, ?, ?, ?, ?)",
        (item_id, action, actor, details, _now_iso())
    )
    conn.commit()

# --- Commands ---
def start(args):
    conn = ensure_synced()
    last_id_row = conn.execute("SELECT id FROM \"index\" ORDER BY id DESC LIMIT 1").fetchone()
    if last_id_row:
        last_num = int(last_id_row['id'].split('-')[1])
        next_id = f"T-{last_num + 1:04d}"
    else:
        files = list(TASKS_DIR.glob("**/*.md"))
        next_id = f"T-{len(files) + 1:04d}"

    slug = _slugify(args.title)
    filename = f"{next_id}-{slug}.md"
    filepath = STATUS_DIRS['backlog'] / filename

    content = TASK_TEMPLATE.format(
        task_id=next_id,
        title=args.title,
        status="Backlog",
        priority=args.priority.upper(),
        timestamp=_now_iso(),
        depends_on=args.depends_on or "—",
        tags=", ".join(args.tags) if args.tags else "—",
        description=args.description or "No description provided."
    )

    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)
    
    conn.execute(
        "INSERT INTO \"index\" (id, slug, title, status, priority, created, tags, path, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (next_id, slug, args.title, "backlog", args.priority.upper(), _now_iso(), ",".join(args.tags) if args.tags else "", str(filepath), _now_iso())
    )
    log_event(conn, next_id, "start", os.getenv("USER", "developer"), f"Created task: {args.title}")
    print(f"Created task {next_id} at {filepath}")

import subprocess

def _git_commit(message: str):
    """Attempt to commit task changes to git."""
    try:
        # Check if there are changes in the tasks directory
        status = subprocess.run(
            ["git", "status", "--porcelain", str(TASKS_DIR)],
            capture_output=True, text=True, check=True
        )
        if not status.stdout.strip():
            return  # Nothing to commit
        
        subprocess.run(["git", "add", str(TASKS_DIR)], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True)
        print(f"✅ Git commit: {message}")
    except subprocess.CalledProcessError as e:
        # If git is not initialized or some other git error
        if "not a git repository" in str(e.stderr).lower():
            pass
        else:
            print(f"⚠️  Git commit failed: {e.stderr.decode().strip() if isinstance(e.stderr, bytes) else e.stderr}")
    except FileNotFoundError:
        pass  # git not installed
    except Exception as e:
        print(f"⚠️  Git error: {e}")

def _move_task(task_id: str, target_status: str, conn: sqlite3.Connection):
    row = conn.execute("SELECT id, path, title FROM \"index\" WHERE id = ? OR slug = ?", (task_id, task_id)).fetchone()
    if not row:
        print(f"Error: Task {task_id} not found. Run 'keeli sync'?")
        return
    tid = row['id']
    title = row['title']
    current_path = Path(row['path'])
    if not current_path.exists():
        print(f"Error: File {current_path} not found.")
        return
    new_path = STATUS_DIRS[target_status] / current_path.name
    STATUS_DIRS[target_status].mkdir(parents=True, exist_ok=True)
    os.rename(current_path, new_path)
    
    # Update internal status
    content = new_path.read_text()
    new_content = re.sub(r"\*\*Status:\*\* .+", f"**Status:** {target_status.capitalize()}", content)
    new_path.write_text(new_content)
    
    conn.execute(
        "UPDATE \"index\" SET status = ?, path = ?, updated = ? WHERE id = ?",
        (target_status.lower(), str(new_path), _now_iso(), tid)
    )
    log_event(conn, tid, target_status, os.getenv("USER", "developer"), f"Moved to {target_status}")
    print(f"Moved {tid} to {target_status}")
    
    # Optional auto-commit
    action_verb = "Complete" if target_status == "archive" else "Started" if target_status == "active" else "Block" if target_status == "blocked" else target_status.capitalize()
    _git_commit(f"keeli {target_status} {tid}: {title}")

def progress(args): _move_task(args.task_id, "active", ensure_synced())
def complete(args): _move_task(args.task_id, "archive", ensure_synced())
def block(args): _move_task(args.task_id, "blocked", ensure_synced())
def review(args): _move_task(args.task_id, "review", ensure_synced())
def reopen(args): _move_task(args.task_id, "active", ensure_synced())

def next_task(args):
    conn = ensure_synced()
    query = """
    SELECT * FROM "index" 
    WHERE status IN ('backlog', 'active') 
    ORDER BY priority = 'P0' DESC, priority = 'P1' DESC, created ASC 
    LIMIT 1;
    """
    row = conn.execute(query).fetchone()
    if row:
        print(f"{row['id']}: {row['title']} ({row['status'].upper()}, {row['priority']})")
    else:
        print("No tasks in backlog or active.")

def sync(args, conn=None):
    if not conn:
        conn = init_db(DB_PATH)
    conn.execute("DELETE FROM \"index\"")
    count = 0
    corrected = 0
    for status, folder in STATUS_DIRS.items():
        if not folder.exists(): continue
        for md_file in folder.glob("*.md"):
            content = md_file.read_text()
            data = parse_task_file(content, md_file)
            if data:
                # Correction Logic: If file metadata status != directory name, update file.
                if data['status'].lower() != status.lower():
                    new_status_str = status.capitalize()
                    new_content = re.sub(r"\*\*Status:\*\* (.+)", f"**Status:** {new_status_str}", content)
                    if "**Status:**" not in new_content: # fallback if missing
                        new_content = new_content.replace("- - -", f"**Status:** {new_status_str}\n- - -")
                    md_file.write_text(new_content)
                    data['status'] = new_status_str
                    corrected += 1

                conn.execute(
                    "INSERT INTO \"index\" (id, slug, title, status, priority, created, tags, path, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (data['id'], data['slug'], data['title'], status, data['priority'], data['created'], data['tags'], data['path'], _now_iso())
                )
                count += 1
    conn.commit()
    msg = f"Rebuilt index with {count} tasks"
    if corrected:
        msg += f" ({corrected} status fields corrected)"
    log_event(conn, None, "sync", "system", msg)
    if args: # only print if not auto-sync
        print(f"Synced {count} tasks. {corrected} corrected.")

def list_tasks(args):
    conn = ensure_synced()
    query = "SELECT id, title, status, priority FROM \"index\""
    params = []
    if args.status:
        query += " WHERE status = ?"
        params.append(args.status)
    rows = conn.execute(query, params).fetchall()
    for r in rows:
        print(f"[{r['status'].upper()}] {r['id']}: {r['title']} ({r['priority']})")

def get_task(args):
    conn = ensure_synced()
    row = conn.execute("SELECT path FROM \"index\" WHERE id = ? OR slug = ?", (args.task_id, args.task_id)).fetchone()
    if row:
        print(Path(row['path']).read_text())
    else:
        print(f"Task {args.task_id} not found.")

def _estimate_tokens(text: str) -> int:
    """Rough token estimation (GPT-4/Claude style)."""
    try:
        import tiktoken
        encoding = tiktoken.encoding_for_model("gpt-4")
        return len(encoding.encode(text))
    except (ImportError, KeyError):
        # Fallback: Approximate 1.35 tokens per word
        return int(len(text.split()) * 1.35)

def digest(args):
    conn = ensure_synced()
    budget = args.budget
    output = []
    
    # Tiered logic
    tier = getattr(args, 'tier', 'standard')
    if tier == 'nano':
        active = conn.execute("SELECT id, title FROM \"index\" WHERE status = 'active' LIMIT 1").fetchall()
        for a in active: output.append(f"Current: {a['id']} - {a['title']}")
        print("\n".join(output))
        return

    active = conn.execute("SELECT id, title, priority FROM \"index\" WHERE status = 'active'").fetchall()
    if active:
        output.append("## Active Tasks")
        for a in active:
            output.append(f"- {a['id']}: {a['title']} ({a['priority']})")
        output.append("")

    if tier != 'brief':
        backlog = conn.execute("SELECT id, title, priority FROM \"index\" WHERE status = 'backlog' ORDER BY priority='P0' DESC, priority='P1' DESC, created ASC LIMIT 5").fetchall()
        if backlog:
            output.append("## Backlog (Top 5)")
            for b in backlog:
                output.append(f"- {b['id']}: {b['title']} ({b['priority']})")
            output.append("")

    claude_path = DOCS_DIR / "CLAUDE.md"
    if claude_path.exists():
        output.append("## Project Overview")
        lines = claude_path.read_text().splitlines()
        output.extend(lines[:15] if tier == 'standard' else lines[:5])
        output.append("")

    logs = conn.execute("SELECT created, item_id, action, details FROM audit ORDER BY created DESC LIMIT 5").fetchall()
    if logs:
        output.append("## Recent Log")
        for l in logs:
            item = l['item_id'] if l['item_id'] else "SYSTEM"
            output.append(f"- {l['created']} | {item} | {l['action'].upper()} | {l['details']}")

    final_text = "\n".join(output)
    
    # Token-aware truncation
    tokens = _estimate_tokens(final_text)
    if tokens > budget:
        # If way over budget, do a character-based prune first then truncate
        ratio = budget / tokens
        cutoff = int(len(final_text) * ratio)
        final_text = final_text[:cutoff] + "...\n(truncated for budget)"
        tokens = _estimate_tokens(final_text)

    print(final_text)
    print(f"\n📊 ~{tokens} tokens (budget: {budget})")

def run_mcp_server(args):
    from keeli.mcp_server import main as mcp_main
    mcp_main()

def history(args):
    conn = ensure_synced()
    rows = conn.execute("SELECT created, action, actor, details FROM audit WHERE item_id = ? ORDER BY created DESC", (args.task_id,)).fetchall()
    for r in rows:
        print(f"{r['created']} | {r['action'].upper()} | {r['actor']} | {r['details']}")

def log_command(args):
    conn = ensure_synced()
    log_event(conn, None, "log", args.actor or os.getenv("USER", "developer"), args.message)
    print("Logged event.")

def doctor(args):
    print("Keeli v4.0 Doctor Report")
    print("-" * 25)
    for name, path in STATUS_DIRS.items():
        exists = "OK" if path.exists() else "MISSING"
        print(f"Status Dir [{name:7}]: {exists}")
    db_exists = "OK" if DB_PATH.exists() else "MISSING"
    print(f"SQLite Index      : {db_exists}")
    
    if DB_PATH.exists():
        conn = init_db(DB_PATH)
        last_sync_row = conn.execute("SELECT MAX(updated) FROM \"index\"").fetchone()
        if last_sync_row and last_sync_row[0]:
            print(f"Last Sync         : {last_sync_row[0]}")
            
    # File checks
    all_files = list(TASKS_DIR.rglob("*.md"))
    print(f"Task Files Total  : {len(all_files)}")
    
    # Orphan checks (not in a status dir)
    status_paths = [Path(p).resolve() for p in STATUS_DIRS.values()]
    orphans = []
    for f in all_files:
        if f.parent.resolve() not in status_paths:
            orphans.append(f)
    
    if orphans:
        print(f"⚠️  ORPHANED FILES (not in status dirs):")
        for o in orphans: print(f"  - {o}")

    # Duplicate ID checks
    ids = {}
    for f in all_files:
        id_match = re.search(r"(T-\d{4})", f.read_text())
        if id_match:
            tid = id_match.group(1)
            if tid in ids:
                ids[tid].append(f)
            else:
                ids[tid] = [f]
    
    for tid, paths in ids.items():
        if len(paths) > 1:
            print(f"⚠️  DUPLICATE ID: {tid}")
            for p in paths: print(f"  - {p}")

    # Index vs Filesystem drift
    if DB_PATH.exists():
        conn = init_db(DB_PATH)
        idx_count = conn.execute("SELECT COUNT(*) FROM \"index\"").fetchone()[0]
        print(f"Index Records     : {idx_count}")
        if len(all_files) != idx_count:
            print(f"⚠️  DRIFT: Filesystem has {len(all_files)} but index has {idx_count}. Run 'keeli sync'.")

def validate(args):
    """Deep validation of all task files."""
    if args.staged:
        print("Feature 'validate --staged' is not yet implemented for v4.0. Skipping...")
        return

    count, errors = 0, []
    all_files = list(TASKS_DIR.rglob("*.md"))
    
    for md_file in all_files:
        count += 1
        content = md_file.read_text()
        
        # Required fields and formats
        checks = [
            (r"# T-\d{4}:", f"Missing or malformed H1 ID/Title (Expected: # T-0001: Title)"),
            (r"\*\*Status:\*\*\s+(Backlog|Active|Archive|Blocked|Review)", f"Invalid or missing **Status:** field"),
            (r"\*\*Priority:\*\*\s+(p0|p1|p2|P0|P1|P2)", f"Invalid or missing **Priority:** field"),
            (r"\*\*Created:\*\*", f"Missing **Created:** field"),
        ]
        
        for pattern, msg in checks:
            if not re.search(pattern, content, re.IGNORECASE):
                errors.append(f"{md_file}: {msg}")
        
        # Dependency check
        deps_match = re.search(r"\*\*Depends On:\*\* (.+)", content)
        if deps_match:
            dep_val = deps_match.group(1).strip()
            if dep_val and dep_val not in ["—", "None", ""]:
                # Split and trim
                deps = [d.strip() for d in dep_val.split(",")]
                for d in deps:
                    # Check if d (e.g. T-0001) exists as a file prefix
                    if not any(d in f.name for f in all_files):
                        errors.append(f"{md_file}: Broken dependency '{d}'")

        # Tag format check
        tags_match = re.search(r"\*\*Tags:\*\* (.+)", content)
        if tags_match:
            tags_str = tags_match.group(1).strip()
            if tags_str and tags_str not in ["—", "None", ""]:
                tags = [t.strip() for t in tags_str.split(",")]
                for t in tags:
                    if not re.match(r"^[a-z0-9-]+:[a-z0-9-]+$", t):
                        errors.append(f"{md_file}: Invalid tag format '{t}' (Expected: namespace:tag)")

    if errors:
        for err in errors:
            print(f"❌ {err}")
        print(f"\nValidated {count} files. Found {len(errors)} errors.")
        sys.exit(1)
    else:
        print(f"✅ Validated {count} files. All OK.")

def configure_copilot(args):
    """Print Copilot Skill and MCP configuration instructions."""
    mcp_path = Path("src/keeli/mcp_server.py").absolute()
    
    print("# Keeli Copilot Integration Instructions")
    print("-" * 40)
    print("\n## 1. Create the Skill File")
    print("Path: .github/skills/keeli/SKILL.md")
    print("\n```markdown")
    print(SKILL_TEMPLATE)
    print("```")
    
    print("\n## 2. Configure the MCP Server")
    print("Path: .vscode/mcp.json (or .cursor/mcp.json)")
    print("\n```json")
    print(MCP_TEMPLATE.format(mcp_path=mcp_path))
    print("```")
    
    print("\n## 3. Verify Connection")
    print("Run: keeli doctor")
    print("Then check your LLM client's MCP tool list.")

def main():
    parser = argparse.ArgumentParser(description="Keeli v4.0 CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("start").add_argument("title"); subparsers.choices["start"].add_argument("--priority", default="p1"); subparsers.choices["start"].add_argument("--tags", nargs="*", default=[]); subparsers.choices["start"].add_argument("--description", default=""); subparsers.choices["start"].add_argument("--depends-on", default="")
    subparsers.add_parser("progress").add_argument("task_id")
    subparsers.add_parser("complete").add_argument("task_id")
    subparsers.add_parser("block").add_argument("task_id")
    subparsers.add_parser("review").add_argument("task_id")
    subparsers.add_parser("reopen").add_argument("task_id")
    subparsers.add_parser("next")
    subparsers.add_parser("sync")
    subparsers.add_parser("list").add_argument("--status")
    subparsers.add_parser("get").add_argument("task_id")
    p_digest = subparsers.add_parser("digest")
    p_digest.add_argument("--budget", type=int, default=2000)
    p_digest.add_argument("--tier", choices=["nano", "brief", "standard", "full"], default="standard")
    subparsers.add_parser("history").add_argument("task_id")
    subparsers.add_parser("mcp")
    subparsers.add_parser("doctor")
    subparsers.add_parser("validate").add_argument("--staged", action="store_true")
    subparsers.add_parser("configure-copilot")
    p_log = subparsers.add_parser("log")
    p_log.add_argument("message")
    p_log.add_argument("--actor")

    args = parser.parse_args()
    if args.command == "start": start(args)
    elif args.command == "progress": progress(args)
    elif args.command == "complete": complete(args)
    elif args.command == "block": block(args)
    elif args.command == "review": review(args)
    elif args.command == "reopen": reopen(args)
    elif args.command == "next": next_task(args)
    elif args.command == "sync": sync(args)
    elif args.command == "list": list_tasks(args)
    elif args.command == "get": get_task(args)
    elif args.command == "digest": digest(args)
    elif args.command == "history": history(args)
    elif args.command == "mcp": run_mcp_server(args)
    elif args.command == "doctor": doctor(args)
    elif args.command == "validate": validate(args)
    elif args.command == "configure-copilot": configure_copilot(args)
    elif args.command == "log": log_command(args)
    else: parser.print_help()

if __name__ == "__main__":
    main()

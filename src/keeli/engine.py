import os
import re
import sqlite3
import string
import subprocess
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from keeli.schema import init_db
from keeli.templates import TASK_TEMPLATE

import hashlib
import tiktoken

class KeeliEngine:
    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or self._find_project_root(Path.cwd())
        self.docs_dir = self.root_dir / "docs"
        self.tasks_dir = self.docs_dir / "tasks"
        self.db_path = self.root_dir / "keeli_state.db"
        self.valid_statuses = ["backlog", "active", "review", "blocked", "archive"]
        self.status_dirs = {s: self.tasks_dir / s for s in self.valid_statuses}
        self._conn = None

    def _get_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self.ensure_synced()
        return self._conn

    def _find_project_root(self, start_path: Path) -> Path:
        if os.getenv("KEELI_ROOT"):
            return Path(os.getenv("KEELI_ROOT")).absolute()
        curr = start_path.absolute()
        home = Path.home()
        for _ in range(20):
            # Prioritize existing Keeli structure
            if (curr / "docs" / "tasks").exists():
                return curr
            # Stop at git root, but be wary of home directory git repos
            if (curr / ".git").exists():
                if curr == home:
                    # Only treat home as root if it specifically has Keeli tasks
                    if (curr / "docs" / "tasks").exists():
                        return curr
                else:
                    return curr
            if curr.parent == curr:
                break
            curr = curr.parent
        return start_path.absolute()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _slugify(self, text: str) -> str:
        slug = text.lower().strip()
        slug = slug.replace("&", "and")
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")

    def parse_task_file(self, content: str, path: Path) -> Dict[str, Any]:
        try:
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

            inferred_status = "backlog"
            for s, d in self.status_dirs.items():
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
        except Exception:
            return {}

    def ensure_synced(self) -> sqlite3.Connection:
        conn = init_db(self.db_path)
        if not self.db_path.exists() or not self.tasks_dir.exists():
            return conn
        
        try:
            last_sync_row = conn.execute("SELECT MAX(updated) FROM task_index").fetchone()
            last_sync_ts = 0
            if last_sync_row and last_sync_row[0]:
                last_sync_ts = datetime.fromisoformat(last_sync_row[0].replace("Z", "+00:00")).timestamp()
        except sqlite3.OperationalError:
            self.sync(conn=conn)
            return conn

        latest_mtime = 0
        for folder in self.status_dirs.values():
            if folder.exists():
                latest_mtime = max(latest_mtime, folder.stat().st_mtime)
        
        if latest_mtime > last_sync_ts + 0.5:
            self.sync(conn=conn)
            
        return conn

    def log_event(self, item_id: Optional[str], action: str, actor: str, details: str, session_id: Optional[str] = None, rationale: Optional[str] = None, conn: Optional[sqlite3.Connection] = None):
        target_conn = conn or self.conn
        target_conn.execute(
            "INSERT INTO audit (item_id, session_id, action, actor, details, rationale, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item_id, session_id, action, actor, details, rationale, self._now_iso())
        )
        if not conn:
            target_conn.commit()

    def _git_commit(self, message: str, file_path: Optional[Path] = None):
        try:
            target = str(file_path) if file_path else str(self.tasks_dir)
            cwd = str(self.root_dir)
            
            check = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, cwd=cwd)
            if check.returncode != 0: return

            subprocess.run(["git", "add", target], check=True, capture_output=True, cwd=cwd)
            diff = subprocess.run(["git", "diff", "--cached", "--quiet", "--", target], cwd=cwd)
            if diff.returncode == 0: return
            
            subprocess.run(["git", "commit", "-m", message, "--", target], check=True, capture_output=True, cwd=cwd)
        except Exception:
            pass

    def start(self, title: str, priority_raw: str = "p2", tags: List[str] = None, description: str = None, depends_on: str = None) -> str:
        conn = self.conn
        p_map = {"high": "P0", "medium": "P1", "low": "P2", "p0": "P0", "p1": "P1", "p2": "P2"}
        priority = p_map.get(priority_raw.lower().split("/")[0], "P1")
        
        ids = []
        for f in self.tasks_dir.rglob("T-*.md"):
            m = re.search(r"T-(\d{4})", f.name)
            if m: ids.append(int(m.group(1)))
        
        next_num = (max(ids) + 1) if ids else 1
        next_id = f"T-{next_num:04d}"
        slug = self._slugify(title or "untitled")
        filename = f"{next_id}-{slug}.md"
        filepath = self.status_dirs['backlog'] / filename

        processed_tags = [t.strip().lower() for t in (tags or []) if t.strip()]
        template = string.Template(TASK_TEMPLATE)
        content = template.safe_substitute(
            task_id=next_id, title=title or "Untitled Task", status="Backlog",
            priority=priority, timestamp=self._now_iso(), depends_on=depends_on or "—",
            tags=", ".join(processed_tags) if processed_tags else "—",
            description=description or "No description provided."
        )

        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        v_hash = self._get_hash(content)
        
        with conn:
            conn.execute(
                "INSERT INTO task_index (id, slug, title, status, priority, created, tags, path, version_hash, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (next_id, slug, title, "backlog", priority, self._now_iso(), ",".join(processed_tags), str(filepath), v_hash, self._now_iso())
            )
            self.log_event(next_id, "start", os.getenv("USER", "developer"), f"Created task: {title}", conn=conn)
        
        self._git_commit(f"keeli start {next_id}: {title}", filepath)
        return next_id

    def sync(self, conn: Optional[sqlite3.Connection] = None) -> Tuple[int, int]:
        """
        Grounded Re-indexing: Re-scans docs/tasks/ and reconciles the performance index.
        Physically moved files are treated as status updates.
        """
        target_conn = conn or init_db(self.db_path)
        seen_ids = {}
        count = 0
        corrected = 0
        rows = []
        files_to_update = []
        
        # Priority mapping for FTS
        p_weight = {"P0": 0, "P1": 1, "P2": 2}

        # Scan all directories in strict order to establish ownership
        for status, folder in self.status_dirs.items():
            if not folder.exists(): 
                folder.mkdir(parents=True, exist_ok=True)
                continue
                
            for md_file in folder.glob("*.md"):
                content = md_file.read_text()
                data = self.parse_task_file(content, md_file)
                if not data or not data.get('id'): continue
                
                tid = data['id']
                # De-duplication: first folder seen "wins"
                if tid in seen_ids: 
                    print(f"Warning: Duplicate task {tid} found at {md_file}. Ignoring.", file=sys.stderr)
                    continue
                seen_ids[tid] = md_file

                # PHYSICAL STATE RECONCILIATION
                # If the folder location disagrees with the internal status metadata,
                # the folder location is the source of truth.
                if data['status'].lower() != status.lower():
                    new_status_str = status.capitalize()
                    # Preserve all other content, only update Status: line
                    new_content = re.sub(r"^\*\*Status:\*\* .+$", f"**Status:** {new_status_str}", content, flags=re.MULTILINE)
                    
                    if new_content != content:
                        files_to_update.append((md_file, new_content))
                        content = new_content
                        data['status'] = status
                        corrected += 1

                v_hash = self._get_hash(content)
                rows.append((
                    data['id'], data['slug'], data['title'], status, 
                    data['priority'], data['created'], data['tags'], 
                    str(md_file), v_hash, self._now_iso()
                ))
                count += 1

        with target_conn:
            target_conn.execute("DELETE FROM task_index")
            if rows:
                target_conn.executemany(
                    "INSERT INTO task_index (id, slug, title, status, priority, created, tags, path, version_hash, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows
                )
            
            # Flush corrected metadata back to filesystem
            for f, c in files_to_update:
                f.write_text(c)
            
            # Rebuild FTS
            try:
                target_conn.execute("DELETE FROM task_fts")
                target_conn.execute("INSERT INTO task_fts(task_id, title, description, tags) SELECT id, title, slug, tags FROM task_index")
            except Exception: pass

            self.prune_context(conn=target_conn)
            self.log_event(None, "sync", "system", f"Grounded sync: {count} tasks, {corrected} metadata corrections", conn=target_conn)
        
        return count, corrected

    def move_task(self, task_id: str, target_status: str, expected_hash: Optional[str] = None, rationale: Optional[str] = None) -> str:
        if target_status not in self.status_dirs:
            raise ValueError(f"Invalid status {target_status}")

        conn = self.conn
        row = conn.execute("SELECT id, path, title, version_hash FROM task_index WHERE id = ? OR slug = ?", (task_id, task_id)).fetchone()
        if not row:
            raise ValueError(f"Task {task_id} not found.")
        
        tid, current_path, title, current_hash = row['id'], Path(row['path']), row['title'], row['version_hash']
        
        # Conflict Detection (Optimistic Locking)
        if expected_hash and current_hash != expected_hash:
            raise ValueError(f"CONFLICT: Task {tid} was modified elsewhere. Expected {expected_hash}, but index has {current_hash}.")

        new_path = self.status_dirs[target_status] / current_path.name
        self.status_dirs[target_status].mkdir(parents=True, exist_ok=True)
        os.rename(current_path, new_path)
        
        content = new_path.read_text()
        new_content = re.sub(r"^\*\*Status:\*\* .+$", f"**Status:** {target_status.capitalize()}", content, flags=re.MULTILINE)
        
        if target_status == "archive":
            ts = self._now_iso()
            new_content = re.sub(r"^\*\*Completed:\*\* .+$", f"**Completed:** {ts}", new_content, flags=re.MULTILINE) if "**Completed:**" in new_content else re.sub(r"^(\*\*Priority:\*\* .+)$", f"\\1\n**Completed:** {ts}", new_content, flags=re.MULTILINE)
        else:
            new_content = re.sub(r"^\*\*Completed:\*\* .+$", "**Completed:** —", new_content, flags=re.MULTILINE)
        
        new_path.write_text(new_content)
        v_hash = self._get_hash(new_content)
        
        with conn:
            conn.execute("UPDATE task_index SET status = ?, path = ?, version_hash = ?, updated = ? WHERE id = ?", (target_status, str(new_path), v_hash, self._now_iso(), tid))
            self.log_event(tid, target_status, os.getenv("USER", "developer"), f"Moved to {target_status}", rationale=rationale, conn=conn)
        
        # Architecture v5.1: No auto-commits in engine core.
        return tid

    def next_task(self, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conn = self.conn
        focus_task = None
        if session_id:
            row = conn.execute("SELECT focus_task_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            if row: focus_task = row['focus_task_id']

        if focus_task:
            # Prioritize focus task if it's not archived, or its dependencies
            row = conn.execute("SELECT * FROM task_index WHERE id = ? AND status != 'archive'", (focus_task,)).fetchone()
            if row: return dict(row)

        query = """
        SELECT * FROM task_index WHERE status IN ('backlog', 'active') 
        ORDER BY CASE WHEN priority = 'P0' THEN 0 WHEN priority = 'P1' THEN 1 WHEN priority = 'P2' THEN 2 ELSE 3 END ASC,
        CASE WHEN (created IS NULL OR created = '') THEN '9999' ELSE created END ASC LIMIT 1;
        """
        row = conn.execute(query).fetchone()
        return dict(row) if row else None

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT id, title, status, priority, version_hash FROM task_index"
        params = []
        if status:
            query += " WHERE status = ? COLLATE NOCASE"
            params.append(status.lower())
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    def get_task(self, task_id: str) -> str:
        row = self.conn.execute("SELECT path, version_hash FROM task_index WHERE id = ? OR slug = ?", (task_id, task_id)).fetchone()
        if row and Path(row['path']).exists():
            content = Path(row['path']).read_text()
            # Inject version hash into header for MCP
            return f"<!-- VERSION_HASH: {row['version_hash']} -->\n{content}"
        raise ValueError(f"Task {task_id} not found.")

    def delete_task(self, task_id: str):
        conn = self.conn
        row = conn.execute("SELECT path FROM task_index WHERE id = ?", (task_id,)).fetchone()
        if row:
            p = Path(row['path'])
            if p.exists(): p.unlink()
            with conn:
                conn.execute("DELETE FROM task_index WHERE id = ?", (task_id,))
                self.log_event(task_id, "delete", os.getenv("USER", "developer"), "Deleted task")

    def prune_context(self, conn: Optional[sqlite3.Connection] = None):
        """GC: Deletes branch-scoped context for branches that no longer exist in Git."""
        try:
            branches = subprocess.check_output(["git", "branch", "--format=%(refname:short)"], text=True).splitlines()
            target_conn = conn or self.conn
            if conn:
                # Part of ongoing transaction
                placeholders = ",".join(["?"] * len(branches))
                target_conn.execute(f"DELETE FROM context_store WHERE scope = 'branch' AND scope_id NOT IN ({placeholders})", branches)
            else:
                with target_conn:
                    placeholders = ",".join(["?"] * len(branches))
                    target_conn.execute(f"DELETE FROM context_store WHERE scope = 'branch' AND scope_id NOT IN ({placeholders})", branches)
        except Exception as e:
            if not os.getenv("KEELI_QUIET"):
                print(f"Prune context failed: {e}")

    # --- Context Engine ---
    def context_resolve(self, key: str, session_id: Optional[str] = None) -> Tuple[Optional[str], str]:
        """Resolves context key using strict waterfall: Session > Branch > Global."""
        conn = self.conn
        branch = self._get_current_branch()
        
        # 1. Session
        if session_id:
            res = conn.execute("SELECT value FROM context_store WHERE key = ? AND scope = 'session' AND scope_id = ?", (key, session_id)).fetchone()
            if res: return res['value'], 'session'
        
        # 2. Branch
        if branch:
            res = conn.execute("SELECT value FROM context_store WHERE key = ? AND scope = 'branch' AND scope_id = ?", (key, branch)).fetchone()
            if res: return res['value'], 'branch'
            
        # 3. Global
        res = conn.execute("SELECT value FROM context_store WHERE key = ? AND scope = 'global'", (key,)).fetchone()
        if res: return res['value'], 'global'
        
        return None, 'none'

    def context_get(self, key: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        val, scope = self.context_resolve(key, session_id)
        return {"key": key, "value": val, "scope": scope}
        
        # 1. Session Lookup
        if session_id:
            row = conn.execute(
                "SELECT value, scope, source, updated FROM context_store WHERE key = ? AND scope = 'session' AND scope_id = ?",
                (key, session_id)
            ).fetchone()
            if row: return dict(row)

        # 2. Branch Lookup (Infer branch)
        branch = self._get_current_branch()
        if branch:
            row = conn.execute(
                "SELECT value, scope, source, updated FROM context_store WHERE key = ? AND scope = 'branch' AND scope_id = ?",
                (key, branch)
            ).fetchone()
            if row: return dict(row)

        # 3. Global Lookup
        row = conn.execute(
            "SELECT value, scope, source, updated FROM context_store WHERE key = ? AND scope = 'global'",
            (key,)
        ).fetchone()
        if row: return dict(row)

        # 4. Implicit Discovery
        discovered = self._discover_context(key)
        if discovered:
            self.context_set(key, discovered, scope='global', source='discovery')
            return {"value": discovered, "scope": "global", "source": "discovery", "updated": self._now_iso()}
        
        return {}

    def context_set(self, key: str, value: str, scope: str = 'session', scope_id: Optional[str] = None, source: str = 'user_override'):
        conn = self.conn
        if scope == 'branch' and not scope_id:
            scope_id = self._get_current_branch()
        
        with conn:
            conn.execute("""
                INSERT INTO context_store (key, value, scope, scope_id, source, updated)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key, scope, scope_id) DO UPDATE SET
                value = excluded.value, source = excluded.source, updated = excluded.updated
            """, (key, value, scope, scope_id, source, self._now_iso()))

    def _get_current_branch(self) -> Optional[str]:
        try:
            return subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
        except Exception:
            return None

    def _discover_context(self, key: str) -> Optional[str]:
        # Basic discovery logic for common keys
        if key == 'python_version':
            return sys.version.split()[0]
        if key == 'project_name':
            return self.root_dir.name
        
        # Check pyproject.toml etc.
        pyproject = self.root_dir / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text()
            if key == 'dependencies':
                # very crude parsing
                deps = re.findall(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
                return deps[0].strip() if deps else None
        
        return None

    # --- Session Management ---
    def session_start(self, name: str = "Investigation", branch: Optional[str] = None, focus_task_id: Optional[str] = None) -> str:
        import uuid
        session_id = str(uuid.uuid4())
        branch = branch or self._get_current_branch()
        conn = self.conn
        with conn:
            conn.execute("""
                INSERT INTO sessions (session_id, branch_name, focus_task_id, goal, last_ping, created)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, branch, focus_task_id, name, self._now_iso(), self._now_iso()))
            
            # Set as active session
            conn.execute("""
                INSERT INTO context_store (key, value, scope, updated, source)
                VALUES ('active_session_id', ?, 'global', ?, 'session_manager')
                ON CONFLICT(key) WHERE scope = 'global' DO UPDATE SET value = excluded.value, updated = excluded.updated
            """, (session_id, self._now_iso()))
            
        return session_id

    def session_focus(self, task_id: str, session_id: Optional[str] = None):
        conn = self.conn
        if not session_id:
            res = conn.execute("SELECT value FROM context_store WHERE key = 'active_session_id'").fetchone()
            if res: session_id = res['value']
        
        if not session_id:
            raise ValueError("No active session. Start a session first.")

        with conn:
            conn.execute("UPDATE sessions SET focus_task_id = ?, last_ping = ? WHERE session_id = ?", (task_id, self._now_iso(), session_id))

    def session_checkpoint(self, note: str = "Sync point", session_id: Optional[str] = None, pending_decisions: List[str] = None):
        conn = self.conn
        if not session_id:
            res = conn.execute("SELECT value FROM context_store WHERE key = 'active_session_id'").fetchone()
            if res: session_id = res['value']
            
        if not session_id:
            raise ValueError("No active session.")

        # Get current context overrides
        rows = conn.execute("SELECT key, value FROM context_store WHERE scope = 'session' AND scope_id = ?", (session_id,)).fetchall()
        context_snapshot = json.dumps({r['key']: r['value'] for r in rows})
        
        # Get current digest
        current_digest = self.digest(tier='standard')
        
        with conn:
            conn.execute("""
                INSERT INTO checkpoints (session_id, llm_summary, active_digest, pending_decisions, context_snapshot, created)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, note, current_digest, json.dumps(pending_decisions or []), context_snapshot, self._now_iso()))
        return "checkpoint-saved"

    def session_restore(self, session_id: str, checkpoint_id: Optional[int] = None) -> Dict[str, Any]:
        conn = self.conn
        query = "SELECT * FROM checkpoints WHERE session_id = ?"
        params = [session_id]
        if checkpoint_id:
            query += " AND checkpoint_id = ?"
            params.append(checkpoint_id)
        query += " ORDER BY checkpoint_id DESC LIMIT 1"
        
        row = conn.execute(query, params).fetchone()
        if row:
            return dict(row)
        return {}

    def digest(self, tier: str = "standard", budget: int = 2000) -> str:
        """
        Generates a structured context snapshot within a specified token budget.
        Implements Architecture v5.1 SectionPriority truncation.
        """
        conn = self.conn
        encoding = tiktoken.get_encoding("cl100k_base")
        
        def count_tokens(text: str) -> int:
            return len(encoding.encode(text))

        # --- Layer 1: Header (Non-negotiable) ---
        header = []
        session_id_row = conn.execute("SELECT value FROM context_store WHERE key = 'active_session_id'").fetchone()
        sid = session_id_row['value'] if session_id_row else None
        
        if sid:
            session = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (sid,)).fetchone()
            if session:
                header.append(f"# SESSION: {session['goal']} ({sid})")
                header.append(f"Focus: {session['focus_task_id'] or 'None'}")
                header.append(f"Branch: {session['branch_name'] or 'main'}")

        stats = conn.execute("SELECT status, COUNT(*) as count FROM task_index GROUP BY status").fetchall()
        if stats:
            summary = " | ".join([f"{s['status'].upper()}: {s['count']}" for s in stats])
            header.append(f"## Status Overview: {summary}\n")
        
        header_text = "\n".join(header)
        current_budget = budget - count_tokens(header_text)

        # --- Layer 2: Active Tasks (Highest Priority) ---
        active_block = []
        active = conn.execute("SELECT id, title, priority, version_hash FROM task_index WHERE status = 'active' ORDER BY priority ASC").fetchall()
        if active:
            active_block.append("## ACTIVE TASKS")
            for a in active:
                p = a['priority']
                p_str = p if p.startswith('P') else f"P{p}"
                active_block.append(f"- {a['id']}: {a['title']} ({p_str}) [Hash: {a['version_hash'][:8]}]")
            active_block.append("")
        
        active_text = "\n".join(active_block)
        current_budget -= count_tokens(active_text)

        # --- Layer 3: Recent Audit (Integrity) ---
        audit_block = []
        logs = conn.execute("SELECT created, actor, action, details FROM audit ORDER BY event_id DESC LIMIT 5").fetchall()
        if logs:
            audit_block.append("## RECENT ACTIVITY")
            for l in logs:
                audit_block.append(f"- {l['created']} | {l['actor']} | {l['action'].upper()} | {l['details']}")
            audit_block.append("")
        
        audit_text = "\n".join(audit_block)
        audit_tokens = count_tokens(audit_text)
        if audit_tokens > (current_budget * 0.2): # Don't let audit take more than 20% of remaining
             audit_text = "\n".join(audit_block[:3]) + "\n... (more activity hidden)"
             audit_tokens = count_tokens(audit_text)
        
        current_budget -= audit_tokens

        # --- Layer 4: Project Overview (Clipping) ---
        overview_text = ""
        if tier in ['standard', 'full']:
            overview_file = self.root_dir / "CLAUDE.md" if (self.root_dir / "CLAUDE.md").exists() else self.root_dir / "README.md"
            if overview_file.exists():
                full_overview = overview_file.read_text()
                # Hard limit of 250 tokens for overview in digest
                tokens = encoding.encode(full_overview)
                if len(tokens) > 250:
                    overview_text = f"## OVERVIEW ({overview_file.name})\n" + encoding.decode(tokens[:250]) + "\n... (content clipped)\n"
                else:
                    overview_text = f"## OVERVIEW ({overview_file.name})\n" + full_overview + "\n"
        
        current_budget -= count_tokens(overview_text)

        # --- Layer 5: Backlog (Buffer) ---
        backlog_text = ""
        if tier != 'brief' and current_budget > 100:
            backlog = conn.execute(f"SELECT id, title, priority FROM task_index WHERE status = 'backlog' ORDER BY priority ASC, id ASC LIMIT 10").fetchall()
            if backlog:
                backlog_lines = ["## BACKLOG"]
                for b in backlog:
                    line = f"- {b['id']}: {b['title']} (P{b['priority']})"
                    if count_tokens("\n".join(backlog_lines) + "\n" + line) < current_budget:
                        backlog_lines.append(line)
                    else:
                        break
                backlog_text = "\n".join(backlog_lines) + "\n"

        return "\n".join(filter(None, [header_text, active_text, audit_text, overview_text, backlog_text]))

        return "\n".join(output)

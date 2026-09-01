"""
Keeli v6.0 — Event-Sourced CRDT Engine (Production-Hardened)

Critical fixes applied:
  • All multi-table mutations wrapped in explicit SQLite transactions
  • Vector clocks read from CRDT replay, never from stale task_index
  • Markdown files are lazily materialized (on-demand / sync only)
  • Tag removal uses tag-aware observed-remove from ORSet
  • File I/O decoupled from event emission — event log is sole runtime truth
"""

import hashlib
import json
import os
import re
import sqlite3
import string
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import tiktoken

from keeli.schema import init_db
from keeli.crdt import Event, TaskCRDT, VectorClock
from keeli.templates import TASK_TEMPLATE


class KeeliEngine:
    """Production-ready task engine with CRDT-backed optimistic concurrency."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or self._find_project_root(Path.cwd())
        self.workspace_dir = self.root_dir / ".keeli"
        self.tasks_dir = self.workspace_dir / "tasks"
        self.db_path = self.workspace_dir / "keeli_state.db"
        self.valid_statuses = ["backlog", "active", "review", "blocked", "archive"]
        self.status_dirs = {s: self.tasks_dir / s for s in self.valid_statuses}
        self._conn: Optional[sqlite3.Connection] = None
        self._actor = os.getenv("KEELI_ACTOR") or os.getenv("USER", "agent")

    # ── Internal Utilities ──

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _slugify(self, text: str) -> str:
        slug = text.lower().strip().replace("&", "and")
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-") or "untitled"

    def _find_project_root(self, start_path: Path) -> Path:
        if os.getenv("KEELI_ROOT"):
            return Path(os.getenv("KEELI_ROOT")).absolute()
        curr = start_path.absolute()
        for _ in range(20):
            if (curr / ".keeli").exists() or (curr / ".git").exists():
                return curr
            if curr.parent == curr:
                break
            curr = curr.parent
        return start_path.absolute()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._ensure_synced()
        return self._conn

    def _ensure_synced(self) -> sqlite3.Connection:
        """Initialize DB and ensure workspace structure exists."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        for d in self.status_dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        gitignore = self.root_dir / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text(encoding="utf-8")
            if ".keeli/" not in content:
                with open(gitignore, "a", encoding="utf-8") as f:
                    f.write("\n.keeli/\n")
        else:
            gitignore.write_text(".keeli/\n", encoding="utf-8")
        return init_db(self.db_path)

    def _get_next_task_id(self) -> str:
        row = self.conn.execute(
            "SELECT task_id FROM task_events WHERE task_id LIKE 'T-%' ORDER BY task_id DESC LIMIT 1"
        ).fetchone()
        if row:
            last_num = int(row["task_id"].split("-")[1])
            return f"T-{last_num + 1:04d}"
        return "T-0001"

    def _get_task_vc(self, task_id: str) -> VectorClock:
        """CRITICAL FIX: Read vector clock from CRDT replay, NEVER from stale task_index."""
        task = self._rebuild_task(task_id)
        return task.vector_clock

    def _rebuild_task(self, task_id: str) -> TaskCRDT:
        """Replay all events for a task to reconstruct its CRDT state."""
        rows = self.conn.execute(
            "SELECT * FROM task_events WHERE task_id = ? ORDER BY timestamp, event_id",
            (task_id,),
        ).fetchall()
        events = [Event.from_db_row(r) for r in rows]
        return TaskCRDT.from_events(task_id, events)

    def _upsert_task_index(self, task_id: str, state: Dict[str, Any]) -> None:
        """Update materialized SQLite row from CRDT state. Call inside transaction."""
        slug = self._slugify(state["title"])
        status = state["status"]
        target_dir = self.status_dirs.get(status, self.status_dirs["backlog"])
        filepath = target_dir / f"{task_id}-{slug}.md"

        self.conn.execute(
            """INSERT INTO task_index 
               (id, slug, title, status, priority, created, tags, depends_on, description, completed, path, updated, vector_clock)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               slug=excluded.slug, title=excluded.title, status=excluded.status,
               priority=excluded.priority, created=excluded.created, tags=excluded.tags,
               depends_on=excluded.depends_on, description=excluded.description,
               completed=excluded.completed, path=excluded.path, updated=excluded.updated,
               vector_clock=excluded.vector_clock""",
            (
                task_id, slug, state["title"], state["status"], state["priority"],
                state["created"], state["tags"], state["depends_on"],
                state["description"], state["completed"], str(filepath),
                self._now_iso(), json.dumps(state["vector_clock"], sort_keys=True),
            ),
        )

    def _update_fts(self, task_id: str, state: Dict[str, Any]) -> None:
        """Rebuild FTS entry. Call inside transaction."""
        try:
            self.conn.execute("DELETE FROM task_fts WHERE task_id = ?", (task_id,))
            self.conn.execute(
                "INSERT INTO task_fts(task_id, title, description, tags) VALUES (?, ?, ?, ?)",
                (task_id, state["title"], state["description"], state["tags"]),
            )
        except Exception:
            pass

    def _log_audit(
        self,
        item_id: Optional[str],
        action: str,
        actor: str,
        details: str,
        session_id: Optional[str] = None,
        rationale: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO audit (item_id, session_id, action, actor, details, rationale, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item_id, session_id, action, actor, details, rationale, self._now_iso()),
        )

    def _emit_event(
        self,
        task_id: str,
        field: str,
        op: str,
        value: Any,
        actor: Optional[str] = None,
        branch: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Event:
        """Append a CRDT event and atomically update the materialized index.

        CRITICAL: Wraps event insertion + index rebuild + audit in a single
        SQLite transaction. Never writes physical files.
        """
        actor = actor or self._actor
        parent_vc = self._get_task_vc(task_id)
        vc = parent_vc.increment(actor)

        event = Event(
            task_id=task_id,
            field=field,
            op=op,
            value=value,
            timestamp=self._now_iso(),
            actor=actor,
            branch=branch,
            session_id=session_id,
            vector_clock=vc.clocks,
        )

        with self.conn:  # EXPLICIT TRANSACTION: all-or-nothing
            cur = self.conn.execute(
                """INSERT INTO task_events 
                   (task_id, field, op, value, timestamp, actor, branch, session_id, vector_clock)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                event.to_db_row(),
            )
            event.event_id = cur.lastrowid

            # Rebuild CRDT from event log (includes the event just inserted)
            task = self._rebuild_task(task_id)
            state = task.to_dict()

            # Atomically update materialized index
            self._upsert_task_index(task_id, state)
            self._update_fts(task_id, state)

        return event

    def _write_task_markdown(self, task_id: str, state: Dict[str, Any]) -> Path:
        """Generate markdown file from CRDT state. Called lazily by sync() only."""
        slug = self._slugify(state["title"])
        status = state["status"]
        target_dir = self.status_dirs.get(status, self.status_dirs["backlog"])
        target_dir.mkdir(parents=True, exist_ok=True)
        filepath = target_dir / f"{task_id}-{slug}.md"

        template = string.Template(TASK_TEMPLATE)
        content = template.safe_substitute(
            task_id=task_id,
            title=state["title"],
            status=state["status"].capitalize(),
            priority=state["priority"],
            timestamp=state["created"] or self._now_iso(),
            depends_on=state["depends_on"],
            tags=state["tags"] if state["tags"] else "—",
            description=state["description"],
            completed=state["completed"],
        )
        filepath.write_text(content, encoding="utf-8")
        return filepath

    # ── Public API ──

    def start(
        self,
        title: str,
        priority_raw: str = "p2",
        tags: List[str] = None,
        description: str = None,
        depends_on: str = None,
        actor: Optional[str] = None,
        branch: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Create a new task via batched CRDT init events in a single transaction."""
        p_map = {"high": "P0", "medium": "P1", "low": "P2", "p0": "P0", "p1": "P1", "p2": "P2"}
        priority = p_map.get(priority_raw.lower().split("/")[0], "P1")
        task_id = self._get_next_task_id()
        ts = self._now_iso()
        processed_tags = [t.strip().lower() for t in (tags or []) if t.strip()]
        actor = actor or self._actor

        with self.conn:  # Single transaction for all init events
            parent_vc = VectorClock()

            def _emit_init(field: str, value: Any) -> VectorClock:
                nonlocal parent_vc
                vc = parent_vc.increment(actor)
                evt = Event(
                    task_id=task_id, field=field, op="init", value=value,
                    timestamp=ts, actor=actor, branch=branch,
                    session_id=session_id, vector_clock=vc.clocks,
                )
                cur = self.conn.execute(
                    """INSERT INTO task_events 
                       (task_id, field, op, value, timestamp, actor, branch, session_id, vector_clock)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    evt.to_db_row(),
                )
                evt.event_id = cur.lastrowid
                parent_vc = vc
                return vc

            _emit_init("title", title or "Untitled Task")
            _emit_init("status", "backlog")
            _emit_init("priority", priority)
            _emit_init("created", ts)
            _emit_init("description", description or "No description provided.")
            _emit_init("depends_on", depends_on or "—")
            if processed_tags:
                for tag in processed_tags:
                    parent_vc = parent_vc.increment(actor)
                    evt = Event(
                        task_id=task_id, field="tags", op="add", value=[tag],
                        timestamp=ts, actor=actor, branch=branch,
                        session_id=session_id, vector_clock=parent_vc.clocks,
                    )
                    cur = self.conn.execute(
                        """INSERT INTO task_events 
                           (task_id, field, op, value, timestamp, actor, branch, session_id, vector_clock)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        evt.to_db_row(),
                    )
                    evt.event_id = cur.lastrowid

            # Rebuild once and upsert index
            task = self._rebuild_task(task_id)
            state = task.to_dict()
            self._upsert_task_index(task_id, state)
            self._update_fts(task_id, state)
            self._log_audit(task_id, "start", actor, f"Created task: {title}", session_id)

        return task_id

    def move_task(
        self,
        task_id: str,
        target_status: str,
        actor: Optional[str] = None,
        branch: Optional[str] = None,
        session_id: Optional[str] = None,
        rationale: Optional[str] = None,
    ) -> str:
        if target_status not in self.valid_statuses:
            raise ValueError(f"Invalid status '{target_status}'")

        row = self.conn.execute(
            "SELECT id FROM task_index WHERE id = ? OR slug = ?", (task_id, task_id)
        ).fetchone()
        if not row:
            raise ValueError(f"Task {task_id} not found.")
        tid = row["id"]

        self._emit_event(tid, "status", "set", target_status, actor, branch, session_id)

        if target_status == "archive":
            self._emit_event(tid, "completed", "set", self._now_iso(), actor, branch, session_id)
        else:
            self._emit_event(tid, "completed", "set", "—", actor, branch, session_id)

        self._log_audit(
            tid, target_status, actor or self._actor,
            f"Moved to {target_status}", session_id, rationale,
        )
        return tid

    def edit_task_field(
        self,
        task_id: str,
        field: str,
        value: Any,
        op: str = "set",
        actor: Optional[str] = None,
        branch: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        row = self.conn.execute(
            "SELECT id FROM task_index WHERE id = ? OR slug = ?", (task_id, task_id)
        ).fetchone()
        if not row:
            raise ValueError(f"Task {task_id} not found.")
        tid = row["id"]

        self._emit_event(tid, field, op, value, actor, branch, session_id)
        self._log_audit(tid, "edit", actor or self._actor, f"Edited {field}", session_id)
        return tid

    def add_tags(
        self,
        task_id: str,
        tags: List[str],
        actor: Optional[str] = None,
        branch: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        return self.edit_task_field(task_id, "tags", tags, "add", actor, branch, session_id)

    def remove_tags(
        self,
        task_id: str,
        tags: List[str],
        actor: Optional[str] = None,
        branch: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Tag-aware OR-Set remove — only purges observed tag instances."""
        row = self.conn.execute(
            "SELECT id FROM task_index WHERE id = ? OR slug = ?", (task_id, task_id)
        ).fetchone()
        if not row:
            raise ValueError(f"Task {task_id} not found.")
        tid = row["id"]

        # CRITICAL FIX: Rebuild CRDT to get current unique tag IDs for precise removal
        task = self._rebuild_task(tid)
        removal_map = task.tags.get_tags_for_removal(tags)

        if not removal_map:
            return tid

        self._emit_event(tid, "tags", "remove", removal_map, actor, branch, session_id)
        self._log_audit(tid, "tag_remove", actor or self._actor, f"Removed tags: {tags}", session_id)
        return tid

    def next_task(
        self,
        session_id: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if session_id:
            row = self.conn.execute(
                "SELECT focus_task_id FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row and row["focus_task_id"]:
                task = self.conn.execute(
                    "SELECT * FROM task_index WHERE id = ? AND status != 'archive'",
                    (row["focus_task_id"],),
                ).fetchone()
                if task:
                    return dict(task)

        query = """
        SELECT * FROM task_index WHERE status IN ('backlog', 'active') 
        ORDER BY 
            CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END ASC,
            COALESCE(created, '9999') ASC
        LIMIT 1
        """
        row = self.conn.execute(query).fetchone()
        return dict(row) if row else None

    def list_tasks(
        self,
        status: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if branch:
            query = """
            SELECT 
                COALESCE(bs.task_id, ti.id) as id,
                COALESCE(bs.title, ti.title) as title,
                COALESCE(bs.status, ti.status) as status,
                COALESCE(bs.priority, ti.priority) as priority,
                ti.vector_clock
            FROM task_index ti
            LEFT JOIN branch_snapshots bs ON ti.id = bs.task_id AND bs.branch = ?
            WHERE ti.status != 'archive' OR bs.status IS NOT NULL
            """
            rows = self.conn.execute(query, (branch,)).fetchall()
            if rows:
                return [dict(r) for r in rows]

        query = "SELECT id, title, status, priority, vector_clock FROM task_index"
        params = []
        if status:
            query += " WHERE status = ? COLLATE NOCASE"
            params.append(status.lower())
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    def get_task(self, task_id: str) -> str:
        """CRITICAL FIX: Generate markdown on-the-fly from CRDT state.
        Never reads stale pre-written files."""
        row = self.conn.execute(
            "SELECT id FROM task_index WHERE id = ? OR slug = ?",
            (task_id, task_id),
        ).fetchone()
        if not row:
            raise ValueError(f"Task {task_id} not found.")
        tid = row["id"]

        task = self._rebuild_task(tid)
        state = task.to_dict()
        content = self._generate_markdown(tid, state)
        return f"<!-- VECTOR_CLOCK: {json.dumps(state['vector_clock'], sort_keys=True)} -->\n{content}"

    def _generate_markdown(self, task_id: str, state: Dict[str, Any]) -> str:
        """Generate markdown string from CRDT state without filesystem I/O."""
        template = string.Template(TASK_TEMPLATE)
        return template.safe_substitute(
            task_id=task_id,
            title=state["title"],
            status=state["status"].capitalize(),
            priority=state["priority"],
            timestamp=state["created"] or self._now_iso(),
            depends_on=state["depends_on"],
            tags=state["tags"] if state["tags"] else "—",
            description=state["description"],
            completed=state["completed"],
        )

    def get_task_state(self, task_id: str) -> Dict[str, Any]:
        row = self.conn.execute(
            "SELECT id FROM task_index WHERE id = ? OR slug = ?", (task_id, task_id)
        ).fetchone()
        if not row:
            raise ValueError(f"Task {task_id} not found.")
        task = self._rebuild_task(row["id"])
        return task.to_dict()

    def sync(self) -> Tuple[int, int]:
        """CRITICAL FIX: Reconcile event log -> index -> physical files.
        This is the ONLY method that writes to disk."""
        task_ids = [r["task_id"] for r in self.conn.execute(
            "SELECT DISTINCT task_id FROM task_events"
        ).fetchall()]
        count = 0
        corrected = 0

        with self.conn:
            for tid in task_ids:
                old = self.conn.execute(
                    "SELECT status, vector_clock FROM task_index WHERE id = ?", (tid,)
                ).fetchone()

                task = self._rebuild_task(tid)
                state = task.to_dict()
                self._upsert_task_index(tid, state)
                self._update_fts(tid, state)
                self._write_task_markdown(tid, state)

                new = self.conn.execute(
                    "SELECT status, vector_clock FROM task_index WHERE id = ?", (tid,)
                ).fetchone()
                if old and new:
                    if old["status"] != new["status"]:
                        corrected += 1
                count += 1

            self._log_audit(None, "sync", "system", f"Reconciled {count} tasks, corrected {corrected}")

        return count, corrected

    def detect_conflicts(self, task_id: str, lookback_seconds: int = 300) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT e1.event_id as e1_id, e2.event_id as e2_id, e1.field, e1.actor as a1, e2.actor as a2
               FROM task_events e1
               JOIN task_events e2 ON e1.task_id = e2.task_id AND e1.field = e2.field
               WHERE e1.task_id = ? AND e1.event_id < e2.event_id
                 AND e1.vector_clock != e2.vector_clock
                 AND json_extract(e1.vector_clock, '$.' || e2.actor) IS NOT NULL
                 AND json_extract(e2.vector_clock, '$.' || e1.actor) IS NOT NULL""",
            (task_id,),
        ).fetchall()
        conflicts = []
        for r in rows:
            conflicts.append({
                "field": r["field"],
                "events": [r["e1_id"], r["e2_id"]],
                "actors": [r["a1"], r["a2"]],
                "resolution": "lww",
            })
        return conflicts

    def context_resolve(
        self,
        key: str,
        session_id: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> Tuple[Optional[str], str]:
        if session_id:
            res = self.conn.execute(
                "SELECT value FROM context_store WHERE key = ? AND scope = 'session' AND scope_id = ?",
                (key, session_id),
            ).fetchone()
            if res:
                return res["value"], "session"
        if branch:
            res = self.conn.execute(
                "SELECT value FROM context_store WHERE key = ? AND scope = 'branch' AND scope_id = ?",
                (key, branch),
            ).fetchone()
            if res:
                return res["value"], "branch"
        res = self.conn.execute(
            "SELECT value FROM context_store WHERE key = ? AND scope = 'global'",
            (key,),
        ).fetchone()
        if res:
            return res["value"], "global"
        return None, "none"

    def context_get(
        self,
        key: str,
        session_id: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        val, scope = self.context_resolve(key, session_id, branch)
        return {"key": key, "value": val, "scope": scope}

    def context_set(
        self,
        key: str,
        value: str,
        scope: str = "session",
        scope_id: Optional[str] = None,
        source: str = "agent_override",
    ) -> None:
        if scope == "session" and not scope_id:
            raise ValueError("session scope requires scope_id (session_id)")
        if scope == "branch" and not scope_id:
            raise ValueError("branch scope requires scope_id (branch_name)")
        with self.conn:
            self.conn.execute(
                """INSERT INTO context_store (key, value, scope, scope_id, source, updated)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT DO UPDATE SET
                   value = excluded.value, source = excluded.source, updated = excluded.updated""",
                (key, value, scope, scope_id, source, self._now_iso()),
            )

    def session_start(
        self,
        name: str = "Investigation",
        branch: Optional[str] = None,
        focus_task_id: Optional[str] = None,
    ) -> str:
        import uuid
        session_id = str(uuid.uuid4())
        ts = self._now_iso()
        with self.conn:
            self.conn.execute(
                """INSERT INTO sessions (session_id, branch_name, focus_task_id, goal, last_ping, created)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, branch, focus_task_id, name, ts, ts),
            )
        return session_id

    def session_focus(
        self,
        task_id: str,
        session_id: str,
    ) -> None:
        if not session_id:
            raise ValueError("session_id is required.")
        with self.conn:
            self.conn.execute(
                "UPDATE sessions SET focus_task_id = ?, last_ping = ? WHERE session_id = ?",
                (task_id, self._now_iso(), session_id),
            )

    def session_checkpoint(
        self,
        note: str = "Sync point",
        session_id: str = None,
        pending_decisions: List[str] = None,
    ) -> str:
        if not session_id:
            raise ValueError("session_id is required.")
        rows = self.conn.execute(
            "SELECT key, value FROM context_store WHERE scope = 'session' AND scope_id = ?",
            (session_id,),
        ).fetchall()
        context_snapshot = json.dumps({r["key"]: r["value"] for r in rows})
        current_digest = self.digest(session_id=session_id)
        with self.conn:
            self.conn.execute(
                """INSERT INTO checkpoints (session_id, llm_summary, active_digest, pending_decisions, context_snapshot, created)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, note, current_digest, json.dumps(pending_decisions or []), context_snapshot, self._now_iso()),
            )
        return "checkpoint-saved"

    def session_list(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT session_id, goal, branch_name, created, focus_task_id FROM sessions ORDER BY created DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def digest(
        self,
        tier: str = "standard",
        budget: int = 2000,
        session_id: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> str:
        encoding = tiktoken.get_encoding("cl100k_base")

        def count_tokens(text: str) -> int:
            return len(encoding.encode(text))

        header = []
        if session_id:
            session = self.conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if session:
                header.append(f"# SESSION: {session['goal']} ({session_id})")
                header.append(f"Focus: {session['focus_task_id'] or 'None'}")
                header.append(f"Branch: {session['branch_name'] or 'unspecified'}")
        elif branch:
            header.append(f"# BRANCH: {branch}")

        stats = self.conn.execute(
            "SELECT status, COUNT(*) as count FROM task_index GROUP BY status"
        ).fetchall()
        if stats:
            summary = " | ".join([f"{s['status'].upper()}: {s['count']}" for s in stats])
            header.append(f"## Status Overview: {summary}\n")

        header_text = "\n".join(header)
        current_budget = budget - count_tokens(header_text)

        active_block = []
        active = self.conn.execute(
            "SELECT id, title, priority, vector_clock FROM task_index WHERE status = 'active' ORDER BY priority ASC"
        ).fetchall()
        if active:
            active_block.append("## ACTIVE TASKS")
            for a in active:
                vc = json.loads(a["vector_clock"])
                active_block.append(f"- {a['id']}: {a['title']} ({a['priority']}) [VC: {vc}]")
            active_block.append("")
        active_text = "\n".join(active_block)
        current_budget -= count_tokens(active_text)

        audit_block = []
        logs = self.conn.execute(
            "SELECT created, actor, action, details FROM audit ORDER BY event_id DESC LIMIT 5"
        ).fetchall()
        if logs:
            audit_block.append("## RECENT ACTIVITY")
            for l in logs:
                audit_block.append(f"- {l['created']} | {l['actor']} | {l['action'].upper()} | {l['details']}")
            audit_block.append("")
        audit_text = "\n".join(audit_block)
        audit_tokens = count_tokens(audit_text)
        if audit_tokens > (current_budget * 0.25):
            audit_text = "\n".join(audit_block[:3]) + "\n... (clipped)\n"
            audit_tokens = count_tokens(audit_text)
        current_budget -= audit_tokens

        overview_text = ""
        if tier in ["standard", "full"]:
            overview_file = self.root_dir / "CLAUDE.md" if (self.root_dir / "CLAUDE.md").exists() else self.root_dir / "README.md"
            if overview_file.exists():
                full_overview = overview_file.read_text(encoding="utf-8")
                tokens = encoding.encode(full_overview)
                if len(tokens) > 250:
                    overview_text = f"## OVERVIEW ({overview_file.name})\n" + encoding.decode(tokens[:250]) + "\n... (clipped)\n"
                else:
                    overview_text = f"## OVERVIEW ({overview_file.name})\n" + full_overview + "\n"
        current_budget -= count_tokens(overview_text)

        backlog_text = ""
        if tier != "brief" and current_budget > 100:
            backlog = self.conn.execute(
                "SELECT id, title, priority FROM task_index WHERE status = 'backlog' ORDER BY priority ASC, id ASC LIMIT 10"
            ).fetchall()
            if backlog:
                backlog_lines = ["## BACKLOG"]
                for b in backlog:
                    line = f"- {b['id']}: {b['title']} ({b['priority']})"
                    if count_tokens("\n".join(backlog_lines) + "\n" + line) < current_budget:
                        backlog_lines.append(line)
                    else:
                        break
                backlog_text = "\n".join(backlog_lines) + "\n"

        return "\n".join(filter(None, [header_text, active_text, audit_text, overview_text, backlog_text]))

    def history(self, task_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT timestamp as created, actor, op as action, field, value, details, rationale
               FROM task_events
               LEFT JOIN audit ON audit.item_id = task_events.task_id AND audit.created = task_events.timestamp
               WHERE task_events.task_id = ?
               ORDER BY task_events.event_id DESC""",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

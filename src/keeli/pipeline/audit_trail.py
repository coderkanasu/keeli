"""Evidence persistence for pipeline gate execution."""

from __future__ import annotations

import contextlib
import json
import sqlite3
from pathlib import Path


class AuditTrail:
    """Persist and query gate evidence records in keeli_state.db."""

    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            from keeli.main import _init_state_db, _state_db_path

            _init_state_db()
            self.db_path = _state_db_path()
        else:
            self.db_path = db_path
            from keeli.main import _init_state_db

            _init_state_db()
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with contextlib.closing(self._connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS persona_gates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    gate_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    entered_at TEXT NOT NULL,
                    exited_at TEXT,
                    UNIQUE(item_id, gate_name)
                );

                CREATE TABLE IF NOT EXISTS gate_evidence (
                    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    gate_name TEXT NOT NULL,
                    actor TEXT,
                    status TEXT NOT NULL,
                    checksum TEXT,
                    payload_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_gate_evidence_item ON gate_evidence(item_id);
                CREATE INDEX IF NOT EXISTS idx_gate_evidence_gate ON gate_evidence(gate_name);
                """
            )
            conn.commit()

    def record_gate_evidence(
        self,
        item_id: str,
        gate_name: str,
        status: str,
        *,
        actor: str,
        checksum: str | None,
        payload: dict[str, object] | None,
    ) -> int:
        """Insert one immutable gate evidence row and return evidence_id."""
        from keeli.main import _now_iso

        payload_json = json.dumps(payload or {}, sort_keys=True)
        now = _now_iso()
        with contextlib.closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO gate_evidence(item_id, gate_name, actor, status, checksum, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, gate_name, actor, status, checksum, payload_json, now),
            )
            conn.execute(
                """
                INSERT INTO persona_gates(item_id, gate_name, status, entered_at, exited_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(item_id, gate_name)
                DO UPDATE SET
                    status=excluded.status,
                    exited_at=excluded.exited_at
                """,
                (item_id, gate_name, status, now, now if status in ("passed", "blocked") else None),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def completed_gates(self, item_id: str) -> list[str]:
        """Return completed gate names for a task in deterministic order."""
        with contextlib.closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT gate_name
                FROM persona_gates
                WHERE item_id = ? AND status = 'passed'
                ORDER BY id ASC
                """,
                (item_id,),
            ).fetchall()
        return [str(row["gate_name"]) for row in rows]

#!/usr/bin/env python3
"""
Keeli CLI — main entry-point.

Commands
--------
  init                  Scaffold the Keeli framework in the current project.
  start <name>          Create a new task file in docs/tasks/<slug>.md.
  bug <title>           Log a bug as docs/tasks/bug-<slug>.md.
  feature <title>       Create a feature request docs/tasks/feat-<slug>.md.
  progress <name>       Mark a task as In Progress.
  block <name>          Mark a task as Blocked.
  complete <name>       Mark a task as Completed and show the next task.
  reopen <name>         Reopen a Completed task (back to In Progress).
  next                  Show the next task by priority and age.
  log <message>         Append a timestamped entry to docs/ai_log.md.
  resume                Dump current project context for a new AI session.
  status                Health-check: verify all expected files exist.
  clear-log             Reset docs/ai_log.md to its default state.
  update                Update copilot-instructions.md to the latest template.
  analyze <slug>        Analyze a task and inject AI context hints (TF-IDF).
"""

import argparse
import contextlib
import io
import json
import os
import math as _math
import re
import sqlite3
import subprocess
import sys
import textwrap
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from keeli.templates import (
    AI_LOG_MD,
    BUG_TEMPLATE,
    COPILOT_INSTRUCTIONS,
    DECISION_MD,
    EPIC_TEMPLATE,
    FEATURE_TEMPLATE,
    GITIGNORE_CONTENT,
    PERSONAS_MD,
    PROJECT_MD,
    SCHEMA_VERSION,
    SKILLS_MD,
    STACK_PRESET_ALIASES,
    STACK_PRESETS,
    STORY_TEMPLATE,
    TASK_CHECKLISTS,
    TASK_TEMPLATE,
    get_flavor_instructions,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_envelope(command: str, ok: bool, data: dict[str, object] | None = None, error: str | None = None) -> dict[str, object]:
    """Build a stable machine-readable response envelope for CLI automation."""
    payload: dict[str, object] = {
        "ok": ok,
        "command": command,
        "timestamp": _now_iso(),
        "data": data or {},
    }
    if error:
        payload["error"] = error
    return payload


def _slugify(text: str) -> str:
    """Turn a task title into a filesystem-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


_STATUS_CANONICAL_MAP: dict[str, str] = {
    "backlog": "Backlog",
    "todo": "Backlog",
    "in progress": "In Progress",
    "in-progress": "In Progress",
    "progress": "In Progress",
    "review": "Review",
    "in review": "Review",
    "in-review": "Review",
    "blocked": "Blocked",
    "complete": "Completed",
    "completed": "Completed",
    "done": "Completed",
    "archived": "Archived",
}


def _canonical_status(value: str | None) -> str | None:
    """Normalize user status input and stored status labels to canonical values."""
    if value is None:
        return None
    key = str(value).strip().lower()
    if not key:
        return None
    return _STATUS_CANONICAL_MAP.get(key, str(value).strip())


def _refresh_state_from_markdown() -> None:
    """Best-effort read-side sync so list/find/status reflect latest markdown edits."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        return
    _init_state_db()
    _db_sync_all_task_files()


def _write_file(path: Path, content: str, *, force: bool = False) -> None:
    """Write *content* to *path*, respecting the force flag."""
    if path.exists() and not force:
        print(f"  ⚠️  {path} already exists. Use --force to overwrite.")
        return
    verb = "Overwrote" if path.exists() else "Created"
    path.write_text(content)
    print(f"  ✅ {verb} {path}")


def _tail(path: Path, n: int = 30) -> str:
    """Return the last *n* lines of a file, or the whole file if shorter."""
    if not path.exists():
        return ""
    lines = path.read_text().splitlines()
    return "\n".join(lines[-n:])


def _find_project_root() -> Path:
    """Walk up from cwd to find the directory containing docs/project.md.

    This lets CLI commands and the MCP server work correctly even when run
    from a subdirectory or when the server process starts in a parent directory.
    Falls back to cwd when no project root is found (e.g. during init).
    """
    here = Path.cwd()
    for candidate in [here, *here.parents]:
        if (candidate / "docs" / "project.md").exists():
            return candidate
    return here


_OBJECTIVE_HINT = (
    "⚠️  No objective — add one with -o 'text', -o '@file.md', or JSON:\n"
    "       -o '{\"goal\":\"...\",\"why\":\"...\",\"criteria\":[\"...\"],\"out_of_scope\":[\"...\"]}'"
)


def _resolve_objective(raw: "str | None") -> str:
    """Resolve -o/--objective input to plain markdown text.

    Accepts three formats:
    - Plain text       → returned as-is
    - "@path/to/file"  → content of the file is used
    - JSON dict        → formatted into structured markdown, e.g.:

        {"goal": "Add login", "why": "Users need auth",
         "criteria": ["OAuth works", "Token expires"],
         "out_of_scope": ["Admin panel"]}

        becomes:

        **Goal:** Add login
        **Why:** Users need auth
        **Success Criteria:**
        - OAuth works
        - Token expires
        **Out of Scope:**
        - Admin panel
    """
    if not raw:
        return ""
    raw = raw.strip()
    if raw.startswith("@"):
        obj_path = Path(raw[1:])
        if obj_path.exists():
            return obj_path.read_text().strip()
        print(f"⚠️  Objective file '{obj_path}' not found. Using empty placeholder.")
        return ""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            lines: list[str] = []
            if "goal" in data:
                lines.append(f"**Goal:** {data['goal']}")
            if "why" in data:
                lines.append(f"**Why:** {data['why']}")
            if isinstance(data.get("criteria"), list):
                lines.append("**Success Criteria:**")
                lines.extend(f"- {c}" for c in data["criteria"])
            if isinstance(data.get("out_of_scope"), list):
                lines.append("**Out of Scope:**")
                lines.extend(f"- {x}" for x in data["out_of_scope"])
            return "\n".join(lines) if lines else raw
    except (json.JSONDecodeError, TypeError):
        pass
    return raw


# ── Transition guard helpers ────────────────────────────────────────────────

_SEC_NFR = "## Non-Functional Requirements"
_SEC_TEST_STRATEGY = "## Test Strategy"
_SEC_EVIDENCE = "## Evidence"
_SEC_VERIFICATION = "## Verification"

# Items containing these keywords require a human persona to sign off.
# Guards and `keeli tick` intentionally skip them.
_GATE_KEYWORDS: tuple[str, ...] = ("@qa", "@security", "@author")


def _is_gate_item(line: str) -> bool:
    """Return True if *line* is a checklist item that requires human sign-off.

    Gate items contain @security or @author and must not be ticked
    automatically, nor should they block automated transitions.
    """
    return any(kw in line for kw in _GATE_KEYWORDS)


def _section_is_filled(section_header: str) -> Callable[[str], bool]:
    """Return a predicate that passes only if *section_header* exists in the
    file text AND has at least one non-comment, non-empty line after it
    (before the next ``##`` heading).
    """
    def _check(text: str) -> bool:
        lines = text.splitlines()
        in_section = False
        for line in lines:
            if line.strip() == section_header.strip():
                in_section = True
                continue
            if in_section:
                if line.startswith("## "):
                    # Next heading reached without finding content
                    return False
                stripped = line.strip()
                if stripped and not stripped.startswith("<!--"):
                    return True
        return False

    return _check


def _section_body(text: str, section_header: str) -> list[str]:
    """Return non-empty body lines for a markdown section (until next ``##``)."""
    lines = text.splitlines()
    in_section = False
    body: list[str] = []
    for line in lines:
        if line.strip() == section_header.strip():
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            stripped = line.strip()
            if stripped:
                body.append(stripped)
    return body


def _section_has_reference(section_lines: list[str]) -> bool:
    """Heuristic check for link/reference-like evidence lines."""
    placeholder_hints = (
        "<!--",
        "tbd",
        "todo",
        "add",
        "replace this",
        "n/a",
    )
    ref_markers = (
        "http://",
        "https://",
        "/",
        ".md",
        ".py",
        ".json",
        "test",
        "pytest",
        "commit",
        "sha",
        "log",
        "report",
        "artifact",
        "evidence",
    )
    for raw in section_lines:
        line = raw.lower()
        if line.startswith("- [ ]"):
            continue
        if any(hint in line for hint in placeholder_hints):
            continue
        if any(marker in line for marker in ref_markers):
            return True
    return False


def _completion_evidence_errors(text: str) -> list[str]:
    """Validate task completion prerequisites for evidence-linked done state."""
    errors: list[str] = []
    evidence_lines = _section_body(text, _SEC_EVIDENCE)
    verification_lines = _section_body(text, _SEC_VERIFICATION)

    if not evidence_lines:
        errors.append("Missing required section content: ## Evidence")
    elif not _section_has_reference(evidence_lines):
        errors.append("## Evidence must include at least one concrete link/reference to delivery artifacts")

    if not verification_lines:
        errors.append("Missing required section content: ## Verification")
    elif not _section_has_reference(verification_lines):
        errors.append("## Verification must include at least one concrete link/reference to validation artifacts")

    return errors


def _upsert_section_stub(text: str, section_header: str, stub_lines: list[str]) -> tuple[str, bool]:
    """Replace or create a section body with scaffold lines when evidence is missing."""
    lines = text.splitlines()
    start_idx = None
    for idx, line in enumerate(lines):
        if line.strip() == section_header.strip():
            start_idx = idx
            break

    if start_idx is None:
        suffix = "\n" if text.endswith("\n") else "\n\n"
        block = "\n".join([section_header, *stub_lines])
        return text + suffix + block + "\n", True

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        if lines[idx].startswith("## "):
            end_idx = idx
            break

    existing = [l.strip() for l in lines[start_idx + 1:end_idx] if l.strip()]
    if existing and _section_has_reference(existing):
        return text, False

    new_lines = [*lines[: start_idx + 1], *stub_lines, *lines[end_idx:]]
    return "\n".join(new_lines), True


def _scaffold_completion_sections(text: str) -> tuple[str, list[str]]:
    """Inject pragmatic Evidence/Verification placeholders for completion readiness."""
    scaffolded: list[str] = []
    updated = text

    updated, changed_evidence = _upsert_section_stub(
        updated,
        _SEC_EVIDENCE,
        [
            "- Delivery artifact: docs/ai_log.md",
            "- Commit: <git-sha>",
        ],
    )
    if changed_evidence:
        scaffolded.append("Evidence")

    updated, changed_verification = _upsert_section_stub(
        updated,
        _SEC_VERIFICATION,
        [
            "- Test command: pytest -q",
            "- Validation report: tests/<file>.py",
        ],
    )
    if changed_verification:
        scaffolded.append("Verification")

    return updated, scaffolded


def _handshake_signed(persona: str) -> Callable[[str], bool]:
    """Return a predicate: True if *persona* has signed the handshake.
    
    Checks the ## Handshakes table for a row like:
      | @po | ☑ signed | 2026-03-03T12:34:56Z | User story complete |
    
    Signed status is ☑ or [x] (checked).
    """
    def _check(text: str) -> bool:
        lines = text.splitlines()
        in_handshakes = False
        for i, line in enumerate(lines):
            if line.strip().startswith("## Handshakes"):
                in_handshakes = True
                continue
            if in_handshakes:
                if line.startswith("## "):
                    # Next section reached without finding the persona row
                    return False
                if f"| @{persona} " in line or f"| @{persona}|" in line:
                    # Found the row; check if it has ☑ or [x]
                    return "☑" in line or "[x]" in line.split("|")[2]
        return False
    
    return _check


def _handshake_personas_in_text(text: str) -> list[str]:
    """Return persona slugs listed in the task's Handshakes table.

    Parses rows like: `| @developer | ... |` and returns `['developer', ...]`
    in table order.
    """
    personas: list[str] = []
    in_handshakes = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Handshakes"):
            in_handshakes = True
            continue
        if in_handshakes and stripped.startswith("## "):
            break
        if in_handshakes:
            m = re.match(r"\|\s*@([a-z0-9-]+)\s*\|", stripped)
            if m:
                personas.append(m.group(1))
    return personas


def _handshake_all_signed_off(text: str) -> bool:
    """ADR-009: Check if ALL personas have signed off on the task.
    
    Returns True only if all 5 personas (@po, @architect, @developer, @security, @author)
    have ☑ or [x] in the Handshakes table. Returns False if any persona is missing or unsigned.
    
    This is a file-first validation check (no tool calls) used at CLI boundaries
    (keeli_complete) to ensure full handshake before archiving.
    """
    personas = _handshake_personas_in_text(text) or ["po", "architect", "developer", "security", "author"]
    
    # Check each persona
    for persona in personas:
        # Use the existing _handshake_signed check
        if not _handshake_signed(persona)(text):
            return False
    
    return True


def _validate_transition(
    path: Path,
    rules: list[tuple[str, Callable[[str], bool]]],
) -> list[str]:
    """Read *path* and evaluate each ``(error_message, predicate)`` rule.

    A rule **passes** when ``predicate(file_text)`` returns ``True``.
    Returns a list of error messages for every rule that failed.
    An empty list means all rules passed.
    """
    text = path.read_text()
    return [msg for msg, pred in rules if not pred(text)]


def _get_hierarchy_type(filename: str) -> str:
    """Determine if a task file is an epic, story, or task.
    
    Returns one of: "epic", "story", "task"
    """
    base = Path(filename).stem
    if base.startswith("epic-"):
        return "epic"
    elif base.startswith("story-"):
        return "story"
    else:
        return "task"


def _validate_hierarchy(path: Path) -> list[str]:
    """ADR-008: Validate Epic > Story > Task hierarchy.
    
    Returns a list of hierarchy errors. Empty list = all hierarchy checks passed.
    
    Rules:
      - Epic files: Cannot have **Epic:** or **Story:** fields set (must be empty/None)
      - Story files: Must have **Epic:** field set to a non-None value
      - Task files: Must have both **Epic:** and **Story:** fields set to non-None values
    
    Note: If both Epic and Story are "None" (default template values), hierarchy checks
    are skipped. This allows test suites to work without full epic/story setup. Real
    workflows that involve transitions will eventually require proper hierarchy.
    """
    text = path.read_text()
    file_type = _get_hierarchy_type(path.name)
    errors: list[str] = []
    
    epic_value = _parse_task_field(text, "Epic").strip()
    story_value = _parse_task_field(text, "Story").strip()
    
    # If BOTH epic and story are at default values ("None"), skip hierarchy check
    # This allows tests and simple single-task workflows without epic structure
    if epic_value.lower() == "none" and story_value.lower() == "none":
        if file_type != "epic":
            # Still allow epics with default values
            return []
    
    if file_type == "epic":
        # Epics should not have Epic or Story fields set
        if epic_value and epic_value.lower() != "none":
            errors.append(f"Epic file cannot have **Epic:** field set (found: {epic_value})")
        if story_value and story_value.lower() != "none":
            errors.append(f"Epic file cannot have **Story:** field set (found: {story_value})")
    
    elif file_type == "story":
        # Stories must have Epic field set (unless both are at defaults)
        if epic_value.lower() == "none" and story_value.lower() != "none":
            errors.append("Story must have an **Epic:** field set (hierarchy violation: Story > Epic required)")
    
    elif file_type == "task":
        # Tasks must have both Epic and Story set (unless both are at defaults)
        if epic_value.lower() == "none" and story_value.lower() != "none":
            errors.append("Task must have an **Epic:** field set (hierarchy violation: Task > Epic required)")
        if story_value.lower() == "none" and epic_value.lower() != "none":
            errors.append("Task must have a **Story:** field set (hierarchy violation: Task > Story required)")
        # If one is set but not the other, it's a problem
        if (epic_value.lower() != "none" and story_value.lower() == "none") or \
           (epic_value.lower() == "none" and story_value.lower() != "none"):
            errors.append("Task must have BOTH **Epic:** and **Story:** fields set (or both default to None)")
    
    return errors


# ── Index / Ledger helpers ─────────────────────────────────────────────────

_INDEX_PATH = Path("docs/.keeli_index.json")
_STATE_DB_FILENAME = "keeli_state.db"
_PRE_COMMIT_HOOK = """#!/bin/sh
set -eu

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT"

paths=$(git diff --cached --name-only --diff-filter=ACMR)
if [ -n "$paths" ]; then
    # shellcheck disable=SC2086
    keeli validate-task-state --paths $paths
else
    keeli validate-task-state
fi
"""

_POST_COMMIT_HOOK = """#!/bin/sh
set -eu

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT"

keeli capture-commit-state
"""
_INDEX_PREFIXES: dict[str, str] = {
    "task": "T",
    "epic": "E",
    "story": "S",
    "bug": "BUG",
    "feat": "FEAT",
}


def _load_index() -> dict:
    """Load docs/.keeli_index.json, returning a fresh blank index if missing/corrupt."""
    if _INDEX_PATH.exists():
        try:
            return json.loads(_INDEX_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "schema": "1.0",
        "counters": {"T": 0, "E": 0, "S": 0, "BUG": 0, "FEAT": 0},
        "items": [],
    }


def _save_index(index: dict) -> None:
    """Persist the index to docs/.keeli_index.json."""
    _INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INDEX_PATH.write_text(json.dumps(index, indent=2))


def _allocate_id(
    item_type: str,
    title: str,
    slug: str,
    status: str = "Backlog",
    priority: str = "P1",
    epic: "str | None" = None,
    story: "str | None" = None,
) -> str:
    """Atomically allocate the next immutable ID and register the item in the index.

    ID format:
        T-0001  task
        E-0001  epic
        S-0001  story
        BUG-0001  bug
        FEAT-0001 feature
    """
    prefix = _INDEX_PREFIXES.get(item_type, "T")
    index = _load_index()
    index["counters"][prefix] = index["counters"].get(prefix, 0) + 1
    n = index["counters"][prefix]
    item_id = f"{prefix}-{n:04d}"
    entry: dict = {
        "id": item_id,
        "type": item_type,
        "title": title,
        "slug": slug,
        "status": status,
        "priority": priority,
        "epic": epic,
        "story": story,
        "created": _now_iso(),
        "completed": None,
        "archived": False,
    }
    index["items"].append(entry)
    _save_index(index)
    return item_id


def _index_update_status(
    task_id: str,
    *,
    status: "str | None" = None,
    completed: "str | None" = None,
    archived: "bool | None" = None,
) -> None:
    """Patch status / completed / archived for a single item in the index."""
    if not task_id:
        return
    index = _load_index()
    for item in index["items"]:
        if item.get("id") == task_id:
            if status is not None:
                item["status"] = status
            if completed is not None:
                item["completed"] = completed
            if archived is not None:
                item["archived"] = archived
            break
    _save_index(index)


def _state_db_path() -> Path:
    """Return the SQLite state database path for the current project root."""
    return _find_project_root() / _STATE_DB_FILENAME


def _connect_state_db() -> sqlite3.Connection:
    """Open a connection to the local Keeli state database."""
    conn = sqlite3.connect(_state_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_state_db() -> None:
    """Create the SQLite state database and schema if missing."""
    with contextlib.closing(_connect_state_db()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS state_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS work_items (
                item_id TEXT PRIMARY KEY,
                item_type TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                priority TEXT NOT NULL,
                epic_slug TEXT,
                story_slug TEXT,
                persona TEXT,
                context_note TEXT,
                depends_on TEXT,
                source_path TEXT,
                created_at TEXT,
                completed_at TEXT,
                archived INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status);
            CREATE INDEX IF NOT EXISTS idx_work_items_priority ON work_items(priority);
            CREATE INDEX IF NOT EXISTS idx_work_items_epic_slug ON work_items(epic_slug);
            CREATE INDEX IF NOT EXISTS idx_work_items_story_slug ON work_items(story_slug);
            CREATE INDEX IF NOT EXISTS idx_work_items_archived ON work_items(archived);

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT,
                actor TEXT,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO state_meta(key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        conn.execute(
            "INSERT OR REPLACE INTO state_meta(key, value) VALUES (?, ?)",
            ("storage_mode", "sqlite"),
        )
        conn.commit()


def _item_type_from_path(path: Path) -> str:
    """Map a task file path to its logical work-item type."""
    name = path.name
    if name.startswith("epic-"):
        return "epic"
    if name.startswith("story-"):
        return "story"
    if name.startswith("bug-"):
        return "bug"
    if name.startswith("feat-"):
        return "feat"
    return "task"


def _title_from_task_text(text: str) -> str:
    """Extract the user-facing title from the first markdown heading."""
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    match = re.match(r"^#\s+(?:Task|Story|Epic|Bug|Feature):\s+(.*)$", first)
    return match.group(1).strip() if match else first.lstrip("# ").strip()


def _normalize_field(value: str) -> str | None:
    """Normalize empty/None-ish markdown field values to None."""
    stripped = value.strip()
    if not stripped or stripped.lower() == "none" or stripped == "—":
        return None
    return stripped


def _db_upsert_work_item(
    *,
    item_id: str,
    item_type: str,
    slug: str,
    title: str,
    status: str,
    priority: str,
    epic_slug: str | None,
    story_slug: str | None,
    persona: str | None,
    context_note: str | None,
    depends_on: str | None,
    source_path: str,
    created_at: str | None,
    completed_at: str | None,
    archived: bool,
) -> None:
    """Insert or update a work item in SQLite."""
    _init_state_db()
    now = _now_iso()
    with contextlib.closing(_connect_state_db()) as conn:
        conn.execute(
            """
            INSERT INTO work_items (
                item_id, item_type, slug, title, status, priority,
                epic_slug, story_slug, persona, context_note, depends_on,
                source_path, created_at, completed_at, archived, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                item_type = excluded.item_type,
                slug = excluded.slug,
                title = excluded.title,
                status = excluded.status,
                priority = excluded.priority,
                epic_slug = excluded.epic_slug,
                story_slug = excluded.story_slug,
                persona = excluded.persona,
                context_note = excluded.context_note,
                depends_on = excluded.depends_on,
                source_path = excluded.source_path,
                created_at = COALESCE(work_items.created_at, excluded.created_at),
                completed_at = excluded.completed_at,
                archived = excluded.archived,
                updated_at = excluded.updated_at
            """,
            (
                item_id,
                item_type,
                slug,
                title,
                status,
                priority,
                epic_slug,
                story_slug,
                persona,
                context_note,
                depends_on,
                source_path,
                created_at,
                completed_at,
                1 if archived else 0,
                now,
            ),
        )
        conn.commit()


def _redact_pii(text: str | None) -> str | None:
    """Replace obvious PII patterns with redacted placeholders before writing to the audit trail."""
    if not text:
        return text
    # email addresses
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED-EMAIL]", text)
    # AWS access key IDs
    text = re.sub(r"AKIA[0-9A-Z]{16}", "[REDACTED-AWS-KEY]", text)
    # secret-like key=value patterns
    text = re.sub(
        r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*['\"]?[^\s'\"]{6,}",
        r"\1=[REDACTED]",
        text,
    )
    return text


def _db_log_event(item_id: str | None, action: str, *, actor: str | None = None, details: str | None = None) -> int:
    """Append one event to the SQLite audit trail (PII is redacted before writing)."""
    _init_state_db()
    with contextlib.closing(_connect_state_db()) as conn:
        cursor = conn.execute(
            "INSERT INTO audit_events(item_id, actor, action, details, created_at) VALUES (?, ?, ?, ?, ?)",
            (item_id, actor, action, _redact_pii(details), _now_iso()),
        )
        conn.commit()
        return int(cursor.lastrowid)


def _log_correlated_event(
    item_id: str | None,
    action: str,
    *,
    actor: str,
    details: str | None,
    message: str,
) -> int:
    """Write one correlated event to SQLite and ai_log.md, returning the audit event id."""
    event_id = _db_log_event(item_id, action, actor=actor, details=details)
    prefix = f"[audit:{event_id}] "
    _append_log(f"@{actor} | {prefix}{message}", task_id=item_id)
    return event_id


def _db_sync_task_file(task_file: Path) -> None:
    """Mirror one markdown work item into SQLite state."""
    text = task_file.read_text()
    item_id = _parse_task_field(text, "ID")
    if not item_id:
        return
    _db_upsert_work_item(
        item_id=item_id,
        item_type=_item_type_from_path(task_file),
        slug=task_file.stem,
        title=_title_from_task_text(text),
        status=_parse_task_field(text, "Status") or "Backlog",
        priority=_parse_task_field(text, "Priority") or "P1",
        epic_slug=_normalize_field(_parse_task_field(text, "Epic")),
        story_slug=_normalize_field(_parse_task_field(text, "Story")),
        persona=_normalize_field(_parse_task_field(text, "Persona")) or None,
        context_note=_normalize_field(_parse_task_field(text, "Context")),
        depends_on=_normalize_field(_parse_task_field(text, "Depends On")),
        source_path=str(task_file),
        created_at=_normalize_field(_parse_task_field(text, "Created")),
        completed_at=_normalize_field(_parse_task_field(text, "Completed")),
        archived=task_file.parent.name == "archive",
    )


def _db_sync_all_task_files() -> None:
    """Backfill SQLite from all current markdown work items, then reconcile stale rows."""
    root = _find_project_root()
    tasks_dir = root / "docs" / "tasks"
    if not tasks_dir.exists():
        return
    for candidate in sorted(tasks_dir.glob("*.md")):
        if candidate.name == ".gitkeep":
            continue
        _db_sync_task_file(candidate)
    archive_dir = tasks_dir / "archive"
    if archive_dir.exists():
        for candidate in sorted(archive_dir.glob("*.md")):
            _db_sync_task_file(candidate)
    _db_reconcile_stale_items()


def _db_reconcile_stale_items() -> None:
    """Archive SQLite rows whose source_path no longer exists on disk.

    This prevents ghost 'In Progress' items surfacing after a forced reinit that
    regenerates docs/ from scratch — the old markdown files are gone but the
    SQLite rows would otherwise persist with stale active status.
    """
    if not _state_db_path().exists():
        return
    with contextlib.closing(_connect_state_db()) as conn:
        rows = conn.execute(
            "SELECT item_id, source_path FROM work_items WHERE archived = 0 AND source_path IS NOT NULL"
        ).fetchall()
        stale_ids = [row["item_id"] for row in rows if not Path(row["source_path"]).exists()]
        if stale_ids:
            placeholders = ",".join("?" for _ in stale_ids)
            conn.execute(
                f"UPDATE work_items SET archived = 1, status = 'Archived', updated_at = ? WHERE item_id IN ({placeholders})",
                [_now_iso(), *stale_ids],
            )
            conn.commit()
    for item_id in stale_ids:
        _db_log_event(item_id, "auto-archived", actor="keeli-init", details="source file missing after reinit")


def _install_git_hooks(*, force: bool = False) -> bool:
    """Install the default pre-commit hook when inside a git repository."""
    git_hooks_dir = Path(".git") / "hooks"
    if not git_hooks_dir.exists():
        return False
    git_hooks_dir.mkdir(parents=True, exist_ok=True)
    hooks = {
        "pre-commit": _PRE_COMMIT_HOOK,
        "post-commit": _POST_COMMIT_HOOK,
    }
    for filename, content in hooks.items():
        hook_path = git_hooks_dir / filename
        if hook_path.exists() and not force:
            continue
        hook_path.write_text(content)
        hook_path.chmod(0o755)
    return True


def _scan_paths_for_pii(paths: list[str]) -> list[str]:
    """Return human-readable PII or secret findings for the given file paths."""
    findings: list[str] = []
    patterns = [
        (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "email address"),
        (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
        (re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*['\"]?[^\s'\"]{6,}"), "secret-like assignment"),
    ]

    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists() or path.is_dir():
            continue
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        for regex, label in patterns:
            if regex.search(content):
                findings.append(f"{path}: potential {label}")
                break
    return findings


def _active_leaf_items() -> list[sqlite3.Row]:
    """Return active leaf work items from SQLite."""
    if not _state_db_path().exists():
        return []
    with contextlib.closing(_connect_state_db()) as conn:
        return conn.execute(
            """
            SELECT item_id, slug, item_type, status, epic_slug, story_slug, persona
            FROM work_items
            WHERE archived = 0
              AND item_type IN ('task', 'bug', 'feat')
              AND status IN ('In Progress', 'Review')
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()


def _in_progress_leaf_items() -> list[sqlite3.Row]:
    """Return In Progress leaf work items from SQLite."""
    if not _state_db_path().exists():
        return []
    with contextlib.closing(_connect_state_db()) as conn:
        return conn.execute(
            """
            SELECT item_id, slug, item_type, status, epic_slug, story_slug, persona
            FROM work_items
            WHERE archived = 0
              AND item_type IN ('task', 'bug', 'feat')
              AND status = 'In Progress'
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()


def _pending_leaf_item_count() -> int:
    """Return the number of non-archived leaf work items in the local state DB."""
    if not _state_db_path().exists():
        return 0
    with contextlib.closing(_connect_state_db()) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM work_items
            WHERE archived = 0
              AND item_type IN ('task', 'bug', 'feat')
            """
        ).fetchone()
    return int(row[0]) if row else 0


def _git_output(args: list[str]) -> str:
    """Run a git command and return stripped stdout."""
    completed = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


# ── Interactive prompt (Angular-CLI style) ─────────────────────────────────

def _prompt(
    question: str,
    default: str | None = None,
    choices: list[str] | None = None,
) -> str:
    """Angular-CLI style interactive prompt.

    Displays:  ? Question (choice1/choice2) [default]: 
    Falls back to *default* silently when stdin is not a TTY (e.g. in tests).
    """
    import sys as _sys

    if not _sys.stdin.isatty():
        return default or ""

    choice_str = f" ({'/'.join(choices)})" if choices else ""
    default_str = f" [{default}]" if default is not None else ""
    prompt_line = f"\033[32m?\033[0m {question}{choice_str}{default_str}: "

    while True:
        try:
            raw = input(prompt_line).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            raise SystemExit(1)
        if not raw:
            if default is not None:
                return default
            if choices:
                print(f"  \033[33m›\033[0m Please choose one of: {', '.join(choices)}")
                continue
            print(f"  \033[33m›\033[0m This field is required.")
            continue
        if choices and raw not in choices:
            print(f"  \033[33m›\033[0m Invalid choice. Options: {', '.join(choices)}")
            continue
        return raw


# ── Skills helpers ──────────────────────────────────────────────────────────

SKILL_TYPES = ["lang", "framework", "domain", "infra", "tool"]
_SKILLS_START = "<!-- KEELI_SKILLS_START -->"
_SKILLS_END   = "<!-- KEELI_SKILLS_END -->"


# ── Scan helpers ──────────────────────────────────────────────────────────────

class ScannedSkill:
    """A skill discovered from a project manifest file."""
    __slots__ = ("name", "skill_type", "version", "source_file", "persona")

    def __init__(
        self,
        name: str,
        skill_type: str,
        version: str,
        source_file: str,
        persona: str = "architect",
    ) -> None:
        self.name        = name
        self.skill_type  = skill_type
        self.version     = version
        self.source_file = source_file
        self.persona     = persona

    def __repr__(self) -> str:  # pragma: no cover
        return f"ScannedSkill({self.name!r}, {self.skill_type!r}, {self.version!r})"


_FRAMEWORK_NAMES: frozenset[str] = frozenset({
    "flask", "fastapi", "django", "starlette", "sanic", "tornado", "falcon",
    "react", "next", "nextjs", "nuxt", "angular", "vue", "svelte", "remix",
    "express", "nestjs", "hapi", "koa", "fastify",
    "spring", "springboot", "quarkus", "micronaut",
    "rails", "sinatra",
    "gin", "echo", "fiber",
    "axum", "actix", "warp", "rocket",
    "sqlalchemy", "alembic", "pydantic", "celery", "pytest",
    "hibernate", "mybatis", "jpa",
})
_LANG_NAMES: frozenset[str] = frozenset({
    "python", "node", "nodejs", "java", "go", "rust", "ruby", "php",
    "swift", "kotlin", "scala", "typescript", "javascript", "csharp", "dotnet",
})


def _classify_skill(name: str) -> str:
    """Guess the keeli skill type from a package / module name."""
    n = re.sub(r"[-_.]", "", name.lower())
    if n in _LANG_NAMES:
        return "lang"
    if n in _FRAMEWORK_NAMES:
        return "framework"
    return "tool"


def _scan_manifests(root: Path) -> list[ScannedSkill]:
    """Scan known manifest files in *root* and return discovered ScannedSkill entries.

    Supported sources (in priority order):
      pyproject.toml, requirements*.txt, package.json, .python-version,
      .nvmrc, go.mod, Cargo.toml, pom.xml
    """
    results: list[ScannedSkill] = []

    # 1. pyproject.toml (stdlib tomllib, Python 3.11+)
    ppt = root / "pyproject.toml"
    if ppt.exists():
        try:
            import tomllib  # noqa: PLC0415
            data = tomllib.loads(ppt.read_text())
            req_python = (
                data.get("project", {}).get("requires-python")
                or data.get("tool", {}).get("poetry", {}).get("dependencies", {}).get("python", "")
            )
            if req_python:
                results.append(ScannedSkill("Python", "lang", str(req_python), "pyproject.toml"))
            for dep in data.get("project", {}).get("dependencies", []):
                m = re.match(r"([a-zA-Z0-9_.\-]+)\s*([><=!~^][^\s]*)?", str(dep))
                if m and m.group(1):
                    results.append(ScannedSkill(m.group(1), _classify_skill(m.group(1)), (m.group(2) or "").strip(), "pyproject.toml"))
            for pn, pv in data.get("tool", {}).get("poetry", {}).get("dependencies", {}).items():
                if pn.lower() == "python":
                    results.append(ScannedSkill("Python", "lang", str(pv), "pyproject.toml"))
                    continue
                ver = pv if isinstance(pv, str) else (pv.get("version", "") if isinstance(pv, dict) else "")
                results.append(ScannedSkill(pn, _classify_skill(pn), str(ver), "pyproject.toml"))
        except Exception:
            pass

    # 2. requirements*.txt
    for req_file in sorted(root.glob("requirements*.txt")):
        for line in req_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            m = re.match(r"([a-zA-Z0-9_.\-]+)\s*([><=!~^][^\s]*)?", line)
            if m and m.group(1):
                results.append(ScannedSkill(m.group(1), _classify_skill(m.group(1)), (m.group(2) or "").strip(), req_file.name))

    # 3. package.json
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text())
            node_ver = data.get("engines", {}).get("node", "")
            if node_ver:
                results.append(ScannedSkill("Node.js", "lang", node_ver, "package.json"))
            all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for dep_name, dep_ver in all_deps.items():
                results.append(ScannedSkill(dep_name, _classify_skill(dep_name), str(dep_ver), "package.json"))
        except Exception:
            pass

    # 4. .python-version
    pv = root / ".python-version"
    if pv.exists():
        ver = pv.read_text().strip()
        if ver:
            results.append(ScannedSkill("Python", "lang", ver, ".python-version"))

    # 5. .nvmrc
    nvmrc = root / ".nvmrc"
    if nvmrc.exists():
        ver = nvmrc.read_text().strip()
        if ver:
            results.append(ScannedSkill("Node.js", "lang", ver, ".nvmrc"))

    # 6. go.mod
    gomod = root / "go.mod"
    if gomod.exists():
        in_require = False
        for line in gomod.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("go ") and not in_require:
                results.append(ScannedSkill("Go", "lang", stripped[3:].strip(), "go.mod"))
            elif stripped == "require (":
                in_require = True
            elif stripped == ")" and in_require:
                in_require = False
            elif in_require or stripped.startswith("require "):
                clean = re.sub(r"^require\s+", "", stripped).strip()
                m = re.match(r"([a-zA-Z0-9./\-_]+)\s+v([0-9][^\s]*)", clean)
                if m:
                    pkg_parts = m.group(1).split("/")
                    pkg_name = pkg_parts[-1] if len(pkg_parts) > 1 else m.group(1)
                    results.append(ScannedSkill(pkg_name, _classify_skill(pkg_name), f"v{m.group(2)}", "go.mod"))

    # 7. Cargo.toml
    cargo = root / "Cargo.toml"
    if cargo.exists():
        try:
            import tomllib  # noqa: PLC0415
            data = tomllib.loads(cargo.read_text())
            edition = data.get("package", {}).get("edition", "")
            results.append(ScannedSkill("Rust", "lang", f"edition {edition}" if edition else "", "Cargo.toml"))
            for dep_name, dep_spec in data.get("dependencies", {}).items():
                dep_ver = dep_spec if isinstance(dep_spec, str) else (dep_spec.get("version", "") if isinstance(dep_spec, dict) else "")
                results.append(ScannedSkill(dep_name, _classify_skill(dep_name), str(dep_ver), "Cargo.toml"))
        except Exception:
            pass

    # 8. pom.xml (stdlib regex — no XML dependency)
    pom = root / "pom.xml"
    if pom.exists():
        content = pom.read_text()
        m = re.search(r"<java\.version>([^<]+)</java\.version>", content)
        if m:
            results.append(ScannedSkill("Java", "lang", m.group(1), "pom.xml"))
        skip = {"maven-compiler-plugin", "maven-surefire-plugin", "maven-jar-plugin"}
        for mm in re.finditer(r"<artifactId>([^<]+)</artifactId>\s*(?:<version>([^<]+)</version>)?", content):
            dep_name, dep_ver = mm.group(1), mm.group(2) or ""
            if dep_name not in skip:
                results.append(ScannedSkill(dep_name, _classify_skill(dep_name), dep_ver, "pom.xml"))

    # Deduplicate (first occurrence wins)
    seen: set[str] = set()
    deduped: list[ScannedSkill] = []
    for s in results:
        if s.name.lower() not in seen:
            seen.add(s.name.lower())
            deduped.append(s)
    return deduped


# ── Chain infrastructure ───────────────────────────────────────────────────

BUILTIN_CHAINS: dict[str, dict] = {
    "new-task": {
        "description": "Create a task, inject AI context hints, then mark In Progress",
        "steps": [
            {"cmd": "start",    "args": ["{title}"]},
            {"cmd": "analyze",  "args": ["auto"]},
            {"cmd": "progress", "args": ["auto"]},
        ],
    },
    "close-task": {
        "description": "Send a task to Review then mark it Completed",
        "steps": [
            {"cmd": "review",   "args": ["{slug}"]},
            {"cmd": "complete", "args": ["auto"]},
        ],
    },
    "onboard": {
        "description": "Scan project manifests for skills, then show the next task",
        "steps": [
            {"cmd": "skill", "args": ["scan", "--apply"]},
            {"cmd": "next",  "args": []},
        ],
    },
}


def _extract_slug_from_output(output: str) -> "str | None":
    """Extract a task slug from keeli command output.

    Looks for patterns like: docs/tasks/my-task.md
    """
    m = re.search(r"docs/tasks/([a-z0-9-]+)\.md", output)
    return m.group(1) if m else None


def _run_chain_inline(
    steps_raw: list[str],
    *,
    dry_run: bool = False,
    vars_: "dict[str, str] | None" = None,
) -> None:
    """Execute an ordered list of keeli steps given as 'cmd:arg' strings.

    The task slug produced by each step is automatically propagated to
    the next step whenever that step uses the sentinel value ``auto``.
    Errors in any step halt the chain by default.
    """
    vars_ = vars_ or {}
    context_slug: "str | None" = None

    # Parse raw step strings into dicts
    steps: list[dict] = []
    for raw in steps_raw:
        if ":" in raw:
            cmd_part, rest = raw.split(":", 1)
            step_args = [rest.strip()] if rest.strip() else []
        else:
            cmd_part = raw.strip()
            step_args = []
        steps.append({"cmd": cmd_part.strip(), "args": step_args})

    print(f"\n\u26d3  Chain: {len(steps)} step(s)\n")

    for i, step in enumerate(steps, 1):
        resolved_args: list[str] = []
        for a in step["args"]:
            if a == "auto" and context_slug:
                a = context_slug
            for k, v in vars_.items():
                a = a.replace(f"{{{k}}}", v)
            resolved_args.append(a)

        cmd_display = ("keeli " + step["cmd"] + " " + " ".join(resolved_args)).strip()
        print(f"  \u25b6  Step {i}/{len(steps)}: {cmd_display}")

        if dry_run:
            print(f"     [dry-run] execution skipped\n")
            continue

        old_argv = sys.argv
        buf: "__import__('io').StringIO" = __import__("io").StringIO()
        try:
            sys.argv = ["keeli", step["cmd"]] + resolved_args
            with contextlib.redirect_stdout(buf):
                main()
        except SystemExit:
            pass
        except Exception as exc:
            print(f"  \u274c Step {i} failed: {exc}")
            print(f"     Halting chain.")
            return
        finally:
            sys.argv = old_argv

        output = buf.getvalue()
        print(output, end="")

        # Propagate the task slug to subsequent 'auto' steps
        extracted = _extract_slug_from_output(output)
        if extracted:
            context_slug = extracted

    if not dry_run:
        print(f"\n\u2705 Chain complete ({len(steps)} step(s)).")
    else:
        print(f"\n  [dry-run] {len(steps)} step(s) previewed. Remove --dry-run to execute.")


def _run_chain_from_file(chain_file: Path, *, vars_: "dict[str, str]", dry_run: bool) -> None:
    """Run a chain defined in a YAML file. Requires pyyaml."""
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        print("\u274c pyyaml required for chain files: pip install pyyaml")
        print("   Alternatively use inline syntax: keeli chain \"cmd:arg\" ...")
        return
    try:
        data = yaml.safe_load(chain_file.read_text())
    except Exception as exc:
        print(f"\u274c Failed to parse chain file '{chain_file}': {exc}")
        return
    steps_raw: list[str] = []
    for step in data.get("steps", []):
        cmd = step.get("cmd", "")
        raw_args = [str(a) for a in step.get("args", [])]
        # Apply variable substitution
        subst_args = [a for a in raw_args]
        for k, v in vars_.items():
            subst_args = [a.replace(f"{{{k}}}", v) for a in subst_args]
        steps_raw.append(f"{cmd}:{' '.join(subst_args)}" if subst_args else cmd)
    _run_chain_inline(steps_raw, dry_run=dry_run, vars_=vars_)


# ── Personas helpers ──────────────────────────────────────────────────────────


DEFAULT_PERSONAS = ["po", "architect", "developer", "qa", "security", "author"]


def _load_personas() -> list[str]:
    """Load persona slugs from docs/personas.md, falling back to defaults.

    Supports two formats (auto-detected):
      Rich (new):  ## slug          — heading-based, one section per persona
      Legacy:      - slug: Desc     — simple list format
    Lines not matching either pattern are ignored.
    """
    path = Path("docs/personas.md")
    if not path.exists():
        return DEFAULT_PERSONAS
    personas: list[str] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        # Rich format: ## slug
        if stripped.startswith("## "):
            slug = stripped[3:].strip().lower()
            slug = re.sub(r"[^a-z0-9-]", "", slug)
            if slug:
                personas.append(slug)
        # Legacy format: - slug: Description  (slug must be a simple word, no spaces)
        elif re.match(r'^- [a-z0-9][a-z0-9-]*:', stripped):
            slug = stripped[2:].split(":")[0].strip().lower()
            slug = re.sub(r"[^a-z0-9-]", "", slug)
            if slug:
                personas.append(slug)
    return personas if personas else DEFAULT_PERSONAS


def _read_skills() -> list[tuple[str, str, str, str]]:
    """Return list of (type, name, persona, constraint) tuples from docs/skills.md.

    Supports 4-column (current), 3-column, and 2-column legacy rows.
    Missing fields default to empty string.
    """
    path = Path("docs/skills.md")
    if not path.exists():
        return []
    skills: list[tuple[str, str, str, str]] = []
    for line in path.read_text().splitlines():
        if line.startswith("|") and "|" in line[1:]:
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) < 2:
                continue
            t    = parts[0] if len(parts) > 0 else ""
            n    = parts[1] if len(parts) > 1 else ""
            p    = parts[2] if len(parts) > 2 else ""
            c    = parts[3] if len(parts) > 3 else ""
            # skip header row and separator rows
            if not t or t.lower() in ("type",) or set(t.lstrip("-")) <= {"-", " "}:
                continue
            skills.append((t, n, p, c))
    return skills


def _write_skills(skills: list[tuple[str, str, str, str]]) -> None:
    """Persist skills list to docs/skills.md and regenerate the skills block
    inside .github/copilot-instructions.md."""
    path = Path("docs/skills.md")
    rows = "\n".join(f"| {t} | {n} | {p} | {c} |" for t, n, p, c in skills)
    path.write_text(SKILLS_MD.format(version=SCHEMA_VERSION) + (rows + "\n" if rows else ""))
    _inject_skills_into_instructions(skills)


def _inject_skills_into_instructions(skills: list[tuple[str, str, str, str]]) -> None:
    """Regenerate the KEELI_SKILLS block grouped by persona, including constraints.

    Each skill renders as:
        - **Type** `skill name`: constraint text
    The constraint is the actual decision — what the LLM needs to infer correctly.
    """
    instr = Path(".github/copilot-instructions.md")
    if not instr.exists():
        return
    text = instr.read_text()
    if _SKILLS_START not in text:
        return
    # Group: {persona_key: {type: [(name, constraint), ...]}}
    grouped: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for t, n, p, c in skills:
        persona_key = p.strip() if p and p.strip() else "global"
        grouped.setdefault(persona_key, {}).setdefault(t, []).append((n, c))
    if not grouped:
        block = "(no skills registered \u2014 run `keeli stack` or `keeli skill add` to populate)"
    else:
        persona_order = ["po", "architect", "developer", "qa", "security", "author", "global"]
        ordered_keys = [k for k in persona_order if k in grouped] + [
            k for k in grouped if k not in persona_order
        ]
        sections = []
        for pk in ordered_keys:
            type_map = grouped[pk]
            label = f"@{pk}" if pk != "global" else "global"
            lines = [f"### {label}"]
            for t, entries in sorted(type_map.items()):
                for name, constraint in entries:
                    if constraint:
                        lines.append(f"- **{t.capitalize()}** `{name}`: {constraint}")
                    else:
                        lines.append(f"- **{t.capitalize()}** `{name}`")
            sections.append("\n".join(lines))
        block = "\n\n".join(sections)
    before = text.split(_SKILLS_START)[0]
    after  = text.split(_SKILLS_END)[1]
    instr.write_text(f"{before}{_SKILLS_START}\n{block}\n{_SKILLS_END}{after}")


# ── Commands ───────────────────────────────────────────────────────────────

def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold the Keeli framework in the current project."""
    force = args.force
    print(f"Initializing Keeli Framework v{SCHEMA_VERSION} …\n")

    try:
        # Directories
        for d in [Path(".github"), Path("docs"), Path("docs/tasks"), Path("docs/requirements")]:
            d.mkdir(parents=True, exist_ok=True)

        # .gitkeep for empty dirs (so Git tracks them)
        for d in [Path("docs/tasks"), Path("docs/requirements")]:
            gitkeep = d / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.touch()

        # Core files
        _write_file(Path(".github/copilot-instructions.md"), COPILOT_INSTRUCTIONS, force=force)
        _write_file(Path("docs/project.md"), PROJECT_MD, force=force)
        _write_file(Path("docs/decision.md"), DECISION_MD, force=force)
        _write_file(Path("docs/ai_log.md"), AI_LOG_MD, force=force)
        _write_file(Path("docs/skills.md"), SKILLS_MD.format(version=SCHEMA_VERSION), force=force)
        _write_file(Path("docs/personas.md"), PERSONAS_MD, force=force)
        _init_state_db()
        _db_sync_all_task_files()
        hooks_installed = _install_git_hooks(force=force)

        # Flavor-specific AI instructions (claude, gemini, codex)
        if args.ai:
            for flavor in args.ai:
                flavor_dir = Path(f".{flavor}")
                flavor_dir.mkdir(parents=True, exist_ok=True)
                flavor_file = flavor_dir / "instructions.md"
                flavor_content = get_flavor_instructions(flavor)
                _write_file(flavor_file, flavor_content, force=force)

        # .gitignore
        gitignore = Path(".gitignore")
        if gitignore.exists():
            content = gitignore.read_text()
            if "docs/ai_log.md" not in content:
                with gitignore.open("a") as f:
                    f.write("\n" + GITIGNORE_CONTENT)
                print(f"  ✅ Updated {gitignore}")
        else:
            gitignore.write_text(GITIGNORE_CONTENT)
            print(f"  ✅ Created {gitignore}")

        print("\n🎉 Initialization complete!")
        print(f"   State database ready: {_STATE_DB_FILENAME}")
        if hooks_installed:
            print("   Git hooks installed: .git/hooks/pre-commit, .git/hooks/post-commit")
        if args.ai:
            print(f"   Flavor-specific instructions created for: {', '.join(args.ai)}")
        print("   Copilot is now aware of Keeli. Run `keeli resume --brief` to verify context.")
        print("   Suggested first steps:")
        print("     1. Fill in docs/project.md with your project context")
        print("     2. keeli stack                    # pick your tech stack preset interactively")
        print("     3. keeli epic \"<first goal>\" -p P1   # define your first epic")
        print("     4. keeli story \"<user story>\" --epic <slug>  # break it down")
    except PermissionError as exc:
        print(f"\n❌ Permission Error: {exc}")
    except Exception as exc:
        print(f"\n❌ Unexpected error: {exc}")


def cmd_start(args: argparse.Namespace) -> None:
    """Create a new task file in docs/tasks/."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.task_name)
    task_file = tasks_dir / f"{slug}.md"

    existing_text = task_file.read_text() if task_file.exists() else ""

    if task_file.exists() and not args.force:
        print(f"⚠️  {task_file} already exists. Use --force to overwrite.")
        return

    # Resolve optional context file
    context_note = "None"
    if args.context:
        ctx_path = Path(args.context)
        if ctx_path.exists():
            context_note = f"See [{ctx_path}]({ctx_path})"
        else:
            print(f"⚠️  Context file {ctx_path} not found. Proceeding without link.")

    # Resolve optional objective text
    objective_text = _resolve_objective(getattr(args, "objective", None))
    if not objective_text:
        print(_OBJECTIVE_HINT)

    priority = getattr(args, "priority", None) or _prompt(
        "Task priority", default="P1", choices=["P0", "P1", "P2"]
    )
    persona = getattr(args, "keeli", None) or "architect"
    depends_on = getattr(args, "depends_on", None) or "None"
    epic = getattr(args, "epic", None) or "None"
    story = getattr(args, "story", None) or "None"

    task_id = _parse_task_field(existing_text, "ID") if existing_text else ""
    if not task_id:
        task_id = _allocate_id(
            "task", args.task_name, slug, priority=priority,
            epic=epic if epic != "None" else None,
            story=story if story != "None" else None,
        )
    content = TASK_TEMPLATE.format(
        task_id=task_id,
        title=args.task_name,
        timestamp=_now_iso(),
        context_note=context_note,
        priority=priority,
        depends_on=depends_on,
        epic=epic,
        story=story,
        persona=f"@{persona}",
        what=objective_text or "<!-- Be specific about the implementation work. -->",
        why="<!-- Explain the user or business impact. -->",
        acceptance="<!-- Add verification steps or test evidence here. -->",
        evidence="<!-- Link delivery artifacts (PR, commit, docs, screenshots, build logs). -->",
        verification="<!-- Link validation artifacts (tests, checks, commands with outcomes). -->",
    )
    task_file.write_text(content)
    _db_sync_task_file(task_file)
    print(f"✅ Created task: {task_file} [{task_id}]")

    # Auto-log the event
    _append_log(f"@{persona} | Task created: {args.task_name} → {task_file}", task_id=task_id)
    _db_log_event(task_id, "created", actor=persona, details=args.task_name)


def cmd_log(args: argparse.Namespace) -> None:
    """Append a timestamped entry to docs/ai_log.md."""
    _append_log(args.message)
    print(f"✅ Logged to docs/ai_log.md")


def cmd_validate_task_state(args: argparse.Namespace) -> None:
    """Validate local task state and optional file paths for passive guardrails."""
    _init_state_db()

    findings = _scan_paths_for_pii(getattr(args, "paths", None) or [])
    if findings:
        print("❌ PII / secret scan failed:")
        for finding in findings:
            print(f"   • {finding}")
        raise SystemExit(1)

    pending_leaf_items = _pending_leaf_item_count()
    active_leaf_items = _active_leaf_items()

    if pending_leaf_items and not active_leaf_items:
        if getattr(args, "auto_stub", False):
            stub_task = _ensure_validate_stub_task()
            print(f"ℹ️  No active task found; auto-created stub: {stub_task}")
            active_leaf_items = _active_leaf_items()
        else:
            print("❌ No active task is In Progress or Review.")
            print("   → Start work explicitly with `keeli progress <task>` before committing.")
            print("   → Or rerun with `keeli validate-task-state --auto-stub` to create a temporary active stub task.")
            raise SystemExit(1)

    hierarchy_errors: list[str] = []
    for row in active_leaf_items:
        item_type = row["item_type"]
        if item_type == "task":
            if row["epic_slug"] and not row["story_slug"]:
                hierarchy_errors.append(
                    f"{row['slug']}: task is linked to epic '{row['epic_slug']}' but has no story; run `keeli story` first"
                )
            if row["story_slug"] and not row["epic_slug"]:
                hierarchy_errors.append(
                    f"{row['slug']}: task has story '{row['story_slug']}' but no epic"
                )

    if hierarchy_errors:
        print("❌ Task state validation failed:")
        for error in hierarchy_errors:
            print(f"   • {error}")
        raise SystemExit(1)

    print("✅ Task state valid")
    if active_leaf_items:
        print("   Active items:")
        for row in active_leaf_items:
            print(f"   • {row['slug']} [{row['status']}] {row['persona'] or ''}".rstrip())


def cmd_capture_commit_state(args: argparse.Namespace) -> None:
    """Capture the latest git commit against the current active task state."""
    _init_state_db()
    active_leaf_items = _active_leaf_items()
    target_id = getattr(args, "target_id", "").strip() or None
    
    if not active_leaf_items and not target_id:
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope(
                "capture-commit-state",
                True,
                {"message": "No active task to attach commit metadata to.", "transitions": []},
            ), indent=2))
        else:
            print("ℹ️  No active task to attach commit metadata to.")
        return

    try:
        commit_hash = _git_output(["rev-parse", "HEAD"])
        commit_subject = _git_output(["log", "-1", "--pretty=%s"])
        commit_body = _git_output(["log", "-1", "--pretty=%b"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope(
                "capture-commit-state",
                False,
                {"transitions": []},
                error="Unable to capture git commit metadata.",
            ), indent=2))
        else:
            print("ℹ️  Unable to capture git commit metadata.")
        return

    active_item = _resolve_transition_target(active_leaf_items, target_id)
    
    if not active_item:
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope(
                "capture-commit-state",
                False,
                {"transitions": []},
                error="Target task not found.",
            ), indent=2))
        else:
            print("❌ Target task not found.")
        return
    
    evaluation = _evaluate_commit_transitions(commit_subject, active_item["item_id"], commit_body, target_id)
    conflict = _transition_conflict_reason(evaluation, active_leaf_items)
    if conflict:
        payload = _json_envelope(
            "capture-commit-state",
            False,
            {
                "active_items": [{"item_id": row["item_id"], "slug": row["slug"], "status": row["status"]} for row in active_leaf_items],
                "transitions": [],
            },
            error=conflict,
        )
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            print(f"❌ {conflict}")
            print("   Active items:")
            for row in active_leaf_items:
                print(f"   • {row['item_id']} {row['slug']} [{row['status']}]")
            print("   → Use explicit closes markers or reduce active tasks before capture.")
        return

    details = json.dumps({
        "commit": commit_hash,
        "subject": commit_subject,
        "body": commit_body,
        "task": active_item["slug"],
    })
    commit_event_id = _log_correlated_event(
        active_item["item_id"],
        "commit",
        actor="git",
        details=details,
        message=f"Commit captured for {active_item['slug']}: {commit_hash[:12]} {commit_subject}",
    )
    transitions = _apply_commit_transitions(active_item, commit_subject, commit_body, target_id)
    payload = _json_envelope(
        "capture-commit-state",
        True,
        {
            "commit": {"hash": commit_hash, "subject": commit_subject, "body": commit_body},
            "active_item": {"item_id": active_item["item_id"], "slug": active_item["slug"]},
            "commit_event_id": commit_event_id,
            "evaluation": evaluation,
            "transitions": transitions,
        },
    )
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print(f"✅ Commit captured for {active_item['slug']}: {commit_hash[:12]}")
        if transitions:
            print("   🔄 Commit semantic transitions:")
            for transition in transitions:
                print(f"   • {transition}")


def _ensure_validate_stub_task() -> str:
    """Create or restore a temporary active task used by validate-task-state."""
    tasks_dir = Path("docs/tasks")
    tasks_dir.mkdir(parents=True, exist_ok=True)

    title = "Working on uncommitted changes"
    slug = _slugify(title)
    task_file = _resolve_task_file(tasks_dir, slug)
    if task_file is None:
        task_file = tasks_dir / f"{slug}.md"
        task_id = _allocate_id("task", title, slug, priority="P1")
        content = TASK_TEMPLATE.format(
            task_id=task_id,
            title=title,
            timestamp=_now_iso(),
            context_note="Auto-created by validate-task-state",
            priority="P1",
            depends_on="None",
            epic="None",
            story="None",
            persona="@developer",
            what="Investigate and reconcile untracked ongoing work.",
            why="Validation found pending leaf work without an active task.",
            acceptance="Validation passes with one active task; replace this stub with a real task.",
            evidence="- Validation context: docs/ai_log.md",
            verification="- Command: keeli validate-task-state --auto-stub",
        )
        task_file.write_text(content)
    else:
        if task_file.parent.name == "archive":
            live_dest = tasks_dir / task_file.name
            task_file.rename(live_dest)
            task_file = live_dest
        content = task_file.read_text()
        task_id = _parse_task_field(content, "ID")

    text = task_file.read_text()
    text = _update_task_field(text, "Status", "In Progress")
    text = _update_task_field(text, "Completed", "—")
    task_file.write_text(text)
    _db_sync_task_file(task_file)
    _index_update_status(task_id, status="In Progress", completed=None, archived=False)
    _append_log(f"@system | Auto-stub activated: {title} → {task_file}", task_id=task_id)
    _db_log_event(task_id, "auto_stub_activated", actor="system", details=title)
    return task_file.stem


def _evaluate_commit_transitions(subject: str, active_item_id: str | None = None, body: str | None = None, target_id: str | None = None) -> dict[str, object]:
    """Pure evaluator for commit-driven transitions.

    Returns a deterministic payload that can be used by CLI, CI, and MCP callers
    without mutating state.

    Args:
        subject: Commit subject line
        active_item_id: Current active item ID (used as baseline context)
        body: Commit body with trailers
        target_id: Explicit target for keeli:complete (overrides active_item_id)
    """
    commit_subject = subject or ""
    commit_body = body or ""
    normalized_subject = commit_subject.strip()
    normalized_body = commit_body.strip()
    explicit_target = (target_id or "").upper() if target_id else None
    active_upper = (active_item_id or "").upper()
    commit_text = "\n".join(part for part in (normalized_subject, normalized_body) if part)

    close_ids: list[str] = []
    for chunk in re.findall(r"(?i)\b(?:closes?|fixes?|resolves?)\s+([A-Z0-9\-_,\s]+)", commit_text):
        for token in re.findall(r"(?i)\bT-\d{4}\b", chunk):
            token_u = token.upper()
            if token_u not in close_ids:
                close_ids.append(token_u)
    for trailer in re.findall(r"(?im)^(?:closes?|fixes?|resolves?)\s*:?\s*(.+)$", commit_text):
        for token in re.findall(r"(?i)\bT-\d{4}\b", trailer):
            token_u = token.upper()
            if token_u not in close_ids:
                close_ids.append(token_u)

    actions: list[dict[str, object]] = []
    if re.search(r"(?i)\bkeeli:complete\b", commit_text):
        if explicit_target:
            actions.append({"type": "complete_explicit", "target": explicit_target, "reason": "keeli:complete with explicit --target-id"})
        else:
            actions.append({"type": "complete_active", "reason": "keeli:complete marker"})

    if close_ids:
        actions.append({"type": "review_ids", "ids": close_ids, "reason": "closes marker"})

    return {
        "subject": normalized_subject,
        "body": normalized_body,
        "active_item_id": active_upper or None,
        "explicit_target": explicit_target,
        "actions": actions,
    }


def _transition_conflict_reason(evaluation: dict[str, object], active_items: list[sqlite3.Row]) -> str | None:
    """Return a conflict reason when transition intent is ambiguous."""
    if len(active_items) <= 1:
        return None
    actions = evaluation.get("actions", [])
    has_review_ids = any(a.get("type") == "review_ids" for a in actions if isinstance(a, dict))
    has_complete_active = any(a.get("type") == "complete_active" for a in actions if isinstance(a, dict))
    if has_complete_active and not has_review_ids:
        return "Ambiguous commit intent: multiple active tasks and `keeli:complete` has no explicit target."
    return None


def _build_commit_transition_preview(active_item: sqlite3.Row, subject: str, body: str | None = None, target_id: str | None = None) -> list[dict[str, object]]:
    """Build a per-item transition preview with before/after statuses."""
    item_id = (active_item["item_id"] or "").upper()
    evaluation = _evaluate_commit_transitions(subject, item_id, body, target_id)
    preview: list[dict[str, object]] = []
    did_complete = False

    for action in evaluation["actions"]:  # type: ignore[index]
        if action.get("type") != "complete_active":
            continue
        preview.append(
            {
                "item_id": item_id,
                "slug": active_item["slug"],
                "before": active_item["status"],
                "after": "Completed",
                "action": "complete_active",
                "would_apply": True,
                "reason": action.get("reason"),
            }
        )
        did_complete = True

    for action in evaluation["actions"]:  # type: ignore[index]
        if action.get("type") != "review_ids":
            continue
        close_ids = [str(i).upper() for i in action.get("ids", [])]
        with contextlib.closing(_connect_state_db()) as conn:
            for close_id in close_ids:
                row = conn.execute(
                    "SELECT item_id, slug, status, archived, item_type FROM work_items WHERE item_id = ?",
                    (close_id,),
                ).fetchone()
                if row is None:
                    preview.append({"item_id": close_id, "slug": None, "before": None, "after": None, "action": "review", "would_apply": False, "reason": "not found"})
                    continue
                if int(row["archived"] or 0) == 1:
                    preview.append({"item_id": close_id, "slug": row["slug"], "before": row["status"], "after": row["status"], "action": "review", "would_apply": False, "reason": "archived"})
                    continue
                if row["item_type"] not in ("task", "bug", "feat"):
                    preview.append({"item_id": close_id, "slug": row["slug"], "before": row["status"], "after": row["status"], "action": "review", "would_apply": False, "reason": "not a leaf item"})
                    continue
                if str(row["status"]).lower() != "in progress":
                    preview.append({"item_id": close_id, "slug": row["slug"], "before": row["status"], "after": row["status"], "action": "review", "would_apply": False, "reason": f"status={row['status']}"})
                    continue
                if did_complete and close_id == item_id:
                    preview.append({"item_id": close_id, "slug": row["slug"], "before": row["status"], "after": "Completed", "action": "review", "would_apply": False, "reason": "already completed by marker"})
                    continue
                preview.append({"item_id": close_id, "slug": row["slug"], "before": row["status"], "after": "Review", "action": "review", "would_apply": True, "reason": action.get("reason")})

    return preview


def _resolve_transition_target(active_leaf_items: list[sqlite3.Row], target_id: str | None = None) -> sqlite3.Row | None:
    """Resolve the row that should anchor a commit transition action."""
    explicit_target = (target_id or "").strip().upper()
    if explicit_target:
        with contextlib.closing(_connect_state_db()) as conn:
            row = conn.execute(
                "SELECT item_id, slug, status, archived, item_type FROM work_items WHERE item_id = ?",
                (explicit_target,),
            ).fetchone()
        if row is not None:
            return row
    return active_leaf_items[0] if active_leaf_items else None


def _apply_commit_transitions(active_item: sqlite3.Row, commit_subject: str, commit_body: str | None = None, target_id: str | None = None) -> list[str]:
    """Apply evaluated commit transitions and return human-readable event lines."""
    item_id = (active_item["item_id"] or "").upper()
    slug = active_item["slug"]
    evaluation = _evaluate_commit_transitions(commit_subject, item_id, commit_body, target_id)
    events: list[str] = []
    did_complete = False

    for action in evaluation["actions"]:  # type: ignore[index]
        action_type = action.get("type")
        if action_type == "complete_active":
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_complete(argparse.Namespace(task_name=slug, keeli="system"))
            event_id = _log_correlated_event(
                item_id,
                "auto_completed_from_commit",
                actor="system",
                details=commit_subject,
                message=f"Transition applied: {item_id} completed from keeli:complete marker",
            )
            events.append(f"{item_id}: Completed from keeli:complete marker")
            events.append(f"{item_id}: audit_event={event_id}")
            did_complete = True
        elif action_type == "complete_explicit":
            target = action.get("target", "")
            with contextlib.closing(_connect_state_db()) as conn:
                row = conn.execute(
                    "SELECT item_id, slug FROM work_items WHERE item_id = ?",
                    (target,),
                ).fetchone()
                if row:
                    with contextlib.redirect_stdout(io.StringIO()):
                        cmd_complete(argparse.Namespace(task_name=row["slug"], keeli="system"))
                    event_id = _log_correlated_event(
                        target,
                        "auto_completed_from_commit",
                        actor="system",
                        details=commit_subject,
                        message=f"Transition applied: {target} completed from keeli:complete explicit target",
                    )
                    events.append(f"{target}: Completed from keeli:complete with explicit target")
                    events.append(f"{target}: audit_event={event_id}")
                    did_complete = True
                else:
                    events.append(f"{target}: skipped (not found)")

    for action in evaluation["actions"]:  # type: ignore[index]
        action_type = action.get("type")
        if action_type != "review_ids":
            continue
        close_ids = [str(i).upper() for i in action.get("ids", [])]
        if not close_ids:
            continue
        with contextlib.closing(_connect_state_db()) as conn:
            for close_id in close_ids:
                row = conn.execute(
                    "SELECT item_id, slug, status, archived, item_type FROM work_items WHERE item_id = ?",
                    (close_id,),
                ).fetchone()
                if row is None:
                    events.append(f"{close_id}: skipped (not found)")
                    continue
                if int(row["archived"] or 0) == 1:
                    events.append(f"{close_id}: skipped (archived)")
                    continue
                if row["item_type"] not in ("task", "bug", "feat"):
                    events.append(f"{close_id}: skipped (not a leaf item)")
                    continue
                if str(row["status"]).lower() != "in progress":
                    events.append(f"{close_id}: skipped (status={row['status']})")
                    continue
                if did_complete and close_id == item_id:
                    events.append(f"{close_id}: skipped (already completed by marker)")
                    continue
                with contextlib.redirect_stdout(io.StringIO()):
                    cmd_review(argparse.Namespace(task_name=row["slug"], keeli="system"))
                event_id = _log_correlated_event(
                    close_id,
                    "auto_review_from_commit",
                    actor="system",
                    details=commit_subject,
                    message=f"Transition applied: {close_id} moved to Review from closes marker",
                )
                events.append(f"{close_id}: moved to Review from closes marker")
                events.append(f"{close_id}: audit_event={event_id}")

    return events


def cmd_transition_from_commit(args: argparse.Namespace) -> None:
    """Evaluate commit transition semantics without mutating task state by default."""
    _init_state_db()
    active_leaf_items = _active_leaf_items()
    target_id = getattr(args, "target_id", "").strip() or None
    active_item = _resolve_transition_target(active_leaf_items, target_id)
    active_item_id = active_item["item_id"] if active_item else None

    evaluation = _evaluate_commit_transitions(args.subject, active_item_id, getattr(args, "body", None), target_id)
    output: dict[str, object] = {"evaluation": evaluation, "applied": []}
    conflict = _transition_conflict_reason(evaluation, active_leaf_items)
    if conflict:
        output["conflict"] = conflict

    if getattr(args, "apply", False) and getattr(args, "dry_run", False):
        if active_item is None and not target_id:
            output["preview"] = []
            print(json.dumps(_json_envelope("transition-from-commit", True, output), indent=2))
            return
        item_to_preview = active_item
        if item_to_preview:
            output["preview"] = _build_commit_transition_preview(item_to_preview, args.subject, getattr(args, "body", None), target_id)
        else:
            output["preview"] = []
        print(json.dumps(_json_envelope("transition-from-commit", True, output), indent=2))
        return

    if getattr(args, "apply", False):
        if active_item is None and not target_id:
            print("ℹ️  No active task to apply commit transitions to.")
            print(json.dumps(_json_envelope("transition-from-commit", True, output), indent=2))
            return
        if conflict:
            print(json.dumps(_json_envelope("transition-from-commit", False, output, error=conflict), indent=2))
            return
        item_to_apply = active_item
        if item_to_apply:
            output["applied"] = _apply_commit_transitions(item_to_apply, args.subject, getattr(args, "body", None), target_id)

    print(json.dumps(_json_envelope("transition-from-commit", True, output), indent=2))


def cmd_sync(args: argparse.Namespace) -> None:
    """Rebuild SQLite work item state from markdown task files."""
    if getattr(args, "dry_run", False):
        tasks_dir = Path("docs/tasks")
        active_items = [p for p in sorted(tasks_dir.glob("*.md")) if p.name != ".gitkeep"] if tasks_dir.exists() else []
        archived_items = sorted((tasks_dir / "archive").glob("*.md")) if (tasks_dir / "archive").exists() else []
        predicted = len(active_items) + len(archived_items)
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope(
                "sync",
                True,
                {"dry_run": True, "predicted_items": predicted},
            ), indent=2))
        else:
            print(f"[dry-run] Would rebuild SQLite state from markdown files ({predicted} item(s)).")
        return
    _init_state_db()
    with contextlib.closing(_connect_state_db()) as conn:
        conn.execute("DELETE FROM work_items")
        conn.commit()
    _db_sync_all_task_files()
    with contextlib.closing(_connect_state_db()) as conn:
        row = conn.execute("SELECT COUNT(*) FROM work_items").fetchone()
    item_count = int(row[0]) if row else 0
    event_id = _db_log_event(None, "sync", actor="system", details=f"rebuild={item_count}")
    if getattr(args, "json", False):
        print(json.dumps(_json_envelope(
            "sync",
            True,
            {"dry_run": False, "item_count": item_count, "audit_event_id": event_id},
        ), indent=2))
    else:
        print(f"✅ Synced SQLite state from markdown files ({item_count} item(s)).")


def cmd_test(args: argparse.Namespace) -> None:
    """Run pytest and auto-transition active In Progress work to Review on pass."""
    _init_state_db()
    pytest_args = list(getattr(args, "pytest_args", []) or [])
    cmd = ["pytest", *pytest_args]

    if getattr(args, "dry_run", False):
        active_in_progress = _in_progress_leaf_items()
        target_slug = active_in_progress[0]["slug"] if active_in_progress else None
        target_item_id = active_in_progress[0]["item_id"] if active_in_progress else None
        if getattr(args, "json", False):
            print(
                json.dumps(
                    _json_envelope(
                        "test",
                        True,
                        {
                            "dry_run": True,
                            "pytest_command": cmd,
                            "transition_target": {
                                "item_id": target_item_id,
                                "slug": target_slug,
                                "after": "Review" if target_slug else None,
                            },
                        },
                    ),
                    indent=2,
                )
            )
            raise SystemExit(0)
        if active_in_progress:
            print(f"[dry-run] Would run: {' '.join(cmd)}")
            print(f"[dry-run] On success, would move '{active_in_progress[0]['slug']}' to Review.")
        else:
            print(f"[dry-run] Would run: {' '.join(cmd)}")
            print("[dry-run] No In Progress task currently available for auto-transition.")
        raise SystemExit(0)

    if not getattr(args, "json", False):
        print(f"▶ Running: {' '.join(cmd)}")
    completed = subprocess.run(cmd)

    transition = None
    if completed.returncode == 0:
        active_in_progress = _in_progress_leaf_items()
        if active_in_progress:
            active_item = active_in_progress[0]
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_review(argparse.Namespace(task_name=active_item["slug"], keeli="system", json=False))
            event_id = _db_log_event(active_item["item_id"], "auto_review_from_tests", actor="system", details="pytest passed")
            transition = {
                "item_id": active_item["item_id"],
                "slug": active_item["slug"],
                "before": "In Progress",
                "after": "Review",
                "audit_event_id": event_id,
            }
            if not getattr(args, "json", False):
                print(f"✅ Tests passed; moved {active_item['slug']} to Review.")
        else:
            if not getattr(args, "json", False):
                print("ℹ️  Tests passed; no In Progress task found to auto-transition.")

    if getattr(args, "json", False):
        print(
            json.dumps(
                _json_envelope(
                    "test",
                    completed.returncode == 0,
                    {
                        "returncode": completed.returncode,
                        "pytest_command": cmd,
                        "transition": transition,
                    },
                ),
                indent=2,
            )
        )
    raise SystemExit(completed.returncode)


def _append_log(message: str, *, task_id: "str | None" = None) -> None:
    """Low-level helper: append one timestamped line to the audit log.

    Format:  <ISO-8601> | <ID> | <message>
    The ID segment is omitted when task_id is None.
    """
    log_file = Path("docs/ai_log.md")
    if not log_file.exists():
        log_file.write_text(AI_LOG_MD)
    id_part = f" | {task_id}" if task_id else ""
    with log_file.open("a") as f:
        f.write(f"{_now_iso()}{id_part} | {message}\n")


def _parse_task_field(text: str, field: str) -> str:
    """Extract the value of a **Field:** line from a task file."""
    for line in text.splitlines():
        if line.startswith(f"**{field}:**"):
            return line.split(":**", 1)[1].strip()
    return ""


def _update_task_field(text: str, field: str, new_value: str) -> str:
    """Replace the value of a **Field:** line in task file content."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"**{field}:**"):
            lines[i] = f"**{field}:** {new_value}"
            break
    return "\n".join(lines)


def _resolve_task_file(tasks_dir: Path, slug: str) -> "Path | None":
    """Return the first existing file matching plain, bug-, feat-, story- or epic- prefix.

    Checks the live *tasks_dir* first, then the *archive/* subdirectory, so that
    completed/archived items remain addressable for reopen / history.
    """
    for base in (tasks_dir, tasks_dir / "archive"):
        for candidate in (
            base / f"{slug}.md",
            base / f"bug-{slug}.md",
            base / f"feat-{slug}.md",
            base / f"story-{slug}.md",
            base / f"epic-{slug}.md",
        ):
            if candidate.exists():
                return candidate
    return None


def _normalize_story_slug(value: str) -> str | None:
    """Normalize story references to a canonical slug."""
    raw = (value or "").strip()
    if not raw or raw.lower() == "none":
        return None
    if raw.startswith("story-"):
        raw = raw[6:]
    return _slugify(raw)


def _story_target_status_from_children(child_statuses: list[str]) -> str | None:
    """Compute story status from child task statuses."""
    if not child_statuses:
        return None
    normalized = [status.strip().lower() for status in child_statuses]
    if normalized and all(status == "completed" for status in normalized):
        return "Completed"
    if any(status in ("in progress", "review") for status in normalized):
        return "In Progress"
    if any(status == "blocked" for status in normalized):
        return "Blocked"
    return "Backlog"


def _sync_parent_story_status(tasks_dir: Path, story_slug: str, *, actor: str = "system") -> dict[str, object] | None:
    """Sync a live story's status with aggregate child task state."""
    canonical_story = _normalize_story_slug(story_slug)
    if not canonical_story:
        return None

    story_file = tasks_dir / f"story-{canonical_story}.md"
    if not story_file.exists():
        return None

    child_statuses: list[str] = []
    for base in (tasks_dir, tasks_dir / "archive"):
        if not base.exists():
            continue
        for candidate in sorted(base.glob("*.md")):
            if candidate.name == ".gitkeep" or candidate.name.startswith(("story-", "epic-")):
                continue
            child_text = candidate.read_text()
            child_story = _normalize_story_slug(_parse_task_field(child_text, "Story"))
            if child_story == canonical_story:
                child_statuses.append(_parse_task_field(child_text, "Status") or "Backlog")

    target_status = _story_target_status_from_children(child_statuses)
    if target_status is None:
        return None

    story_text = story_file.read_text()
    story_id = _parse_task_field(story_text, "ID")
    current_status = _parse_task_field(story_text, "Status") or "Backlog"
    updated = False

    if current_status.lower() != target_status.lower():
        story_text = _update_task_field(story_text, "Status", target_status)
        updated = True

    if target_status == "Completed":
        completed_value = _parse_task_field(story_text, "Completed")
        if completed_value in ("", "—"):
            story_text = _update_task_field(story_text, "Completed", _now_iso())
            updated = True
    else:
        completed_value = _parse_task_field(story_text, "Completed")
        if completed_value not in ("", "—"):
            story_text = _update_task_field(story_text, "Completed", "—")
            updated = True

    if not updated:
        return {
            "story_slug": canonical_story,
            "updated": False,
            "status": current_status,
        }

    story_file.write_text(story_text)
    _db_sync_task_file(story_file)
    _index_update_status(story_id, status=target_status)
    _append_log(
        f"@{actor} | Story status synced from child tasks: {canonical_story} {current_status} → {target_status}",
        task_id=story_id,
    )
    _db_log_event(
        story_id,
        "story_status_synced",
        actor=actor,
        details=f"{canonical_story}:{current_status}->{target_status}",
    )
    return {
        "story_slug": canonical_story,
        "updated": True,
        "before": current_status,
        "after": target_status,
    }


def _is_task_completed(tasks_dir: Path, slug: str) -> bool:
    """Check if a task is completed or archived."""
    # Check archive first
    archive_file = tasks_dir / "archive" / f"{slug}.md"
    if archive_file.exists():
        return True
    
    task_file = _resolve_task_file(tasks_dir, slug)
    if not task_file:
        return False
    
    text = task_file.read_text()
    status = _parse_task_field(text, "Status")
    return status.lower() == "completed"


def _get_next_task() -> tuple[Path | None, str | None]:
    """Find the next task to work on based on priority and age.

    Returns (task_path, task_title) or (None, None).
    """
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        return None, None

    # Epics and stories are planning artifacts — not leaf implementation tasks.
    _SKIP_PREFIXES = ("epic-", "story-")

    # First: any In Progress tasks (resume those first)
    for tf in sorted(tasks_dir.glob("*.md")):
        if tf.name.startswith(_SKIP_PREFIXES):
            continue
        text = tf.read_text()
        status = _parse_task_field(text, "Status")
        if status.lower() == "in progress":
            return tf, tf.stem

    # Second: Backlog tasks sorted by priority (P0 > P1 > P2) then by creation date
    backlog: list[tuple[str, str, Path]] = []
    for tf in sorted(tasks_dir.glob("*.md")):
        if tf.name == ".gitkeep":
            continue
        if tf.name.startswith(_SKIP_PREFIXES):
            continue
        text = tf.read_text()
        status = _parse_task_field(text, "Status")
        if status.lower() == "backlog":
            # Check dependencies
            depends_on = _parse_task_field(text, "Depends On")
            if depends_on and depends_on.lower() != "none":
                deps = [d.strip() for d in depends_on.split(",")]
                all_deps_met = all(_is_task_completed(tasks_dir, _slugify(d)) for d in deps)
                if not all_deps_met:
                    continue

            priority = _parse_task_field(text, "Priority") or "P1"
            created = _parse_task_field(text, "Created") or "9999"
            backlog.append((priority, created, tf))

    if backlog:
        backlog.sort(key=lambda x: (x[0], x[1]))  # P0 < P1 < P2 lexically, then oldest first
        best = backlog[0]
        return best[2], best[2].stem

    return None, None


def _transition_task(args: argparse.Namespace, new_status: str, log_verb: str, command_name: str) -> dict[str, object] | None:
    """Generic helper to transition a task to a new status. Returns transition dict or None on error."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope(command_name, False, error="docs/tasks/ not found")))
        else:
            print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return None

    slug = _slugify(args.task_name)
    task_file = _resolve_task_file(tasks_dir, slug)
    if task_file is None:
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope(command_name, False, error=f"Task '{args.task_name}' not found")))
        else:
            print(f"❌ Task file for '{args.task_name}' not found.")
        return None

    text = task_file.read_text()
    current = _parse_task_field(text, "Status")
    if current.lower() == new_status.lower():
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope(command_name, False, error=f"Already {new_status}")))
        else:
            print(f"⚠️  {task_file} is already {new_status}.")
        return None

    task_id = _parse_task_field(text, "ID")
    story_slug = _normalize_story_slug(_parse_task_field(text, "Story"))
    text = _update_task_field(text, "Status", new_status)
    task_file.write_text(text)
    _db_sync_task_file(task_file)
    _index_update_status(task_id, status=new_status)
    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task {log_verb}: {args.task_name} → {task_file}", task_id=task_id)
    _db_log_event(task_id, new_status.lower().replace(" ", "_"), actor=persona, details=args.task_name)
    story_rollup = _sync_parent_story_status(tasks_dir, story_slug, actor=persona) if story_slug else None

    result = {
        "task_id": task_id,
        "slug": slug,
        "before": current,
        "after": new_status,
        "actor": persona,
        "story_rollup": story_rollup,
    }
    if getattr(args, "json", False):
        print(json.dumps(_json_envelope(command_name, True, result), indent=2))
    else:
        print(f"✅ Marked as {new_status}: {task_file}")
        if story_rollup and story_rollup.get("updated"):
            print(
                f"   ↳ Story rollup: {story_rollup.get('story_slug')} "
                f"{story_rollup.get('before')} -> {story_rollup.get('after')}"
            )
    return _json_envelope(command_name, True, result)


def cmd_progress(args: argparse.Namespace) -> None:
    """Mark a task as In Progress."""
    _transition_task(args, "In Progress", "started", "progress")


def cmd_block(args: argparse.Namespace) -> None:
    """Mark a task as Blocked."""
    _transition_task(args, "Blocked", "blocked", "block")


def cmd_review(args: argparse.Namespace) -> None:
    """Mark a task as In Review (ready for @security sign-off)."""
    _transition_task(args, "Review", "in review", "review")


def cmd_reopen(args: argparse.Namespace) -> None:
    """Reopen a completed task (move it back to In Progress)."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope("reopen", False, error="docs/tasks/ not found")))
        else:
            print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.task_name)
    task_file = _resolve_task_file(tasks_dir, slug)
    if task_file is None:
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope("reopen", False, error=f"Task '{args.task_name}' not found")))
        else:
            print(f"❌ Task file for '{args.task_name}' not found.")
        return

    text = task_file.read_text()
    status = _parse_task_field(text, "Status")
    if status.lower() not in ("completed", "review"):
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope("reopen", False, error=f"Cannot reopen task in status: {status}")))
        else:
            print(f"⚠️  {task_file} is currently '{status}' — reopen only works on Completed or Review tasks.")
        return

    task_id = _parse_task_field(text, "ID")
    story_slug = _normalize_story_slug(_parse_task_field(text, "Story"))
    if task_file.parent.name == "archive":
        live_dest = tasks_dir / task_file.name
        task_file.rename(live_dest)
        task_file = live_dest
        if not getattr(args, "json", False):
            print(f"   📤 Restored from archive → {task_file}")

    text = _update_task_field(text, "Status", "In Progress")
    text = _update_task_field(text, "Completed", "—")
    task_file.write_text(text)
    _db_sync_task_file(task_file)
    _index_update_status(task_id, status="In Progress", completed=None, archived=False)
    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task reopened: {args.task_name} → {task_file}", task_id=task_id)
    _db_log_event(task_id, "reopened", actor=persona, details=args.task_name)
    if story_slug:
        _sync_parent_story_status(tasks_dir, story_slug, actor=persona)

    result = {"task_id": task_id, "slug": slug, "before": status, "after": "In Progress", "actor": persona}
    if getattr(args, "json", False):
        print(json.dumps(_json_envelope("reopen", True, result), indent=2))
    else:
        print(f"✅ Reopened: {task_file} (now In Progress)")


def cmd_bug(args: argparse.Namespace) -> None:
    """Log a bug found during development and create a tracked bug task."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.title)
    task_file = tasks_dir / f"bug-{slug}.md"

    existing_text = task_file.read_text() if task_file.exists() else ""

    if task_file.exists() and not args.force:
        print(f"⚠️  {task_file} already exists. Use --force to overwrite.")
        return

    priority = args.priority or _prompt(
        "Bug priority", default="P0", choices=["P0", "P1", "P2"]
    )
    found_during = args.found_during or "debugging"
    description = args.description or _prompt(
        "Short description (or press Enter to leave blank)", default=""
    ) or "<!-- Describe the bug here -->"
    epic = getattr(args, "epic", None) or "None"

    bug_id = _parse_task_field(existing_text, "ID") if existing_text else ""
    if not bug_id:
        bug_id = _allocate_id(
            "bug", args.title, f"bug-{slug}", priority=priority,
            epic=epic if epic != "None" else None,
        )
    content = BUG_TEMPLATE.format(
        task_id=bug_id,
        title=args.title,
        priority=priority,
        timestamp=_now_iso(),
        epic=epic,
        found_during=found_during,
        description=description,
    )
    task_file.write_text(content)
    _db_sync_task_file(task_file)
    print(f"🐛 Created bug report: {task_file} [{bug_id}]")

    _append_log(f"@developer | Bug reported: {args.title} [{priority}] → {task_file}", task_id=bug_id)
    _db_log_event(bug_id, "created", actor="developer", details=args.title)


def cmd_feature(args: argparse.Namespace) -> None:
    """Create a feature request task with user story and acceptance criteria."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.title)
    task_file = tasks_dir / f"feat-{slug}.md"

    existing_text = task_file.read_text() if task_file.exists() else ""

    if task_file.exists() and not args.force:
        print(f"⚠️  {task_file} already exists. Use --force to overwrite.")
        return

    # Resolve optional context file
    context_note = "None"
    if args.context:
        ctx_path = Path(args.context)
        if ctx_path.exists():
            context_note = f"See [{ctx_path}]({ctx_path})"
        else:
            print(f"⚠️  Context file {ctx_path} not found. Proceeding without link.")

    priority = args.priority or _prompt(
        "Feature priority", default="P1", choices=["P0", "P1", "P2"]
    )
    epic = getattr(args, "epic", None) or "None"

    feat_id = _parse_task_field(existing_text, "ID") if existing_text else ""
    if not feat_id:
        feat_id = _allocate_id(
            "feat", args.title, f"feat-{slug}", priority=priority,
            epic=epic if epic != "None" else None,
        )
    user_story_text = _resolve_objective(getattr(args, "objective", None))
    if not user_story_text:
        print(_OBJECTIVE_HINT)
    content = FEATURE_TEMPLATE.format(
        task_id=feat_id,
        title=args.title,
        priority=priority,
        timestamp=_now_iso(),
        epic=epic,
        context_note=context_note,
        user_story=user_story_text or "<!-- As a <user>, I want <goal>, so that <reason>. -->",
    )
    task_file.write_text(content)
    _db_sync_task_file(task_file)
    print(f"✨ Created feature: {task_file} [{feat_id}]")

    _append_log(f"@architect | Feature created: {args.title} [{priority}] → {task_file}", task_id=feat_id)
    _db_log_event(feat_id, "created", actor="architect", details=args.title)


def cmd_skill(args: argparse.Namespace) -> None:
    """Manage project skills (add / list / remove).

    Skills are stored in docs/skills.md and injected into
    .github/copilot-instructions.md so personas use them automatically.
    """
    if not Path("docs").exists():
        print("❌ docs/ not found. Run `keeli init` first.")
        return

    sub = args.skill_action

    if sub == "list":
        skills = _read_skills()
        if not skills:
            print("No skills registered. Use `keeli stack` to apply a preset or `keeli skill add` to add one.")
            return
        print(f"\n  {'Type':<12} {'Skill':<24} {'Persona':<14} Constraint")
        print("  " + "-" * 72)
        for t, n, p, c in sorted(skills, key=lambda x: (x[2], x[0], x[1])):
            constraint_display = (c[:36] + "\u2026") if c and len(c) > 37 else (c or "")
            print(f"  {t:<12} {n:<24} {p or '(global)':<14} {constraint_display}")
        print(f"\n  {len(skills)} skill(s) registered. Use `keeli skill show <name>` for full constraint.")

    elif sub == "show":
        name = getattr(args, "skill_name", None) or _prompt("Skill name")
        skills = _read_skills()
        matches = [(t, n, p, c) for t, n, p, c in skills if n.lower() == name.lower()]
        if not matches:
            print(f"\u26a0\ufe0f  Skill '{name}' not found.")
            return
        for t, n, p, c in matches:
            scope = f"@{p}" if p else "global"
            print(f"\n  Skill:       {n}")
            print(f"  Type:        {t}")
            print(f"  Persona:     {scope}")
            print(f"  Constraint:  {c or '(none \u2014 recommend adding one for LLM clarity)'}")

    elif sub == "add":
        name = getattr(args, "skill_name", None) or _prompt("Skill name (be specific: e.g. 'FastAPI', not just 'Python')")
        if not name:
            print("\u26a0\ufe0f  Skill name is required.")
            return
        _GENERIC_NAMES = {"python", "java", "javascript", "typescript", "node", "react",
                          "angular", "vue", "go", "rust", "ruby", "php", "swift", "kotlin"}
        if name.strip().lower() in _GENERIC_NAMES:
            print(f"  \u26a0\ufe0f  '{name}' is a generic language name \u2014 the LLM already knows {name}.")
            print(f"     The constraint field is where you teach it YOUR project's dialect.")
            print(f"     Example: '3.12+; Pydantic v2 strict; async/await throughout'")
        skill_type = getattr(args, "type", None) or _prompt(
            "Skill type", default="lang", choices=SKILL_TYPES
        )
        personas = _load_personas()
        persona = getattr(args, "persona", None) or _prompt(
            "Which persona owns this skill? (blank = global)",
            default="",
            choices=personas + ["global"],
        )
        persona = "" if persona.strip().lower() in ("global", "") else persona.strip().lower()
        constraint = getattr(args, "constraint", None)
        if constraint is None:
            # Interactive — require non-empty (@architect must document the why)
            print("  \u26a0\ufe0f  Constraint is REQUIRED — @architect must document the why and how.")
            print("     Include: version pin, project-specific rules, key decisions.")
            print("     Example: '3.12+; Pydantic v2 strict; async/await throughout'")
            while True:
                constraint = _prompt("Constraint (required)", default="")
                if constraint.strip():
                    break
                print("  \u274c Cannot be empty. This teaches the LLM your project's dialect.")
        elif not constraint.strip():
            print("\u274c --constraint / -c cannot be empty. @architect must document why and how.")
            print("   Example: -c '3.12+; async/await throughout; Pydantic v2 strictly'")
            return
        skills = _read_skills()
        if any(n2.lower() == name.lower() and t2 == skill_type and p2 == persona
               for t2, n2, p2, _ in skills):
            scope = f"@{persona}" if persona else "global"
            print(f"\u26a0\ufe0f  '{name}' ({skill_type}) is already registered for {scope}.")
            return
        skills.append((skill_type, name, persona, constraint or ""))
        _write_skills(skills)
        scope = f"@{persona}" if persona else "global"
        print(f"\u2705 Added skill: [{skill_type}] {name}  \u2192  {scope}")
        if constraint:
            print(f"   Constraint:  {constraint}")
        print(f"   \u2192 docs/skills.md and .github/copilot-instructions.md updated")
        _append_log(f"@architect | Skill added: [{skill_type}] {name} \u2192 {scope}")

    elif sub == "remove":
        name = getattr(args, "skill_name", None) or _prompt("Skill name to remove")
        if not name:
            print("\u26a0\ufe0f  Skill name is required.")
            return
        skills = _read_skills()
        new_skills = [(t, n, p, c) for t, n, p, c in skills if n.lower() != name.lower()]
        if len(new_skills) == len(skills):
            print(f"\u26a0\ufe0f  Skill '{name}' not found.")
            return
        _write_skills(new_skills)
        print(f"\u2705 Removed skill: {name}")
        _append_log(f"@architect | Skill removed: {name}")

    elif sub == "scan":
        root = _find_project_root()
        scan_path = getattr(args, "scan_path", None)
        if scan_path:
            root = Path(scan_path)
        dry_run   = getattr(args, "dry_run", False)
        apply_now = getattr(args, "apply",   False)

        found = _scan_manifests(root)
        if not found:
            print(
                "\u26a0\ufe0f  No recognised manifest files found.\n"
                "   Supported: pyproject.toml  requirements*.txt  package.json\n"
                "              go.mod  Cargo.toml  pom.xml  .python-version  .nvmrc"
            )
            return

        print(f"\n\U0001f50d Scanned {root} \u2014 {len(found)} technology/package(s) detected\n")
        print(f"  {'Type':<12} {'Name':<28} {'Version':<16} Source")
        print("  " + "-" * 72)
        for s in found:
            print(f"  {s.skill_type:<12} {s.name:<28} {s.version or '?':<16} {s.source_file}")

        if dry_run or not apply_now:
            print(f"\n  Run with --apply to register these in docs/skills.md")
            print(f"  @architect: you will be prompted for a constraint on each skill.")
            return

        # --apply: interactive constraint prompt per skill
        existing      = _read_skills()
        existing_keys = {n2.lower() for _, n2, _, _ in existing}

        print(f"\n  @architect: Add a constraint for each detected skill.")
        print(f"  Constraint = version pin + why you chose it + project-specific rules.")
        print(f"  Press Enter to skip a skill. Type 'q' to stop.\n")
        print("  " + "-" * 72)

        added = 0
        for s in found:
            if s.name.lower() in existing_keys:
                print(f"  \u23ed  [{s.skill_type}] {s.name}  \u2014 already registered, skipping")
                continue
            ver_hint = f"  (detected: {s.version})" if s.version else ""
            print(f"\n  [{s.skill_type}] {s.name}{ver_hint}  from {s.source_file}")
            if not sys.stdin.isatty():
                print(f"  Non-interactive \u2014 skipping. Add manually: keeli skill add \"{s.name}\"")
                continue
            constraint = input("  Constraint (blank=skip, q=stop): ").strip()
            if constraint.lower() == "q":
                print("  Stopped. Skills added so far will be saved.")
                break
            if not constraint:
                print("  Skipped.")
                continue
            existing.append((s.skill_type, s.name, "architect", constraint))
            existing_keys.add(s.name.lower())
            added += 1

        if added:
            _write_skills(existing)
            print(f"\n\u2705 Added {added} skill(s) to docs/skills.md + updated copilot-instructions.md")
            _append_log(f"@architect | Skill scan applied: {added} new skill(s) from manifest files")
        else:
            print(f"\n  No new skills added.")

    else:
        print("Usage: keeli skill <add|list|remove|show|scan>")


# ---------------------------------------------------------------------------
# keeli persona  — interactive persona management
# ---------------------------------------------------------------------------

def _write_persona_block(slug: str, description: str, skills: list[str], must_not: str) -> None:
    """Append a new persona block to docs/personas.md in the rich ## format."""
    path = Path("docs/personas.md")
    content = path.read_text() if path.exists() else ""
    # Strip trailing comment block if present
    new_block = f"\n## {slug}\n"
    new_block += f"**Mindset:** {description}\n\n"
    if skills:
        new_block += "**Core Skills:**\n"
        for s in skills:
            new_block += f"- {s}\n"
        new_block += "\n"
    if must_not:
        new_block += "**NEVER:**\n"
        for line in must_not.split(","):
            line = line.strip()
            if line:
                new_block += f"- {line}\n"
        new_block += "\n"
    new_block += "---\n"
    # Insert before the trailing comment block if it exists
    marker = "<!-- Add custom personas below"
    if marker in content:
        content = content.replace(marker, new_block + "\n" + marker)
    else:
        content = content.rstrip() + "\n" + new_block
    path.write_text(content)


# ---------------------------------------------------------------------------
# keeli stack  — interactive preset picker
# ---------------------------------------------------------------------------

def cmd_stack(args: argparse.Namespace) -> None:
    """Apply a stack preset interactively, customising each skill constraint.

    Presets are opinionated starting points: each skill ships with a
    suggested constraint / decision you can accept (Enter) or rewrite.
    The constraint is what teaches the LLM your dialect, not just the
    technology name.
    """
    if not Path("docs").exists():
        print("\u274c docs/ not found. Run `keeli init` first.")
        return

    sub = getattr(args, "stack_action", None) or "pick"

    if sub == "list":
        print("\nAvailable stack presets:\n")
        for key, entries in STACK_PRESETS.items():
            skills_preview = ", ".join(n for _, n, _, _ in entries[:3])
            extra = f" + {len(entries) - 3} more" if len(entries) > 3 else ""
            print(f"  {key:<20} {skills_preview}{extra}")
        aliases = ", ".join(f"{a}\u2192{t}" for a, t in STACK_PRESET_ALIASES.items())
        print(f"\n  Aliases: {aliases}")
        print("\nRun `keeli stack apply <name>` or just `keeli stack` to pick interactively.")
        return

    preset_name = getattr(args, "preset_name", None)

    if sub == "apply" and preset_name:
        # Resolve alias
        resolved = STACK_PRESET_ALIASES.get(preset_name.lower(), preset_name.lower())
        if resolved not in STACK_PRESETS:
            print(f"\u26a0\ufe0f  Unknown preset '{preset_name}'.")
            print(f"   Available: {', '.join(STACK_PRESETS.keys())}")
            return
        chosen = [resolved]
    else:
        # Interactive picker
        preset_keys = list(STACK_PRESETS.keys())
        print("\nAvailable stack presets (you can pick multiple):\n")
        for i, key in enumerate(preset_keys, 1):
            entries = STACK_PRESETS[key]
            preview = ", ".join(n for _, n, _, _ in entries[:3])
            extra = f" + {len(entries) - 3} more" if len(entries) > 3 else ""
            print(f"  {i:>2}. {key:<20} {preview}{extra}")
        print()
        raw = input("Enter preset numbers or names (space/comma-separated): ").strip()
        if not raw:
            print("No selection made. Exiting.")
            return
        chosen: list[str] = []
        for token in re.split(r"[,\s]+", raw):
            token = token.strip()
            if not token:
                continue
            if token.isdigit():
                idx = int(token) - 1
                if 0 <= idx < len(preset_keys):
                    chosen.append(preset_keys[idx])
                else:
                    print(f"  \u26a0\ufe0f  {token} out of range, skipping.")
            else:
                resolved = STACK_PRESET_ALIASES.get(token.lower(), token.lower())
                if resolved in STACK_PRESETS:
                    chosen.append(resolved)
                else:
                    print(f"  \u26a0\ufe0f  Unknown preset '{token}', skipping.")
        if not chosen:
            print("No valid presets selected.")
            return

    # Build deduped list of skills to add from chosen presets
    to_add: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for preset_key in chosen:
        for t, n, p, hint in STACK_PRESETS[preset_key]:
            key = (t, n.lower(), p)
            if key not in seen:
                seen.add(key)
                to_add.append((t, n, p, hint))

    no_confirm = getattr(args, "yes", False)
    existing = _read_skills()
    existing_keys = {(t2, n2.lower(), p2) for t2, n2, p2, _ in existing}

    print(f"\n  Applying {len(to_add)} skill(s) from preset(s): {', '.join(chosen)}\n")
    print("  y/Enter = accept suggestion  |  n = skip  |  type = custom constraint  |  q = quit\n")
    print("  " + "-" * 68)

    added = 0
    skipped_existing = 0
    for t, n, p, hint in to_add:
        scope = f"@{p}" if p else "global"
        if (t, n.lower(), p) in existing_keys:
            print(f"  \u23ed  [{t}] {n} ({scope})  \u2014 already registered, skipping")
            skipped_existing += 1
            continue
        print(f"\n  [{t}] {n}  \u2192  {scope}")
        if no_confirm:
            constraint = hint
            print(f"  Constraint: {constraint}")
        else:
            print(f"  Suggested:  {hint}")
            user_input = input("  Accept? [Y/n/edit/q]: ").strip()
            if user_input.lower() == "q":
                print("\n  Stopped. Skills added so far will be saved.")
                break
            if user_input.lower() == "n":
                print("  Skipped.")
                continue
            constraint = hint if user_input.lower() in ("", "y", "yes", "accept") else user_input
        existing.append((t, n, p, constraint))
        existing_keys.add((t, n.lower(), p))
        added += 1

    if added:
        _write_skills(existing)
        print(f"\n\u2705 Added {added} skill(s). {skipped_existing} already existed.")
        print(f"   \u2192 docs/skills.md and .github/copilot-instructions.md updated")
        _append_log(f"@architect | Stack preset applied: {', '.join(chosen)} | {added} skill(s) added")
    else:
        print(f"\n  No new skills added ({skipped_existing} already registered).")


def cmd_persona(args: argparse.Namespace) -> None:
    """Manage project personas (add / list / remove)."""
    if not Path("docs").exists():
        print("\u274c docs/ not found. Run `keeli init` first.")
        return

    sub = args.persona_action

    if sub == "list":
        personas = _load_personas()
        print(f"\n  {'Slug':<16} Source")
        print("  " + "-" * 40)
        path = Path("docs/personas.md")
        for p in personas:
            src = "built-in" if p in DEFAULT_PERSONAS else "custom"
            if path.exists() and f"## {p}" in path.read_text():
                src = "docs/personas.md"
            print(f"  {p:<16} {src}")
        print(f"\n  {len(personas)} persona(s) registered.")

    elif sub == "add":
        slug = getattr(args, "persona_slug", None) or _prompt("Persona slug (e.g. qa, devops)")
        if not slug:
            print("\u26a0\ufe0f  Persona slug is required.")
            return
        slug = re.sub(r"[^a-z0-9-]", "", slug.strip().lower())
        existing = _load_personas()
        if slug in existing:
            print(f"\u26a0\ufe0f  Persona '{slug}' already exists.")
            return

        description = _prompt(
            f"Describe @{slug}'s mindset in one sentence",
            default=f"{slug.title()} specialist",
        )

        print(f"\nWhat skills does @{slug} need?")
        print("  Enter one skill per prompt, or paste a comma-separated list.")
        print("  Press Enter with no input to finish.\n")
        skills: list[str] = []
        while True:
            entry = input("  Skill (or comma list, blank to finish): ").strip()
            if not entry:
                break
            for item in entry.split(","):
                item = item.strip()
                if item:
                    skills.append(item)
        if not skills:
            print("  (no skills added — you can edit docs/personas.md to add them later)")

        must_not = _prompt(
            f"What should @{slug} NEVER do? (comma-separated, blank to skip)",
            default="",
        )

        _write_persona_block(slug, description, skills, must_not)
        print(f"\n\u2705 Persona '@{slug}' added to docs/personas.md")
        _append_log(f"@architect | Persona added: {slug} | skills: {', '.join(skills) or 'none'}")

    elif sub == "remove":
        slug = getattr(args, "persona_slug", None) or _prompt("Persona slug to remove")
        if not slug:
            print("\u26a0\ufe0f  Persona slug is required.")
            return
        if slug in DEFAULT_PERSONAS:
            confirm = _prompt(f"'{slug}' is a built-in persona. Remove anyway? (yes/no)", default="no")
            if confirm.lower() not in ("yes", "y"):
                print("Aborted.")
                return
        path = Path("docs/personas.md")
        if not path.exists():
            print("\u26a0\ufe0f  docs/personas.md not found.")
            return
        content = path.read_text()
        # Remove the ## slug block up to the next ## or end of file
        pattern = rf"\n## {re.escape(slug)}\n.*?(?=\n## |\Z)"
        new_content = re.sub(pattern, "", content, flags=re.DOTALL).rstrip() + "\n"
        if new_content == content:
            print(f"\u26a0\ufe0f  Persona '{slug}' not found in docs/personas.md.")
            return
        path.write_text(new_content)
        print(f"\u2705 Persona '@{slug}' removed from docs/personas.md.")
        _append_log(f"@architect | Persona removed: {slug}")

    else:
        print("Usage: keeli persona <add|list|remove>")


def cmd_story(args: argparse.Namespace) -> None:
    """Create a user story under an epic (@architect responsibility)."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.title)
    task_file = tasks_dir / f"story-{slug}.md"

    existing_text = task_file.read_text() if task_file.exists() else ""

    if task_file.exists() and not args.force:
        print(f"⚠️  {task_file} already exists. Use --force to overwrite.")
        return

    epic = getattr(args, "epic", None) or _prompt(
        "Epic slug this story belongs to", default="None"
    )
    priority = args.priority or _prompt(
        "Story priority", default="P1", choices=["P0", "P1", "P2"]
    )
    role = getattr(args, "role", None)
    goal = getattr(args, "goal", None)
    reason = getattr(args, "reason", None)

    # Build acceptance criteria block from --ac flags or placeholder comments
    raw_acs: list[str] = getattr(args, "ac", None) or []
    if raw_acs:
        criteria_lines = "\n".join(f"- [ ] {ac}" for ac in raw_acs)
    else:
        criteria_lines = (
            "- [ ] <!-- Criterion 1 -->\n"
            "- [ ] <!-- Criterion 2 -->\n"
            "- [ ] <!-- Criterion 3 -->"
        )

    if role and goal and reason:
        user_story = f"As a {role}, I want {goal} so that I can {reason}."
    else:
        user_story = "<!-- As a [role], I want [feature] so that [benefit]. -->"

    nfr_block = "None"

    story_id = _parse_task_field(existing_text, "ID") if existing_text else ""
    if not story_id:
        story_id = _allocate_id(
            "story", args.title, f"story-{slug}", priority=priority,
            epic=epic if epic != "None" else None,
        )
    content = STORY_TEMPLATE.format(
        task_id=story_id,
        title=args.title,
        priority=priority,
        timestamp=_now_iso(),
        epic=epic,
        user_story=user_story,
        acceptance_criteria=criteria_lines,
        non_functional_requirements=nfr_block,
    )
    task_file.write_text(content)
    _db_sync_task_file(task_file)
    print(f"📖 Created story: {task_file} [{story_id}]")
    if epic != "None":
        print(f"   → Linked to epic: {epic}")
    print(f"   → Add tasks with: keeli start \"<title>\" --story {slug} --epic {epic}")

    _append_log(f"@architect | Story created: {args.title} [{priority}] epic={epic} → {task_file}", task_id=story_id)
    _db_log_event(story_id, "created", actor="architect", details=args.title)


def cmd_epic(args: argparse.Namespace) -> None:
    """Create a new epic file in docs/tasks/."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.title)
    task_file = tasks_dir / f"epic-{slug}.md"

    existing_text = task_file.read_text() if task_file.exists() else ""

    if task_file.exists() and not args.force:
        print(f"⚠️  {task_file} already exists. Use --force to overwrite.")
        return

    priority = args.priority or _prompt(
        "Epic priority", default="P1", choices=["P0", "P1", "P2"]
    )

    epic_id = _parse_task_field(existing_text, "ID") if existing_text else ""
    if not epic_id:
        epic_id = _allocate_id("epic", args.title, f"epic-{slug}", priority=priority)
    objective_text = _resolve_objective(getattr(args, "objective", None))
    if not objective_text:
        print(_OBJECTIVE_HINT)
    content = EPIC_TEMPLATE.format(
        task_id=epic_id,
        title=args.title,
        priority=priority,
        timestamp=_now_iso(),
        goal=objective_text or "<!-- What business/user outcome does this epic deliver? -->",
    )
    task_file.write_text(content)
    _db_sync_task_file(task_file)
    print(f"🚀 Created epic: {task_file} [{epic_id}]")
    print(f"   → @architect: define objective/scope, then run: keeli story \"<title>\" --epic {slug}")

    _append_log(f"@architect | Epic created: {args.title} [{priority}] → {task_file}", task_id=epic_id)
    _db_log_event(epic_id, "created", actor="architect", details=args.title)


def cmd_complete(args: argparse.Namespace) -> None:
    """Mark a task as completed, auto-archive it, and suggest the next one."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope("complete", False, error="docs/tasks/ not found")))
        else:
            print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.task_name)
    task_file = _resolve_task_file(tasks_dir, slug)

    if task_file is None:
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope("complete", False, error=f"Task '{args.task_name}' not found")))
        else:
            print(f"❌ Task file for '{args.task_name}' not found.")
        return

    text = task_file.read_text()
    status = _parse_task_field(text, "Status")

    evidence_errors = _completion_evidence_errors(text)
    scaffolded_sections: list[str] = []
    if evidence_errors and getattr(args, "scaffold_missing", False):
        text, scaffolded_sections = _scaffold_completion_sections(text)
        task_file.write_text(text)
        _db_sync_task_file(task_file)
        evidence_errors = _completion_evidence_errors(text)

    if evidence_errors:
        msg = "Task is missing required completion evidence"
        if getattr(args, "json", False):
            payload: dict[str, object] = {"errors": evidence_errors}
            if scaffolded_sections:
                payload["scaffolded"] = scaffolded_sections
            print(json.dumps(_json_envelope("complete", False, error=msg, data=payload), indent=2))
        else:
            print(f"❌ {msg}:")
            for err in evidence_errors:
                print(f"   - {err}")
            if scaffolded_sections:
                print(f"   ↳ Scaffolded sections: {', '.join(scaffolded_sections)}")
                print("   ↳ Fill in the generated placeholders, then rerun complete.")
            else:
                print("   ↳ Tip: rerun with --scaffold-missing to auto-generate placeholders.")
        return

    if status.lower() == "completed":
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope("complete", False, error="Task is already marked as Completed")))
        else:
            print(f"⚠️  {task_file} is already marked as Completed.")
        return

    now = _now_iso()
    task_id = _parse_task_field(text, "ID")
    story_slug = _normalize_story_slug(_parse_task_field(text, "Story"))

    # Update status and add completion timestamp
    text = _update_task_field(text, "Status", "Completed")
    text = _update_task_field(text, "Completed", now)
    task_file.write_text(text)
    if not getattr(args, "json", False):
        print(f"✅ Marked as Completed: {task_file}")

    # Auto-archive to docs/tasks/archive/
    archive_dir = tasks_dir / "archive"
    archive_dir.mkdir(exist_ok=True)
    dest = archive_dir / task_file.name
    task_file.rename(dest)
    _db_sync_task_file(dest)
    if not getattr(args, "json", False):
        print(f"   📦 Auto-archived → {dest}")

    # Update index
    _index_update_status(task_id, status="Completed", completed=now, archived=True)

    # Auto-log
    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task completed: {args.task_name} → {dest}", task_id=task_id)
    _db_log_event(task_id, "completed", actor=persona, details=args.task_name)
    story_rollup = _sync_parent_story_status(tasks_dir, story_slug, actor=persona) if story_slug else None

    # Suggest next task
    next_path, next_slug = _get_next_task()
    next_task = None
    if next_path:
        next_text = next_path.read_text()
        next_status = _parse_task_field(next_text, "Status")
        next_priority = _parse_task_field(next_text, "Priority")
        next_task = next_slug
        if not getattr(args, "json", False):
            print(f"\n📋 Next task: {next_slug} [{next_priority}] ({next_status})")
            print(f"   → {next_path}")
    else:
        if not getattr(args, "json", False):
            print("\n🎉 All tasks are complete. Awaiting new instructions.")

    result = {
        "task_id": task_id,
        "slug": slug,
        "before": status,
        "after": "Completed",
        "actor": persona,
        "archived": True,
        "next_task": next_task,
        "story_rollup": story_rollup,
    }
    if getattr(args, "json", False):
        print(json.dumps(_json_envelope("complete", True, result), indent=2))
    elif story_rollup and story_rollup.get("updated"):
        print(
            f"   ↳ Story rollup: {story_rollup.get('story_slug')} "
            f"{story_rollup.get('before')} -> {story_rollup.get('after')}"
        )


def cmd_ensure(args: argparse.Namespace) -> None:
    """Check for an existing task matching *description*; optionally create one.

    If several files contain a slug match, they are listed and nothing else is done.
    Without -y/--yes the user is prompted before creation; --no suppresses creation.
    """
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    desc = args.title
    slug = _slugify(desc)
    matches = [tf for tf in tasks_dir.glob("*.md") if slug in tf.stem]
    if matches:
        print("✅ Found existing task(s):")
        for tf in matches:
            print(f"  - {tf.name}")
        return

    # no match found
    if args.no:
        return
    if args.yes:
        create = True
    else:
        resp = _prompt("No task found. Create one?", default="Y", choices=["Y", "n"])
        create = resp.lower().startswith("y")
    if not create:
        print("ok, nothing created")
        return

    # delegate to cmd_start with objective defaulting to description
    new_args = argparse.Namespace(
        task_name=desc,
        context=None,
        objective=desc,
        priority=None,
        depends_on=None,
        keeli=None,
    )
    cmd_start(new_args)


def cmd_tick(args: argparse.Namespace) -> None:
    """Tick all mechanical checklist items; leave @security/@author gate items untouched."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.task_name)
    task_file = _resolve_task_file(tasks_dir, slug)

    if task_file is None:
        print(f"❌ Task file for '{args.task_name}' not found.")
        return

    lines = task_file.read_text().splitlines()
    updated, count = [], 0
    for line in lines:
        if line.strip().startswith("- [ ]") and not _is_gate_item(line):
            updated.append(line.replace("- [ ]", "- [x]", 1))
            count += 1
        else:
            updated.append(line)

    task_file.write_text("\n".join(updated))
    if count:
        print(f"✅ Ticked {count} item(s) in {task_file}")
        # Gate items remaining?
        gate_left = sum(
            1 for l in updated
            if l.strip().startswith("- [ ]") and _is_gate_item(l)
        )
        if gate_left:
            print(f"   ⚠️  {gate_left} gate item(s) still require human sign-off (@security/@author)")
    else:
        print(f"ℹ️  No mechanical items to tick in {task_file}")


def cmd_next(args: argparse.Namespace) -> None:
    """Show the next task to work on."""
    next_path, next_slug = _get_next_task()
    if next_path:
        next_text = next_path.read_text()
        next_status = _parse_task_field(next_text, "Status")
        next_priority = _parse_task_field(next_text, "Priority")
        
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope(
                "next",
                True,
                {
                    "task": next_slug,
                    "priority": next_priority,
                    "status": next_status,
                    "path": str(next_path),
                    "content": next_text,
                },
            ), indent=2))
            return

        print(f"📋 Next task: {next_slug} [{next_priority}] ({next_status})")
        print(f"   → {next_path}")
        if not args.quiet:
            print(f"\n{next_text}")
            # Auto context hints in terminal output (never written to disk)
            try:
                hints = _score_task(next_text)
                if hints["skills"] or hints["adrs"]:
                    print("\n\u2500\u2500\u2500 AI Context Hints \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                    if hints["skills"]:
                        skill_str = ", ".join(f'`{m["name"]}`' for _, m in hints["skills"])
                        print(f"  Skills:  {skill_str}")
                    if hints["adrs"]:
                        adr_str = ", ".join(m["ref"] for _, m in hints["adrs"])
                        print(f"  ADRs:    {adr_str}")
                    if hints["persona"]:
                        print(f"  Persona: @{hints['persona']}")
                    print("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
            except Exception:
                pass  # never let analysis errors break `keeli next`
    else:
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope("next", True, {"task": None}), indent=2))
            return
        print("🎉 All tasks are complete. Awaiting new instructions.")


def cmd_list(args: argparse.Namespace) -> None:
    """List all tasks with status, priority, and creation date."""
    _refresh_state_from_markdown()
    raw_filter_status = getattr(args, "status", None)
    filter_status = _canonical_status(raw_filter_status) if raw_filter_status else None
    filter_epic = getattr(args, "epic", None)
    STATUS_ICON = {
        "backlog":     "⬜",
        "in progress": "🔵",
        "review":      "🟡",
        "blocked":     "🔴",
        "completed":   "✅",
    }

    rows = []
    db_path = _state_db_path()
    if db_path.exists():
        with contextlib.closing(_connect_state_db()) as conn:
            query = (
                "SELECT priority, substr(COALESCE(created_at, ''), 1, 10) AS created, "
                "status, slug, COALESCE(epic_slug, 'None') AS epic "
                "FROM work_items WHERE archived = 0"
            )
            params: list[str] = []
            clauses: list[str] = []
            if filter_status:
                clauses.append("lower(status) = lower(?)")
                params.append(filter_status)
            if filter_epic:
                clauses.append("lower(COALESCE(epic_slug, 'None')) = lower(?)")
                params.append(filter_epic)
            if clauses:
                query += " AND " + " AND ".join(clauses)
            query += " ORDER BY priority, created_at"
            for row in conn.execute(query, params):
                icon = STATUS_ICON.get((row["status"] or "").lower(), "❓")
                rows.append((row["priority"] or "P1", row["created"] or "?", icon, row["status"] or "", row["slug"], row["epic"]))
    else:
        tasks_dir = Path("docs/tasks")
        if not tasks_dir.exists():
            print("❌ docs/tasks/ not found. Run `keeli init` first.")
            return
        for tf in sorted(tasks_dir.glob("*.md")):
            if tf.name == ".gitkeep":
                continue
            text = tf.read_text()
            status = _parse_task_field(text, "Status")
            priority = _parse_task_field(text, "Priority") or "P1"
            created = (_parse_task_field(text, "Created") or "?")[:10]
            epic = _parse_task_field(text, "Epic") or "None"
            if filter_status and (_canonical_status(status) or status).lower() != filter_status.lower():
                continue
            if filter_epic and epic.lower() != filter_epic.lower():
                continue
            icon = STATUS_ICON.get(status.lower(), "❓")
            rows.append((priority, created, icon, status, tf.stem, epic))

    if not rows:
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope("list", True, {"items": [], "count": 0}), indent=2))
            return
        msg = "No tasks found matching criteria."
        print(msg)
        return

    rows.sort(key=lambda r: (r[0], r[1]))
    
    if getattr(args, "json", False):
        out = [{"priority": r[0], "created": r[1], "status": r[3], "task": r[4], "epic": r[5]} for r in rows]
        print(json.dumps(_json_envelope("list", True, {"items": out, "count": len(out)}), indent=2))
        return

    print(f"\n  {'Pri':<4} {'Created':<12} {'Status':<14} {'Epic':<15} Task")
    print("  " + "-" * 70)
    for pri, cr, icon, st, name, ep in rows:
        ep_disp = ep[:13] + ".." if len(ep) > 15 else ep
        print(f"  {pri:<4} {cr:<12} {icon} {st:<11} {ep_disp:<15} {name}")
    print(f"\n  {len(rows)} task(s) found.")


def cmd_note(args: argparse.Namespace) -> None:
    """Append a timestamped note to an existing task file."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.task_name)
    task_file = _resolve_task_file(tasks_dir, slug)

    if task_file is None:
        print(f"❌ Task file for '{args.task_name}' not found.")
        return

    note_text = getattr(args, "message", None) or _prompt("Note message")
    if not note_text:
        print("⚠️  No message provided.")
        return

    persona   = getattr(args, "keeli", "developer") or "developer"
    timestamp = _now_iso()
    text      = task_file.read_text()
    note_line = f"\n**[{timestamp}] @{persona}:** {note_text}"

    if "## Notes" in text:
        text = text.replace("## Notes", f"## Notes{note_line}", 1)
    else:
        text += f"\n## Notes{note_line}\n"

    task_file.write_text(text)
    print(f"✅ Note added to {task_file}")
    _append_log(f"@{persona} | Note on '{args.task_name}': {note_text[:80]}")


def cmd_archive(args: argparse.Namespace) -> None:
    """Move a completed task to docs/tasks/archive/."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.task_name)
    task_file = _resolve_task_file(tasks_dir, slug)

    if task_file is None:
        print(f"❌ Task file for '{args.task_name}' not found.")
        return

    text = task_file.read_text()
    status = _parse_task_field(text, "Status")

    if status.lower() != "completed":
        print(f"⚠️  {task_file} is currently '{status}' — only Completed tasks can be archived.")
        return

    archive_dir = tasks_dir / "archive"
    archive_dir.mkdir(exist_ok=True)
    
    task_id = _parse_task_field(text, "ID")
    dest_file = archive_dir / task_file.name
    task_file.rename(dest_file)
    _db_sync_task_file(dest_file)
    print(f"✅ Archived: {task_file.name} → {dest_file}")

    _index_update_status(task_id, archived=True)
    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task archived: {args.task_name} → {dest_file}", task_id=task_id)
    _db_log_event(task_id, "archived", actor=persona, details=args.task_name)


def cmd_handoff(args: argparse.Namespace) -> None:
    """Sign off on a task handshake row as a specific persona.
    
    Updates the ## Handshakes table to mark a persona as signed with a timestamp.
    """
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.task_name)
    task_file = _resolve_task_file(tasks_dir, slug)

    if task_file is None:
        print(f"❌ Task file for '{args.task_name}' not found.")
        return

    persona = args.persona
    message = getattr(args, "message", None) or ""
    text = task_file.read_text()
    lines = text.splitlines()

    # Find and update the handshakes table row for this persona
    updated = False
    new_lines: list[str] = []
    in_handshakes = False
    
    for line in lines:
        if line.strip().startswith("## Handshakes"):
            in_handshakes = True
            new_lines.append(line)
        elif in_handshakes and line.startswith("## "):
            # Left the handshakes section
            in_handshakes = False
            new_lines.append(line)
        elif in_handshakes and f"| @{persona} " in line:
            # Found the persona row — update it
            parts = [p.strip() for p in line.split("|")]
            # Format: | @persona | status | timestamp | summary |
            if len(parts) >= 5:
                parts[2] = "☑ signed"  # status column
                parts[3] = _now_iso()   # timestamp column
                parts[4] = message or "Signed off"  # summary column
                new_lines.append("|" + "|".join(f" {p} " for p in parts) + "|")
                updated = True
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    if not updated:
        print(f"❌ Could not find handshake row for @{persona} in {task_file}")
        return

    task_file.write_text("\n".join(new_lines))
    print(f"✅ Handoff signed: @{persona} → {task_file}")
    if message:
        print(f"   Message: {message}")

    _append_log(f"@{persona} | Handshake signed: {args.task_name}", task_id=_parse_task_field(text, "ID"))



def cmd_resume(args: argparse.Namespace) -> None:
    """Dump project context for a new AI session.

    Four verbosity levels to respect context-window limits:
      --nano    ≈ 200 tokens  — current in-progress task ID+title only
      --brief   ≈ 500 tokens  — project overview + active tasks only
      (default) ≈ 1500 tokens — above + recent log + decisions summary
      --full    ≈ 3000 tokens — everything including full decision log
      --budget N              — auto-select depth to hit a token ceiling
    """
    nano = getattr(args, "nano", False)
    brief = args.brief
    full = args.full

    # ── nano mode: current task ID + title only (~200 tokens) ────────
    if nano:
        tasks_dir = Path("docs/tasks")
        active_lines: list[str] = []
        if tasks_dir.exists():
            for tf in sorted(tasks_dir.glob("*.md")):
                text = tf.read_text()
                status = _parse_task_field(text, "Status").lower()
                if status == "in progress":
                    tid = _parse_task_field(text, "ID") or "—"
                    title = text.splitlines()[0].lstrip("# ").strip()
                    active_lines.append(f"[{tid}] {title}")
        if active_lines:
            print("Current task: " + "\n".join(active_lines))
        else:
            print("No active task. Run `keeli next` to pick one.")
        print(f"\n> Keeli v{SCHEMA_VERSION} | nano mode")
        word_count = sum(len(l.split()) for l in active_lines)
        print(f"\n📊 ~{int(word_count * 1.35)} tokens (nano mode)")
        return

    sections: list[str] = []

    # 1. Project overview (always included)
    project = Path("docs/project.md")
    if project.exists():
        content = project.read_text().strip()
        if brief and len(content) > 500:
            lines = content.splitlines()[:10]
            sections.append("## Project (truncated)\n" + "\n".join(lines) + "\n…")
        else:
            sections.append(content)

    # 2. Active tasks (always included)
    tasks_dir = Path("docs/tasks")
    if tasks_dir.exists():
        active: list[str] = []
        for tf in sorted(tasks_dir.glob("*.md")):
            text = tf.read_text()
            status = _parse_task_field(text, "Status")
            if status.lower() in ("in progress", "blocked", "backlog"):
                if brief:
                    active.append(f"- [{tf.stem}] {status}")
                else:
                    active.append(f"### {tf.stem} ({status})\n{text}")
        if active:
            sections.append("## Active Tasks\n" + "\n".join(active))
        else:
            sections.append("## Active Tasks\nNo active tasks found.")

    # 3. Recently completed tasks (always included — key for handshake)
    if tasks_dir.exists():
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        recent_done: list[str] = []
        for tf in sorted(tasks_dir.glob("*.md"), reverse=True):
            text = tf.read_text()
            status = _parse_task_field(text, "Status")
            if status.lower() == "completed":
                completed_ts = _parse_task_field(text, "Completed")
                if completed_ts and completed_ts[:10] >= cutoff:
                    recent_done.append(f"- [{tf.stem}] completed {completed_ts[:10]}")
        if recent_done:
            label = "Recently Completed (last 7 days)"
            if brief:
                sections.append(f"## {label}\n" + "\n".join(recent_done[:5]))
            else:
                sections.append(f"## {label}\n" + "\n".join(recent_done))
        else:
            sections.append("## Recently Completed (last 7 days)\nNone.")

    # 4. Recent log (skip in brief mode)
    if not brief:
        log_file = Path("docs/ai_log.md")
        tail_lines = 50 if full else 20
        tail = _tail(log_file, n=tail_lines)
        if tail.strip():
            sections.append(f"## Recent AI Log (last {tail_lines} lines)\n```\n{tail}\n```")

    # 5. Decisions (full only unless default)
    decision = Path("docs/decision.md")
    if decision.exists():
        dec_text = decision.read_text().strip()
        if full:
            sections.append(dec_text)
        elif not brief:
            # Default: show last 2 decisions (rough heuristic: split by ---)
            blocks = dec_text.split("\n---\n")
            recent = blocks[-3:] if len(blocks) > 3 else blocks
            sections.append("## Recent Decisions (summary)\n" + "\n---\n".join(recent))

    # 6. Schema version footer
    sections.append(f"\n> Keeli Framework v{SCHEMA_VERSION}")

    output = "\n\n---\n\n".join(sections)
    print(output)

    # Token estimate
    word_count = len(output.split())
    token_estimate = int(word_count * 1.3)  # rough word→token ratio
    mode_label = "brief" if brief else ("full" if full else "default")
    print(f"\n📊 ~{word_count} words / ~{token_estimate} tokens ({mode_label} mode)")


def cmd_status(args: argparse.Namespace) -> None:
    """Health-check: verify all expected files exist."""
    _refresh_state_from_markdown()
    print(f"Keeli Framework v{SCHEMA_VERSION} — Status Check\n")

    paths = [
        Path(".github/copilot-instructions.md"),
        Path("docs/project.md"),
        Path("docs/decision.md"),
        Path("docs/ai_log.md"),
        Path("docs/skills.md"),
        Path("docs/personas.md"),
        Path("docs/tasks"),
        Path("docs/requirements"),
        Path(_STATE_DB_FILENAME),
    ]

    all_ok = True
    for p in paths:
        if p.exists():
            print(f"  ✅ {p}")
        else:
            print(f"  ❌ {p}")
            all_ok = False

    # Count tasks by status
    db_path = _state_db_path()
    if db_path.exists():
        with contextlib.closing(_connect_state_db()) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM work_items WHERE archived = 0 GROUP BY status"
            ).fetchall()
        status_counts = {row["status"].lower(): row["count"] for row in rows if row["status"]}
        total = sum(status_counts.values())
        print(f"\n  🗄️  State DB: {_STATE_DB_FILENAME}")
        print(f"     Mode: sqlite")
        print(f"     Items: {total}")
    else:
        status_counts = {}

    tasks_dir = Path("docs/tasks")
    if tasks_dir.exists() and not status_counts:
        from collections import Counter
        status_counts: Counter = Counter()
        for tf in tasks_dir.glob("*.md"):
            if tf.name == ".gitkeep":
                continue
            text = tf.read_text()
            s = _parse_task_field(text, "Status").lower() or "unknown"
            status_counts[s] += 1
        total = sum(status_counts.values())
        print(f"\n  📋 Tasks ({total} total):")
        order = ["in progress", "blocked", "review", "backlog", "completed", "unknown"]
        icons = {"in progress": "🔵", "blocked": "🔴", "review": "🟡",
                 "backlog": "⬜", "completed": "✅", "unknown": "❓"}
        for s in order:
            if s in status_counts:
                print(f"     {icons.get(s, '❓')} {s.capitalize():<14} {status_counts[s]}")

    print("\n" + ("🟢 Healthy" if all_ok else "🔴 Incomplete — run `keeli init` to fix"))


def cmd_clear_log(args: argparse.Namespace) -> None:
    """Reset docs/ai_log.md to its default state."""
    log_file = Path("docs/ai_log.md")
    if log_file.exists():
        log_file.write_text(AI_LOG_MD)
        print("✅ Cleared docs/ai_log.md")
    else:
        print("⚠️  docs/ai_log.md not found. Run `keeli init` first.")


# ── TF-IDF Context Analysis ──────────────────────────────────────────────────

def _tokenize_analyze(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) > 1]


def _build_corpus() -> list[tuple[str, str, dict]]:
    """Return (label, text, meta) pairs from skills.md and decision.md ADRs."""
    corpus: list[tuple[str, str, dict]] = []
    for t, n, p, c in _read_skills():
        corpus.append((f"skill:{n}", f"{t} {n} {c}", {"type": "skill", "name": n, "persona": p, "constraint": c}))
    dec_path = Path("docs/decision.md")
    if dec_path.exists():
        current_title: str | None = None
        current_body: list[str] = []
        for line in dec_path.read_text().splitlines():
            if line.startswith("### "):
                if current_title and current_body:
                    corpus.append((
                        current_title,
                        current_title + " " + " ".join(current_body),
                        {"type": "adr", "ref": current_title},
                    ))
                current_title = line.lstrip("# ").strip()
                current_body = []
            elif current_title:
                current_body.append(line)
        if current_title and current_body:
            corpus.append((
                current_title,
                current_title + " " + " ".join(current_body),
                {"type": "adr", "ref": current_title},
            ))
    return corpus


def _cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    dot = sum(a.get(k, 0.0) * v for k, v in b.items())
    mag_a = _math.sqrt(sum(v * v for v in a.values()))
    mag_b = _math.sqrt(sum(v * v for v in b.values()))
    return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0


def _tfidf_scores_pure(query: str, corpus: list[tuple[str, str, dict]]) -> list[tuple[float, dict]]:
    """Pure-Python TF-IDF cosine similarity — zero extra dependencies."""
    all_docs = [text for _, text, _ in corpus] + [query]
    tokenized = [_tokenize_analyze(d) for d in all_docs]
    N = len(all_docs)
    df: dict[str, int] = {}
    for tokens in tokenized:
        for term in set(tokens):
            df[term] = df.get(term, 0) + 1
    idf = {term: _math.log((N + 1) / (cnt + 1)) + 1.0 for term, cnt in df.items()}

    def vectorize(tokens: list[str]) -> dict[str, float]:
        tf: dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0.0) + 1.0
        total = len(tokens) or 1
        return {t: (c / total) * idf.get(t, 1.0) for t, c in tf.items()}

    vecs = [vectorize(t) for t in tokenized]
    query_vec = vecs[-1]
    results = [(_cosine_sim(vecs[i], query_vec), meta) for i, (_, _, meta) in enumerate(corpus)]
    results.sort(key=lambda x: x[0], reverse=True)
    return results


def _tfidf_scores_sklearn(query: str, corpus: list[tuple[str, str, dict]]) -> list[tuple[float, dict]]:
    """sklearn TfidfVectorizer + cosine similarity — richer IDF, bigrams."""
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
    from sklearn.metrics.pairwise import cosine_similarity as _cos  # type: ignore

    texts = [text for _, text, _ in corpus] + [query]
    mat = TfidfVectorizer(stop_words="english", ngram_range=(1, 2)).fit_transform(texts)
    scores = _cos(mat[-1], mat[:-1]).flatten()
    results = [(float(scores[i]), meta) for i, (_, _, meta) in enumerate(corpus)]
    results.sort(key=lambda x: x[0], reverse=True)
    return results


_SKLEARN_AVAILABLE: bool | None = None


def _sklearn_available() -> bool:
    global _SKLEARN_AVAILABLE
    if _SKLEARN_AVAILABLE is not None:
        return _SKLEARN_AVAILABLE
    try:
        import io, sys as _sys
        _old_err = _sys.stderr
        _sys.stderr = io.StringIO()  # suppress numpy/scipy compat noise
        try:
            import sklearn  # noqa: F401
            from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: F401
            _SKLEARN_AVAILABLE = True
        finally:
            _sys.stderr = _old_err
    except Exception:
        _SKLEARN_AVAILABLE = False
    return _SKLEARN_AVAILABLE


def _score_task(task_text: str, use_sklearn: bool = False) -> dict:
    """Score task text against project corpus; return top skills, ADRs, persona."""
    corpus = _build_corpus()
    if not corpus:
        return {"skills": [], "adrs": [], "persona": None}

    query_lines: list[str] = []
    # Always lead with the task title (strips the "# Task:" prefix)
    for line in task_text.splitlines()[:3]:
        stripped = line.strip()
        if stripped.startswith("# Task:"):
            query_lines.append(stripped[7:].strip())
            break
        if stripped.startswith("# "):
            query_lines.append(stripped[2:].strip())
            break
    for line in task_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("**") or stripped.startswith("#"):
            continue
        stripped = re.sub(r"^- \[[ x]\] ", "", stripped)
        query_lines.append(stripped)
    query = " ".join(query_lines[:30])

    if use_sklearn:
        if not _sklearn_available():
            raise SystemExit("\u274c scikit-learn not installed. Run: pip install scikit-learn")
        engine_fn = _tfidf_scores_sklearn
    elif _sklearn_available():
        engine_fn = _tfidf_scores_sklearn
    else:
        engine_fn = _tfidf_scores_pure

    try:
        scored = engine_fn(query, corpus)
    except Exception:
        scored = _tfidf_scores_pure(query, corpus)

    top_skills = [(s, m) for s, m in scored if m["type"] == "skill" and s > 0][:3]
    top_adrs   = [(s, m) for s, m in scored if m["type"] == "adr"   and s > 0.01][:2]

    task_lower = task_text.lower()
    persona: str | None = None
    if any(k in task_lower for k in ("secure", "auth", "injection", "vulnerab")):
        persona = "security"
    elif any(k in task_lower for k in ("document", "readme", "content", "blog")):
        persona = "author"
    elif any(k in task_lower for k in ("design", "architect", "system", "interface", "epic")):
        persona = "architect"
    elif any(k in task_lower for k in ("implement", "build", "add", "fix", "test", "write")):
        persona = "developer"

    return {"skills": top_skills, "adrs": top_adrs, "persona": persona}


_HINTS_MARKER_START = "<!-- KEELI_HINTS_START -->"
_HINTS_MARKER_END   = "<!-- KEELI_HINTS_END -->"


def _format_hints_block(hints: dict) -> str:
    """Render hints dict as a Markdown block wrapped in KEELI_HINTS markers."""
    lines: list[str] = [
        "",
        "---",
        "",
        "## AI Context Hints  (auto-generated \u2014 do not edit manually)",
        "",
        _HINTS_MARKER_START,
    ]
    if hints["skills"]:
        lines.append("### Relevant Skills")
        for _s, meta in hints["skills"]:
            c_text = f": {meta['constraint']}" if meta.get("constraint") else ""
            p_tag  = f" (@{meta['persona']})"  if meta.get("persona")    else ""
            lines.append(f'- **`{meta["name"]}`**{p_tag}{c_text}')
    else:
        lines.append("_No skill matches \u2014 run `keeli stack` to populate skills._")
    lines.append("")
    if hints["adrs"]:
        lines.append("### Relevant Decisions")
        for _s, meta in hints["adrs"]:
            lines.append(f"- {meta['ref']}")
    else:
        lines.append("_No ADR matches found._")
    if hints["persona"]:
        lines.append("")
        lines.append("### Suggested Persona")
        lines.append(f"- @{hints['persona']}")
    lines.append(_HINTS_MARKER_END)
    return "\n".join(lines)



# ── Discovery commands ────────────────────────────────────────────────────────

def _print_index_results(items: list[dict], label: str) -> None:
    """Pretty-print a list of index items."""
    tasks_dir = Path("docs/tasks")
    print(f"\n🔍 {label} — {len(items)} result(s)\n")
    print(f"  {'ID':<10} {'Type':<6} {'Pri':<4} {'Status':<14} Title")
    print("  " + "-" * 70)
    for item in sorted(items, key=lambda i: i.get("created", ""), reverse=True):
        archived = " [archived]" if item.get("archived") else ""
        epic_tag = f" epic={item['epic']}" if item.get("epic") else ""
        print(
            f"  {item.get('id', '?'):<10} {item.get('type', ''):<6} "
            f"{item.get('priority', '?'):<4} {item.get('status', '?'):<14} "
            f"{item.get('title', '')}{archived}{epic_tag}"
        )
        slug = item.get("slug", "")
        arch = tasks_dir / "archive" / f"{slug}.md"
        live = tasks_dir / f"{slug}.md"
        if arch.exists():
            print(f"  {'':10} → {arch}")
        elif live.exists():
            print(f"  {'':10} → {live}")


def cmd_find(args: argparse.Namespace) -> None:
    """Search the index by exact ID or keyword across title/slug.

    Examples:
        keeli find T-0003          # exact ID lookup
        keeli find "auth login"    # keyword search
    """
    _refresh_state_from_markdown()
    query = args.query.strip()
    query_upper = query.upper()
    status_filter_raw = getattr(args, "status", None)
    status_filter = _canonical_status(status_filter_raw) if status_filter_raw else None

    db_path = _state_db_path()
    if not db_path.exists():
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope(
                "find",
                False,
                {"query": query, "results": []},
                error="State DB not found. Run `keeli init` first.",
            ), indent=2))
        else:
            print("❌ State DB not found. Run `keeli init` first.")
        return

    with contextlib.closing(_connect_state_db()) as conn:
        def _to_item(row: sqlite3.Row) -> dict[str, object]:
            return {
                "id": row["item_id"],
                "type": row["item_type"],
                "title": row["title"],
                "slug": row["slug"],
                "status": row["status"],
                "priority": row["priority"],
                "epic": row["epic_slug"],
                "story": row["story_slug"],
                "created": row["created_at"],
                "completed": row["completed_at"],
                "archived": bool(row["archived"]),
            }

        # Exact ID match first (e.g. T-0001, BUG-0003)
        id_rows = conn.execute(
            """
            SELECT item_id, item_type, title, slug, status, priority, epic_slug, story_slug,
                   created_at, completed_at, archived
            FROM work_items
            WHERE upper(item_id) = ?
            """,
            (query_upper,),
        ).fetchall()

    id_matches = [_to_item(row) for row in id_rows]
    if status_filter:
        id_matches = [i for i in id_matches if _canonical_status(str(i.get("status", ""))) == status_filter]

    if id_matches:
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope(
                "find",
                True,
                {"query": query, "mode": "id", "results": id_matches},
            ), indent=2))
        else:
            _print_index_results(id_matches, label=f"ID: {query_upper}")
        return

    # Keyword match across title + slug (+ item ID), excluding archived by default.
    q_like = f"%{query.lower()}%"
    with contextlib.closing(_connect_state_db()) as conn:
        where = [
            "archived = 0",
            "(lower(title) LIKE ? OR lower(slug) LIKE ? OR lower(item_id) LIKE ?)",
        ]
        params: list[str] = [q_like, q_like, q_like]
        if status_filter:
            where.append("lower(status) = lower(?)")
            params.append(status_filter)

        kw_rows = conn.execute(
            f"""
            SELECT item_id, item_type, title, slug, status, priority, epic_slug, story_slug,
                   created_at, completed_at, archived
            FROM work_items
            WHERE {' AND '.join(where)}
            ORDER BY updated_at DESC, created_at DESC
            """,
            params,
        ).fetchall()

    kw_matches = [_to_item(row) for row in kw_rows]

    if getattr(args, "json", False):
        print(json.dumps(_json_envelope(
            "find",
            True,
            {"query": query, "mode": "keyword", "results": kw_matches},
        ), indent=2))
        return

    if kw_matches:
        _print_index_results(kw_matches, label=f"Keyword: '{query}'")
    else:
        print(f"No results for '{query}'.")


def cmd_history(args: argparse.Namespace) -> None:
    """Show all ai_log entries for a specific task ID or title keyword.

    Examples:
        keeli history T-0003
        keeli history "auth"
    """
    log_file = Path("docs/ai_log.md")
    if not log_file.exists():
        if getattr(args, "json", False):
            print(json.dumps(_json_envelope("history", False, {"query": args.task_id.strip(), "entries": [], "count": 0}, error="docs/ai_log.md not found."), indent=2))
        else:
            print("❌ docs/ai_log.md not found.")
        return

    query = args.task_id.strip()
    target = query.upper()
    lines = log_file.read_text().splitlines()
    matches = [line for line in lines if target in line.upper()]

    if getattr(args, "json", False):
        print(json.dumps(_json_envelope("history", True, {"query": query, "entries": matches, "count": len(matches)}), indent=2))
        return

    if not matches:
        print(f"No log entries found for '{target}'.")
        return

    print(f"\n📜 History for {target} — {len(matches)} entries\n")
    for line in matches:
        print(f"  {line}")
    print()


def cmd_doctor(args: argparse.Namespace) -> None:
    """Diagnose state drift and active-task anomalies in a single command."""
    _refresh_state_from_markdown()
    db_path = _state_db_path()
    if not db_path.exists():
        payload = _json_envelope("doctor", False, {"checks": []}, error="State DB not found. Run `keeli init` first.")
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            print("❌ State DB not found. Run `keeli init` first.")
        return

    with contextlib.closing(_connect_state_db()) as conn:
        in_progress_rows = conn.execute(
            """
            SELECT item_id, slug, item_type, status, story_slug, epic_slug
            FROM work_items
            WHERE archived = 0 AND status = 'In Progress' AND item_type IN ('task', 'bug', 'feat')
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
        active_rows = conn.execute(
            """
            SELECT item_id, slug, item_type, status
            FROM work_items
            WHERE archived = 0 AND status IN ('In Progress', 'Review', 'Blocked') AND item_type IN ('task', 'bug', 'feat')
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
        stale_rows = conn.execute(
            """
            SELECT item_id, slug, source_path
            FROM work_items
            WHERE archived = 0 AND source_path IS NOT NULL
            """
        ).fetchall()

    stale_sources = [
        {"item_id": row["item_id"], "slug": row["slug"], "source_path": row["source_path"]}
        for row in stale_rows
        if row["source_path"] and not Path(str(row["source_path"])).exists()
    ]

    index = _load_index() if _INDEX_PATH.exists() else {"items": []}
    index_by_id = {str(item.get("id")): item for item in index.get("items", [])}
    with contextlib.closing(_connect_state_db()) as conn:
        db_rows = conn.execute("SELECT item_id, status, archived FROM work_items").fetchall()
    db_by_id = {str(row["item_id"]): row for row in db_rows}

    mismatches: list[dict[str, object]] = []
    for item_id, db_row in db_by_id.items():
        idx = index_by_id.get(item_id)
        if not idx:
            continue
        idx_status = _canonical_status(str(idx.get("status", ""))) or str(idx.get("status", ""))
        db_status = _canonical_status(str(db_row["status"] or "")) or str(db_row["status"] or "")
        idx_archived = bool(idx.get("archived"))
        db_archived = bool(db_row["archived"])
        if idx_status != db_status or idx_archived != db_archived:
            mismatches.append(
                {
                    "item_id": item_id,
                    "index_status": idx_status,
                    "db_status": db_status,
                    "index_archived": idx_archived,
                    "db_archived": db_archived,
                }
            )

    tasks_dir = Path("docs/tasks")
    story_drift: list[dict[str, object]] = []
    if tasks_dir.exists():
        for story_path in sorted(tasks_dir.glob("story-*.md")):
            story_text = story_path.read_text()
            story_slug = story_path.stem[6:]
            current_status = _parse_task_field(story_text, "Status") or "Backlog"
            child_statuses: list[str] = []
            for base in (tasks_dir, tasks_dir / "archive"):
                if not base.exists():
                    continue
                for candidate in sorted(base.glob("*.md")):
                    if candidate.name == ".gitkeep" or candidate.name.startswith(("story-", "epic-")):
                        continue
                    child_text = candidate.read_text()
                    child_story = _normalize_story_slug(_parse_task_field(child_text, "Story"))
                    if child_story == story_slug:
                        child_statuses.append(_parse_task_field(child_text, "Status") or "Backlog")
            target_status = _story_target_status_from_children(child_statuses)
            if target_status and target_status.lower() != current_status.lower():
                story_drift.append(
                    {
                        "story_slug": story_slug,
                        "current": current_status,
                        "expected": target_status,
                        "child_count": len(child_statuses),
                    }
                )

    checks = {
        "in_progress_count": len(in_progress_rows),
        "active_leaf_count": len(active_rows),
        "index_db_mismatch_count": len(mismatches),
        "stale_source_count": len(stale_sources),
        "story_rollup_drift_count": len(story_drift),
        "in_progress_items": [dict(row) for row in in_progress_rows],
        "mismatches": mismatches,
        "stale_sources": stale_sources,
        "story_rollup_drift": story_drift,
    }

    if getattr(args, "json", False):
        print(json.dumps(_json_envelope("doctor", True, checks), indent=2))
        return

    print("Keeli Doctor Report")
    print("-------------------")
    print(f"In Progress leaf tasks: {checks['in_progress_count']}")
    print(f"Active leaf tasks (In Progress/Review/Blocked): {checks['active_leaf_count']}")
    print(f"Index <-> DB mismatches: {checks['index_db_mismatch_count']}")
    print(f"Stale source rows: {checks['stale_source_count']}")
    print(f"Story rollup drift rows: {checks['story_rollup_drift_count']}")

    if checks["in_progress_count"] > 1:
        print("\n⚠️  Multiple In Progress leaf tasks detected (potential hung-thread symptom):")
        for row in checks["in_progress_items"]:
            print(f"   • {row['item_id']} {row['slug']} [{row['status']}]")

    if checks["index_db_mismatch_count"]:
        print("\n⚠️  Index/DB status drift detected:")
        for row in checks["mismatches"][:10]:
            print(
                f"   • {row['item_id']}: index={row['index_status']} archived={row['index_archived']} "
                f"db={row['db_status']} archived={row['db_archived']}"
            )

    if checks["story_rollup_drift_count"]:
        print("\n⚠️  Story rollup drift detected:")
        for row in checks["story_rollup_drift"][:10]:
            print(
                f"   • story-{row['story_slug']}: current={row['current']} expected={row['expected']} "
                f"(children={row['child_count']})"
            )

    if not any(
        checks[key] for key in ("index_db_mismatch_count", "stale_source_count", "story_rollup_drift_count")
    ) and checks["in_progress_count"] <= 1:
        print("\n✅ No obvious drift or hung-thread indicators detected.")


def cmd_digest(args: argparse.Namespace) -> None:
    """Machine-optimised, token-budgeted context dump for LLM session starts.

    Fills sections greedily in priority order until the token budget is reached:
      1. Active / In-Progress tasks (always included)
      2. Project overview (first 5 lines)
      3. Backlog summary from index (top 10 by priority)
      4. Recently completed items from index (last 5)
      5. Recent log lines

    Use --budget to tune the output size for your model's context window.
    """
    budget: int = getattr(args, "budget", 2000)
    sections: list[str] = []
    used = 0

    def _tokens(text: str) -> int:
        return int(len(text.split()) * 1.35)

    def _fits(text: str) -> bool:
        return used + _tokens(text) <= budget

    # 1. Active tasks (in-progress / blocked) — always included
    tasks_dir = Path("docs/tasks")
    if tasks_dir.exists():
        active_lines: list[str] = []
        for tf in sorted(tasks_dir.glob("*.md")):
            if tf.name == ".gitkeep":
                continue
            text = tf.read_text()
            status = _parse_task_field(text, "Status").lower()
            if status in ("in progress", "blocked"):
                tid = _parse_task_field(text, "ID") or "—"
                title = text.splitlines()[0].lstrip("# ").strip()
                active_lines.append(f"- [{tid}] {title} ({status})")
        if active_lines:
            sec = "## Active\n" + "\n".join(active_lines)
            sections.append(sec)
            used += _tokens(sec)

    # 2. Project overview (first 5 lines)
    project = Path("docs/project.md")
    if project.exists():
        first5 = "\n".join(project.read_text().splitlines()[:5])
        sec = f"## Project\n{first5}"
        if _fits(sec):
            sections.append(sec)
            used += _tokens(sec)

    # 3. Backlog from index (top 10 by priority then age)
    if _INDEX_PATH.exists():
        index = _load_index()
        backlog = [
            i for i in index.get("items", [])
            if i.get("status", "").lower() == "backlog" and not i.get("archived")
        ]
        backlog.sort(key=lambda i: (i.get("priority", "P2"), i.get("created", "")))
        lines = [f"- [{i['id']}] [{i['priority']}] {i['title']}" for i in backlog[:10]]
        if lines:
            sec = "## Backlog (top 10)\n" + "\n".join(lines)
            if _fits(sec):
                sections.append(sec)
                used += _tokens(sec)

    # 4. Recently completed from index (last 5 by completion date)
    if _INDEX_PATH.exists():
        index = _load_index()
        done = [
            i for i in index.get("items", [])
            if i.get("status", "").lower() == "completed"
        ]
        done.sort(key=lambda i: i.get("completed") or "", reverse=True)
        lines = [
            f"- [{i['id']}] {i['title']} (done {(i.get('completed') or '')[:10]})"
            for i in done[:5]
        ]
        if lines:
            sec = "## Recently Completed\n" + "\n".join(lines)
            if _fits(sec):
                sections.append(sec)
                used += _tokens(sec)

    # 5. Recent log (if budget allows)
    log_file = Path("docs/ai_log.md")
    if log_file.exists():
        tail = _tail(log_file, n=10)
        sec = f"## Recent Log\n```\n{tail}\n```"
        if _fits(sec):
            sections.append(sec)
            used += _tokens(sec)

    output = "\n\n".join(sections) if sections else "No Keeli context found."
    if getattr(args, "json", False):
        print(json.dumps(_json_envelope("digest", True, {"context": output, "used_tokens": used, "budget": budget}), indent=2))
        return
    print(output)
    print(f"\n📊 ~{used} tokens (budget: {budget})")


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze a task and inject AI context hints (skill/ADR relevance)."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("\u274c docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = args.slug
    candidates = sorted(tasks_dir.glob(f"{slug}*.md"))
    if not candidates:
        print(f"\u274c No task matching '{slug}' in docs/tasks/")
        return
    task_path = candidates[0]
    task_text = task_path.read_text()

    use_sklearn = getattr(args, "use_sklearn", False)
    dry_run     = getattr(args, "dry_run", False)
    hints       = _score_task(task_text, use_sklearn=use_sklearn)
    hints_block = _format_hints_block(hints)
    engine      = "sklearn" if (use_sklearn or _sklearn_available()) else "pure Python"

    if dry_run:
        print(f"\U0001f50d Analysis (dry-run): {task_path.name}  [engine: {engine}]\n")
        print(hints_block)
        return

    if _HINTS_MARKER_START in task_text:
        pat = r"\n---\n\n## AI Context Hints.*?" + re.escape(_HINTS_MARKER_END)
        new_text = re.sub(pat, hints_block, task_text, flags=re.DOTALL)
    else:
        new_text = task_text.rstrip() + "\n" + hints_block + "\n"

    task_path.write_text(new_text)
    print(f"\u2705 Hints injected \u2192 {task_path}  [engine: {engine}]")
    summary = f"   Skills: {len(hints['skills'])}  ADRs: {len(hints['adrs'])}"
    if hints["persona"]:
        summary += f"  Persona: @{hints['persona']}"
    print(summary)


def cmd_chain(args: argparse.Namespace) -> None:
    """Execute a sequential pipeline of keeli commands (tool chaining).

    Inline usage::

        keeli chain "start:My Task" "analyze:auto" "progress:auto"

    Named chain::

        keeli chain run new-task --var title="My Task"

    The keyword ``auto`` in any step argument is replaced by the task slug
    produced by the previous step.
    """
    steps_raw: list[str] = getattr(args, "steps", []) or []
    dry_run:   bool      = getattr(args, "dry_run", False)
    vars_raw:  list[str] = getattr(args, "var", None) or []

    def _parse_vars(raw: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for item in raw:
            if "=" in item:
                k, v = item.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    if not steps_raw:
        print("Usage:")
        print("  keeli chain \"start:My Task\" \"analyze:auto\" \"progress:auto\"  # inline")
        print("  keeli chain list                                                  # show chains")
        print("  keeli chain run <name> [--var key=value ...]                     # named chain")
        print("  Add --dry-run to preview without executing.\n")
        print("Inline step format:  cmd:arg   (use 'auto' = slug from previous step)")
        return

    first = steps_raw[0].strip()

    # ── list ──────────────────────────────────────────────────────────────────
    if first == "list":
        chain_dir = Path(".keeli/chains")
        print("\n\u26d3  Built-in chains:\n")
        print(f"  {'Name':<22} Description")
        print("  " + "-" * 66)
        for name, defn in BUILTIN_CHAINS.items():
            steps_preview = " \u2192 ".join(s["cmd"] for s in defn["steps"])
            print(f"  {name:<22} {defn['description']}")
            print(f"  {'':22} Steps: {steps_preview}")
        if chain_dir.exists():
            project_chains = sorted(
                list(chain_dir.glob("*.yaml")) + list(chain_dir.glob("*.yml"))
            )
            if project_chains:
                print(f"\n  Project chains ({chain_dir}):\n")
                for cf in project_chains:
                    print(f"  {cf.stem}")
        print()
        return

    # ── run <name> [--var ...] ─────────────────────────────────────────────────
    if first == "run":
        chain_name = steps_raw[1] if len(steps_raw) > 1 else None
        if not chain_name:
            print("\u274c Usage: keeli chain run <chain-name>")
            print(f"   Available: {', '.join(BUILTIN_CHAINS)}")
            return
        vars_ = _parse_vars(vars_raw)
        # Built-in chain
        if chain_name in BUILTIN_CHAINS:
            defn = BUILTIN_CHAINS[chain_name]
            step_strs = [
                f"{s['cmd']}:{' '.join(s['args'])}" if s["args"] else s["cmd"]
                for s in defn["steps"]
            ]
            for k, v in vars_.items():
                step_strs = [s.replace(f"{{{k}}}", v) for s in step_strs]
            _run_chain_inline(step_strs, dry_run=dry_run, vars_=vars_)
            return
        # Project chain file
        for ext in (".yaml", ".yml"):
            chain_file = Path(f".keeli/chains/{chain_name}{ext}")
            if chain_file.exists():
                _run_chain_from_file(chain_file, vars_=vars_, dry_run=dry_run)
                return
        print(f"\u274c Unknown chain '{chain_name}'. Run `keeli chain list` to see available chains.")
        return

    # ── inline pipeline ────────────────────────────────────────────────────────
    vars_ = _parse_vars(vars_raw)
    _run_chain_inline(steps_raw, dry_run=dry_run, vars_=vars_)


def cmd_update(args: argparse.Namespace) -> None:
    """Update copilot-instructions.md to the latest template version.

    Preserves user files (project.md, decision.md, tasks, log).
    Only regenerates the instruction file and .gitignore rules.
    """
    instructions = Path(".github/copilot-instructions.md")
    if not instructions.exists():
        print("❌ .github/copilot-instructions.md not found. Run `keeli init` first.")
        return

    old_text = instructions.read_text()
    # Extract old version if possible
    old_version = "unknown"
    for line in old_text.splitlines():
        if "Keeli Framework v" in line:
            import re as _re
            m = _re.search(r"v(\d+\.\d+\.\d+)", line)
            if m:
                old_version = m.group(1)
            break

    if old_version == SCHEMA_VERSION and not args.force:
        print(f"✅ Already at v{SCHEMA_VERSION}. Use --force to regenerate.")
        return

    instructions.write_text(COPILOT_INSTRUCTIONS)
    print(f"✅ Updated copilot-instructions.md: v{old_version} → v{SCHEMA_VERSION}")

    # Migrate skills.md to 4-column format and re-inject into instructions
    existing_skills = _read_skills()
    if existing_skills:
        _write_skills(existing_skills)  # rewrites skills.md in current 4-column format
        print(f"   → Migrated skills.md to 4-column format ({len(existing_skills)} skill(s))")
    else:
        _inject_skills_into_instructions(existing_skills)

    # Ensure .gitkeep files exist
    for d in [Path("docs/tasks"), Path("docs/requirements")]:
        d.mkdir(parents=True, exist_ok=True)
        gitkeep = d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    _append_log(f"@architect | Schema updated: v{old_version} → v{SCHEMA_VERSION}")
    print(f"📝 User files (project.md, decision.md, tasks, log) preserved.")


# ── Custom Prompts ─────────────────────────────────────────────────────────

def _load_all_prompts() -> dict:
    """Load all custom prompts from docs/prompts/ and .keeli/prompts/.
    
    Returns a dict: {slug: {"path": Path, "metadata": dict, "body": str}}
    """
    prompts = {}
    
    # Load from both user-facing and internal directories
    for base_dir in [Path("docs/prompts"), Path(".keeli/prompts")]:
        if not base_dir.exists():
            continue
        
        for md_file in base_dir.glob("*.md"):
            slug = md_file.stem
            content = md_file.read_text()
            metadata, body = _parse_prompt_metadata(content)
            
            prompts[slug] = {
                "path": md_file,
                "metadata": metadata,
                "body": body,
            }
    
    return prompts


def _parse_prompt_metadata(content: str) -> tuple[dict, str]:
    """Extract YAML-like frontmatter from a prompt file.
    
    Expected format:
    ```
    ---
    persona: architect
    applies_to: all
    priority: high
    ---
    Prompt body here...
    ```
    
    Returns: (metadata_dict, body_str)
    """
    lines = content.strip().split("\n")
    
    # If no frontmatter, return empty metadata
    if not lines or lines[0] != "---":
        return {}, content
    
    # Find closing ---
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line == "---":
            end_idx = i
            break
    
    if end_idx is None:
        return {}, content
    
    metadata = {}
    for line in lines[1:end_idx]:
        if ":" in line:
            key, val = line.split(":", 1)
            metadata[key.strip()] = val.strip()
    
    body = "\n".join(lines[end_idx + 1:]).strip()
    return metadata, body


def _filter_prompts_by_persona(prompts: dict, persona: str) -> dict:
    """Filter prompts applicable to a specific persona."""
    filtered = {}
    for slug, data in prompts.items():
        meta = data.get("metadata", {})
        prompt_persona = meta.get("persona", "").lower()
        applies_to = meta.get("applies_to", "all").lower()
        
        # Include if: persona matches OR applies_to is "all"
        if prompt_persona == persona.lower() or applies_to == "all":
            filtered[slug] = data
    
    return filtered


def cmd_prompt(args: argparse.Namespace) -> None:
    """Manage custom prompts for the project."""
    action = getattr(args, "prompt_action", None)
    
    if action == "add":
        cmd_prompt_add(args)
    elif action == "apply":
        cmd_prompt_apply(args)
    elif action == "list":
        cmd_prompt_list(args)
    elif action == "show":
        cmd_prompt_show(args)
    elif action == "remove":
        cmd_prompt_remove(args)
    else:
        print("Usage: keeli prompt {add|apply|list|show|remove}")


def _parse_prompt_vars(raw_vars: list[str] | None) -> dict[str, str]:
    """Parse repeated --var KEY=VALUE flags into a dict."""
    out: dict[str, str] = {}
    for pair in raw_vars or []:
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        k = k.strip()
        if not k:
            continue
        out[k] = v
    return out


def _render_prompt_template(body: str, variables: dict[str, str]) -> str:
    """Render a prompt body by substituting {{key}} placeholders."""
    rendered = body
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def cmd_prompt_apply(args: argparse.Namespace) -> None:
    """Render a custom prompt template with variables and optionally write output."""
    slug = args.slug
    prompts = _load_all_prompts()

    if slug not in prompts:
        print(f"❌ Prompt '{slug}' not found.")
        return

    variables = _parse_prompt_vars(getattr(args, "vars", None))
    body = prompts[slug]["body"]
    rendered = _render_prompt_template(body, variables)

    output_path = getattr(args, "output", None)
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered)
        print(f"✅ Applied prompt '{slug}' → {path}")
        _append_log(f"@developer | Prompt applied: {slug} → {path}")
        return

    print(rendered)


def cmd_prompt_add(args: argparse.Namespace) -> None:
    """Add a custom prompt from a file.
    
    Usage: keeli prompt add SLUG --file ./my-prompt.md
                          [--persona PERSONA] [--applies-to APPLIES_TO]
                          [--priority PRIORITY] [--force]
    """
    slug = args.slug
    file_path = Path(args.file)
    
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return
    
    # Determine destination
    dest_dir = Path("docs/prompts")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{slug}.md"
    
    if dest_path.exists() and not args.force:
        print(f"❌ Prompt '{slug}' already exists. Use --force to overwrite.")
        return
    
    # Read source content
    content = file_path.read_text()
    
    # If not already frontmatter'd, add defaults
    if not content.strip().startswith("---"):
        persona = (getattr(args, "persona", "") or "").lower() or "developer"
        applies_to = (getattr(args, "applies_to", "") or "").lower() or "all"
        priority = (getattr(args, "priority", "") or "").lower() or "medium"
        
        frontmatter = f"""---
persona: {persona}
applies_to: {applies_to}
priority: {priority}
created: {_now_iso()}
---

{content}"""
        content = frontmatter
    
    dest_path.write_text(content)
    print(f"✅ Added prompt '{slug}' to {dest_path}")
    _append_log(f"@developer | Prompt added: {slug}")


def cmd_prompt_list(args: argparse.Namespace) -> None:
    """List all custom prompts with metadata."""
    prompts = _load_all_prompts()
    
    if not prompts:
        print("No custom prompts registered yet.")
        return
    
    print(f"\nFound {len(prompts)} custom prompt(s):\n")
    for slug, data in sorted(prompts.items()):
        meta = data["metadata"]
        persona = meta.get("persona", "?")
        applies_to = meta.get("applies_to", "?")
        priority = meta.get("priority", "?")
        created = meta.get("created", "?")
        location = "user" if "docs/prompts" in str(data["path"]) else "internal"
        
        print(f"  • {slug}")
        print(f"    Persona: {persona} | Applies: {applies_to} | Priority: {priority}")
        print(f"    Created: {created} | Location: {location}")
        print()


def cmd_prompt_show(args: argparse.Namespace) -> None:
    """Show the full content of a custom prompt."""
    slug = args.slug
    prompts = _load_all_prompts()
    
    if slug not in prompts:
        print(f"❌ Prompt '{slug}' not found.")
        return
    
    data = prompts[slug]
    meta = data["metadata"]
    body = data["body"]
    
    print(f"\n{'='*60}")
    print(f"Prompt: {slug}")
    print(f"{'='*60}")
    print(f"Persona:    {meta.get('persona', '?')}")
    print(f"Applies to: {meta.get('applies_to', '?')}")
    print(f"Priority:   {meta.get('priority', '?')}")
    print(f"Created:    {meta.get('created', '?')}")
    print(f"Location:   {data['path']}")
    print(f"{'='*60}\n")
    print(body)
    print(f"\n{'='*60}\n")


def cmd_prompt_remove(args: argparse.Namespace) -> None:
    """Remove a custom prompt."""
    slug = args.slug
    prompts = _load_all_prompts()
    
    if slug not in prompts:
        print(f"❌ Prompt '{slug}' not found.")
        return
    
    # Only allow removing from docs/prompts (user-facing)
    path = prompts[slug]["path"]
    if "docs/prompts" not in str(path):
        print(f"❌ Cannot remove internal prompt. Location: {path}")
        return
    
    if not args.force:
        response = input(f"Remove '{slug}'? (yes/no): ").strip().lower()
        if response != "yes":
            print("Cancelled.")
            return
    
    path.unlink()
    print(f"✅ Removed prompt '{slug}'")
    _append_log(f"@developer | Prompt removed: {slug}")


# ── Argument parser ────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="keeli",
        description="Keeli CLI — Enforce a Five-Persona Architecture for AI Agents.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {SCHEMA_VERSION}"
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = sub.add_parser("init", help="Scaffold the Keeli framework.")
    p_init.add_argument("-f", "--force", action="store_true", help="Overwrite existing files.")
    p_init.add_argument(
        "--ai",
        action="append",
        choices=["claude", "gemini", "codex"],
        help="Generate setup for additional AI flavor (can specify multiple times). Default creates .github/copilot-instructions.md.",
    )

    personas = _load_personas()

    # start
    p_start = sub.add_parser("start", help="Create a new task in docs/tasks/.")
    p_start.add_argument("task_name", help="Human-readable task title.")
    p_start.add_argument("-c", "--context", help="Path to a requirements or context file to link.")
    p_start.add_argument("-o", "--objective", help="Rich objective/requirements text (supports @file for file input).")
    p_start.add_argument("-p", "--priority", choices=["P0", "P1", "P2"], default=None, help="Task priority: P0 (critical), P1 (default), P2 (low). Prompted if omitted.")
    p_start.add_argument("-d", "--depends-on", help="Comma-separated list of task slugs this task depends on.")
    p_start.add_argument("-e", "--epic", help="Associate this task with an epic slug.")
    p_start.add_argument("--story", help="Associate this task with a story slug.")
    p_start.add_argument("-k", "--keeli", choices=personas, default="architect", metavar="PERSONA", help=f"Persona to attribute task creation to ({'/'.join(personas)}). Default: architect.")
    p_start.add_argument("-f", "--force", action="store_true", help="Overwrite an existing task file.")

    # complete
    p_complete = sub.add_parser("complete", help="Mark a task as completed and show next task.")
    p_complete.add_argument("task_name", help="Task title or slug to mark as completed.")
    p_complete.add_argument("-k", "--keeli", choices=personas, default="developer", metavar="PERSONA", help="Persona completing the task.")
    p_complete.add_argument("--scaffold-missing", action="store_true", help="Auto-scaffold missing Evidence/Verification placeholders before validation.")
    p_complete.add_argument("--json", action="store_true", help="Output transition details as JSON.")

    # tick
    p_tick = sub.add_parser("tick", help="Tick all mechanical checklist items (skips @security/@author gate items).")
    p_tick.add_argument("task_name", help="Task title or slug.")
    p_tick.set_defaults(func=cmd_tick)

    # ensure
    p_ensure = sub.add_parser("ensure", help="Verify a task exists or offer to create it.")
    p_ensure.add_argument("title", help="Short description of the work or problem.")
    p_ensure.add_argument("-y", "--yes", action="store_true", help="Automatically create the task if it does not exist.")
    p_ensure.add_argument("-n", "--no", action="store_true", help="Do not create a task if one is not found.")
    p_ensure.add_argument("-o", "--objective", help="Objective text to use when auto-creating a task.")
    p_ensure.add_argument("-p", "--priority", choices=["P0","P1","P2"], default="P1", help="Priority when auto-creating a task.")
    p_ensure.set_defaults(func=cmd_ensure)

    # archive
    p_archive = sub.add_parser("archive", help="Move a completed task to docs/tasks/archive/.")
    p_archive.add_argument("task_name", help="Task title or slug to archive.")
    p_archive.add_argument("-k", "--keeli", choices=personas, default="developer", metavar="PERSONA", help="Persona archiving the task.")

    # next
    p_next = sub.add_parser("next", help="Show the next task to work on.")
    p_next.add_argument("-q", "--quiet", action="store_true", help="Show only task name, not full content.")
    p_next.add_argument("--json", action="store_true", help="Output as JSON.")

    # log
    p_log = sub.add_parser("log", help="Append a timestamped entry to the audit log.")
    p_log.add_argument("message", help="The log message.")

    # resume
    p_resume = sub.add_parser("resume", help="Dump project context for a new AI session.")
    mode = p_resume.add_mutually_exclusive_group()
    mode.add_argument("--brief", action="store_true", help="Minimal output (~500 tokens).")
    mode.add_argument("--full", action="store_true", help="Full output (~3000 tokens).")
    mode.add_argument("--nano", action="store_true", help="~200 tokens: current task ID+title only. Ideal for Copilot in-editor injection.")
    p_resume.add_argument("--budget", type=int, default=None, metavar="N",
                          help="Target token budget (e.g. 4096). Auto-selects depth.")

    # status
    sub.add_parser("status", help="Health-check all Keeli files.")

    # doctor
    p_doctor = sub.add_parser("doctor", help="Diagnose task-state drift and hung-thread symptoms.")
    p_doctor.add_argument("--json", action="store_true", help="Output diagnostics as JSON.")

    # validate-task-state
    p_validate = sub.add_parser("validate-task-state", help="Validate passive task guardrails for hooks and local automation.")
    p_validate.add_argument("--paths", nargs="*", default=[], help="Optional file paths to scan for PII or secrets.")
    p_validate.add_argument("--auto-stub", action="store_true", help="Auto-create a temporary active task when pending leaf work exists but no task is active.")

    # capture-commit-state
    p_capture = sub.add_parser("capture-commit-state", help="Record the latest git commit against the current active task.")
    p_capture.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    p_capture.add_argument("--target-id", default="", help="Explicit target task ID for keeli:complete (overrides active task).")

    # transition-from-commit
    p_transition_from_commit = sub.add_parser(
        "transition-from-commit",
        help="Evaluate commit transition semantics from a subject line (optionally apply).",
    )
    p_transition_from_commit.add_argument("--subject", required=True, help="Commit subject to evaluate.")
    p_transition_from_commit.add_argument("--body", default="", help="Optional commit body/trailers to include in evaluation.")
    p_transition_from_commit.add_argument("--target-id", default="", help="Explicit target task ID for keeli:complete (overrides active task).")
    p_transition_from_commit.add_argument("--apply", action="store_true", help="Apply evaluated transitions to current task state.")
    p_transition_from_commit.add_argument("--dry-run", action="store_true", dest="dry_run", help="Preview per-item before/after transitions without mutating state (use with --apply).")

    # sync
    p_sync = sub.add_parser("sync", help="Rebuild SQLite work item state from markdown files.")
    p_sync.add_argument("--dry-run", action="store_true", dest="dry_run", help="Preview sync effect without mutating SQLite state.")
    p_sync.add_argument("--json", action="store_true", help="Output sync details as JSON.")

    # test
    p_test = sub.add_parser("test", help="Run pytest and auto-transition active In Progress work to Review on pass.")
    p_test.add_argument("--dry-run", action="store_true", dest="dry_run", help="Preview the test command and transition target without running pytest.")
    p_test.add_argument("--json", action="store_true", help="Output test result and transition details as JSON.")
    p_test.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Arguments forwarded directly to pytest.")

    # clear-log
    sub.add_parser("clear-log", help="Reset the AI audit log.")

    # progress
    p_progress = sub.add_parser("progress", help="Mark a task as In Progress.")
    p_progress.add_argument("task_name", help="Task title or slug.")
    p_progress.add_argument("-k", "--keeli", choices=personas, default="developer", metavar="PERSONA", help="Persona making the transition.")
    p_progress.add_argument("--json", action="store_true", help="Output transition details as JSON.")

    # block
    p_block = sub.add_parser("block", help="Mark a task as Blocked.")
    p_block.add_argument("task_name", help="Task title or slug.")
    p_block.add_argument("-k", "--keeli", choices=personas, default="developer", metavar="PERSONA", help="Persona making the transition.")
    p_block.add_argument("--json", action="store_true", help="Output transition details as JSON.")

    # update
    p_update = sub.add_parser("update", help="Update copilot-instructions.md to latest template.")
    p_update.add_argument("-f", "--force", action="store_true", help="Regenerate even if same version.")

    # reopen
    p_reopen = sub.add_parser("reopen", help="Reopen a completed task (back to In Progress).")
    p_reopen.add_argument("task_name", help="Task title or slug to reopen.")
    p_reopen.add_argument("-k", "--keeli", choices=personas, default="developer", metavar="PERSONA", help="Persona reopening the task.")
    p_reopen.add_argument("--json", action="store_true", help="Output transition details as JSON.")

    # review
    p_review = sub.add_parser("review", help="Mark a task as In Review (ready for @security sign-off).")
    p_review.add_argument("task_name", help="Task title or slug.")
    p_review.add_argument("-k", "--keeli", choices=personas, default="developer", metavar="PERSONA", help="Persona requesting the review.")
    p_review.add_argument("--json", action="store_true", help="Output transition details as JSON.")

    # bug
    p_bug = sub.add_parser("bug", help="Log a bug report as a tracked task.")
    p_bug.add_argument("title", help="Short bug title.")
    p_bug.add_argument("-d", "--description", help="Bug description. Prompted if omitted.")
    p_bug.add_argument("-p", "--priority", choices=["P0", "P1", "P2"], default=None, help="Bug priority. Prompted if omitted (default P0).")
    p_bug.add_argument("-e", "--epic", help="Associate this bug with an epic slug.")
    p_bug.add_argument("--found-during", help="What task or activity the bug was found during.")
    p_bug.add_argument("-f", "--force", action="store_true", help="Overwrite existing bug file.")

    # feature
    p_feature = sub.add_parser("feature", help="Create a feature request with user story and acceptance criteria.")
    p_feature.add_argument("title", help="Short feature title.")
    p_feature.add_argument("-c", "--context", help="Path to a requirements or context file to link.")
    p_feature.add_argument("-o", "--objective", help="User story / objective text. Accepts plain text, @file.md, or JSON: '{\"goal\":\"...\",\"why\":\"...\",\"criteria\":[\"...\"]}'. Prompted via warning if omitted.")
    p_feature.add_argument("-p", "--priority", choices=["P0", "P1", "P2"], default=None, help="Feature priority. Prompted if omitted (default P1).")
    p_feature.add_argument("-e", "--epic", help="Associate this feature with an epic slug.")
    p_feature.add_argument("-f", "--force", action="store_true", help="Overwrite existing feature file.")

    # story
    p_story = sub.add_parser("story", help="Create a user story under an epic (@architect).")
    p_story.add_argument("title", help="Short story title.")
    p_story.add_argument("--epic", help="Epic slug this story belongs to. Prompted if omitted.")
    p_story.add_argument("-p", "--priority", choices=["P0", "P1", "P2"], default=None, help="Story priority. Prompted if omitted (default P1).")
    p_story.add_argument("--role", help="The user role (e.g. 'developer', 'admin'). Prompted if omitted.")
    p_story.add_argument("--goal", help="What the user wants to do. Prompted if omitted.")
    p_story.add_argument("--reason", help="Why the user wants it. Prompted if omitted.")
    p_story.add_argument("--ac", action="append", metavar="CRITERION",
                         help="Acceptance criterion (repeatable). E.g. --ac 'Can add a todo' --ac 'Persists to disk'.")
    p_story.add_argument("-f", "--force", action="store_true", help="Overwrite existing story file.")

    # epic
    p_epic = sub.add_parser("epic", help="Create a new epic to group stories and tasks.")
    p_epic.add_argument("title", help="Short epic title.")
    p_epic.add_argument("-p", "--priority", choices=["P0", "P1", "P2"], default=None, help="Epic priority. Prompted if omitted (default P1).")
    p_epic.add_argument("-o", "--objective", help="Epic objective. Accepts plain text, @file.md, or JSON: '{\"goal\":\"...\",\"why\":\"...\",\"criteria\":[\"...\"]}'. Warned if omitted.")
    p_epic.add_argument("-f", "--force", action="store_true", help="Overwrite existing epic file.")

    # skill
    p_skill = sub.add_parser("skill", help="Manage project skills (add / list / remove / show).")
    skill_sub = p_skill.add_subparsers(dest="skill_action", help="Skill action")
    # skill add
    p_skill_add = skill_sub.add_parser("add", help="Register a new skill with an optional constraint.")
    p_skill_add.add_argument("skill_name", nargs="?", default=None, help="Skill name. Prompted if omitted.")
    p_skill_add.add_argument("-t", "--type", choices=SKILL_TYPES, default=None, metavar="TYPE", help=f"Skill type ({'/'.join(SKILL_TYPES)}). Prompted if omitted.")
    p_skill_add.add_argument("-k", "--persona", default=None, metavar="PERSONA", help="Persona this skill belongs to. Prompted if omitted. Blank = global.")
    p_skill_add.add_argument("-c", "--constraint", default=None, metavar="CONSTRAINT", help="Decision/constraint text. What your project chose and how. Prompted if omitted.")
    # skill list
    skill_sub.add_parser("list", help="List all registered skills (truncated constraint).")
    # skill show
    p_skill_show = skill_sub.add_parser("show", help="Show full constraint for a skill.")
    p_skill_show.add_argument("skill_name", nargs="?", default=None, help="Skill name. Prompted if omitted.")
    # skill remove
    p_skill_rm = skill_sub.add_parser("remove", help="Remove a registered skill.")
    p_skill_rm.add_argument("skill_name", nargs="?", default=None, help="Skill name to remove. Prompted if omitted.")
    # skill scan
    p_skill_scan = skill_sub.add_parser(
        "scan",
        help="Scan manifest files (pyproject.toml, requirements.txt, package.json, etc.) to discover project technologies."
    )
    p_skill_scan.add_argument(
        "scan_path", nargs="?", default=None,
        help="Root directory to scan (default: project root)."
    )
    p_skill_scan.add_argument(
        "--apply", action="store_true",
        help="Interactively register discovered skills with @architect constraints into docs/skills.md."
    )
    p_skill_scan.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Print detected technologies without writing or prompting (default when --apply is omitted)."
    )

    # stack
    p_stack = sub.add_parser("stack", help="Apply an opinionated stack preset interactively.")
    stack_sub = p_stack.add_subparsers(dest="stack_action", help="Stack action")
    # stack list
    stack_sub.add_parser("list", help="List all available stack presets.")
    # stack apply
    p_stack_apply = stack_sub.add_parser("apply", help="Apply a named preset directly.")
    p_stack_apply.add_argument("preset_name", help="Preset name or alias (e.g. python-fastapi, java, react).")
    p_stack_apply.add_argument("-y", "--yes", action="store_true", help="Accept all suggested constraints without prompting.")

    # persona
    p_persona = sub.add_parser("persona", help="Manage personas (add / list / remove).")
    persona_sub = p_persona.add_subparsers(dest="persona_action", help="Persona action")
    # persona add
    p_persona_add = persona_sub.add_parser("add", help="Add a new persona interactively.")
    p_persona_add.add_argument("persona_slug", nargs="?", default=None, help="Persona slug. Prompted if omitted.")
    # persona list
    persona_sub.add_parser("list", help="List all registered personas.")
    # persona remove
    p_persona_rm = persona_sub.add_parser("remove", help="Remove a persona.")
    p_persona_rm.add_argument("persona_slug", nargs="?", default=None, help="Persona slug to remove. Prompted if omitted.")

    # list
    p_list = sub.add_parser("list", help="List all tasks with status and priority.")
    p_list.add_argument("-s", "--status", help="Filter by status (backlog, in-progress, review, blocked, completed).")
    p_list.add_argument("-e", "--epic", help="Filter by epic slug.")
    p_list.add_argument("--json", action="store_true", help="Output as JSON.")

    # note
    p_note = sub.add_parser("note", help="Append a timestamped note to a task.")
    p_note.add_argument("task_name", help="Task title or slug.")
    p_note.add_argument("message", nargs="?", default=None, help="Note text. Prompted if omitted.")
    p_note.add_argument("-k", "--keeli", choices=personas, default="developer", metavar="PERSONA", help="Persona adding the note.")

    # analyze
    p_analyze = sub.add_parser("analyze", help="Analyze a task and inject AI context hints.")
    p_analyze.add_argument("slug", help="Task slug (or prefix) to analyze.")
    p_analyze.add_argument("--use-sklearn", action="store_true", dest="use_sklearn",
                           help="Force scikit-learn TfidfVectorizer (must be installed).")
    p_analyze.add_argument("--dry-run", action="store_true", dest="dry_run",
                           help="Print hints to terminal without writing to file.")

    # find
    p_find = sub.add_parser("find", help="Search the index by ID (T-0001) or keyword.")
    p_find.add_argument("query", help="An ID (e.g. T-0001) or keyword to search.")
    p_find.add_argument("-s", "--status", default=None, help="Filter by status.")
    p_find.add_argument("--json", action="store_true", help="Output as JSON.")

    # history
    p_history = sub.add_parser("history", help="Show all ai_log entries for a task ID.")
    p_history.add_argument("task_id", help="Task ID (e.g. T-0001) or keyword.")
    p_history.add_argument("--json", action="store_true", help="Output as JSON.")

    # digest
    p_digest = sub.add_parser("digest", help="Machine-optimised token-budgeted context dump.")
    p_digest.add_argument("--budget", type=int, default=2000,
                          help="Token budget (default: 2000).")
    p_digest.add_argument("--json", action="store_true", help="Output as JSON.")

    # chain
    p_chain = sub.add_parser(
        "chain",
        help="Run a sequential pipeline of keeli commands (tool chaining).",
        description=(
            "Execute multiple keeli commands in order, automatically propagating "
            "the output task slug between steps via the 'auto' sentinel.\n\n"
            "Examples:\n"
            "  keeli chain \"start:My Task\" \"analyze:auto\" \"progress:auto\"\n"
            "  keeli chain list\n"
            "  keeli chain run new-task --var title=\"My Task\"\n"
            "  keeli chain run close-task --var slug=my-task"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_chain.add_argument(
        "steps", nargs="*", metavar="STEP",
        help="Inline steps as 'cmd:arg'. Use 'list' to list chains or 'run <name>' for named chains."
    )
    p_chain.add_argument(
        "--var", action="append", metavar="KEY=VALUE",
        help="Variable substitution for named chains (repeatable: --var title=\"Foo\" --var slug=bar)."
    )
    p_chain.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Print the resolved steps without executing them."
    )

    # mcp
    p_mcp = sub.add_parser("mcp", help="Start the Keeli MCP server.")
    p_mcp.add_argument("--sse", action="store_true", help="Run over HTTP/SSE instead of stdio.")
    p_mcp.add_argument("--port", type=int, default=8000, help="Port for SSE server (default: 8000).")

    # prompt
    p_prompt = sub.add_parser("prompt", help="Manage custom prompts for the project.")
    prompt_sub = p_prompt.add_subparsers(dest="prompt_action", help="Prompt action")
    
    # prompt add
    p_prompt_add = prompt_sub.add_parser("add", help="Add a custom prompt from a file.")
    p_prompt_add.add_argument("slug", help="Short slug for the prompt (used as filename).")
    p_prompt_add.add_argument("--file", required=True, help="Path to the .md prompt file to add.")
    p_prompt_add.add_argument("--persona", help="Persona this prompt applies to (architect, developer, etc.). Prompted if omitted.")
    p_prompt_add.add_argument("--applies-to", help="When prompt applies (all, domain, task-type, etc.). Prompted if omitted.")
    p_prompt_add.add_argument("--priority", help="Prompt priority (high, medium, low). Prompted if omitted.")
    p_prompt_add.add_argument("-f", "--force", action="store_true", help="Overwrite existing prompt.")

    # prompt apply
    p_prompt_apply = prompt_sub.add_parser(
        "apply",
        help="Render a custom prompt with variables and optionally write it to a file.",
    )
    p_prompt_apply.add_argument("slug", help="Slug of the prompt to apply.")
    p_prompt_apply.add_argument(
        "--var",
        action="append",
        dest="vars",
        metavar="KEY=VALUE",
        help="Template variable substitution (repeatable).",
    )
    p_prompt_apply.add_argument(
        "--output",
        help="Optional output file path. If omitted, rendered content is printed.",
    )
    
    # prompt list
    prompt_sub.add_parser("list", help="List all custom prompts with metadata.")
    
    # prompt show
    p_prompt_show = prompt_sub.add_parser("show", help="Show the full content of a custom prompt.")
    p_prompt_show.add_argument("slug", help="Slug of the prompt to display.")
    
    # prompt remove
    p_prompt_remove = prompt_sub.add_parser("remove", help="Remove a custom prompt.")
    p_prompt_remove.add_argument("slug", help="Slug of the prompt to remove.")
    p_prompt_remove.add_argument("-f", "--force", action="store_true", help="Skip confirmation prompt.")

    # handoff
    p_handoff = sub.add_parser("handoff", help="Sign a persona handshake on a task.")
    p_handoff.add_argument("task_name", help="Task title or slug.")
    p_handoff.add_argument("-p", "--persona", required=True, choices=personas, metavar="PERSONA", 
                          help=f"Persona signing off ({'/'.join(personas)}).")
    p_handoff.add_argument("-m", "--message", default=None, help="Optional handoff summary/notes.")

    # snapshot
    p_snapshot = sub.add_parser(
        "snapshot",
        help="Generate a weekly governance snapshot from task state and audit log.",
    )
    p_snapshot.add_argument(
        "--week-ending",
        default=None,
        metavar="DATE",
        help="ISO date for the 'Week ending' header (default: today).",
    )
    p_snapshot.add_argument(
        "--out",
        default=None,
        metavar="FILE",
        help="Write snapshot to FILE instead of printing to stdout.",
    )
    p_snapshot.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit machine-readable KPI summary JSON instead of markdown.",
    )
    p_snapshot.add_argument(
        "--json-out",
        default=None,
        metavar="FILE",
        help="Write JSON payload to FILE (useful for CI artifacts).",
    )

    return parser

def cmd_snapshot(args: argparse.Namespace) -> None:
    """Generate a weekly governance snapshot from task state and audit log."""
    root = _find_project_root()
    tasks_dir = root / "docs" / "tasks"
    log_file = root / "docs" / "ai_log.md"
    week_ending = getattr(args, "week_ending", None) or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Collect task counts ─────────────────────────────────────────────────
    counts: dict[str, int] = {"Backlog": 0, "In Progress": 0, "Review": 0, "Blocked": 0, "Completed": 0}
    completed_this_week: list[str] = []
    if _state_db_path().exists():
        with contextlib.closing(_connect_state_db()) as conn:
            for row in conn.execute(
                "SELECT status, slug, completed_at FROM work_items WHERE item_type IN ('task','bug','feat','story')"
            ).fetchall():
                status = (row["status"] or "Backlog")
                key = status if status in counts else "Backlog"
                counts[key] = counts.get(key, 0) + 1
                if status == "Completed" and row["completed_at"] and row["completed_at"][:10] == week_ending:
                    completed_this_week.append(row["slug"])
    else:
        # Fall back to filesystem scan
        if tasks_dir.exists():
            for tf in tasks_dir.glob("*.md"):
                if tf.name == ".gitkeep":
                    continue
                text = tf.read_text()
                status = _parse_task_field(text, "Status") or "Backlog"
                key = status if status in counts else "Backlog"
                counts[key] = counts.get(key, 0) + 1
            archive_dir = tasks_dir / "archive"
            if archive_dir.exists():
                for tf in archive_dir.glob("*.md"):
                    text = tf.read_text()
                    completed_at = _parse_task_field(text, "Completed")
                    if completed_at and completed_at[:10] == week_ending:
                        completed_this_week.append(tf.stem)

    in_progress_count = counts.get("In Progress", 0) + counts.get("Review", 0)
    blocked_count = counts.get("Blocked", 0)

    # ── Recent log lines ────────────────────────────────────────────────────
    recent_log_lines: list[str] = []
    if log_file.exists():
        lines = log_file.read_text().splitlines()
        recent_log_lines = [l for l in lines if l.strip() and not l.startswith("#") and not l.startswith("<!--")][-10:]

    # ── KPI table (current values where calculable, else Data Gap) ──────────
    total_items = sum(counts.values())

    def _story_has_defined_nfr(story_text: str) -> bool:
        lines = _section_body(story_text, _SEC_NFR)
        if not lines:
            return False
        for raw in lines:
            value = raw.strip().lower()
            if value in ("", "none", "n/a"):
                continue
            if value.startswith("<!--"):
                continue
            return True
        return False

    # Planning completeness: stories with non-None NFR section
    planning_completeness = "Data Gap"
    story_count = 0
    stories_with_nfr = 0
    if tasks_dir.exists():
        for tf in tasks_dir.glob("story-*.md"):
            text = tf.read_text()
            story_count += 1
            if _story_has_defined_nfr(text):
                stories_with_nfr += 1
        if story_count:
            planning_completeness = f"{stories_with_nfr / story_count:.2f} ({stories_with_nfr}/{story_count} stories)"

    blocked_ratio = (
        f"{blocked_count / max(in_progress_count + blocked_count, 1):.2f}"
        if (in_progress_count + blocked_count) > 0
        else "0.00"
    )

    planning_status = "At Risk" if story_count and stories_with_nfr / max(story_count, 1) < 0.8 else "On Track" if story_count else "Data Gap"
    blocked_status = "On Track" if float(blocked_ratio) <= 0.15 else "At Risk"
    kpi_rows = [
        ("Planning completeness ratio", planning_completeness, "", "30-day >= 0.80", planning_status),
        ("Story acceptance clarity score", "Data Gap", "", "30-day >= 3.5", "Data Gap"),
        ("Backlog churn percentage", "Data Gap", "", "30-day <= 20%", "Data Gap"),
        ("Cycle time median", "Data Gap", "", "60-day <= 5 days", "Data Gap"),
        ("Blocked work ratio", blocked_ratio, "", "60-day <= 15%", blocked_status),
        ("Requirement-change rework hours", "Data Gap", "", "60-day <= 12h/sprint", "Data Gap"),
        ("Hallucination-attributed rework hours", "Data Gap", "", "60-day", "Data Gap"),
        ("Hallucination rework rate", "Data Gap", "", "60/90-day", "Data Gap"),
        ("Defect escape rate", "Data Gap", "", "90-day <= 10%", "Data Gap"),
        ("Incident rate from req gaps", "Data Gap", "", "90-day <= 1/release", "Data Gap"),
        ("Throughput stability", "Data Gap", "", "90-day CoV <= 0.25", "Data Gap"),
    ]

    kpi_metrics = [
        {
            "name": kpi,
            "current": current,
            "last_week": last,
            "target_band": target,
            "status": status_,
        }
        for kpi, current, last, target, status_ in kpi_rows
    ]

    kpi_dict = {
        "planning_completeness_ratio": planning_completeness,
        "blocked_work_ratio": blocked_ratio,
        "planning_completeness_status": planning_status,
        "blocked_work_status": blocked_status,
        "in_progress_count": in_progress_count,
        "blocked_count": blocked_count,
        "completed_this_week_count": len(completed_this_week),
    }

    payload = _json_envelope("snapshot", True, {
        "week_ending": week_ending,
        "delivery": {
            "in_progress": in_progress_count,
            "completed_this_week": len(completed_this_week),
            "blocked": blocked_count,
            "total_items": total_items,
        },
        "kpis": kpi_dict,
        "kpi_metrics": kpi_metrics,
        "completed_items": completed_this_week[:20],
        "sources": [
            "docs/tasks/",
            "docs/ai_log.md",
            "docs/decision.md",
            "keeli_state.db",
            "docs/requirements/governance-kpi-framework-30-60-90.md",
            "docs/requirements/hallucination-rework-benchmark-protocol.md",
        ],
    })

    json_out_path = getattr(args, "json_out", None)
    if json_out_path:
        dest = Path(json_out_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(payload, indent=2) + "\n")
        _append_log(f"@system | Snapshot JSON generated: {dest} (week-ending {week_ending})")

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
        return

    # ── Build markdown ──────────────────────────────────────────────────────
    kpi_table_rows = "\n".join(
        f"| {kpi} | {current} | {last} | {target} | {status_} |"
        for kpi, current, last, target, status_ in kpi_rows
    )

    completed_bullets = (
        "\n".join(f"  - {s}" for s in completed_this_week[:5])
        if completed_this_week
        else "  - (none recorded with matching completion date)"
    )

    log_section = (
        "\n".join(f"  {l}" for l in recent_log_lines)
        if recent_log_lines
        else "  (audit log empty)"
    )

    # Source artifact references
    source_refs = []
    for candidate in ["docs/tasks/", "docs/ai_log.md", "docs/decision.md", "keeli_state.db"]:
        source_refs.append(f"  - {candidate}")
    kpi_ref = "docs/requirements/governance-kpi-framework-30-60-90.md"
    if (root / kpi_ref).exists():
        source_refs.append(f"  - {kpi_ref}")

    md = f"""# Weekly Governance Snapshot

## Header
- Week ending: {week_ending}
- Prepared by: @system (keeli snapshot)
- Scope: All active work items
- Source artifacts reviewed:
{chr(10).join(source_refs)}

## 1. Delivery Status
- In Progress count: {in_progress_count}
- Completed this week: {len(completed_this_week)}
- Blocked items: {blocked_count}
- Top completed this week:
{completed_bullets}

## 2. KPI Delta (WoW)

| KPI | Current | Last Week | Target Band | Status |
|---|---|---|---|---|
{kpi_table_rows}

## 3. Risk Register

| Risk | Impact | Likelihood | Owner | Mitigation | Status |
|---|---|---|---|---|---|
| KPI data collection partly manual | Medium | High | @po | Automate extraction from keeli_state.db | Open |

## 4. Decisions Needed
- (review docs/decision.md for open decisions)

## 5. Evidence And Links
- Task artifacts: docs/tasks/
- Audit log references: docs/ai_log.md
- Decision log: docs/decision.md

## Recent Audit Log
{log_section}
"""

    out_path = getattr(args, "out", None)
    if out_path:
        dest = Path(out_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(md)
        print(f"✅ Snapshot written → {dest}")
        _append_log(f"@system | Snapshot generated: {dest} (week-ending {week_ending})")
    else:
        print(md)


def cmd_mcp(args: argparse.Namespace) -> None:
    """Start the Keeli MCP server."""
    try:
        from keeli.mcp_server import main as mcp_main
        transport = "sse" if args.sse else "stdio"
        mcp_main(transport=transport, port=args.port)
    except ImportError:
        import sys
        print("Error: The 'mcp' package is required to run the MCP server.")
        print("Install it with: pip install mcp")
        sys.exit(1)

def main() -> None:
    parser = build_parser()
    args, unknown = parser.parse_known_args()

    if unknown:
        if getattr(args, "command", None) == "test":
            forwarded = list(getattr(args, "pytest_args", []) or [])
            forwarded.extend(unknown)
            args.pytest_args = forwarded
        else:
            parser.error(f"unrecognized arguments: {' '.join(unknown)}")

    # Resolve project root so commands work from any subdirectory and the MCP
    # server works even when launched from a parent of the project directory.
    if getattr(args, "command", None) != "init":
        project_root = _find_project_root()
        if project_root != Path.cwd():
            os.chdir(project_root)

    dispatch = {
        "init": cmd_init,
        "start": cmd_start,
        "complete": cmd_complete,
        "tick": cmd_tick,
        "archive": cmd_archive,
        "next": cmd_next,
        "list": cmd_list,
        "note": cmd_note,
        "log": cmd_log,
        "resume": cmd_resume,
        "status": cmd_status,
        "doctor": cmd_doctor,
        "validate-task-state": cmd_validate_task_state,
        "capture-commit-state": cmd_capture_commit_state,
        "transition-from-commit": cmd_transition_from_commit,
        "sync": cmd_sync,
        "test": cmd_test,
        "clear-log": cmd_clear_log,
        "progress": cmd_progress,
        "block": cmd_block,
        "review": cmd_review,
        "update": cmd_update,
        "reopen": cmd_reopen,
        "bug": cmd_bug,
        "feature": cmd_feature,
        "epic": cmd_epic,
        "story": cmd_story,
        "ensure": cmd_ensure,
        "skill": cmd_skill,
        "stack": cmd_stack,
        "persona": cmd_persona,
        "analyze": cmd_analyze,
        "find": cmd_find,
        "history": cmd_history,
        "digest": cmd_digest,
        "mcp": cmd_mcp,
        "chain": cmd_chain,
        "handoff": cmd_handoff,
        "prompt": cmd_prompt,
        "snapshot": cmd_snapshot,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

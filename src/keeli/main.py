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
import json
import os
import math as _math
import re
import textwrap
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
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text: str) -> str:
    """Turn a task title into a filesystem-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


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


# ── Index / Ledger helpers ─────────────────────────────────────────────────

_INDEX_PATH = Path("docs/.keeli_index.json")
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

# ── Personas helpers ──────────────────────────────────────────────────────────

DEFAULT_PERSONAS = ["po", "architect", "developer", "security", "author"]


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
        persona_order = ["po", "architect", "developer", "security", "author", "global"]
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
    persona = getattr(args, "keeli", "architect") or "architect"
    checklist = TASK_CHECKLISTS.get(persona, TASK_CHECKLISTS["developer"])
    depends_on = getattr(args, "depends_on", None) or "None"
    epic = getattr(args, "epic", None) or "None"
    story = getattr(args, "story", None) or "None"

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
        checklist=checklist,
        objective=objective_text,
    )
    task_file.write_text(content)
    print(f"✅ Created task: {task_file} [{task_id}] [@{persona} checklist]")
    if objective_text:
        print(f"   → Objective set ({len(objective_text.splitlines())} line(s))")

    # Auto-log the event
    _append_log(f"@{persona} | Task created: {args.task_name} → {task_file}", task_id=task_id)


def cmd_log(args: argparse.Namespace) -> None:
    """Append a timestamped entry to docs/ai_log.md."""
    _append_log(args.message)
    print(f"✅ Logged to docs/ai_log.md")


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

    # First: any In Progress tasks (resume those first)
    for tf in sorted(tasks_dir.glob("*.md")):
        text = tf.read_text()
        status = _parse_task_field(text, "Status")
        if status.lower() == "in progress":
            return tf, tf.stem

    # Second: Backlog tasks sorted by priority (P0 > P1 > P2) then by creation date
    backlog: list[tuple[str, str, Path]] = []
    for tf in sorted(tasks_dir.glob("*.md")):
        if tf.name == ".gitkeep":
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


def _transition_task(args: argparse.Namespace, new_status: str, log_verb: str) -> None:
    """Generic helper to transition a task to a new status."""
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
    current = _parse_task_field(text, "Status")

    if current.lower() == new_status.lower():
        print(f"⚠️  {task_file} is already {new_status}.")
        return

    task_id = _parse_task_field(text, "ID")
    text = _update_task_field(text, "Status", new_status)
    task_file.write_text(text)
    print(f"✅ Marked as {new_status}: {task_file}")

    _index_update_status(task_id, status=new_status)
    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task {log_verb}: {args.task_name} → {task_file}", task_id=task_id)


def cmd_progress(args: argparse.Namespace) -> None:
    """Mark a task as In Progress."""
    _transition_task(args, "In Progress", "started")


def cmd_block(args: argparse.Namespace) -> None:
    """Mark a task as Blocked."""
    _transition_task(args, "Blocked", "blocked")


def cmd_review(args: argparse.Namespace) -> None:
    """Mark a task as In Review (ready for @security sign-off)."""
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
    current = _parse_task_field(text, "Status")

    if current.lower() == "review":
        print(f"⚠️  {task_file} is already In Review.")
        return

    text = _update_task_field(text, "Status", "Review")
    task_file.write_text(text)
    print(f"✅ Marked as Review: {task_file}")
    print("   → Awaiting @security sign-off. Run `keeli complete` when approved.")

    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task in review: {args.task_name} → {task_file}")


def cmd_reopen(args: argparse.Namespace) -> None:
    """Reopen a completed task (move it back to In Progress)."""
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

    if status.lower() not in ("completed", "review"):
        print(f"⚠️  {task_file} is currently '{status}' — reopen only works on Completed or Review tasks.")
        return

    task_id = _parse_task_field(text, "ID")

    # Move back to live tasks_dir if it was in archive
    if task_file.parent.name == "archive":
        live_dest = tasks_dir / task_file.name
        task_file.rename(live_dest)
        task_file = live_dest
        print(f"   📤 Restored from archive → {task_file}")

    text = _update_task_field(text, "Status", "In Progress")
    text = _update_task_field(text, "Completed", "—")
    task_file.write_text(text)
    print(f"✅ Reopened: {task_file} (now In Progress)")

    _index_update_status(task_id, status="In Progress", completed=None, archived=False)
    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task reopened: {args.task_name} → {task_file}", task_id=task_id)


def cmd_bug(args: argparse.Namespace) -> None:
    """Log a bug found during development and create a tracked bug task."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.title)
    task_file = tasks_dir / f"bug-{slug}.md"

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
    print(f"🐛 Created bug report: {task_file} [{bug_id}]")

    _append_log(f"@developer | Bug reported: {args.title} [{priority}] → {task_file}", task_id=bug_id)


def cmd_feature(args: argparse.Namespace) -> None:
    """Create a feature request task with user story and acceptance criteria."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.title)
    task_file = tasks_dir / f"feat-{slug}.md"

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
    print(f"✨ Created feature: {task_file} [{feat_id}]")

    _append_log(f"@architect | Feature created: {args.title} [{priority}] → {task_file}", task_id=feat_id)


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
            print("  Tip: constraint = the specific VERSION + RULES your project chose.")
            print("       Generic names alone add no value. Leave blank to add later.")
            constraint = _prompt("Constraint / decision (blank to skip)", default="")
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

    else:
        print("Usage: keeli skill <add|list|remove|show>")


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

    if task_file.exists() and not args.force:
        print(f"⚠️  {task_file} already exists. Use --force to overwrite.")
        return

    epic = getattr(args, "epic", None) or _prompt(
        "Epic slug this story belongs to", default="None"
    )
    priority = args.priority or _prompt(
        "Story priority", default="P1", choices=["P0", "P1", "P2"]
    )
    role   = getattr(args, "role", None)   or _prompt("Role (e.g. 'developer')", default="user")
    goal   = getattr(args, "goal", None)   or _prompt("Goal (e.g. 'create a task')"        )
    reason = getattr(args, "reason", None) or _prompt("Reason (e.g. 'track my work')", default="...")

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
        slug=slug,
        role=role,
        goal=goal,
        reason=reason,
    )
    task_file.write_text(content)
    print(f"📖 Created story: {task_file} [{story_id}]")
    if epic != "None":
        print(f"   → Linked to epic: {epic}")
    print(f"   → Add tasks with: keeli start \"<title>\" --story {slug} --epic {epic}")

    _append_log(f"@architect | Story created: {args.title} [{priority}] epic={epic} → {task_file}", task_id=story_id)


def cmd_epic(args: argparse.Namespace) -> None:
    """Create a new epic file in docs/tasks/."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    slug = _slugify(args.title)
    task_file = tasks_dir / f"epic-{slug}.md"

    if task_file.exists() and not args.force:
        print(f"⚠️  {task_file} already exists. Use --force to overwrite.")
        return

    priority = args.priority or _prompt(
        "Epic priority", default="P1", choices=["P0", "P1", "P2"]
    )

    epic_id = _allocate_id("epic", args.title, f"epic-{slug}", priority=priority)
    objective_text = _resolve_objective(getattr(args, "objective", None))
    if not objective_text:
        print(_OBJECTIVE_HINT)
    content = EPIC_TEMPLATE.format(
        task_id=epic_id,
        title=args.title,
        priority=priority,
        timestamp=_now_iso(),
        slug=slug,
        objective=objective_text or "<!-- @architect: high-level goal — what user/business outcome does this deliver? -->",
    )
    task_file.write_text(content)
    print(f"🚀 Created epic: {task_file} [{epic_id}]")
    print(f"   → @architect: define objective/scope, then run: keeli story \"<title>\" --epic {slug}")

    _append_log(f"@architect | Epic created: {args.title} [{priority}] → {task_file}", task_id=epic_id)


def cmd_complete(args: argparse.Namespace) -> None:
    """Mark a task as completed, auto-archive it, and suggest the next one."""
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

    if status.lower() == "completed":
        print(f"⚠️  {task_file} is already marked as Completed.")
        return

    now = _now_iso()
    task_id = _parse_task_field(text, "ID")

    # Update status and add completion timestamp
    text = _update_task_field(text, "Status", "Completed")
    text = _update_task_field(text, "Completed", now)
    task_file.write_text(text)
    print(f"✅ Marked as Completed: {task_file}")

    # Auto-archive to docs/tasks/archive/
    archive_dir = tasks_dir / "archive"
    archive_dir.mkdir(exist_ok=True)
    dest = archive_dir / task_file.name
    task_file.rename(dest)
    print(f"   📦 Auto-archived → {dest}")

    # Update index
    _index_update_status(task_id, status="Completed", completed=now, archived=True)

    # Auto-log
    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task completed: {args.task_name} → {dest}", task_id=task_id)

    # Suggest next task
    next_path, next_slug = _get_next_task()
    if next_path:
        next_text = next_path.read_text()
        next_status = _parse_task_field(next_text, "Status")
        next_priority = _parse_task_field(next_text, "Priority")
        print(f"\n📋 Next task: {next_slug} [{next_priority}] ({next_status})")
        print(f"   → {next_path}")
    else:
        print("\n🎉 All tasks are complete. Awaiting new instructions.")


def cmd_next(args: argparse.Namespace) -> None:
    """Show the next task to work on."""
    next_path, next_slug = _get_next_task()
    if next_path:
        next_text = next_path.read_text()
        next_status = _parse_task_field(next_text, "Status")
        next_priority = _parse_task_field(next_text, "Priority")
        
        if getattr(args, "json", False):
            import json
            print(json.dumps({
                "task": next_slug,
                "priority": next_priority,
                "status": next_status,
                "path": str(next_path),
                "content": next_text
            }, indent=2))
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
            import json
            print(json.dumps({"task": None}))
            return
        print("🎉 All tasks are complete. Awaiting new instructions.")


def cmd_list(args: argparse.Namespace) -> None:
    """List all tasks with status, priority, and creation date."""
    tasks_dir = Path("docs/tasks")
    if not tasks_dir.exists():
        print("❌ docs/tasks/ not found. Run `keeli init` first.")
        return

    filter_status = getattr(args, "status", None)
    filter_epic = getattr(args, "epic", None)
    STATUS_ICON = {
        "backlog":     "⬜",
        "in progress": "🔵",
        "review":      "🟡",
        "blocked":     "🔴",
        "completed":   "✅",
    }

    rows = []
    for tf in sorted(tasks_dir.glob("*.md")):
        if tf.name == ".gitkeep":
            continue
        text = tf.read_text()
        status   = _parse_task_field(text, "Status")
        priority = _parse_task_field(text, "Priority") or "P1"
        created  = (_parse_task_field(text, "Created") or "?")[:10]
        epic     = _parse_task_field(text, "Epic") or "None"
        
        if filter_status and status.lower() != filter_status.lower():
            continue
        if filter_epic and epic.lower() != filter_epic.lower():
            continue
            
        icon = STATUS_ICON.get(status.lower(), "❓")
        rows.append((priority, created, icon, status, tf.stem, epic))

    if not rows:
        if getattr(args, "json", False):
            import json
            print(json.dumps([]))
            return
        msg = "No tasks found matching criteria."
        print(msg)
        return

    rows.sort(key=lambda r: (r[0], r[1]))
    
    if getattr(args, "json", False):
        import json
        out = [{"priority": r[0], "created": r[1], "status": r[3], "task": r[4], "epic": r[5]} for r in rows]
        print(json.dumps(out, indent=2))
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
    print(f"✅ Archived: {task_file.name} → {dest_file}")

    _index_update_status(task_id, archived=True)
    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task archived: {args.task_name} → {dest_file}", task_id=task_id)


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
    ]

    all_ok = True
    for p in paths:
        if p.exists():
            print(f"  ✅ {p}")
        else:
            print(f"  ❌ {p}")
            all_ok = False

    # Count tasks by status
    tasks_dir = Path("docs/tasks")
    if tasks_dir.exists():
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
    if not _INDEX_PATH.exists():
        print("❌ Index not found. Create some tasks first (keeli start / epic / story / bug).")
        return

    index = _load_index()
    items = index.get("items", [])
    query = args.query.strip()
    query_upper = query.upper()

    # Exact ID match first (e.g. T-0001, BUG-0003)
    id_matches = [i for i in items if i.get("id", "").upper() == query_upper]
    if id_matches:
        _print_index_results(id_matches, label=f"ID: {query_upper}")
        return

    # Keyword match across title + slug
    q_lower = query.lower()
    kw_matches = [
        i for i in items
        if q_lower in i.get("title", "").lower() or q_lower in i.get("slug", "").lower()
    ]
    if kw_matches:
        status_filter = getattr(args, "status", None)
        if status_filter:
            kw_matches = [i for i in kw_matches if i.get("status", "").lower() == status_filter.lower()]
        _print_index_results(kw_matches, label=f"Keyword: '{query}'")
    else:
        print(f"No results for '{query}'.")
    if getattr(args, "json", False):
        import json
        print("\n" + json.dumps(id_matches or kw_matches, indent=2))


def cmd_history(args: argparse.Namespace) -> None:
    """Show all ai_log entries for a specific task ID or title keyword.

    Examples:
        keeli history T-0003
        keeli history "auth"
    """
    log_file = Path("docs/ai_log.md")
    if not log_file.exists():
        print("❌ docs/ai_log.md not found.")
        return

    target = args.task_id.strip().upper()
    lines = log_file.read_text().splitlines()
    matches = [line for line in lines if target in line.upper()]

    if not matches:
        print(f"No log entries found for '{target}'.")
        return

    print(f"\n📜 History for {target} — {len(matches)} entries\n")
    for line in matches:
        print(f"  {line}")
    print()


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

    # clear-log
    sub.add_parser("clear-log", help="Reset the AI audit log.")

    # progress
    p_progress = sub.add_parser("progress", help="Mark a task as In Progress.")
    p_progress.add_argument("task_name", help="Task title or slug.")
    p_progress.add_argument("-k", "--keeli", choices=personas, default="developer", metavar="PERSONA", help="Persona making the transition.")

    # block
    p_block = sub.add_parser("block", help="Mark a task as Blocked.")
    p_block.add_argument("task_name", help="Task title or slug.")
    p_block.add_argument("-k", "--keeli", choices=personas, default="developer", metavar="PERSONA", help="Persona making the transition.")

    # update
    p_update = sub.add_parser("update", help="Update copilot-instructions.md to latest template.")
    p_update.add_argument("-f", "--force", action="store_true", help="Regenerate even if same version.")

    # reopen
    p_reopen = sub.add_parser("reopen", help="Reopen a completed task (back to In Progress).")
    p_reopen.add_argument("task_name", help="Task title or slug to reopen.")
    p_reopen.add_argument("-k", "--keeli", choices=personas, default="developer", metavar="PERSONA", help="Persona reopening the task.")

    # review
    p_review = sub.add_parser("review", help="Mark a task as In Review (ready for @security sign-off).")
    p_review.add_argument("task_name", help="Task title or slug.")
    p_review.add_argument("-k", "--keeli", choices=personas, default="developer", metavar="PERSONA", help="Persona requesting the review.")

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

    # digest
    p_digest = sub.add_parser("digest", help="Machine-optimised token-budgeted context dump.")
    p_digest.add_argument("--budget", type=int, default=2000,
                          help="Token budget (default: 2000).")

    # mcp
    p_mcp = sub.add_parser("mcp", help="Start the Keeli MCP server.")
    p_mcp.add_argument("--sse", action="store_true", help="Run over HTTP/SSE instead of stdio.")
    p_mcp.add_argument("--port", type=int, default=8000, help="Port for SSE server (default: 8000).")

    return parser

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
    args = parser.parse_args()

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
        "archive": cmd_archive,
        "next": cmd_next,
        "list": cmd_list,
        "note": cmd_note,
        "log": cmd_log,
        "resume": cmd_resume,
        "status": cmd_status,
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
        "skill": cmd_skill,
        "stack": cmd_stack,
        "persona": cmd_persona,
        "analyze": cmd_analyze,
        "find": cmd_find,
        "history": cmd_history,
        "digest": cmd_digest,
        "mcp": cmd_mcp,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

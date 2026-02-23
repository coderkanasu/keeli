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
"""

import argparse
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
    PROJECT_MD,
    SCHEMA_VERSION,
    SKILLS_MD,
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


def _read_skills() -> list[tuple[str, str]]:
    """Return list of (type, name) tuples from docs/skills.md."""
    path = Path("docs/skills.md")
    if not path.exists():
        return []
    skills = []
    for line in path.read_text().splitlines():
        if line.startswith("|") and "|" in line[1:]:
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) == 2:
                t, n = parts
                # skip header row, separator rows (all dashes), and empty
                if not t or t.lower() in ("type",) or t.lstrip("-") == "":
                    continue
                skills.append((t, n))
    return skills


def _write_skills(skills: list[tuple[str, str]]) -> None:
    """Persist skills list to docs/skills.md and regenerate the skills block
    inside .github/copilot-instructions.md."""
    path = Path("docs/skills.md")
    rows = "\n".join(f"| {t} | {n} |" for t, n in skills)
    path.write_text(SKILLS_MD.format(version=SCHEMA_VERSION) + (rows + "\n" if rows else ""))
    _inject_skills_into_instructions(skills)


def _inject_skills_into_instructions(skills: list[tuple[str, str]]) -> None:
    """Regenerate the <!-- KEELI_SKILLS --> block in copilot-instructions.md."""
    instr = Path(".github/copilot-instructions.md")
    if not instr.exists():
        return
    text = instr.read_text()
    if _SKILLS_START not in text:
        return
    # Build grouped block
    grouped: dict[str, list[str]] = {}
    for t, n in skills:
        grouped.setdefault(t, []).append(n)
    lines = [f"- **{t.capitalize()}**: {', '.join(names)}" for t, names in grouped.items()]
    block = "\n".join(lines) if lines else "(no skills registered — run `keeli skill add` to populate)"
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

    priority = getattr(args, "priority", None) or _prompt(
        "Task priority", default="P1", choices=["P0", "P1", "P2"]
    )
    persona = getattr(args, "keeli", "architect") or "architect"
    checklist = TASK_CHECKLISTS.get(persona, TASK_CHECKLISTS["developer"])
    depends_on = getattr(args, "depends_on", None) or "None"
    epic = getattr(args, "epic", None) or "None"
    story = getattr(args, "story", None) or "None"

    content = TASK_TEMPLATE.format(
        title=args.task_name,
        timestamp=_now_iso(),
        context_note=context_note,
        priority=priority,
        depends_on=depends_on,
        epic=epic,
        story=story,
        persona=f"@{persona}",
        checklist=checklist,
    )
    task_file.write_text(content)
    print(f"✅ Created task: {task_file} [@{persona} checklist]")

    # Auto-log the event
    _append_log(f"@{persona} | Task created: {args.task_name} → {task_file}")


def cmd_log(args: argparse.Namespace) -> None:
    """Append a timestamped entry to docs/ai_log.md."""
    _append_log(args.message)
    print(f"✅ Logged to docs/ai_log.md")


def _append_log(message: str) -> None:
    """Low-level helper: append one line to the audit log."""
    log_file = Path("docs/ai_log.md")
    if not log_file.exists():
        log_file.write_text(AI_LOG_MD)
    with log_file.open("a") as f:
        f.write(f"{_now_iso()} | {message}\n")


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
    """Return the first existing file matching plain, bug-, or feat- prefix."""
    for candidate in (
        tasks_dir / f"{slug}.md",
        tasks_dir / f"bug-{slug}.md",
        tasks_dir / f"feat-{slug}.md",
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

    text = _update_task_field(text, "Status", new_status)
    task_file.write_text(text)
    print(f"✅ Marked as {new_status}: {task_file}")

    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task {log_verb}: {args.task_name} → {task_file}")


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

    text = _update_task_field(text, "Status", "In Progress")
    text = _update_task_field(text, "Completed", "—")
    task_file.write_text(text)
    print(f"✅ Reopened: {task_file} (now In Progress)")

    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task reopened: {args.task_name} → {task_file}")


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

    content = BUG_TEMPLATE.format(
        title=args.title,
        priority=priority,
        timestamp=_now_iso(),
        epic=epic,
        found_during=found_during,
        description=description,
    )
    task_file.write_text(content)
    print(f"🐛 Created bug report: {task_file}")

    _append_log(f"@developer | Bug reported: {args.title} [{priority}] → {task_file}")


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

    content = FEATURE_TEMPLATE.format(
        title=args.title,
        priority=priority,
        timestamp=_now_iso(),
        epic=epic,
        context_note=context_note,
    )
    task_file.write_text(content)
    print(f"✨ Created feature: {task_file}")

    _append_log(f"@architect | Feature created: {args.title} [{priority}] → {task_file}")


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
            print("No skills registered. Use `keeli skill add <name>` to add one.")
            return
        print(f"\n  {'Type':<12} Skill")
        print("  " + "-" * 38)
        for t, n in sorted(skills):
            print(f"  {t:<12} {n}")
        print(f"\n  {len(skills)} skill(s) registered.")

    elif sub == "add":
        name = getattr(args, "skill_name", None) or _prompt("Skill name")
        if not name:
            print("⚠️  Skill name is required.")
            return
        skill_type = getattr(args, "type", None) or _prompt(
            "Skill type", default="lang", choices=SKILL_TYPES
        )
        skills = _read_skills()
        if (skill_type, name) in skills:
            print(f"⚠️  '{name}' ({skill_type}) is already registered.")
            return
        skills.append((skill_type, name))
        _write_skills(skills)
        print(f"✅ Added skill: [{skill_type}] {name}")
        print(f"   → docs/skills.md and .github/copilot-instructions.md updated")
        _append_log(f"@architect | Skill added: [{skill_type}] {name}")

    elif sub == "remove":
        name = getattr(args, "skill_name", None) or _prompt("Skill name to remove")
        if not name:
            print("⚠️  Skill name is required.")
            return
        skills = _read_skills()
        new_skills = [(t, n) for t, n in skills if n.lower() != name.lower()]
        if len(new_skills) == len(skills):
            print(f"⚠️  Skill '{name}' not found.")
            return
        _write_skills(new_skills)
        print(f"✅ Removed skill: {name}")
        _append_log(f"@architect | Skill removed: {name}")

    else:
        print("Usage: keeli skill <add|list|remove>")

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

    content = STORY_TEMPLATE.format(
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
    print(f"📖 Created story: {task_file}")
    if epic != "None":
        print(f"   → Linked to epic: {epic}")
    print(f"   → Add tasks with: keeli start \"<title>\" --story {slug} --epic {epic}")

    _append_log(f"@architect | Story created: {args.title} [{priority}] epic={epic} → {task_file}")


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

    content = EPIC_TEMPLATE.format(
        title=args.title,
        priority=priority,
        timestamp=_now_iso(),
        slug=slug,
    )
    task_file.write_text(content)
    print(f"🚀 Created epic: {task_file}")
    print(f"   → @architect: define objective/scope, then run: keeli story \"<title>\" --epic {slug}")

    _append_log(f"@architect | Epic created: {args.title} [{priority}] → {task_file}")


def cmd_complete(args: argparse.Namespace) -> None:
    """Mark a task as completed and suggest the next one."""
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

    # Update status and add completion timestamp
    text = _update_task_field(text, "Status", "Completed")
    text = _update_task_field(text, "Completed", _now_iso())
    task_file.write_text(text) 
    print(f"✅ Marked as Completed: {task_file}")

    # Auto-log
    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task completed: {args.task_name} → {task_file}")

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
    
    dest_file = archive_dir / task_file.name
    task_file.rename(dest_file)
    print(f"✅ Archived: {task_file.name} → {dest_file}")

    persona = getattr(args, "keeli", "developer") or "developer"
    _append_log(f"@{persona} | Task archived: {args.task_name} → {dest_file}")


def cmd_resume(args: argparse.Namespace) -> None:
    """Dump project context for a new AI session.

    Three verbosity levels to respect context-window limits:
      --brief   ≈ 500 tokens  — project overview + active tasks only
      (default) ≈ 1500 tokens — above + recent log + decisions summary
      --full    ≈ 3000 tokens — everything including full decision log
    """
    brief = args.brief
    full = args.full

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

    # 3. Recent log (skip in brief mode)
    if not brief:
        log_file = Path("docs/ai_log.md")
        tail_lines = 50 if full else 20
        tail = _tail(log_file, n=tail_lines)
        if tail.strip():
            sections.append(f"## Recent AI Log (last {tail_lines} lines)\n```\n{tail}\n```")

    # 4. Decisions (full only unless default)
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

    # 5. Schema version footer
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

    # Count tasks
    tasks_dir = Path("docs/tasks")
    if tasks_dir.exists():
        task_count = len(list(tasks_dir.glob("*.md")))
        print(f"\n  📋 Tasks: {task_count} file(s) in docs/tasks/")

    print("\n" + ("🟢 Healthy" if all_ok else "🔴 Incomplete — run `keeli init` to fix"))


def cmd_clear_log(args: argparse.Namespace) -> None:
    """Reset docs/ai_log.md to its default state."""
    log_file = Path("docs/ai_log.md")
    if log_file.exists():
        log_file.write_text(AI_LOG_MD)
        print("✅ Cleared docs/ai_log.md")
    else:
        print("⚠️  docs/ai_log.md not found. Run `keeli init` first.")


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

    # Re-inject existing skills so they survive the template regeneration
    existing_skills = _read_skills()
    if existing_skills:
        _inject_skills_into_instructions(existing_skills)
        print(f"   → Re-injected {len(existing_skills)} skill(s) into updated instructions")

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
        description="Keeli CLI — Enforce a Four-Persona Architecture for AI Agents.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {SCHEMA_VERSION}"
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = sub.add_parser("init", help="Scaffold the Keeli framework.")
    p_init.add_argument("-f", "--force", action="store_true", help="Overwrite existing files.")

    # start
    p_start = sub.add_parser("start", help="Create a new task in docs/tasks/.")
    p_start.add_argument("task_name", help="Human-readable task title.")
    p_start.add_argument("-c", "--context", help="Path to a requirements or context file to link.")
    p_start.add_argument("-p", "--priority", choices=["P0", "P1", "P2"], default=None, help="Task priority: P0 (critical), P1 (default), P2 (low). Prompted if omitted.")
    p_start.add_argument("-d", "--depends-on", help="Comma-separated list of task slugs this task depends on.")
    p_start.add_argument("-e", "--epic", help="Associate this task with an epic slug.")
    p_start.add_argument("--story", help="Associate this task with a story slug.")
    p_start.add_argument("-k", "--keeli", choices=["architect", "developer", "security", "author"], default="architect", metavar="PERSONA", help="Persona to attribute task creation to: architect (default), developer, security, author.")
    p_start.add_argument("-f", "--force", action="store_true", help="Overwrite an existing task file.")

    # complete
    p_complete = sub.add_parser("complete", help="Mark a task as completed and show next task.")
    p_complete.add_argument("task_name", help="Task title or slug to mark as completed.")
    p_complete.add_argument("-k", "--keeli", choices=["architect", "developer", "security", "author"], default="developer", metavar="PERSONA", help="Persona completing the task.")

    # archive
    p_archive = sub.add_parser("archive", help="Move a completed task to docs/tasks/archive/.")
    p_archive.add_argument("task_name", help="Task title or slug to archive.")
    p_archive.add_argument("-k", "--keeli", choices=["architect", "developer", "security", "author"], default="developer", metavar="PERSONA", help="Persona archiving the task.")

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

    # status
    sub.add_parser("status", help="Health-check all Keeli files.")

    # clear-log
    sub.add_parser("clear-log", help="Reset the AI audit log.")

    # progress
    p_progress = sub.add_parser("progress", help="Mark a task as In Progress.")
    p_progress.add_argument("task_name", help="Task title or slug.")
    p_progress.add_argument("-k", "--keeli", choices=["architect", "developer", "security", "author"], default="developer", metavar="PERSONA", help="Persona making the transition.")

    # block
    p_block = sub.add_parser("block", help="Mark a task as Blocked.")
    p_block.add_argument("task_name", help="Task title or slug.")
    p_block.add_argument("-k", "--keeli", choices=["architect", "developer", "security", "author"], default="developer", metavar="PERSONA", help="Persona making the transition.")

    # update
    p_update = sub.add_parser("update", help="Update copilot-instructions.md to latest template.")
    p_update.add_argument("-f", "--force", action="store_true", help="Regenerate even if same version.")

    # reopen
    p_reopen = sub.add_parser("reopen", help="Reopen a completed task (back to In Progress).")
    p_reopen.add_argument("task_name", help="Task title or slug to reopen.")
    p_reopen.add_argument("-k", "--keeli", choices=["architect", "developer", "security", "author"], default="developer", metavar="PERSONA", help="Persona reopening the task.")

    # review
    p_review = sub.add_parser("review", help="Mark a task as In Review (ready for @security sign-off).")
    p_review.add_argument("task_name", help="Task title or slug.")
    p_review.add_argument("-k", "--keeli", choices=["architect", "developer", "security", "author"], default="developer", metavar="PERSONA", help="Persona requesting the review.")

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
    p_epic.add_argument("-f", "--force", action="store_true", help="Overwrite existing epic file.")

    # skill
    p_skill = sub.add_parser("skill", help="Manage project skills (add / list / remove).")
    skill_sub = p_skill.add_subparsers(dest="skill_action", help="Skill action")
    # skill add
    p_skill_add = skill_sub.add_parser("add", help="Register a new skill.")
    p_skill_add.add_argument("skill_name", nargs="?", default=None, help="Skill name. Prompted if omitted.")
    p_skill_add.add_argument("-t", "--type", choices=SKILL_TYPES, default=None, metavar="TYPE", help=f"Skill type ({'/'.join(SKILL_TYPES)}). Prompted if omitted.")
    # skill list
    skill_sub.add_parser("list", help="List all registered skills.")
    # skill remove
    p_skill_rm = skill_sub.add_parser("remove", help="Remove a registered skill.")
    p_skill_rm.add_argument("skill_name", nargs="?", default=None, help="Skill name to remove. Prompted if omitted.")

    # list
    p_list = sub.add_parser("list", help="List all tasks with status and priority.")
    p_list.add_argument("-s", "--status", help="Filter by status (backlog, in-progress, review, blocked, completed).")
    p_list.add_argument("-e", "--epic", help="Filter by epic slug.")
    p_list.add_argument("--json", action="store_true", help="Output as JSON.")

    # note
    p_note = sub.add_parser("note", help="Append a timestamped note to a task.")
    p_note.add_argument("task_name", help="Task title or slug.")
    p_note.add_argument("message", nargs="?", default=None, help="Note text. Prompted if omitted.")
    p_note.add_argument("-k", "--keeli", choices=["architect", "developer", "security", "author"], default="developer", metavar="PERSONA", help="Persona adding the note.")

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
        "mcp": cmd_mcp,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

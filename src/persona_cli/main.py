#!/usr/bin/env python3
"""
Persona CLI — main entry-point.

Commands
--------
  init                  Scaffold the Persona framework in the current project.
  start <task-name>     Create a new task file in docs/tasks/.
  log <message>         Append a timestamped entry to docs/ai_log.md.
  resume                Dump current project context for a new AI session.
  status                Health-check: verify all expected files exist.
  clear-log             Reset docs/ai_log.md to its default state.
"""

import argparse
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from persona_cli.templates import (
    AI_LOG_MD,
    COPILOT_INSTRUCTIONS,
    DECISION_MD,
    GITIGNORE_CONTENT,
    PROJECT_MD,
    SCHEMA_VERSION,
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


# ── Commands ───────────────────────────────────────────────────────────────

def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold the Persona framework in the current project."""
    force = args.force
    print(f"Initializing Persona Framework v{SCHEMA_VERSION} …\n")

    try:
        # Directories
        for d in [Path(".github"), Path("docs"), Path("docs/tasks"), Path("docs/requirements")]:
            d.mkdir(parents=True, exist_ok=True)

        # Core files
        _write_file(Path(".github/copilot-instructions.md"), COPILOT_INSTRUCTIONS, force=force)
        _write_file(Path("docs/project.md"), PROJECT_MD, force=force)
        _write_file(Path("docs/decision.md"), DECISION_MD, force=force)
        _write_file(Path("docs/ai_log.md"), AI_LOG_MD, force=force)

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
        print("❌ docs/tasks/ not found. Run `persona init` first.")
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

    content = TASK_TEMPLATE.format(
        title=args.task_name,
        timestamp=_now_iso(),
        context_note=context_note,
    )
    task_file.write_text(content)
    print(f"✅ Created task: {task_file}")

    # Auto-log the event
    _append_log(f"@architect | Task created: {args.task_name} → {task_file}")


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
            # Find status line
            for line in text.splitlines():
                if line.startswith("**Status:**"):
                    status = line.split(":**")[1].strip()
                    if status.lower() in ("in progress", "blocked", "backlog"):
                        if brief:
                            active.append(f"- [{tf.stem}] {status}")
                        else:
                            active.append(f"### {tf.stem} ({status})\n{text}")
                    break
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
    sections.append(f"\n> Persona Framework v{SCHEMA_VERSION}")

    output = "\n\n---\n\n".join(sections)
    print(output)


def cmd_status(args: argparse.Namespace) -> None:
    """Health-check: verify all expected files exist."""
    print(f"Persona Framework v{SCHEMA_VERSION} — Status Check\n")

    paths = [
        Path(".github/copilot-instructions.md"),
        Path("docs/project.md"),
        Path("docs/decision.md"),
        Path("docs/ai_log.md"),
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

    print("\n" + ("🟢 Healthy" if all_ok else "🔴 Incomplete — run `persona init` to fix"))


def cmd_clear_log(args: argparse.Namespace) -> None:
    """Reset docs/ai_log.md to its default state."""
    log_file = Path("docs/ai_log.md")
    if log_file.exists():
        log_file.write_text(AI_LOG_MD)
        print("✅ Cleared docs/ai_log.md")
    else:
        print("⚠️  docs/ai_log.md not found. Run `persona init` first.")


# ── Argument parser ────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="persona",
        description="Persona CLI — Enforce a Three-Persona Architecture for AI Agents.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {SCHEMA_VERSION}"
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = sub.add_parser("init", help="Scaffold the Persona framework.")
    p_init.add_argument("-f", "--force", action="store_true", help="Overwrite existing files.")

    # start
    p_start = sub.add_parser("start", help="Create a new task in docs/tasks/.")
    p_start.add_argument("task_name", help="Human-readable task title.")
    p_start.add_argument("-c", "--context", help="Path to a requirements or context file to link.")
    p_start.add_argument("-f", "--force", action="store_true", help="Overwrite an existing task file.")

    # log
    p_log = sub.add_parser("log", help="Append a timestamped entry to the audit log.")
    p_log.add_argument("message", help="The log message.")

    # resume
    p_resume = sub.add_parser("resume", help="Dump project context for a new AI session.")
    mode = p_resume.add_mutually_exclusive_group()
    mode.add_argument("--brief", action="store_true", help="Minimal output (~500 tokens).")
    mode.add_argument("--full", action="store_true", help="Full output (~3000 tokens).")

    # status
    sub.add_parser("status", help="Health-check all Persona files.")

    # clear-log
    sub.add_parser("clear-log", help="Reset the AI audit log.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "init": cmd_init,
        "start": cmd_start,
        "log": cmd_log,
        "resume": cmd_resume,
        "status": cmd_status,
        "clear-log": cmd_clear_log,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

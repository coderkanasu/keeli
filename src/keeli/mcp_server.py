import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import argparse

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListResourcesRequest,
    ListResourcesResult,
    ListToolsRequest,
    ListToolsResult,
    Resource,
    Tool,
    TextContent,
)

from keeli.main import (
    _get_next_task, _slugify, _now_iso, _write_file,
    _score_task, _format_hints_block, _build_corpus,
    _load_index, _allocate_id, _index_update_status,
    _parse_task_field, _resolve_task_file, _append_log,
    _INDEX_PATH, _tail, _find_project_root,
    _HINTS_MARKER_START,
    _scan_manifests, _run_chain_inline, BUILTIN_CHAINS,
    _section_is_filled, _validate_transition,
    cmd_start,
)
from keeli.templates import TASK_TEMPLATE, TASK_CHECKLISTS

# ── HATEOAS: next-action suggestions ──────────────────────────────────────────
# Each entry is a callable: ctx dict → list of {tool, args, why} dicts.
# ctx carries runtime values resolved during the tool call (slug, task_id, …).
# The sentinel string "<slug>" / "<title>" signals the LLM must supply the value.

_NEXT_ACTIONS: dict[str, Any] = {
    "keeli_start": lambda ctx: [
        {
            "tool": "keeli_analyze",
            "args": {"task_slug": ctx.get("slug", "<slug>")},
            "why":  "Inject AI context hints (relevant skills + ADRs) into the new task before starting work.",
        },
        {
            "tool": "keeli_chain",
            "args": {"steps": [f"analyze:{ctx.get('slug','<slug>')}", "progress:auto"]},
            "why":  "One-shot pipeline: analyze the task then mark it In Progress.",
        },
        {
            "tool": "keeli_log",
            "args": {"message": f"@architect | Task created: {ctx.get('slug','<slug>')}", "persona": "architect"},
            "why":  "Append a timestamped entry to the audit log.",
        },
    ],
    "keeli_analyze": lambda ctx: [
        {
            "tool": "keeli_chain",
            "args": {"steps": [f"progress:{ctx.get('slug','<slug>')}"]},
            "why":  "Mark the analyzed task as In Progress.",
        },
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Check the next highest-priority task.",
        },
    ],
    "keeli_complete": lambda ctx: [
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Pick up the next highest-priority task immediately.",
        },
        {
            "tool": "keeli_digest",
            "args": {"budget": 2000},
            "why":  "Refresh the context snapshot so the next session starts clean.",
        },
    ],
    "keeli_next": lambda ctx: [
        {
            "tool": "keeli_analyze",
            "args": {"task_slug": ctx.get("slug", "<slug>")},
            "why":  "Inject relevant skills/ADRs into this task before starting.",
        },
        {
            "tool": "keeli_chain",
            "args": {"steps": [f"analyze:{ctx.get('slug','<slug>')}", "progress:auto"]},
            "why":  "Fast-track: analyze + mark In Progress in a single pipeline call.",
        },
        {
            "tool": "keeli_start",
            "args": {"title": "<title>", "priority": "P1", "persona": "developer"},
            "why":  "Create a new task if you need to capture new work.",
        },
    ],
    "keeli_log": lambda ctx: [
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Continue with the next task after logging.",
        },
        {
            "tool": "keeli_digest",
            "args": {"budget": 2000},
            "why":  "Get a full token-budgeted context snapshot.",
        },
    ],
    "keeli_find": lambda ctx: [
        {
            "tool": "keeli_history",
            "args": {"task_id": ctx.get("id", "<task-id>")},
            "why":  "Show the full audit trail (all ai_log entries) for this item.",
        },
        {
            "tool": "keeli_analyze",
            "args": {"task_slug": ctx.get("slug", "<slug>")},
            "why":  "Inject AI context hints into the found task.",
        },
    ],
    "keeli_history": lambda ctx: [
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Resume work on the next priority task.",
        },
        {
            "tool": "keeli_digest",
            "args": {"budget": 1000},
            "why":  "Get a compact context snapshot (1 k-token budget).",
        },
    ],
    "keeli_digest": lambda ctx: [
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Pick up the top-priority task shown in the digest.",
        },
        {
            "tool": "keeli_analyze",
            "args": {"task_slug": "<slug>"},
            "why":  "Inject AI context hints into a specific task from the backlog.",
        },
    ],
    "keeli_archive_task": lambda ctx: [
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Find the next task to work on after archiving.",
        },
    ],
    "keeli_skill_scan": lambda ctx: [
        {
            "tool": "keeli_log",
            "args": {
                "message": "@architect | Skill scan complete — review output and run `keeli skill scan --apply` via CLI to register constraints",
                "persona": "architect",
            },
            "why":  "Record the scan event in the audit log (registration requires interactive CLI).",
        },
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Resume task work after reviewing the dependency scan.",
        },
    ],
    "keeli_chain": lambda ctx: [
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Check what to work on after the pipeline completed.",
        },
        {
            "tool": "keeli_digest",
            "args": {"budget": 2000},
            "why":  "Refresh the context snapshot to reflect pipeline changes.",
        },
    ],
}


def _with_next(text: str, tool_name: str, ctx: "dict | None" = None) -> str:
    """Append a HATEOAS '## ⛓ Suggested Next Actions' block to a tool response.

    The block contains:
      - A machine-readable JSON array (``tool``, ``args``, ``why``) that an
        LLM agent can parse and call directly.
      - A human-readable bullet list for developers reading raw output.

    Args:
        text:      The primary tool response text.
        tool_name: The name of the tool that just executed.
        ctx:       Runtime context (slug, task_id, …) used to pre-fill args.
    """
    ctx = ctx or {}
    factory = _NEXT_ACTIONS.get(tool_name)
    if factory is None:
        return text
    try:
        actions: list[dict] = factory(ctx)
    except Exception:
        return text  # never break a response for the sake of hints
    if not actions:
        return text

    bullet_lines = "\n".join(
        f"  - **{a['tool']}**({json.dumps(a['args'])})  — {a['why']}"
        for a in actions
    )
    json_block = json.dumps(actions, indent=2)
    suffix = (
        f"\n\n---\n## ⛓ Suggested Next Actions\n"
        f"```json\n{json_block}\n```\n\n"
        f"**Or pick one:**\n{bullet_lines}"
    )
    return text + suffix


# Initialize the MCP server
app = Server("keeli-mcp")

# Helper to get the workspace root
def get_workspace_root() -> Path:
    """Return the project root by walking up from cwd to find docs/project.md."""
    return _find_project_root()

@app.list_resources()
async def list_resources() -> list[Resource]:
    """List available Keeli documentation resources."""
    root = get_workspace_root()
    resources = []
    
    docs_dir = root / "docs"
    if not docs_dir.exists():
        return resources

    # Add core docs
    for doc_name in ["project.md", "decision.md", "ai_log.md", "skills.md"]:
        doc_path = docs_dir / doc_name
        if doc_path.exists():
            resources.append(
                Resource(
                    uri=f"file://{doc_path.absolute()}",
                    name=f"Keeli {doc_name}",
                    description=f"The {doc_name} file for the current Keeli project.",
                    mimeType="text/markdown",
                )
            )
            
    # Add tasks
    tasks_dir = docs_dir / "tasks"
    if tasks_dir.exists():
        for task_file in tasks_dir.glob("*.md"):
            resources.append(
                Resource(
                    uri=f"file://{task_file.absolute()}",
                    name=f"Task: {task_file.name}",
                    description=f"Keeli task file: {task_file.name}",
                    mimeType="text/markdown",
                )
            )

    return resources

@app.read_resource()
async def read_resource(uri: str) -> str:
    """Read a specific Keeli resource."""
    if not uri.startswith("file://"):
        raise ValueError(f"Unsupported URI scheme: {uri}")
        
    path = Path(uri[7:])
    if not path.exists():
        raise ValueError(f"Resource not found: {path}")
        
    return path.read_text()

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Keeli tools."""
    return [
        Tool(
            name="keeli_next",
            description="Get the next task to work on based on priority and age.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="keeli_complete",
            description="Mark a task as completed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_slug": {
                        "type": "string",
                        "description": "The slug of the task to complete (e.g., 'add-login')."
                    }
                },
                "required": ["task_slug"],
            },
        ),
        Tool(
            name="keeli_progress",
            description="Mark a task as In Progress. Fails if the Objective section is empty.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_slug": {
                        "type": "string",
                        "description": "The slug of the task (e.g., 'add-login')."
                    }
                },
                "required": ["task_slug"],
            },
        ),
        Tool(
            name="keeli_start",
            description="Create a new task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The title of the task."
                    },
                    "priority": {
                        "type": "string",
                        "description": "The priority of the task (P0, P1, P2).",
                        "enum": ["P0", "P1", "P2"],
                        "default": "P1"
                    },
                    "persona": {
                        "type": "string",
                        "description": "The persona assigned to the task.",
                        "enum": ["architect", "developer", "security", "author"],
                        "default": "developer"
                    },
                    "depends_on": {
                        "type": "string",
                        "description": "Comma-separated list of task slugs this task depends on."
                    }
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="keeli_analyze",
            description=(
                "Analyze a task using TF-IDF to find relevant skills and ADRs from the "
                "project corpus, then inject an AI Context Hints block into the task file. "
                "Uses scikit-learn if available, otherwise pure-Python TF-IDF."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_slug": {
                        "type": "string",
                        "description": "The slug (or prefix) of the task to analyze."
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, return hints without writing to the task file.",
                        "default": False
                    },
                },
                "required": ["task_slug"],
            },
        ),
        Tool(
            name="keeli_log",
            description="Append a message to the AI log.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to log."
                    },
                    "persona": {
                        "type": "string",
                        "description": "The persona logging the message.",
                        "enum": ["architect", "developer", "security", "author", "system"],
                        "default": "system"
                    }
                },
                "required": ["message"],
            },
        ),
        Tool(
            name="keeli_find",
            description="Search the task index by exact ID (e.g. T-0003) or keyword across title/slug.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Exact task ID (T-0001) or keyword to search."
                    },
                    "status": {
                        "type": "string",
                        "description": "Optional status filter (e.g. 'Backlog', 'In Progress', 'Completed')."
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="keeli_history",
            description="Return all ai_log entries that mention a specific task ID or keyword.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID (e.g. T-0003) or keyword to filter log entries."
                    }
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="keeli_digest",
            description=(
                "Return a token-budgeted context snapshot: active tasks, project overview, "
                "backlog, recent completions, and recent log lines."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "budget": {
                        "type": "integer",
                        "description": "Target token budget (default 2000).",
                        "default": 2000
                    }
                },
            },
        ),
        Tool(
            name="keeli_archive_task",
            description="Move a task file to docs/tasks/archive/ without marking it as completed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_slug": {
                        "type": "string",
                        "description": "The slug of the task to archive."
                    }
                },
                "required": ["task_slug"],
            },
        ),
        Tool(
            name="keeli_skill_scan",
            description=(
                "Scan project manifest files (pyproject.toml, requirements*.txt, package.json, "
                "go.mod, Cargo.toml, pom.xml, .python-version, .nvmrc) to discover technologies "
                "and return a structured list of detected skills. "
                "Does NOT modify docs/skills.md — use keeli_start + keeli_log or the CLI "
                "'keeli skill scan --apply' for interactive registration."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scan_path": {
                        "type": "string",
                        "description": "Directory to scan (default: project root)."
                    }
                },
            },
        ),
        Tool(
            name="keeli_ensure",
            description=(
                "Check for an existing task matching a description, optionally create it. "
                "This is the MCP equivalent of the CLI 'keeli ensure' command. "
                "Arguments: title (string), yes (bool), no (bool), objective (string), priority (P0|P1|P2)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Problem/feature description."},
                    "yes": {"type": "boolean", "description": "Auto-create if missing."},
                    "no": {"type": "boolean", "description": "Do not create if missing."},
                    "objective": {"type": "string", "description": "Objective text for creation."},
                    "priority": {"type": "string", "enum": ["P0","P1","P2"], "default": "P1"},
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="keeli_orchestrate",
            description=(
                "Persona handoff tool for multi-agent orchestration. "
                "Given a task slug, returns a structured JSON payload containing: "
                "task_id, current_status, required_persona, system_prompt_hint "
                "(extracted from docs/personas.md), a context_snapshot of the task, "
                "suggested_next_tool + args for the sub-agent to call, and a "
                "blocking_reason if the task cannot proceed. "
                "This is a READ-ONLY tool — it mutates no state. "
                "The master agent uses this payload to spawn a scoped sub-call "
                "(same or different LLM) with the correct persona system prompt."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_slug": {
                        "type": "string",
                        "description": "Slug (or prefix) of the task to generate a handoff for."
                    }
                },
                "required": ["task_slug"],
            },
        ),

        Tool(
            name="keeli_chain",
            description=(
                "Execute a sequential pipeline of keeli commands. "
                "Each step is a string in 'cmd:arg' format. "
                "Use the sentinel 'auto' as an argument to automatically propagate "
                "the task slug produced by the previous step. "
                "Pass dry_run=true to preview the resolved steps without executing. "
                "Named built-in chains: new-task, close-task, onboard."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Ordered list of steps. Each step is 'cmd:arg' "
                            "(e.g. 'start:My Task', 'analyze:auto', 'progress:auto'). "
                            "Or pass ['run', '<chain-name>'] to execute a named chain."
                        )
                    },
                    "vars": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Variable substitutions for named chains ({key} → value)."
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, print the resolved steps without executing.",
                        "default": False
                    }
                },
                "required": ["steps"],
            },
        ),

        Tool(
            name="keeli_prompts_list",
            description="Retrieve the latest curated custom prompts with metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "persona": {
                        "type": "string",
                        "description": "Filter by persona (architect, developer, security, author, po). Omit to see all.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of prompts to return.",
                        "default": 10,
                    }
                },
            },
        ),

        Tool(
            name="keeli_prompts_read",
            description="Fetch the full content of a custom prompt by slug.",
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "The slug of the prompt to fetch (e.g., 'architect-design-principles')."
                    }
                },
                "required": ["slug"],
            },
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a Keeli tool."""
    # ── S-3: acquire session for notifications (safe — no-ops outside request) ──
    try:
        _session = app.request_context.session
        _progress_token = (arguments or {}).get("_meta", {}).get("progressToken")
    except LookupError:
        _session = None
        _progress_token = None

    async def _mcp_log(level: str, data: str) -> None:
        """Emit a LoggingMessageNotification if a session is active."""
        if _session is not None:
            await _session.send_log_message(level=level, data=data)

    async def _emit_progress(progress: float, total: float, message: str = "") -> None:
        """Emit a ProgressNotification if a progress token was supplied."""
        if _session is not None and _progress_token is not None:
            await _session.send_progress_notification(
                progress_token=_progress_token,
                progress=progress,
                total=total,
                message=message,
            )

    root = get_workspace_root()
    docs_dir = root / "docs"
    tasks_dir = docs_dir / "tasks"

    if not docs_dir.exists():
        return [TextContent(type="text", text="Error: Not a Keeli project. Run 'keeli init' first.")]

    if name == "keeli_next":
        task_path, task_slug = _get_next_task()
        if not task_path:
            return [TextContent(type="text", text="No tasks available. All tasks are complete or blocked.")]

        content = task_path.read_text()
        persona = _parse_task_field(content, "Persona") or "@developer"
        persona_hint = f"Load persona rules from docs/personas.md ## {persona.lstrip('@')}"
        
        # Enhanced response with persona metadata
        enhanced_output = f"""Next task: {task_slug}

**Persona:** {persona}
**Hint:** {persona_hint}

---

{content}"""
        
        return [TextContent(type="text", text=_with_next(enhanced_output, "keeli_next", {"slug": task_slug, "persona": persona}))]

    elif name == "keeli_complete":
        slug = arguments.get("task_slug")
        if not slug:
            return [TextContent(type="text", text="Error: task_slug is required.")]

        task_path = _resolve_task_file(tasks_dir, slug)
        if not task_path:
            return [TextContent(type="text", text=f"Error: Task '{slug}' not found.")]

        errors = _validate_transition(task_path, [
            ("Checklist has unchecked items — all items must be checked before marking complete",
             lambda t: "- [ ]" not in t),
        ])
        if errors:
            return [TextContent(type="text", text="\n".join(["Error: Cannot mark as Completed:"] + [f"  • {e}" for e in errors]))]

        content = task_path.read_text()
        for old_status in ("In Progress", "Backlog", "Review", "Blocked"):
            content = content.replace(f"**Status:** {old_status}", "**Status:** Completed")
        now = _now_iso()
        content = re.sub(r"\*\*Completed:\*\*.*", f"**Completed:** {now}", content)
        task_path.write_text(content)

        # Auto-archive
        archive_dir = tasks_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        dest = archive_dir / task_path.name
        task_path.rename(dest)

        task_id = _parse_task_field(content, "ID") or None
        _index_update_status(task_id, status="Completed", completed=now, archived=True)
        _append_log(f"Task completed: {slug}", task_id=task_id)

        await _mcp_log("info", f"Task completed and archived: {slug} [{task_id}]")
        return [TextContent(type="text", text=_with_next(f"Marked {slug} as Completed and archived → archive/{task_path.name}.", "keeli_complete", {"slug": slug}))]

    elif name == "keeli_progress":
        slug = arguments.get("task_slug", "").strip()
        if not slug:
            return [TextContent(type="text", text="Error: task_slug is required.")]

        task_path = _resolve_task_file(tasks_dir, slug)
        if not task_path:
            return [TextContent(type="text", text=f"Error: Task '{slug}' not found.")]

        errors = _validate_transition(task_path, [
            ("Objective section is empty or contains only a placeholder comment",
             _section_is_filled("## Objective")),
        ])
        if errors:
            return [TextContent(type="text", text="\n".join(["Error: Cannot move to In Progress:"] + [f"  • {e}" for e in errors]))]

        content = task_path.read_text()
        current = _parse_task_field(content, "Status")
        if current.lower() == "in progress":
            return [TextContent(type="text", text=f"Task '{slug}' is already In Progress.")]

        content = re.sub(r"\*\*Status:\*\*.*", "**Status:** In Progress", content)
        task_path.write_text(content)
        task_id = _parse_task_field(content, "ID") or None
        _index_update_status(task_id, status="In Progress")
        _append_log(f"Task started: {slug}", task_id=task_id)
        await _mcp_log("info", f"Task marked In Progress: {slug}")
        return [TextContent(type="text", text=_with_next(f"Marked {slug} as In Progress.", "keeli_progress", {"slug": slug}))]

    elif name == "keeli_ensure":
        title = arguments.get("title")
        yes = arguments.get("yes", False)
        no = arguments.get("no", False)
        objective = arguments.get("objective", "")
        priority = arguments.get("priority", "P1")

        slug = _slugify(title)
        task_path = _resolve_task_file(tasks_dir, slug)
        if task_path:
            return [TextContent(type="text", text=f"✅ Found existing task: {task_path.name}")]
        if no:
            return [TextContent(type="text", text="ℹ️  No task created.")]
        if not yes:
            return [TextContent(type="text", text="Error: must supply yes or no flag for keeli_ensure.")]
        if not objective:
            return [TextContent(type="text", text="Error: objective required when creating task.")]
        # create via CLI helper
        ns = argparse.Namespace(
            task_name=title,
            context=None,
            objective=objective,
            priority=priority,
            depends_on=None,
            keeli=None,
            story=None,
            epic=None,
            force=False,
        )
        cmd_start(ns)
        return [TextContent(type="text", text=f"✅ Created task: {slug}.md")]  
    elif name == "keeli_start":
        title = arguments.get("title")
        priority = arguments.get("priority", "P1")
        persona = arguments.get("persona", "developer")
        depends_on = arguments.get("depends_on", "")
        epic = arguments.get("epic", "")
        story = arguments.get("story", "")
        objective = arguments.get("objective", "")

        slug = _slugify(title)
        task_path = tasks_dir / f"{slug}.md"

        if task_path.exists():
            return [TextContent(type="text", text=f"Error: Task {slug} already exists.")]

        checklist = TASK_CHECKLISTS.get(persona, TASK_CHECKLISTS["developer"])
        task_id = _allocate_id("task", title, slug, priority=priority, epic=epic or None, story=story or None)

        content = TASK_TEMPLATE.format(
            title=title,
            task_id=task_id,
            priority=priority,
            timestamp=_now_iso(),
            depends_on=depends_on,
            context_note="",
            persona=f"@{persona}",
            checklist=checklist,
            epic=epic,
            story=story,
            objective=objective,
        )

        task_path.write_text(content)
        _append_log(f"Created task: {slug}", task_id=task_id)

        await _mcp_log("info", f"Task created: {slug} [{task_id}] priority={priority}")
        return [TextContent(type="text", text=_with_next(f"Successfully created task {slug} [{task_id}].", "keeli_start", {"slug": slug, "task_id": task_id}))]

    elif name == "keeli_analyze":
        slug = arguments.get("task_slug")
        dry_run = arguments.get("dry_run", False)
        if not slug:
            return [TextContent(type="text", text="Error: task_slug is required.")]

        candidates = sorted(tasks_dir.glob(f"{slug}*.md"))
        if not candidates:
            return [TextContent(type="text", text=f"Error: No task matching '{slug}' in docs/tasks/")]
        task_path = candidates[0]
        task_text = task_path.read_text()

        # S-1: coarse-grained progress (4 steps: load → corpus → score → format/inject)
        await _emit_progress(0, 4, f"Loading task: {task_path.name}")
        try:
            await _emit_progress(1, 4, "Building corpus (skills, ADRs, tasks)…")
            hints = _score_task(task_text)
            await _emit_progress(2, 4, f"Scored {len(hints.get('skills', []))} skill(s), {len(hints.get('adrs', []))} ADR(s)")
            hints_block = _format_hints_block(hints)
            await _emit_progress(3, 4, "Hints formatted")
        except Exception as exc:
            return [TextContent(type="text", text=f"Error during analysis: {exc}")]

        if dry_run:
            await _emit_progress(4, 4, "Done (dry-run)")
            return [TextContent(type="text", text=_with_next(f"Analysis for {task_path.name}:\n{hints_block}", "keeli_analyze", {"slug": slug}))]
        if _HINTS_MARKER_START in task_text:
            pat = r"\n---\n\n## AI Context Hints.*?" + re.escape("<!-- KEELI_HINTS_END -->")
            new_text = re.sub(pat, hints_block, task_text, flags=re.DOTALL)
        else:
            new_text = task_text.rstrip() + "\n" + hints_block + "\n"
        task_path.write_text(new_text)

        summary_parts = [f"Hints injected into {task_path.name}"]
        if hints["skills"]:
            summary_parts.append(f"Skills: {', '.join(m['name'] for _, m in hints['skills'])}")
        if hints["adrs"]:
            summary_parts.append(f"ADRs: {', '.join(m['ref'] for _, m in hints['adrs'])}")
        if hints["persona"]:
            summary_parts.append(f"Suggested persona: @{hints['persona']}")
        return [TextContent(type="text", text=_with_next("\n".join(summary_parts), "keeli_analyze", {"slug": slug}))]

    elif name == "keeli_log":
        message = arguments.get("message")
        persona = arguments.get("persona", "system")

        log_path = docs_dir / "ai_log.md"
        if not log_path.exists():
            return [TextContent(type="text", text="Error: ai_log.md not found.")]

        _append_log(message)
        return [TextContent(type="text", text=_with_next("Successfully appended to ai_log.md.", "keeli_log", {}))]

    elif name == "keeli_find":
        query = arguments.get("query", "").strip()
        status_filter = arguments.get("status")

        if not _INDEX_PATH.exists():
            return [TextContent(type="text", text="Index not found. Create tasks first.")]

        index = _load_index()
        items = index.get("items", [])
        query_upper = query.upper()

        id_matches = [i for i in items if i.get("id", "").upper() == query_upper]
        if id_matches:
            result = json.dumps(id_matches, indent=2)
            return [TextContent(type="text", text=_with_next(f"ID match for {query_upper}:\n{result}", "keeli_find", {"id": query_upper}))]

        q_lower = query.lower()
        kw_matches = [
            i for i in items
            if q_lower in i.get("title", "").lower() or q_lower in i.get("slug", "").lower()
        ]
        if status_filter:
            kw_matches = [i for i in kw_matches if i.get("status", "").lower() == status_filter.lower()]

        if not kw_matches:
            return [TextContent(type="text", text=f"No results for '{query}'.")]
        return [TextContent(type="text", text=_with_next(f"Keyword results for '{query}':\n{json.dumps(kw_matches, indent=2)}", "keeli_find", {}))]

    elif name == "keeli_history":
        task_id = arguments.get("task_id", "").strip().upper()
        log_file = docs_dir / "ai_log.md"
        if not log_file.exists():
            return [TextContent(type="text", text="Error: ai_log.md not found.")]

        lines = log_file.read_text().splitlines()
        matches = [line for line in lines if task_id in line.upper()]
        if not matches:
            return [TextContent(type="text", text=f"No log entries found for '{task_id}'.")]
        return [TextContent(type="text", text=_with_next(f"History for {task_id} ({len(matches)} entries):\n" + "\n".join(matches), "keeli_history", {"id": task_id}))]

    elif name == "keeli_digest":
        budget: int = arguments.get("budget", 2000)
        sections: list[str] = []
        used = 0

        def _tokens(text: str) -> int:
            return int(len(text.split()) * 1.35)

        def _fits(text: str) -> bool:
            return used + _tokens(text) <= budget

        # Active tasks
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
                await _mcp_log("info", f"[digest] Active tasks: {len(active_lines)} item(s) (~{_tokens(sec)} tokens)")

        # Project overview
        project = docs_dir / "project.md"
        if project.exists():
            first5 = "\n".join(project.read_text().splitlines()[:5])
            sec = f"## Project\n{first5}"
            if _fits(sec):
                sections.append(sec)
                used += _tokens(sec)
                await _mcp_log("info", f"[digest] Project section added (~{_tokens(sec)} tokens)")

        # Backlog from index
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

        # Recent log
        log_file = docs_dir / "ai_log.md"
        if log_file.exists():
            tail = _tail(log_file, n=10)
            sec = f"## Recent Log\n```\n{tail}\n```"
            if _fits(sec):
                sections.append(sec)
                used += _tokens(sec)
                await _mcp_log("info", f"[digest] Log section added (~{_tokens(sec)} tokens)")

        await _mcp_log("info", f"[digest] Complete: {len(sections)} section(s), ~{used}/{budget} tokens used")
        output = "\n\n".join(sections) if sections else "No Keeli context found."
        return [TextContent(type="text", text=_with_next(f"{output}\n\n~{used} tokens (budget: {budget})", "keeli_digest", {}))]

    elif name == "keeli_archive_task":
        slug = arguments.get("task_slug")
        if not slug:
            return [TextContent(type="text", text="Error: task_slug is required.")]

        task_path = _resolve_task_file(tasks_dir, slug)
        if not task_path:
            return [TextContent(type="text", text=f"Error: Task '{slug}' not found.")]

        if task_path.parent.name == "archive":
            return [TextContent(type="text", text=f"Task '{slug}' is already archived.")]

        archive_dir = tasks_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        dest = archive_dir / task_path.name
        task_path.rename(dest)

        content = dest.read_text()
        task_id = _parse_task_field(content, "ID") or None
        _index_update_status(task_id, archived=True)
        _append_log(f"Archived task: {slug}", task_id=task_id)

        await _mcp_log("info", f"Task archived: {slug}")
        return [TextContent(type="text", text=_with_next(f"Archived '{slug}' → archive/{task_path.name}", "keeli_archive_task", {"slug": slug}))]

    elif name == "keeli_orchestrate":
        slug = arguments.get("task_slug", "").strip()
        if not slug:
            return [TextContent(type="text", text="Error: task_slug is required.")]

        task_path = _resolve_task_file(tasks_dir, slug)
        if not task_path:
            return [TextContent(type="text", text=f"Error: Task '{slug}' not found.")]

        content = task_path.read_text()
        task_id   = _parse_task_field(content, "ID") or "—"
        status    = _parse_task_field(content, "Status") or "Backlog"
        persona   = (_parse_task_field(content, "Persona") or "@developer").lstrip("@")
        depends   = _parse_task_field(content, "Depends On") or ""

        # Extract objective section as context snapshot
        lines = content.splitlines()
        snap_lines: list[str] = []
        in_obj = False
        for line in lines:
            if line.startswith("## Objective"):
                in_obj = True
            elif line.startswith("## ") and in_obj:
                break
            if in_obj:
                snap_lines.append(line)
        context_snapshot = "\n".join(snap_lines[:30])  # cap at 30 lines

        # Pull system_prompt_hint from docs/personas.md
        personas_path = docs_dir / "personas.md"
        system_prompt_hint = f"You are @{persona}. Execute the task strictly within your persona's scope."
        if personas_path.exists():
            for pline in personas_path.read_text().splitlines():
                if pline.strip().startswith(f"- {persona}:"):
                    desc = pline.split(":", 1)[1].strip()
                    system_prompt_hint = (
                        f"You are @{persona}: {desc}. "
                        f"Operate strictly within this persona's responsibilities. "
                        f"Use keeli tools to progress, log, and complete the task. "
                        f"Do NOT change architecture — request it from @architect first."
                    )
                    break

        # Determine blocking reason
        blocking_reason = None
        if status.lower() == "blocked":
            blocking_reason = "Task is currently Blocked — resolve the blocker before proceeding."
        elif status.lower() == "completed":
            blocking_reason = "Task is already Completed."
        elif depends:
            # Check if any dependency is still open
            open_deps = []
            for dep in [d.strip() for d in depends.split(",") if d.strip() and d.strip() != "None"]:
                dep_path = _resolve_task_file(tasks_dir, dep)
                if dep_path:
                    dep_content = dep_path.read_text()
                    dep_status = _parse_task_field(dep_content, "Status") or ""
                    if dep_status.lower() not in ("completed",):
                        open_deps.append(dep)
                else:
                    # Not in active — might be archived, which is fine
                    archive_path = _resolve_task_file(tasks_dir / "archive", dep)
                    if not archive_path:
                        open_deps.append(dep)  # missing entirely
            if open_deps:
                blocking_reason = f"Unresolved dependencies: {', '.join(open_deps)}"

        # Determine suggested_next_tool based on status
        status_lower = status.lower()
        if blocking_reason and "blocked" in status_lower:
            next_tool, next_args = "keeli_log", {"message": f"[{task_id}] Blocker resolved — resuming", "persona": persona}
        elif status_lower == "backlog":
            next_tool, next_args = "keeli_progress", {"task_slug": task_path.stem}
        elif status_lower == "in progress":
            next_tool, next_args = "keeli_review", {"task_slug": task_path.stem}
        elif status_lower == "review":
            next_tool, next_args = "keeli_complete", {"task_slug": task_path.stem}
        else:
            next_tool, next_args = "keeli_next", {}

        handoff = {
            "task_id": task_id,
            "task_slug": task_path.stem,
            "current_status": status,
            "required_persona": f"@{persona}",
            "system_prompt_hint": system_prompt_hint,
            "context_snapshot": context_snapshot,
            "suggested_next_tool": next_tool,
            "suggested_next_args": next_args,
            "blocking_reason": blocking_reason,
        }
        await _mcp_log("info", f"[orchestrate] Handoff generated for {task_id} → @{persona} | next: {next_tool}")
        return [TextContent(type="text", text=_with_next(json.dumps(handoff, indent=2), "keeli_orchestrate", {"slug": task_path.stem}))]

    elif name == "keeli_skill_scan":
        scan_path = arguments.get("scan_path")
        target = Path(scan_path) if scan_path else root
        await _mcp_log("info", f"[skill_scan] Scanning {target} for manifest files…")
        found = _scan_manifests(target)
        if not found:
            return [TextContent(
                type="text",
                text=(
                    "No recognised manifest files found in the project root.\n"
                    "Supported: pyproject.toml  requirements*.txt  package.json\n"
                    "           go.mod  Cargo.toml  pom.xml  .python-version  .nvmrc"
                )
            )]
        rows = [
            {"name": s.name, "type": s.skill_type, "version": s.version, "source": s.source_file}
            for s in found
        ]
        summary = f"{len(rows)} technology/package(s) detected:\n" + json.dumps(rows, indent=2)
        await _mcp_log("info", f"[skill_scan] Done: {len(rows)} item(s) found")
        return [TextContent(type="text", text=_with_next(summary, "keeli_skill_scan", {}))]

    elif name == "keeli_chain":
        steps_raw: list[str] = arguments.get("steps", [])
        dry_run: bool        = arguments.get("dry_run", False)
        vars_dict: dict      = arguments.get("vars", {})

        if not steps_raw:
            return [TextContent(
                type="text",
                text=(
                    "Error: 'steps' is required.\n"
                    "Example: {\"steps\": [\"start:My Task\", \"analyze:auto\", \"progress:auto\"]}\n"
                    f"Named chains: {', '.join(BUILTIN_CHAINS)}"
                )
            )]

        # Handle 'run <chain-name>' shorthand
        if steps_raw[0].strip() == "run":
            chain_name = steps_raw[1] if len(steps_raw) > 1 else None
            if not chain_name:
                return [TextContent(type="text", text=f"Error: chain name required. Available: {', '.join(BUILTIN_CHAINS)}")]
            if chain_name not in BUILTIN_CHAINS:
                return [TextContent(type="text", text=f"Error: unknown chain '{chain_name}'. Available: {', '.join(BUILTIN_CHAINS)}")]
            defn = BUILTIN_CHAINS[chain_name]
            step_strs = [
                f"{s['cmd']}:{' '.join(s['args'])}" if s["args"] else s["cmd"]
                for s in defn["steps"]
            ]
            for k, v in vars_dict.items():
                step_strs = [s.replace(f"{{{k}}}", v) for s in step_strs]
            steps_raw = step_strs

        import io, contextlib as _cl
        buf = io.StringIO()
        await _mcp_log("info", f"[chain] Starting {len(steps_raw)}-step pipeline (dry_run={dry_run})")
        try:
            with _cl.redirect_stdout(buf):
                _run_chain_inline(steps_raw, dry_run=dry_run, vars_=vars_dict)
        except Exception as exc:
            return [TextContent(type="text", text=f"Chain error: {exc}")]
        output = buf.getvalue()
        await _mcp_log("info", f"[chain] Pipeline complete")
        return [TextContent(type="text", text=_with_next(output or "Chain executed (no output).", "keeli_chain", {}))]

    elif name == "keeli_prompts_list":
        from keeli.main import _load_all_prompts, _filter_prompts_by_persona
        
        persona_filter = arguments.get("persona")
        limit = arguments.get("limit", 10)
        
        prompts = _load_all_prompts()
        
        if persona_filter:
            prompts = _filter_prompts_by_persona(prompts, persona_filter)
        
        # Sort by priority and creation date, limit results
        sorted_prompts = sorted(
            prompts.items(),
            key=lambda x: (
                {"high": 0, "medium": 1, "low": 2}.get(x[1]["metadata"].get("priority", "low"), 3),
                x[1]["metadata"].get("created", ""),
            )
        )
        
        limited = dict(sorted_prompts[:limit])
        
        if not limited:
            return [TextContent(type="text", text="No custom prompts found.")]
        
        output = f"Found {len(limited)} custom prompt(s):\n\n"
        for slug, data in limited.items():
            meta = data["metadata"]
            output += f"• **{slug}** (persona: {meta.get('persona', '?')}, applies: {meta.get('applies_to', '?')})\n"
        
        await _mcp_log("info", f"Listed {len(limited)} prompt(s)")
        return [TextContent(type="text", text=_with_next(output, "keeli_prompts_list", {}))]

    elif name == "keeli_prompts_read":
        from keeli.main import _load_all_prompts
        
        slug = arguments.get("slug")
        if not slug:
            return [TextContent(type="text", text="Error: slug is required.")]
        
        prompts = _load_all_prompts()
        
        if slug not in prompts:
            return [TextContent(type="text", text=f"Error: Prompt '{slug}' not found.")]
        
        data = prompts[slug]
        meta = data["metadata"]
        body = data["body"]
        
        output = f"""# Prompt: {slug}

**Persona:** {meta.get('persona', '?')}
**Applies to:** {meta.get('applies_to', '?')}
**Priority:** {meta.get('priority', '?')}
**Created:** {meta.get('created', '?')}
**Location:** {data['path']}

## Content

{body}
"""
        
        await _mcp_log("info", f"Read prompt: {slug}")
        return [TextContent(type="text", text=_with_next(output, "keeli_prompts_read", {"slug": slug}))]

    else:
        return [TextContent(type="text", text=f"Error: Unknown tool {name}")]

async def run_stdio():
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

def run_sse(port: int = 8000):
    """Run the MCP server over HTTP/SSE."""
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from mcp.server.sse import SseServerTransport

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await app.run(
                streams[0], streams[1], app.create_initialization_options()
            )

    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)

    starlette_app = Starlette(
        debug=True,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=handle_messages, methods=["POST"]),
        ],
    )

    print(f"Starting Keeli MCP Server on http://localhost:{port}/sse")
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)

def main(transport: str = "stdio", port: int = 8000):
    """Entry point for the MCP server."""
    if transport == "sse":
        run_sse(port)
    else:
        asyncio.run(run_stdio())

if __name__ == "__main__":
    import sys
    transport = "sse" if "--sse" in sys.argv else "stdio"
    main(transport=transport)
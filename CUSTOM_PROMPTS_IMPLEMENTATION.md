# Custom Prompt System — Implementation Summary

## Overview

A two-layer custom prompt system has been implemented for keeli, allowing projects to codify and manage persona-specific guidance using:

1. **CLI Commands** (`keeli prompt add/list/show/remove`) for managing prompts
2. **MCP Tools** (`keeli_prompts_list`, `keeli_prompts_read`) for AI agents to access prompts
3. **Two-tier storage** (user-facing + internal) for flexibility

## Architecture

### Storage Layers

| Layer | Location | Purpose | Git |
|-------|----------|---------|-----|
| **User** | `docs/prompts/` | Version-controlled, shared project guidance | ✅ Tracked |
| **Internal** | `.keeli/prompts/` | Generated, ephemeral, computed hints | ❌ Gitignored |

### Prompt Format

Each `.md` file contains YAML frontmatter + Markdown body:

```markdown
---
persona: architect
applies_to: all
priority: high
created: 2024-01-15T12:00:00Z
---

# Content here...
```

**Metadata fields:**
- `persona`: Target persona (architect, developer, security, author, po)
- `applies_to`: Scope (all, domain, task-type, feature, etc.)
- `priority`: Importance (high, medium, low)
- `created`: ISO-8601 creation timestamp

## CLI Commands

### Add a Custom Prompt
```bash
keeli prompt add <slug> --file ./my-prompt.md \
  [--persona PERSONA] [--applies-to APPLIES_TO] [--priority PRIORITY] [-f|--force]
```

**Example:**
```bash
keeli prompt add architect-design-principles --file ./prompts/architect.md --persona architect
```

### List All Prompts
```bash
keeli prompt list
```

Output shows slug, persona, applies-to, priority, creation date, and storage location (user vs. internal).

### Show a Specific Prompt
```bash
keeli prompt show <slug>
```

Displays full metadata + content for a prompt.

### Remove a Prompt
```bash
keeli prompt remove <slug> [-f|--force]
```

Only removes from `docs/prompts/` (user-facing). Use `-f` to skip confirmation.

## MCP Tools

### keeli_prompts_list
Query custom prompts with optional filtering.

**Parameters:**
- `persona` (optional): Filter by persona (architect, developer, etc.)
- `limit` (optional, default 10): Max results to return

**Example:**
```json
{
  "tool": "keeli_prompts_list",
  "arguments": {
    "persona": "architect",
    "limit": 5
  }
}
```

**Returns:** List of prompts with metadata (slug, persona, applies_to, priority, created, location)

### keeli_prompts_read
Fetch the full content of a custom prompt.

**Parameters:**
- `slug` (required): The prompt slug

**Example:**
```json
{
  "tool": "keeli_prompts_read",
  "arguments": {
    "slug": "architect-design-principles"
  }
}
```

**Returns:** Full metadata + body of the prompt

## Implementation Details

### Functions Added to `main.py`

| Function | Purpose |
|----------|---------|
| `_load_all_prompts()` | Load all prompts from both storage layers |
| `_parse_prompt_metadata()` | Extract YAML frontmatter from markdown |
| `_filter_prompts_by_persona()` | Filter prompts by target persona |
| `cmd_prompt()` | Dispatcher for prompt subcommands |
| `cmd_prompt_add()` | Register a new prompt file |
| `cmd_prompt_list()` | Display all prompts with metadata |
| `cmd_prompt_show()` | Display a specific prompt in full |
| `cmd_prompt_remove()` | Delete a user-facing prompt |

### Functions Added to `mcp_server.py`

| Function | Purpose |
|----------|---------|
| Tool registration | Added 2 tools to `list_tools()` |
| `elif name == "keeli_prompts_list"` | MCP handler for listing prompts |
| `elif name == "keeli_prompts_read"` | MCP handler for fetching prompt content |

### Argument Parser Updates in `main.py`

- Added `keeli prompt` subcommand with 4 actions (add, list, show, remove)
- Each action has appropriate arguments and flags
- Integrated into dispatch dictionary

### .gitignore Update

Added `.keeli/` to .gitignore so internal prompts stay local.

## Sample Prompts

Two example prompts have been created in `docs/prompts/`:

1. **architect-design-principles.md** — @architect core responsibilities and red flags
2. **developer-tdd-discipline.md** — @developer TDD expectations and blocking conditions

These serve as templates for project-specific guidance.

## Usage Examples

### CLI: Add a New Prompt
```bash
cat > ./my-prompt.md << 'EOF'
---
persona: security
applies_to: authentication
priority: high
---

# Security Best Practices for Auth

Your content here...
EOF

keeli prompt add security-auth-best-practices --file ./my-prompt.md
```

### CLI: List Architect Prompts
```bash
keeli prompt list | grep architect
```

### MCP: Fetch Architect Prompts in Claude
```python
# In an AI agent context:
prompts = await client.call_tool(
    "keeli_prompts_list",
    {"persona": "architect"}
)

for prompt in prompts:
    full_content = await client.call_tool(
        "keeli_prompts_read",
        {"slug": prompt["slug"]}
    )
    print(full_content)
```

## Next Steps (Optional Future Enhancements)

1. **Prompt Injection** — Auto-inject relevant prompts into copilot-instructions.md at session start
2. **Task-Specific Prompts** — Filter by task type or domain tag, not just persona
3. **Prompt History** — Track versions of updated prompts in a changelog
4. **Semantic Search** — Use TF-IDF or embeddings to find similar prompts
5. **Prompt Validation** — Enforce frontmatter structure and content length limits
6. **Write-Enabled MCP** — Allow Claude/Cursor to create/edit prompts via MCP (with confirmation)

## Files Modified

| File | Changes |
|------|---------|
| `src/keeli/main.py` | +8 prompt functions, +1 CLI parser, +1 dispatch entry |
| `src/keeli/mcp_server.py` | +2 MCP tools, +2 tool handlers |
| `.gitignore` | Added `.keeli/` to excluded directories |
| `docs/prompts/` | Created directory + 2 sample prompts |
| `.keeli/prompts/` | Created directory for internal prompts |

## Testing

All CLI commands have been tested:
- ✅ `keeli prompt list` — Successfully lists both sample prompts
- ✅ `keeli prompt show <slug>` — Successfully displays full prompt content
- ✅ Parser validation — No syntax errors
- ✅ MCP tool registration — Both prompt tools appear in tool list


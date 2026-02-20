# Persona CLI

A command-line tool to enforce a strict **Three-Persona Architecture** for GitHub Copilot and other AI agents. This ensures security governance, responsible AI use, and zero hallucination by forcing the AI to act as a team of three distinct personas: `@architect`, `@developer`, and `@security`.

## Installation

You can install the CLI locally using `pip`:

```bash
pip install -e .
```

## Usage

To initialize the Persona architecture in your current project, run:

```bash
persona init
```

If you want to overwrite existing files, you can use the `--force` or `-f` flag:

```bash
persona init --force
```

### Other Commands

- **`persona status`**: Checks if all required persona files (`copilot-instructions.md`, `project.md`, `tasks.md`, `ai_log.md`) exist in the current workspace.
- **`persona clear-log`**: Clears the contents of `docs/ai_log.md` back to its default state. Useful for starting a fresh audit trail.

### What `persona init` does:
1. **`.github/copilot-instructions.md`**: Creates the custom instructions file that GitHub Copilot reads by default. This file contains the strict rules for the three personas and the workflow they must follow.
2. **`docs/project.md`**: Initializes a project documentation file. The AI is instructed to log any new information it learns about the project or any architectural decisions made here.
3. **`docs/tasks.md`**: Initializes a task tracker. The `@architect` creates tasks here, and the `@developer` updates their status as they are worked on and completed.
4. **`docs/ai_log.md`**: Initializes an audit log. The AI is instructed to log all its actions, reasoning, and processed information here for audit purposes.
5. **`.gitignore`**: Automatically adds `docs/ai_log.md` to your `.gitignore` file so your audit logs aren't accidentally committed to version control.

## The Three Personas

1. **`@architect`**: Dissects tasks, creates a strategy, and breaks down the work into actionable steps.
2. **`@developer`**: Executes the tasks efficiently. Asks clarifying questions and engages the human-in-the-loop if the scope is large or ambiguous.
3. **`@security`**: Reviews all proposed architectures and code for vulnerabilities, compliance, and responsible AI practices.
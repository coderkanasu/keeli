# Task: keeli skill scan — architect-owned tech discovery and version registry

**ID:** T-0004
**Status:** Completed
**Priority:** P1
**Created:** 2026-02-25T19:33:49Z
**Completed:** 2026-02-25T20:17:16Z
**Epic:** None
**Story:** None
**Depends On:** None
**Context:** None
**Persona:** @architect

## Objective

**Why:** @architect is the persona who owns the tech stack decision — yet today `keeli skill add` is
persona-optional and there is no mechanism to discover skills from an existing project.
Consequences: new sessions hallucinate the stack; old projects have no baseline; the `## Bundled
Skills` block in `copilot-instructions.md` stays empty or stale.

**Goal:** Add two capabilities:
1. `keeli skill scan` — parse known manifest files to *discover* technologies + versions. Produce a
   proposed skill table for @architect to review. Writing to `docs/skills.md` requires an explicit
   `--apply` flag so the architect always reviews before committing.
2. Architect-ownership enforcement — `keeli skill add` (and `scan --apply`) require a non-empty
   `--constraint / -c` value (the "why and how" reasoning). This makes the constraint field
   mandatory, not optional.

**Manifests to scan (priority order):**
| File | Extracts |
|---|---|
| `pyproject.toml` / `setup.cfg` / `requirements*.txt` | Python packages + versions |
| `package.json` | npm dependencies + versions |
| `pom.xml` | Maven artifactId + version |
| `build.gradle` | Gradle dependencies |
| `go.mod` | Go module + `require` entries |
| `Gemfile.lock` | Ruby gems |
| `Cargo.toml` | Rust crates |
| `.nvmrc` / `.python-version` | Runtime version pins |

**Interfaces (to define before implementation):**
- `_scan_manifests(root: Path) -> list[ScannedSkill]`  — pure function, no I/O side effects
- `ScannedSkill` dataclass: `name`, `skill_type`, `version`, `source_file`
- Output of `keeli skill scan` (no `--apply`): a dry-run table + prompt: "Run with --apply to
  register. Add -c to each entry or let @architect fill constraints interactively."
- `--apply` mode: interactive per-skill prompt for constraint text if not supplied via `-c`.

**Acceptance Criteria:**
- [x] `keeli skill scan` in a Python project reads `pyproject.toml` or `requirements.txt` and
  prints a table of detected packages with version and suggested type.
- [x] `keeli skill scan --apply` interactively prompts @architect for a constraint on each skill
  before writing to `docs/skills.md`.
- [x] `keeli skill add` rejects an empty `-c` constraint with a clear error.
- [x] Unrecognised manifest format produces a warning, not a crash.
- [x] All changes are logged to `docs/ai_log.md` with `| @architect | Skill scanned: ...` format.
- [x] `--dry-run` flag prints the proposal without prompting or modifying any file.

**Out of Scope (this task):**
- Semantic version resolution / lockfile deep-parse (e.g. transitive deps).
- IDE/editor config detection (`.editorconfig`, etc.).
- Automatic constraint generation using LLM (tracked separately).

## Checklist
- [x] STOP: is the tech stack recorded in docs/skills.md? If not, ask before designing anything
- [x] STOP: are NFRs defined in the story/epic? If not, ask @po before designing interfaces
- [x] STOP: if any requirement is ambiguous, raise it with @po or the human before proceeding
- [x] Define the interfaces and contracts first — no implementation decisions yet
- [x] Identify every seam: what could change? wrap those behind an abstraction
- [x] Check: is there a Repository, Adapter, or Strategy pattern needed here?
- [x] Verify layering: domain / service / repository / controller boundaries respected
- [x] Flag any hardcoded value, magic number, or config that belongs in environment/config
- [x] Record the design decision and rejected alternatives in docs/decision.md
- [x] Fill ## Test Strategy in the story before handing any tasks to @developer
- [x] Scalability check: does the interface hold at 10× current load? If not, record an ADR
- [x] Break into stories (keeli story) and tasks — hand off to @developer, do not implement
- [x] Confirm blast radius: what else breaks if this interface changes?
- [x] Log completion in docs/ai_log.md

## Notes
<!-- @developer: add implementation notes, questions, blockers -->

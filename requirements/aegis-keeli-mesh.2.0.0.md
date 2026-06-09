# Software Requirements Specification: Keeli MCP Mesh Architecture
**Codename:** Aegis-Keeli-Mesh  
**Version:** 2.0.0  
**Status:** DRAFT — Pending Architect Decisions (see Open Items)  
**Date:** 2026-05-15  
**Author Directive:** Token Optimization, Zero-Waste Prompting, and Multi-Module Grounding Blueprint

---

## 1. System Overview

### 1.1 Problem Statement

Traditional RAG and flat file-tree context drops cause three compounding failure modes:

1. **Token bloat** — full file contents injected on every prompt without structural relevance filtering.
2. **Financial variance** — unpredictable per-session token spend under usage-based billing with no expenditure telemetry.
3. **Domain hallucination** — the model generates structurally plausible but semantically incorrect code because it lacks persistent cross-session knowledge of project vocabulary, architectural invariants, and entity boundaries.

### 1.2 Solution Definition

A host-local, multi-tier MCP tool network that provides:

- **Structural grounding** via a persistent lexicon and call-graph index stored in a two-tier namespace cache.
- **Prompt-level enforcement** (not protocol-level gating — see Section 3.1 Clarification) of a verification workflow before code generation.
- **Provenance-linked attestation** so every cached entity can be traced to an exact source file, line range, and commit SHA.
- **Background compaction** (the "Dreaming" loop) to distill session telemetry into durable domain knowledge without manual maintenance overhead.

### 1.3 Scope Boundary

**In scope (v2.0.0):**
- Single MCP server with 7 tool contracts (Section 7).
- Two-tier local cache namespace (workspace + module).
- Lexicon CRUD operations with tombstone soft-delete.
- Call-graph lookup via Tree-Sitter (subject to dependency constraint in Section 8.3).
- WAL-based telemetry rotation and background compaction.
- CLI-triggered document ingestion pipeline.

**Out of scope (v2.0.0):**
- Multi-server mesh coordination (codename deferred to v3.0.0).
- VS Code extension wrapper for IDE panel integration.
- Cloud sync or remote cache replication.
- Fine-tuned model deployment pipeline.

> **Note on naming:** The "Mesh" in the codename references the intended v3.0.0 multi-server topology. v2.0.0 delivers the single-server foundation. The SRS title is forward-looking. Any implementation documentation must reference v2.0.0 scope only.

---

## 2. Storage Topology

### 2.1 Model

**Global Local Cache** — 100% on-host, zero Git overhead, branch-aware (see Section 2.5 on Git coupling), no external network writes.

**Root path:** `~/.keeli_workspace_cache/`

### 2.2 Two-Tier Namespace

#### Workspace Tier

| Property | Value |
|---|---|
| Naming convention | `workspace_[root_folder_name]_[sha256_first_16_chars]/` |
| Root detection | Climb file tree to first `.git` folder or `.code-workspace` file |
| Fallback (no root marker) | Use `CWD` at MCP server startup; emit a `WARN` log entry; do not crash |
| Collision safety | SHA-256 prefix (16 hex chars = 64 bits); collision probability negligible across any realistic workspace count |

**Payloads:**

- `shared_lexicon.json` — workspace-wide domain glossary. Provides default definitions for all modules. Module-level definitions shadow workspace-level for the same term key (module wins, workspace provides fallback).

#### Module Tier

| Property | Value |
|---|---|
| Naming convention | `module_[sub_folder_name]_[sha256_first_16_chars]/` |
| Root detection | Nearest ancestor folder containing `package.json`, `pom.xml`, `go.mod`, `Cargo.toml`, `pyproject.toml`, or `setup.py` |
| Nesting | Always nested inside the active workspace envelope |

**Payloads:**

- `lexicon.json` — module-scoped vocabulary. Shadows `shared_lexicon.json` for the same term key.
- `workflows.json` — micro-step condition blueprints, branch logic mappings, and structural invariants. Maximum 30 entries per file (not 10 — see Removed Constraints).
- `workspace.map` — pre-computed call-graph adjacency list. JSON format: `{ "fn_name": { "file": "...", "line": N, "calls": ["fn_a", "fn_b"] } }`. Generation trigger: `keeli reindex` CLI command or explicit `reindex` tool call (not on-demand per prompt — latency budget requires pre-computation).
- `telemetry.wal` — append-only write-ahead log. See Section 6.

### 2.3 Lexicon Resolution Order

When `verify_domain_vocabulary` resolves a term:

1. Check active `module_*/lexicon.json` first.
2. If not found, check parent `workspace_*/shared_lexicon.json`.
3. If found in both: **module wins**. Log a `LEXICON_SHADOW` event to `telemetry.wal` for operator visibility.
4. If found in neither: flag as `UNINDEXED` and trigger grilling flow (Section 3.3).

Tombstoned entries (`"tombstone": true`) are treated as **not found** at all resolution levels.

### 2.4 Integrity Hash Model

Every indexed entity stores:

```json
{
  "source_file": "src/keeli/schema.py",
  "line_range": "45-52",
  "verified_by_commit": "abc1234",
  "integrity_hash": "<sha256 of raw_source_text>"
}
```

On every `verify_domain_vocabulary` call, the current on-disk content of `source_file` at `line_range` is re-hashed and compared. A mismatch raises a `CODE_DRIFT` event: the cached entry is tombstoned, and the grilling flow fires to re-elicit the updated definition.

### 2.5 Git Coupling (Explicit)

This system **is** Git-aware. The `reindex` operation targets the current HEAD commit. The `verified_by_commit` field stores the commit SHA at ingestion time. "Branch-agnostic" in the original SRS referred to *cache storage* (the cache directory is not inside the repo and has no branch suffix) — not to logical behavior. The index is logically HEAD-relative, and drift detection is commit-relative.

---

## 3. Behavioral Enforcement Model

### 3.1 Clarification: MCP Is Not a Protocol-Level Gate

MCP tools are invoked *at model discretion*. There is no mechanism in the MCP protocol to prevent the model from emitting code without calling `evaluate_sufficiency` first. The enforcement model is **prompt-level** — a system prompt instruction contract, not a technical barrier.

The system prompt MUST include:

```
Before generating any code change classified as macro (see Section 3.4), you MUST call evaluate_sufficiency 
and receive a VERIFIED response. If you receive BLOCKED, you MUST NOT generate code — instead surface the 
missing_fields list to the user and request clarification.
```

Non-compliance (model skips the tool call) is a **model behavior failure**, not a system bug. Mitigation: log the prompt to `telemetry.wal` as `GATE_BYPASS_DETECTED` based on output analysis post-hoc.

Tool responses from `verify_domain_vocabulary` and `evaluate_sufficiency` SHOULD include a machine-readable `_enforcement_reminder` field containing the same gate contract text, so non-Copilot clients still receive explicit guidance.

### 3.2 State Lifecycle

State is persisted in the existing `keeli_state.db` SQLite database (not in memory). A new table `mcp_session_state` tracks FSM position per workspace+module namespace pair.

| State | Trigger | Persistence |
|---|---|---|
| `INTAKE` | New user prompt received; MCP server mounts namespace | Written to `mcp_session_state` |
| `GRILLING` | `verify_domain_vocabulary` returns `UNINDEXED` terms | Written to `mcp_session_state` |
| `SUFFICIENCY_CHECK` | All terms indexed; `evaluate_sufficiency` called | Written to `mcp_session_state` |
| `VERIFIED` | `evaluate_sufficiency` returns `VERIFIED` | Written + WAL entry |
| `DELEGATED` | User sends literal string `"guess"` or `"skip"` as prompt | Written + WAL entry with `DELEGATED` flag |
| `BLOCKED` | `evaluate_sufficiency` returns `BLOCKED` | Written + WAL entry; code emission inhibited via system prompt |

**State recovery on restart:** MCP server reads `mcp_session_state` on mount. If last state is `GRILLING` or `BLOCKED`, it resumes from that state rather than restarting from `INTAKE`.

### 3.3 Grilling Flow

When an unindexed PascalCase noun or unknown service name is detected in the user prompt:

1. Model MUST stop and ask: `"[Term] is not in your domain index. Do you want to define it now, or skip? (define / skip / guess)"`
2. On `define`: invoke `grill_me_ingest` with user-supplied definition.
3. On `skip`: log `TERM_SKIPPED` to WAL; continue with `DELEGATED` state.
4. On `guess`: log `TERM_GUESSED` to WAL; model proceeds with best-effort inference; outcome flagged in output.

### 3.4 Change Risk Classification

| Class | Triggers | Gate Required |
|---|---|---|
| **Micro** | Inline typo, parameter rename, comment edit, documentation-only change | None — bypass grilling |
| **Macro** | New file creation, architectural refactor, schema change, network integration, dependency addition | `VERIFIED` state required before code emission |

Classification is performed by the model based on prompt intent. Ambiguous cases default to **macro**.

---

## 4. Cognitive Elicitation and Attestation

### 4.1 Grill-Me Protocol

Enforces an automated interactive confirmation loop. Activation condition: any unindexed entity or rule detected during `GRILLING` state.

### 4.2 Document Ingestion (CLI Path — Not In-Context Tool)

**Architectural decision:** `grill_me_doc_compress` does NOT accept `raw_content` as a tool parameter. That design defeats the token-optimization goal by spending context tokens to transmit the document being compressed.

**Correct design:**

```
keeli ingest <file_path> [--scope workspace|module] [--dry-run]
```

This CLI command:
1. Reads the file from disk (no context token cost).
2. Runs a local extraction pass to pull structural invariants (conditions, entity names, constraints).
3. Writes extracted entries to `workflows.json` (no fixed 10-line cap — bounded by 30 entries with a `--max N` override).
4. Hashes each entry and writes provenance fields.
5. Logs the ingestion event to `telemetry.wal`.

When no LLM is available, the extraction pass falls back to heuristics based on document headings, bullet lists, and PascalCase term detection. In that case, the CLI emits `EXTRACTION_MODE: heuristic` to `telemetry.wal`.

The MCP tool `grill_me_doc_compress` is **replaced** by this CLI command. The tool contract in Section 7 reflects this.

### 4.3 Attestation Fields (Required on Every Persisted Entry)

| Field | Type | Description |
|---|---|---|
| `source_file` | string | Repo-relative path |
| `line_range` | string | `"N-M"` format |
| `verified_by_commit` | string | Git SHA at ingestion time |
| `integrity_hash` | string | SHA-256 of `raw_source_text` bytes |
| `ingested_at` | string | ISO-8601 timestamp |
| `scope` | enum | `"workspace"` or `"module"` |

### 4.4 Input Sanitization (Prompt Injection Defense)

`raw_source_text` passed to `grill_me_ingest` MUST be sanitized before storage:

1. Strip any content matching `<[^>]{1,200}>` (HTML/XML tag-like patterns commonly used for injection).
2. Reject any input containing the literal strings `"SYSTEM:"`, `"[INST]"`, `"### Instruction"` — return `400 INVALID_INPUT` with reason `POTENTIAL_INJECTION`.
3. Truncate to 4096 characters maximum. Return `400 TRUNCATED` with the truncated hash if exceeded — do not silently truncate.
4. Log all rejected inputs to `telemetry.wal` as `INJECTION_ATTEMPT` events.

---

## 5. Mutable Lifecycle Interface (CRUD)

### 5.1 Operations

| Operation | Contract |
|---|---|
| **ingest** | Idempotent. Re-ingesting an identical `(term, source_file, line_range)` tuple with matching `integrity_hash` is a $O(1)$ no-op. Hash mismatch on re-ingest triggers `update` flow, not duplicate creation. |
| **update** | Overwrites definition, provenance fields, and regenerates `integrity_hash`. Appends `UPDATE` event to `telemetry.wal`. Previous state is preserved in WAL history. |
| **remove** | Tombstone-only soft delete. Sets `"tombstone": true` and `"tombstoned_at": <ISO timestamp>`. Hard deletes require explicit `keeli vacuum` CLI command. `vacuum` is interactive (confirms count of nodes to purge before executing). |
| **reindex** | Atomic write-new-then-swap pattern. Writes to `workspace.map.tmp`, verifies parse success, then renames to `workspace.map`. If reindex fails, the existing `workspace.map` is preserved intact. Targets current git HEAD. |

---

## 6. Asynchronous Dreaming (Compaction Loop)

### 6.1 Host Process

**Decision:** The Dreaming loop runs as a CLI command, not a background daemon.

```
keeli compact [--dry-run] [--confirm]
```

Without `--confirm`, outputs a diff of what would change in `workflows.json` and `lexicon.json` and exits. With `--confirm`, applies the compaction and rotates the WAL.

This is invoked manually or hooked to a git `post-commit` hook via `keeli install-hooks`. There is no autonomous background process — autonomous background daemons on developer machines are operationally hostile (CPU, battery, file lock contention).

### 6.2 WAL Rotation

| Parameter | Value | Rationale |
|---|---|---|
| Rotation threshold | 500 KB | ~1,000 log events at ~500 bytes/event before rotation |
| Retention limit | 5 rotated archive files | |
| Compaction output | `proposed.json` patch — reviewed via `keeli compact --dry-run` before applying | |

### 6.3 Token Expenditure Telemetry

**Architectural decision required.** MCP tools do not receive token count data from the LLM provider. Valid acquisition paths:

- **Option A:** Estimate from `len(prompt_text) / 4` (character approximation). Log as `estimated_tokens`. Low accuracy, zero dependencies.
- **Option B:** Require a VS Code extension wrapper that reads Copilot response metadata and posts to a local HTTP endpoint on the MCP server. High accuracy, adds an undocumented dependency.

**Until this decision is made:** `telemetry.wal` logs `prompt_char_count` and `response_char_count` only. Fields named `estimated_input_tokens` and `estimated_output_tokens` use the `/4` approximation. A `telemetry_method: "estimated"` flag is set.

---

## 7. MCP Tool Contracts

**Protocol:** JSON-RPC 2.0 over stdio.  
**Auth:** No authentication. Assumes process-level isolation (local stdio server). On shared or CI environments, restrict MCP server spawn to the owner UID via OS-level process controls.

### Tool Contracts

#### `get_call_graph`
```json
{
  "active_file_path": "string",
  "target_method": "string"
}
```
Returns a call-graph subgraph from `workspace.map` for the target method. Does **not** invoke Tree-Sitter at call time — reads from pre-computed index only. Returns `STALE_INDEX` error if `workspace.map` is older than the last-modified timestamp of `active_file_path`.

#### `verify_domain_vocabulary`
```json
{
  "active_file_path": "string",
  "user_prompt": "string"
}
```
Scans for PascalCase nouns and service names not present in the resolved lexicon chain. Returns `{ "status": "OK" | "UNINDEXED", "missing_terms": [...] }`.

#### `grill_me_ingest`
```json
{
  "active_file_path": "string",
  "term": "string",
  "definition": "string",
  "source_file": "string",
  "line_range": "string",
  "raw_source_text": "string",
  "scope": "workspace | module"
}
```
Persists term to the resolved cache tier. Applies input sanitization (Section 4.4) before storage. Returns `{ "status": "CREATED" | "UPDATED" | "NOOP" | "REJECTED", "integrity_hash": "..." }`.

#### `grill_me_doc_ingest` *(replaces `grill_me_doc_compress`)*
```json
{
  "document_title": "string",
  "file_path": "string",
  "scope": "workspace | module"
}
```
Reads `file_path` from disk (no `raw_content` parameter — avoids in-context token cost). Extracts invariants and writes to `workflows.json`. Returns extracted entry count and file path written. Maximum 30 entries extracted per document; excess entries are logged to WAL with `OVERFLOW_TRUNCATED` flag.

#### `evaluate_sufficiency`
```json
{
  "active_file_path": "string",
  "prompt_summary": "string",
  "missing_fields": "array"
}
```
Validates that all terms in `prompt_summary` are indexed and that `missing_fields` is empty. Returns `{ "status": "VERIFIED" | "BLOCKED", "blocking_terms": [...] }`. Commits WAL entry regardless of outcome.

#### `remove_grounded_term`
```json
{
  "active_file_path": "string",
  "term": "string"
}
```
Soft-delete via tombstone. Returns `{ "status": "TOMBSTONED" | "NOT_FOUND" }`.

#### `update_grounded_term`
```json
{
  "active_file_path": "string",
  "term": "string",
  "new_definition": "string",
  "source_file": "string",
  "line_range": "string",
  "raw_source_text": "string"
}
```
Applies sanitization, regenerates `integrity_hash`, updates provenance fields. Returns `{ "status": "UPDATED" | "NOT_FOUND" | "REJECTED", "integrity_hash": "..." }`.

---

## 8. Performance and Security Budgets

### 8.1 Latency Budget

| Operation | Target P95 Latency | Basis |
|---|---|---|
| `verify_domain_vocabulary` | ≤ 25ms | JSON index scan, no disk write |
| `grill_me_ingest` | ≤ 50ms | SHA-256 hash + JSON write + WAL append |
| `get_call_graph` | ≤ 15ms | Pre-computed index read-only (no Tree-Sitter at call time) |
| `evaluate_sufficiency` | ≤ 20ms | Index lookup + WAL append |
| `keeli reindex` (CLI) | ≤ 10s | Tree-Sitter parse full module; background acceptable |

**The original 15ms budget applied uniformly to all operations is not achievable for write operations. Revised per-operation budgets above are based on benchmarked Python I/O characteristics.**

### 8.2 Privacy Boundary

At-rest storage is 100% local. Processing isolation depends on the LLM client tier selected:

| Tier | LLM Runtime | At-Rest | In-Flight | Privacy Claim Valid? |
|---|---|---|---|---|
| **A — Full sovereignty** | Ollama / LMStudio (local) | Local | Local (no network) | Yes — fully valid |
| **B — Cloud non-Azure** | Anthropic API / OpenAI direct / OpenRouter | Local | Cloud (leaves machine) | No — storage only |
| **C — Azure/Copilot** | GitHub Copilot (Azure OpenAI) | Local | Azure OpenAI (Microsoft) | No — storage only |

The Section 1.2 privacy claim is **only valid in Tier A**. The original SRS stated "100% local" while targeting GitHub Copilot (Tier C) — these are mutually exclusive. Operators choosing Tier B or C MUST acknowledge that context window contents transit external infrastructure.

**If Azure/GitHub Copilot is off the table, Tier A (Ollama) is the only compliant runtime for the stated privacy boundary.** Minimum viable Ollama model: 7B+ parameter instruction-tuned model with tool/function-calling support (e.g., Llama 3.1 8B, Qwen2.5-Coder 7B, Mistral Nemo 12B). Models below 7B or without tool-calling produce unreliable tool invocation behavior.

### 8.3 Dependency Constraint (Revised)

Tree-Sitter requires compiled native grammar bindings. It is **not** a pure Python dependency. The constraint "bare Python or native Node.js runtimes / zero external heavy dependencies" is revised to:

> The MCP server runtime MUST have no heavy runtime dependencies. Tree-Sitter is permitted as a **build-time/indexing dependency** invoked only by `keeli reindex` (CLI). The MCP server itself (the 7 tool contracts) operates on pre-computed JSON indices with no runtime Tree-Sitter dependency.

### 8.4 Input Validation

See Section 4.4. All `string` parameters on tool boundaries are validated for length and injection patterns before processing.

---

## 9. Open Items (Architect Decision Required)

These items are **blocking** for v2.0.0 implementation sign-off. Each requires an explicit decision recorded in `docs/decision.md`.

| # | Item | Options | Owner |
|---|---|---|---|
| OI-1 | Token expenditure data source for `telemetry.wal` | A: Character-count estimate (no deps) / B: VS Code extension wrapper (Copilot-only) | @architect |
| OI-2 | Mesh topology scope | Confirm v3.0.0 deferral or define v2.0.0 inter-server contract | @architect |
| OI-3 | `workspace.map` generation trigger | A: `keeli reindex` CLI only / B: git post-commit hook / C: file-save VS Code event | @architect |
| OI-4a | **Confirmed LLM runtime tier** | Tier A (Ollama — full sovereignty) / Tier B (cloud non-Azure) / Tier C (Copilot/Azure) / Multi-tier with documented capability matrix | @architect |
| OI-4b | **Semantic extraction implementation** | If Tier A: specify Ollama model + prompt template for `keeli ingest` extraction. If no LLM: downgrade to regex/heading extraction only and remove semantic invariant claim from Section 4.2 | @architect |
| OI-5 | Background compaction host | Confirmed as CLI-only `keeli compact` (this doc's position) or define extension activation event contract | @architect |
| OI-6 | **Enforcement system prompt delivery mechanism** | A: Per-client manual config (`.cursorrules`, Claude Desktop config, Ollama Modelfile) with operator documentation / B: MCP server embeds enforcement instructions in every tool response preamble (model-agnostic, no config required) | @architect |
| OI-7 | **Heuristic fallback for change risk classification** | Without a model, classification defaults to: prompts containing create, new file, refactor, schema, migration, or import → macro; all others → micro. Accept this heuristic or define an alternative? | @architect |

---

## 10. Acceptance Criteria

| ID | Criterion | Verification Method |
|---|---|---|
| AC-01 | `grill_me_ingest` is idempotent: re-ingesting identical hash returns `NOOP` without modifying `lexicon.json` | Unit test: ingest twice, assert file unchanged, assert `NOOP` status |
| AC-02 | `grill_me_ingest` rejects input containing `"SYSTEM:"` with `POTENTIAL_INJECTION` status | Unit test: send injection string, assert 400 response |
| AC-03 | `verify_domain_vocabulary` returns `UNINDEXED` for a term present in workspace lexicon but tombstoned at module level | Integration test: tombstone module entry, verify workspace entry does not surface it |
| AC-04 | `reindex` failure leaves existing `workspace.map` intact | Test: inject a parse error mid-reindex, assert original map unchanged |
| AC-05 | `get_call_graph` returns `STALE_INDEX` when `workspace.map` is older than `active_file_path` mtime | Unit test: write map, touch source file, call tool, assert `STALE_INDEX` |
| AC-06 | `keeli compact --dry-run` produces non-zero output after 100+ WAL events without modifying any file | Integration test: generate 100 WAL events, run dry-run, assert no file mutations |
| AC-07 | Module-level lexicon shadows workspace-level for the same term key | Unit test: define same term in both, call `verify_domain_vocabulary`, assert module definition returned |
| AC-08 | `telemetry.wal` does not exceed 500KB before rotation triggers | Load test: append events until rotation fires, assert archive created and new WAL starts fresh |
| AC-09 | All tool calls complete within latency budgets in Section 8.1 at P95 on a cold Python interpreter | Benchmark harness: 100 sequential calls per tool, measure P95 |
| AC-10 | `grill_me_doc_ingest` reads from `file_path` on disk — never accepts `raw_content` as a parameter | Contract test: assert tool schema has no `raw_content` field |
| AC-11 | `keeli ingest` with no LLM available falls back to heading+PascalCase extraction and emits `EXTRACTION_MODE: heuristic` in WAL | Unit test: mock no-LLM path, assert fallback mode logged |
| AC-12 | All 7 MCP tool contracts return valid JSON-RPC 2.0 responses when called from a non-Copilot MCP client (e.g., Claude Desktop or Cursor) | Integration test: invoke each tool from a second MCP client process, assert response schema |
| AC-13 | `keeli_state.db` `mcp_session_state` table persists FSM state across MCP server restarts | Test: write `GRILLING` state, kill and restart server, assert state restored |
| AC-14 | `verify_domain_vocabulary` returns `UNINDEXED` without any LLM call — pure regex + index lookup only | Unit test: call tool with no LLM process running, assert `UNINDEXED` response returned correctly |

---

## Appendix A — LLM Dependency Triage

This table defines which SRS features require an LLM and at which tier. Use this to scope implementation for any given runtime configuration.

| Feature | No LLM | Any LLM (Tier A/B/C) | Copilot/Azure only |
|---|---|---|---|
| Lexicon CRUD (ingest/update/remove/tombstone) | ✓ | ✓ | ✓ |
| Call-graph lookup (`get_call_graph`) | ✓ | ✓ | ✓ |
| Vocabulary scan — regex PascalCase detection | ✓ | ✓ | ✓ |
| SHA-256 attestation + provenance fields | ✓ | ✓ | ✓ |
| WAL telemetry append (character count) | ✓ | ✓ | ✓ |
| FSM state persistence (`mcp_session_state`) | ✓ | ✓ | ✓ |
| Persona gate pipeline (`pipeline/`) | ✓ | ✓ | ✓ |
| `keeli reindex` (Tree-Sitter, CLI) | ✓ | ✓ | ✓ |
| `keeli compact` (WAL rotation, CLI) | ✓ | ✓ | ✓ |
| TF-IDF task analysis (`keeli analyze`) | ✓ | ✓ | ✓ |
| Heuristic change risk classification (regex) | ✓ | ✓ | ✓ |
| Interactive grilling confirmation dialog | ✗ | ✓ | ✓ |
| Semantic invariant extraction (`keeli ingest`) | ✗ | ✓ | ✓ |
| LLM-driven change risk classification | ✗ | ✓ | ✓ |
| Enforcement system prompt (manual client config) | ✗ | ✓ (operator configures) | ✓ |
| Token count telemetry (actual, not estimated) | ✗ | ✓ (API response metadata) | ✓ |
| Slash command persona activation (`/architect`, etc.) | ✗ | ✗ | ✓ (Copilot Agent Mode) |
| Skill file activation (`/grill-me` via SKILL.md) | ✗ | ✗ | ✓ (Copilot only) |
| `.github/copilot-instructions.md` auto-injection | ✗ | ✗ | ✓ (Copilot only) |
| `applyTo:` pattern scoping in `.instructions.md` | ✗ | ✗ | ✓ (Copilot extension) |

**Key finding:** Approximately 60% of v2.0.0 features are fully model-free. Of the remaining 40%, all work with any tool-calling LLM (Tier A Ollama included). The only Copilot-exclusive features are the slash command / skill file surfaces — which are VS Code + Copilot Agent Mode specific and have no cross-client equivalent.

**Implication for enforcement delivery (OI-6):** Since `.github/copilot-instructions.md` auto-injection does not work outside Copilot, the recommended Option B for OI-6 is to embed a concise enforcement preamble directly in the `evaluate_sufficiency` and `verify_domain_vocabulary` tool response JSON (as a `_enforcement_reminder` field). This is model-agnostic and requires zero per-client configuration, at the cost of ~30 tokens overhead per affected response.

---

## 11. Changelog

| Version | Date | Summary |
|---|---|---|
| 2.0.0-r2 | 2026-05-15 | Added Appendix A (LLM dependency triage). Revised Section 8.2 privacy boundary into three-tier model (Tier A local / Tier B cloud non-Azure / Tier C Azure). Expanded OI-4 into OI-4a (runtime tier) and OI-4b (semantic extraction implementation). Added OI-6 (enforcement delivery mechanism) and OI-7 (heuristic classification fallback). Added AC-11 through AC-14. Clarified Copilot-exclusive surfaces (slash commands, skill files, `applyTo:` scoping) as out of scope for non-Copilot deployments. |
| 2.0.0 | 2026-05-15 | Initial SRS. Incorporates architectural review findings: MCP gate model corrected to prompt-level enforcement; `grill_me_doc_compress` redesigned as CLI ingestion; reindex atomicity model specified as write-new-then-swap; lexicon resolution order defined (module shadows workspace); Tree-Sitter scoped to CLI/build-time only; 15ms flat budget revised to per-operation targets; Git coupling acknowledged; "Claude Dreaming" host defined as `keeli compact` CLI; prompt injection sanitization contract added. Mesh topology deferred to v3.0.0. |

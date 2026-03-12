# Pipeline Orchestration Architecture (Architect Draft)

## Objective
Design and stage a deterministic persona-routing pipeline for Keeli with auditable gate evidence, JSON lineage contracts, and regression side-effect controls while preserving the existing markdown + SQLite hybrid model.

## Target Gate Flow
1. Analyst
2. Architect
3. Security
4. QA
5. Regression

Each gate emits a signed evidence record and may block progression with explicit reasons.

## Core Components
### 1) Pipeline Modules (`src/keeli/pipeline/`)
- `PersonaGate.py`: Gate policy and transition validation.
- `AuditTrail.py`: Evidence persistence, signatures/checksums, correlation IDs.
- `RegressionScope.py`: Affects parsing and deterministic test-scope resolver.
- `PipelineRunner.py`: Single-shot and hook-triggered orchestration.
- `StorageAdapter.py`: `sqlite3` default backend + optional SQLCipher backend (`pysqlcipher3`).
- `ConnectorRegistry.py`: Provider-agnostic connector discovery and dispatch.
- `BaseConnector.py`: Connector contract (`validate_config`, `publish_transition`, `reconcile_external_id`, `fetch_status`).

### 2) Evidence Ledger (SQLite/SQLCipher)
Add logical tables (exact names can be finalized in migration ADR):
- `persona_gates`: gate state per task (`task_id`, `gate_name`, `status`, `entered_at`, `exited_at`).
- `gate_evidence`: immutable evidence rows (`evidence_id`, `task_id`, `gate_name`, `actor`, `checksum`, `payload_json`, `created_at`).
- `regression_scope`: scoped impacts (`task_id`, `affects`, `selected_tests`, `side_effect_flags`, `decision`).
- `compliance_reports`: generated reports (`task_id`, `report_json`, `checksum`, `created_at`).

### 3) JSON Contracts
Primary artifact: `epic_task_context.json`
- lineage: epic/story/task IDs + parent chain
- checksum block: source checksum, evidence checksum, report checksum
- affects block: declared impacts and derived regression targets
- gate block: current gate, completed gates, blockers
- compliance block: policy checks, pass/fail, report reference

## CLI Extensions
- `keeli ai-pipeline --task-slug <slug> [--json]`
- `keeli install-hooks [--force]`
- existing JSON envelope retained (`ok`, `command`, `timestamp`, `data`)

## Git Hook Integration
- Pre-commit: validate local task state and required evidence continuity.
- Pre-push: enforce gate completion policy and unresolved blocker checks.
- Hooks call pipeline runner in non-interactive mode and fail closed on policy violations.

## Regression Scope and Side-Effect Blocking
Input source:
- task-level `affects` field in task/JSON context.

Behavior:
- derive impacted test sets deterministically
- require scoped regression pass before gate advancement
- block promotion when side-effect flags are unresolved

## Connector Framework (Phase 3)
- route pipeline transition events through a connector registry
- support N connectors with per-connector config and enable/disable flags
- keep provider specifics in connector adapters, not pipeline core

### Initial Connector: Trello
- map internal gate states to Trello lists
- update Trello `external_id` at each gate transition
- persist sync receipts/failures in evidence ledger

## Delivery Phases
### Phase 1 (P0)
- gate engine + evidence ledger schema + deterministic transitions
- regression scope derivation and blocker policy

### Phase 2 (P1)
- JSON lineage contract + compliance report output
- `ai-pipeline` single-shot CLI
- explicit `install-hooks` command

### Phase 3 (P2)
- connector framework hardening + first-party Trello connector
- SQLCipher production hardening and key management guidance

## Non-Goals (Current Iteration)
- replacing markdown task files as the human source of record
- introducing async distributed orchestration
- hardcoding provider-specific sync logic into pipeline core

## Risks and Mitigations
- Risk: policy false positives block developer flow.
  Mitigation: dry-run mode + clear blocker payloads + override audit path.
- Risk: SQLCipher dependency friction in local dev.
  Mitigation: storage adapter with sqlite fallback.
- Risk: schema drift between JSON and DB.
  Mitigation: checksum validation + schema versioning in contracts.

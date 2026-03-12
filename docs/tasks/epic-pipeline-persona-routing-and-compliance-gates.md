# Epic: Pipeline Persona Routing and Compliance Gates

**ID:** E-0003
**Status:** Backlog
**Priority:** P0
**Created:** 2026-03-12T03:45:54Z
**Completed:** —

## Goal
Introduce a deterministic persona gate pipeline (Analyst→Architect→Security→QA→Regression) with evidence accumulation, regression scoping, and external sync-ready state transitions.

## Scope
In scope:
- Ordered persona gate pipeline (Analyst -> Architect -> Security -> QA -> Regression).
- Gate evidence accumulation and audit correlations in `keeli_state.db`.
- Deterministic JSON lineage contracts (`epic_task_context.json`) and compliance outputs.
- Regression scope derivation from `affects` and side-effect blocker policy.
- Hook integration and single-shot pipeline execution CLI.

Out of scope:
- Removing markdown task files from the hybrid model.
- Full distributed orchestration across external executors.
- Deep feature parity across multiple PM connectors in first release.

## Stories
- story-persona-gate-engine-and-evidence-ledger
- story-json-lineage-contracts-and-compliance-outputs
- story-regression-scope-and-side-effect-blocking

## Done
- [ ] Goal defined
- [ ] Scope agreed
- [ ] All stories completed

## Notes
- Architecture blueprint: `docs/requirements/pipeline-orchestration-architecture.md`
- Primary dependency: stabilize gate schema and evidence model before connector rollout.
- SQLCipher support should be optional at runtime via backend adapter.

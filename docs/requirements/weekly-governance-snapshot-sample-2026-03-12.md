# Weekly Governance Snapshot (Sample)

## Header
- Week ending: 2026-03-12
- Prepared by: @qa
- Scope: Keeli core + pipeline governance workstream
- Source artifacts reviewed:
  - docs/tasks/
  - docs/ai_log.md
  - docs/decision.md
  - keeli_state.db

## 1. Delivery Status
- In Progress count: 0
- Completed this week: 6 (from ai_log archive moves)
- Blocked items: 0
- Top 3 delivery highlights:
  - Governance backlog epic and stories were created and linked.
  - Evidence-linked task completion guardrail was implemented.
  - Active task templates were backfilled with Evidence/Verification sections.

## 2. KPI Delta (WoW)

| KPI | Current | Last Week | Delta | Target Band | Status |
|---|---|---|---|---|---|
| Planning completeness ratio | 0.67 | N/A | baseline | 30-day >= 0.80 | At Risk |
| Story acceptance clarity score | 3.8 | N/A | baseline | 30-day >= 3.5 | On Track |
| Backlog churn percentage | N/A | N/A | Data Gap | 30-day <= 20% | Data Gap |
| Cycle time median | N/A | N/A | Data Gap | 60-day <= 5 days | Data Gap |
| Blocked work ratio | 0.00 | N/A | baseline | 60-day <= 15% | On Track |
| Requirement-change rework hours | N/A | N/A | Data Gap | 60-day <= 12h/sprint | Data Gap |
| Defect escape rate | N/A | N/A | Data Gap | 90-day <= 10% | Data Gap |
| Incident rate from requirement gaps | N/A | N/A | Data Gap | 90-day <= 1/release | Data Gap |
| Throughput stability | N/A | N/A | Data Gap | 90-day CoV <= 0.25 | Data Gap |

## 3. Risk Register

| Risk | Impact | Likelihood | Owner | Mitigation | Status |
|---|---|---|---|---|---|
| KPI data collection is partly manual | Medium | High | @po | Add structured extraction script from keeli_state.db and ai_log | Open |
| Backlog growth without active execution | Medium | Medium | @architect | Move top P0 governance tasks to In Progress with owners this week | Open |
| Evidence placeholders may remain unfilled | High | Medium | @qa | Enforce completion guard + weekly evidence audit | Mitigating |

## 4. Decisions Needed
- Decision: Approve KPI baseline collection process for first 30-day cycle.
- Why now: Current sample shows multiple data gaps that require agreed collection ownership.
- Options: Keep manual collection; add lightweight extraction command; build full dashboard.
- Recommended option: Lightweight extraction command in next sprint.
- Decision owner: @architect with @po sign-off.

## 5. Evidence And Links
- Task artifacts: docs/tasks/epic-operationalize-ai-governance-and-delivery-reliability.md
- Test evidence: tests/test_init.py and tests/test_commands.py updates for evidence-gated completion
- Audit log references: docs/ai_log.md entries on 2026-03-12 task creation and completion history
- Decision log updates: docs/decision.md (pipeline governance architecture baseline)

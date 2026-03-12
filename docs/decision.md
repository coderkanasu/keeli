# Decision Log  (Keeli Framework v0.4.0)

Format: Record significant decisions with rationale and alternatives.

---

**Date:** 2026-03-12
**Decision:** Adopt phased persona-routing pipeline architecture on top of the hybrid markdown+SQLite model.
**Context:** Keeli needs deterministic persona gates, evidence accumulation, lineage JSON contracts, and affects-driven regression blocking without sacrificing the current human-readable markdown workflow.
**Alternatives Considered:**
- DB-only migration first — rejected due to high migration risk and loss of file-first ergonomics.
- Hooks-only enforcement without pipeline modules — rejected because it couples policy logic to shell scripts and weakens testability.
- Immediate Trello-first integration — rejected because internal gate/evidence model must stabilize before external sync.

**Consequences:** Implementation will proceed in phases (P0 gate engine + evidence + regression scope, P1 JSON contracts + ai-pipeline + install-hooks, P2 Trello sync + SQLCipher hardening). Markdown remains canonical for human workflow while DB acts as structured evidence and automation substrate.

## TEMPLATE

**Date:** YYYY-MM-DD  
**Decision:** What was decided  
**Context:** Why this decision was needed  
**Alternatives Considered:**
- Option A — rejected because ...
- Option B — rejected because ...

**Consequences:** What this means going forward.

---

<!-- Add decisions above this line -->

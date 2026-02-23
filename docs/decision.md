# Decision Log  (Persona Framework v0.2.0)

Record every significant decision using the template below.

---

### TEMPLATE
**Date:** 2026-02-23
**Decision:** Implement Epics as `epic-<slug>.md` files in `docs/tasks/`
**Context:** We need a way to group related tasks together into larger milestones or epics.
**Alternatives Considered:**
1. A separate `docs/epics/` directory — rejected because it complicates the state machine and `keeli list` logic.
2. Using tags/labels — rejected because epics need their own description, scope, and lifecycle.
**Consequences:** Epics will be tracked as special tasks (`epic-<slug>.md`) and regular tasks will have an `**Epic:** <slug>` field to link them.

---

<!-- Add new decisions above this line -->

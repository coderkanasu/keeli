# Governance KPI Framework (30/60/90)

## Purpose
Define measurable governance signals for Keeli pilot execution quality, requirement stability, and hallucination-risk reduction.

## KPI Dictionary

| Metric | Definition | Formula | Owner | Data Source |
|---|---|---|---|---|
| Planning completeness ratio | Share of stories with clear AC + NFR at creation time | stories_with_ac_and_nfr / total_new_stories | @po | docs/tasks/story-*.md |
| Story acceptance clarity score | Average rubric score for AC quality (specific, testable, bounded) | sum(scores) / story_count | @po + @qa | Weekly story review notes |
| Backlog churn percentage | Share of backlog items materially changed after planning approval | changed_backlog_items / total_backlog_items | @architect | docs/tasks + ai_log deltas |
| Cycle time median | Median days from In Progress to Completed | median(completed_at - in_progress_at) | @developer | keeli_state.db.work_items |
| Blocked work ratio | Fraction of active items currently blocked | blocked_items / active_items | @qa | keeli_state.db.work_items |
| Requirement-change rework hours | Time spent reworking due to requirement change | sum(rework_hours_tagged_requirement_change) | @po | Weekly governance snapshot |
| Defect escape rate | Defects found after release over total defects | escaped_defects / total_defects | @qa | bug tasks + release notes |
| Incident rate from requirement gaps | Prod incidents traced to requirement ambiguity or omissions | req_gap_incidents / release_window | @security + @qa | post-incident review log |
| Throughput stability | Variation in weekly completed work volume | stddev(weekly_completed_tasks) | @architect | keeli_state.db + ai_log |

## Target Bands

### 30 Day Targets
- Planning completeness ratio: >= 0.80
- Story acceptance clarity score: >= 3.5 / 5.0
- Backlog churn percentage: <= 20%

### 60 Day Targets
- Cycle time median: <= 5 business days
- Blocked work ratio: <= 15%
- Requirement-change rework hours: <= 12 hours per sprint

### 90 Day Targets
- Defect escape rate: <= 10%
- Incident rate from requirement gaps: <= 1 per release window
- Throughput stability: coefficient of variation <= 0.25

## Cadence And Owner Model
- Weekly (30 min, owner: @po): KPI movement, risk register updates, blockers needing leadership decision.
- Monthly (60 min, owner: @architect): trend review, root-cause analysis, process changes, decision log updates.
- Snapshot publication owner: @author (every Friday).
- Evidence integrity owner: @qa (verifies links/references in completed tasks).

## Collection Notes
- Prefer DB and immutable logs over manual recollection.
- Each KPI update must include source references in weekly snapshot.
- Missing data is captured explicitly as "Data Gap" and tracked as a task.

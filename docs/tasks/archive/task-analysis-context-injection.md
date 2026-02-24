# Task: AI Context Injection via TF-IDF Analysis

**Status:** Completed
**Priority:** P1
**Persona:** @developer
**Created:** 2026-02-23T00:00:00Z
**Completed:** 2026-02-23T00:00:00Z
**Epic:** (none)

## Description
Add `keeli analyze <slug>` command that scores a task's text against the project corpus
(skills, ADRs, project goals) using TF-IDF + cosine similarity, then appends an
`## AI Context Hints` block to the task file. Auto-run on `keeli next` output.

Pure Python TF-IDF for zero-dep baseline; sklearn available behind `--use-sklearn` flag
or if `scikit-learn` is installed.

## Acceptance Criteria
- [x] `keeli analyze <slug>` reads task file, scores against corpus, writes hints block
- [x] Hints include: top 3 relevant skills, top 2 relevant ADRs, suggested persona
- [x] `keeli next` appends inline context hints to its terminal output (does not write to file)
- [x] Pure Python TF-IDF path requires no new dependencies
- [x] If scikit-learn is importable, use it automatically (richer IDF weighting)
- [x] `--use-sklearn` flag forces sklearn, exits with error if not installed
- [x] Hints block is idempotent: re-running replaces existing block, not appends

## Checklist
- [x] `_build_corpus()` — collect (label, text) pairs from skills/decisions/project.md
- [x] `_tfidf_scores_pure()` — pure Python TF-IDF cosine similarity
- [x] `_tfidf_scores_sklearn()` — sklearn TfidfVectorizer path
- [x] `_score_corpus()` — dispatcher: sklearn if available, else pure
- [x] `cmd_analyze()` — reads task, scores, writes `## AI Context Hints` block
- [x] `cmd_next()` — append top hints to terminal output
- [x] Parser wiring: `keeli analyze <slug> [--use-sklearn] [--dry-run]`
- [x] Tests: 64/64 passing
- [x] @security review: all local, no PII, no external calls

# Iteration 2 Plan: SQLite State Machine Foundation

**Goal:** Build the encrypted SQLite backend (`keeli_state.db`) to replace MD files as state of truth

**Why this iteration:**
- Current system still uses Markdown files for task state (not scalable, not safe)
- Need single source of truth for state machine
- Need encryption before storing any task/decision/person data
- Need to remove manual handoff operations

---

## Architecture (High-Level)

```
┌─────────────────────────────────────┐
│  Git/VSCode (Developer's natural work) │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│  Keeli CLI (keeli start, keeli progress, etc.) │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│  SQLite State Machine (keeli_state.db) │
│  - encrypted at rest (AES-256-GCM)  │
│  - tables: tasks, decisions, audit  │
│  - indexes on task_id, status, etc  │
└─────────────────────────────────────┘
```

---

## Tasks (Breakdown for Iteration 2)

### Phase 2.1: Schema Design

**What:** Define sqlite schema for state machine

**Tables needed:**
```sql
tasks (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE,
  title TEXT,
  epic_slug TEXT,
  story_slug TEXT,
  persona TEXT,
  status TEXT,  -- Backlog, In Progress, Review, Completed, Archived, Blocked
  priority TEXT,  -- P0, P1, P2
  created_at TEXT,
  completed_at TEXT
)

decisions (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE,
  title TEXT,
  date TEXT,
  decision TEXT,
  context TEXT,
  rejected_alternatives TEXT,  -- JSON array
  consequences TEXT
)

audit_log (
  id INTEGER PRIMARY KEY,
  task_id INTEGER,
  action TEXT,  -- started, progressed, blocked, completed, etc.
  timestamp TEXT,
  persona TEXT,
  details TEXT  -- JSON
)

personas (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE,
  name TEXT,
  mindset TEXT,
  skills TEXT  -- JSON array
)
```

**Acceptance:**
- [ ] Schema designed (no PII fields)
- [ ] Indexes on (slug, status, priority, created_at)
- [ ] All nullable fields documented
- [ ] Encryption strategy chosen (SQLiteX + PRAGMA key)

---

### Phase 2.2: Encryption Layer

**What:** Encrypt keeli_state.db at rest

**Approach:**
- Use `apsw` (Another Python SQLite Wrapper) with SQLiteX for encryption
- Or use `sqlcipher` (SQLite with encryption)
- Encryption key: read from `KEELI_ENCRYPTION_KEY` env var
- Fallback: prompt user on first init

**Acceptance:**
- [ ] keeli_state.db is encrypted by default
- [ ] Unencrypted backup prevented (no plaintext dump in Git)
- [ ] Key rotation procedure documented

---

### Phase 2.3: Migrate MD → SQLite

**What:** Tool to convert existing MD tasks into SQLite

**Command:**
```bash
keeli migrate md-to-sqlite
```

**Behavior:**
- Reads all `docs/tasks/*.md` files
- Parses task metadata (ID, status, priority, persona, epic, story)
- Inserts into `keeli_state.db`
- Marks tasks as read-only in MD ("auto-generated from DB, do not edit")
- Optionally backs up .md files to `.archive/`

**Acceptance:**
- [ ] All MD tasks successfully imported
- [ ] No data loss
- [ ] Task relationships (epic→story→task) preserved
- [ ] Reverse tool (SQLite → MD export) for human-readable reports

---

### Phase 2.4: Remove Manual Handoffs

**What:** Replace `keeli handoff` with automatic state transitions

**Current (manual):**
```bash
keeli handoff task-slug -p architect -m "Design approved"
```

**New (automatic):**
```bash
# Developer codes → git commit → keeli auto-logs "T-0001 moved to In Progress"
# Tests pass → keeli auto-logs "T-0001 moved to Review"
# Merged to main → keeli auto-logs "T-0001 completed"
```

**Hooks to implement:**
1. **Git pre-commit:** `keeli validate-task-state`
   - Check: is task in Backlog? If so,reject commit (force `keeli progress` first)
   - Check: no PII in commit message or code
2. **Git post-commit:** `keeli log-commit`
   - Log: commit hash, author, timestamp to audit_log
3. **VSCode save:** background `keeli sync-state`
   - Detect if task moved (if all tests pass, advance to Review)

**Acceptance:**
- [ ] Git hooks installed via `keeli init`
- [ ] Manual `keeli handoff` command deprecated (stub remains for compat)
- [ ] State transitions logged automatically to audit_log
- [ ] No manual persona sign-offs needed

---

## Iteration 2 Success Criteria

When you run:
```bash
rm -rf .github docs keeli_state.db
keeli init --force
keeli epic "Test state machine" -p P0
keeli progress <slug>
git commit -m "test"
keeli status
```

You should see:
```
Task: T-0001 Test state machine
Status: In Progress (auto-detected from git)
Last updated: 2026-03-11T03:40:00Z (auto)
Audit log:
  - 2026-03-11T03:35:00Z: Created (by keeli init)
  - 2026-03-11T03:40:00Z: Progressed to In Progress (by git hook)
```

---

## Notes

- Don't implement web UI yet (CLI only)
- Don't implement Jira sync yet (focus on SQLite first)
- Git hooks are shell scripts in `.git/hooks/`, auto-installed by keeli init
- Encryption adds ~50ms per query (acceptable)

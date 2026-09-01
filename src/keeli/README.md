# Keeli

Keeli is an AI-first task management engine and context grounding framework that bridges the gap between best-practice guidelines and runtime enforcement[cite: 7]. It treats your local filesystem as the canonical source of truth while backing operations with SQLite-based optimistic concurrency, token-budgeted prompt digests, and session isolation[cite: 4, 6, 7].

---

## Key Capabilities

* **Filesystem-Backed Truth**: Tasks live as transparent Markdown documents in status folders (`docs/tasks/backlog`, `active`, `review`, `blocked`, `archive`)[cite: 6, 7]. Physical file moves reconcile automatically into metadata indices[cite: 6, 7].
* **Optimistic Concurrency Control**: Avoids agent race conditions via SHA-256 version hashes[cite: 4, 6]. State mutations require an `expected_hash` check that aborts with `409 CONFLICT` if another agent modified the file.
* **Token-Budgeted Context Digests**: Builds strict token-capped snapshots (`keeli digest`) prioritized by Layer (Session Headers → Active Tasks → Audit → Overview → Backlog) via `tiktoken`[cite: 6].
* **Scoped Context Waterfall**: Context key resolution cascades from Session → Git Branch → Global scopes[cite: 4, 6].
* **Session & Checkpointing**: Isolate agent execution paths with UUID-scoped memory and save reasoning checkpoints for failure recovery[cite: 4, 6].
* **Native Model Context Protocol (MCP)**: Seamlessly connect Cursor, GitHub Copilot, Devin, and custom agents to your project state[cite: 3, 7].

---

## Installation & Setup

### 1. Requirements
* Python `>= 3.12`[cite: 8]
* Git

### 2. Local Editable Installation
```bash
git clone [https://github.com/coderkanasu/keeli.git](https://github.com/coderkanasu/keeli.git)
cd keeli
pip install -e .
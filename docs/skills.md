# Keeli Skills Registry  (Keeli Framework v0.4.0)

<!-- Managed by `keeli skill` and `keeli stack`. Do not edit manually. -->
<!-- Each skill row: type | name | persona | constraint                     -->

| Type | Skill | Persona | Constraint |
|------|-------|---------|------------|
| lang | Python | developer | 3.12+; type hints on every function; cli-first, no framework overhead |
| framework | MCP SDK | developer | server + async stdio/SSE transports; resources + tools exposed as separate APIs |
| framework | FastAPI | developer | Uvicorn ASGI server for SSE mode only; no web UI; minimal dependencies |
| tool | argparse | developer | cli dispatch via subparsers; no external CLI frameworks |
| tool | pytest | developer | TDD; unit tests before implementation; 100% coverage on critical paths |
| tool | scikit-learn | developer | optional dependency; auto-detect with importlib; fallback to pure-Python TF-IDF if absent |
| tool | sentence-transformers | developer | phase 2 optional; semantic analysis behind feature flag; lazy-load model on first use |
| tool | pathlib.Path | developer | all file I/O via pathlib; never os.path; _find_project_root() walks cwd() parents for docs/project.md |
| tool | pytest-asyncio | developer | asyncio_mode = auto in pytest.ini; all MCP server handler tests are async; mock session via PropertyMock on app.request_context |
| tool | json | developer | .keeli_index.json ledger for immutable IDs; never pass PosixPath as a JSON value — always str(); loads/dumps with indent=2 |
| domain | Five-Persona Architecture | architect | @po (requirements/grooming), @architect (design/ADRs), @developer (TDD implementation), @security (governance/sign-off), @author (docs/copy) |
| domain | Task Lifecycle | architect | Backlog → In Progress → Review → Completed (+ Blocked, Reopened); auto-archive on complete; keeli next skips tasks with unresolved depends_on |
| domain | Immutable ID Ledger | architect | T/E/S/BUG/FEAT-NNNN per-type prefixes; allocated at creation via _allocate_id(); stored in docs/.keeli_index.json; survive rename/archive/reopen; keeli find + keeli history query the ledger |
| domain | TF-IDF Context Injection | architect | corpus = skills + ADRs + task titles; pure-Python baseline; sklearn optional; _score_task() returns top-k skills + ADRs + persona hint; injected as ## AI Context Hints block |
| domain | MCP Streaming Notifications | developer | S-1: ProgressNotification on keeli_analyze (4 steps via send_progress_notification); S-2: LoggingMessageNotification per keeli_digest section; S-3: INFO log on keeli_start/complete/archive_task; _mcp_log and _emit_progress closures in call_tool; silent no-ops outside request context (LookupError guard) |
| domain | Project Root Detection | developer | _find_project_root() walks Path.cwd() parents until docs/project.md found; os.chdir(root) at dispatch time; fixes GPT-4.1 cwd-mismatch; never hardcode relative Path("docs/...") |

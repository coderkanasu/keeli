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
| tool | scikit-learn | developer | optional dependency; auto-detect presence; fallback to pure Python |
| tool | sentence-transformers | developer | phase 2 optional; semantic analysis behind feature flag; lazy-load model |
| tool | Path (pathlib) | developer | all file I/O via pathlib; never os.path; always Path.cwd() for workspace root |
| domain | Four-Persona Architecture | architect | @po (requirements), @architect (design), @developer (code), @security (governance), @author (docs) |
| domain | Task Lifecycle | architect | Backlog → In Progress → Review → Completed (+ Blocked, Reopened states) |
| domain | TF-IDF Context Injection | architect | corpus-based relevance scoring; pure Python baseline; sklearn optional; embedding-based phase 2 |

| framework | MCP SDK |
| framework | FastAPI |

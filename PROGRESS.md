# Keel — Progress Log

## Day 1 — Green skeleton + enforced layering
- Date: 2026-07-06
- Done: src-layout scaffold, tooling (ruff/black/mypy/pytest), import-linter layers contract, one-command `make check` gate, all green.
- Environment: Windows Python 3.13, make via GnuWin32. (WSL deferred — 18.04/Py3.6 too old; revisit with fresh distro later.)

### Talking point banked
"I enforce architectural boundaries in CI with import-linter, not conventions — I proved it by adding a deliberate `domain -> adapters` import and watching the build fail with that exact named violation."

## Day 2 — Config + migration-versioned control plane
- Date: 2026-07-06
- Done:
  - 12-factor config via pydantic-settings; `DATABASE_URL` required → fails fast at startup. One config path (Settings) used by app, Alembic, and tests. `.env` gitignored, `.env.example` committed.
  - docker-compose Postgres (port 5432, healthcheck, named volume). Reachable from Windows Python via WSL2 localhost forwarding.
  - SQLAlchemy 2.0 + Alembic wired; env.py pulls URL from Settings and points target_metadata at Base.metadata.
  - Single migration creating teams / pipelines / runs / run_steps, with FKs, tz-aware timestamps (TIMESTAMP WITH TIME ZONE), and unique constraints (teams.name; pipelines(team_id, name)).
  - Pure domain: Run / RunStep / RunStatus (no framework imports — import-linter enforces it).
  - RunRepository port (application); SqlAlchemyRunRepository + explicit translators (adapters).
  - Tests: Run round-trips (save→get→equal) + config fail-fast. Green and repeatably green under a transaction-rollback fixture (isolated, no cross-run pollution).

### Design decisions
- Domain↔ORM mapping: **(b) separate ORM records + explicit to/from translators** — chosen for legibility over classical mapping; the two representations can diverge independently.
- Insert ordering: SQLAlchemy flush order comes from `relationship()`s, NOT bare FK columns. Team→Pipeline has no relationship yet, so the seed helper flushes the parent before the child. (Add the relationship when teams/pipelines become real entities.)

### Talking points banked
- "Control-plane state is migration-versioned from the first commit — the schema is defined by reviewed Alembic migrations, config is 12-factor and typed so a bad DATABASE_URL fails at startup, and the domain↔row seam keeps FKs and timestamps out of the pure domain."
- "The ORM and the migration are two independent declarations of the schema — I design against the drift between them and regenerate migrations when models change rather than hand-patching." (Hit this drift three ways in one session: missing column, missing FK ordering, stale migration.)

### Notes / blockers for future sessions
- Test isolation via connection-level transaction + rollback fixture. Handles a single `session.commit()` correctly (nested-transaction semantics). Deferred: SAVEPOINT-based fixture for multi-commit tests — build only if a test needs real commits.
- mypy: `make type` runs `mypy src` (migrations/ and tests/ not type-checked, by design). Confirm it reports a real source-file count, not "0 source files."
- WSL still on old Python (3.6) — pytest runs on Windows against localhost:5432 to sidestep. Revisit if consolidating onto WSL.
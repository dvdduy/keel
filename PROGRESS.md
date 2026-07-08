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

## Day 3 — Warehouse adapter + hello pipeline (walking skeleton walks)
- Date: 2026-07-07
- Done:
  - `WarehouseAdapter` port (application/ports) — interface defined by what the core needs (ingest_csv, row_count), zero DuckDB types in the signature. DuckDB never named at the port.
  - `DuckDbWarehouse` impl (adapters/warehouse) — `import duckdb` confined here; CREATE SCHEMA IF NOT EXISTS + CREATE OR REPLACE TABLE ... read_csv_auto; row_count via count(*).
  - `RunPipeline` use-case (application/use_cases) — first real orchestration: ingest CSV → build Run + one "ingest" step → persist via RunRepository. Ports injected (DI); no concrete adapter imported.
  - `warehouse_path` added to Settings (required, not defaulted — consistent with database_url, nothing guessed). WAREHOUSE_PATH in .env.example.
  - Tests: adapter ingest→count (temp-file DuckDB, tmp_path); end-to-end asserts BOTH stores — run row SUCCESS in Postgres AND raw.orders rows in DuckDB. Seed logic promoted to conftest `seeded_pipeline` fixture (removed cross-module import of `_seed_pipeline`).
  - make check green: ruff, black, mypy(strict, 17 files), 11 tests, lint-imports.

### Design decisions
- **`raw.` naming policy lives in the core, not the adapter.** Adapter receives a fully-qualified `destination` and only ensures whatever schema it's told about exists (`_schema_of`). The convention that the raw layer is called `raw` belongs to the use-case, which passes "raw.orders". Adapter = dumb mechanism, naming = platform policy.
- **Connection held for the adapter's lifetime.** `__init__` opens one DuckDB connection, methods reuse it — natural for an in-process single-writer engine. Trade-off: stateful, so not trivially thread-shareable; flag when concurrency arrives.
- **warehouse_path required, not defaulted** — could have defaulted to a local file (unlike database_url, which can't be guessed), chose required for a consistent "everything explicit" config story.

### Seam verified (deliberate-violation experiment, like Day 1)
- Added `import duckdb` to application/use_cases/run_pipeline.py, ran `lint-imports`, watched it reject with the named `Layered architecture` contract violation, reverted to green. The DuckDB confinement is machine-enforced, not conventional — and the contract policies third-party imports by layer, not just keel.* internal ones.

### Talking point banked
- "DuckDB now, Snowflake later is a one-adapter swap — the warehouse lives behind a port defined by what the core needs (ingest a CSV, count rows), not what the tool does, so no warehouse SQL leaks into the application. import-linter enforces the seam in CI, and I proved it catches violations rather than just assuming it."

### Notes / open seams for future sessions
- **Dual-write, left open deliberately.** execute() ingests to DuckDB, THEN writes the run to Postgres, with no transaction spanning the two stores. If `runs.add` throws after a successful ingest: the raw table exists in DuckDB but no run row records it in Postgres — a materialized table with no control-plane trace. Ordering (ingest-before-record) makes the seam visible rather than hidden. Not solved today: idempotency Day 10, failure paths Day 12.
- **Run born terminal (SUCCESS), never walks RUNNING.** execute() is synchronous/atomic from outside, so the intermediate state is unobservable — persisting it would build machinery for an observer that doesn't exist. Becomes load-bearing Day 9 when a topological runner makes step states independently observable/failable.
- **Single `now` → zero-duration runs.** Clock read once; created_at == finished_at. Honest while ingest is instant; needs two reads (before/after) once Day 24 SLOs require run duration.
- `ingest_csv` returns row count, currently discarded — that count is the volume signal for Day 17 quality checks.

## Day 4 — Spec DSL schema + parsing
- Date: 2026-07-07
- Done:
  - Added typed `PipelineSpec` models for YAML pipeline specs: source, destination, contract columns, freshness target, transform ref, and quality checks.
  - Added YAML parser using `yaml.safe_load` + `PipelineSpec.model_validate`, plus YAML serialization with JSON-mode dumping for clean enum round-trips.
  - Added fixture-backed happy-path and round-trip tests.
  - Added negative-path coverage for parser failures, unknown keys, required freshness, freshness bounds, empty contract, duplicate columns, dangling quality-check references, invalid destination format, invalid owner format, and unsupported quality-check types.

### Design decisions
- Freshness is required on every pipeline spec. Day 4 captures the target; Day 16 decides clock semantics; Day 24 uses it as part of SLO evaluation.
- Structural validation was pulled forward from Day 5 for now. Day 5 should extend this into product-quality diagnostics rather than duplicate the same checks.

### Talking point banked
"The pipeline is data, not code — declarative YAML specs are reviewable, diffable, parsed through a typed Pydantic boundary, and protected by negative-path tests for the failure modes users actually hit."

## Day 5 — Spec diagnostics as product UX

* Date: 2026-07-07
* Done: Added Keel-owned `SpecError`, `SpecValidationError`, and structured `Diagnostic`s. Parser now catches Pydantic `ValidationError` and re-raises Keel-owned diagnostics, so raw Pydantic errors no longer cross the spec boundary.
* Done: Implemented stable diagnostic paths like `(root)`, `freshness.max_age_minutes`, and `contract[1].name`; sorted diagnostics for deterministic output.
* Done: Chose hybrid message ownership: preserve custom validator messages, map common structural Pydantic errors, and keep fallback messages clean.
* Tests: `pytest tests/test_spec.py` green — 23 passed.

### Design notes

* Accepted a small Option-C UX trade-off: custom validator messages may include the field name (`owner: owner must be an email-like value`), while mapped structural messages are field-relative (`freshness.max_age_minutes: must be greater than 0`). Future polish could normalize all messages to field-relative predicates.
* Clean-message tests include regression insurance against accidentally using `str(ValidationError)`, which would leak Pydantic URLs/type noise.

### Scope guards

* Deferred YAML line/column diagnostics; `yaml.safe_load` discards source positions.
* Deferred “Did you mean …?” suggestions for unknown keys.
* Did not change `models.py` validators; Day 5 only wraps and translates their output.

### Talking point banked

"Good platform errors are a feature — Keel rejects bad specs before side effects, reports all field-level problems in one pass, and exposes a stable Keel error contract instead of leaking Pydantic internals."

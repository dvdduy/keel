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

## Day 6 — Immutable spec versioning
- Date: 2026-07-07
- Done:
  - Added canonical spec serialization for identity: validated `PipelineSpec` → `model_dump(mode="json")` with all resolved defaults → deterministic JSON → SHA-256.
  - Added `SpecVersion` with surrogate `version_id`, recurring `spec_id` content hash, parent link, canonical content preimage, and timestamp.
  - Added `SubmitSpec` use case with observable idempotency: identical resubmit returns the existing head with `created=False`; changed specs append a child.
  - Added pure versioning tests covering deterministic hash, default normalization, key-order normalization, contract order sensitivity, root creation, no-op submit, child append, and revert append.
  - Added `spec_versions` persistence with DB-owned monotonic `seq` for unambiguous per-pipeline head ordering.
  - Added SQLAlchemy repository/translators and integration coverage for identical submit dedup and changed submit parent linkage.

### Design decisions
- Hash meaning, not YAML bytes: comments, whitespace, key order, and explicit defaults should not create new versions.
- Preserve list order in canonicalization: contract order is part of the declared dataset contract, so swapping columns is a meaningful change.
- Use surrogate `version_id` plus indexed non-unique `spec_id`: reverts can legitimately reuse the same content hash while creating a new audit event.
- Use DB identity `seq` for head ordering instead of `created_at desc`: audit head selection must be total and unambiguous.

### Talking point banked
"Every spec change is an immutable, auditable version — I hash the canonical validated meaning of the spec, not YAML bytes, and use a surrogate version id so reverts preserve history instead of overwriting it."

## Day 7 — Contract compatibility engine

* Date: 2026-07-08
* Done:

  * Added a pure compatibility engine for pipeline contract evolution.
  * Compatibility is checked by column name, so column reorder is safe.
  * Implemented the explicit widening lattice: `integer -> decimal` only.
  * Compatible changes covered: identical contract, add nullable column, widen integer to decimal, relax not-null to nullable, reorder columns.
  * Breaking changes covered: dropped column, rename-as-drop, narrowing decimal to integer, unrelated type change, nullable -> not-null, required column added.
  * Engine reports all breaking changes, including multiple breaking dimensions on the same column.
  * Tests now use real `PipelineSpec` / `ContractColumn` objects instead of duck-typed fakes.
  * Wired compatibility into `SubmitSpec`: breaking updates are rejected by default and do not append a new spec version.
  * Added explicit `allow_breaking` override; overridden breaking updates are recorded with `breaking_override=True`.
  * Preserved ordering invariant: identical resubmits and first submits never run compatibility checks.
  * Persisted `breaking_override` through the SQL adapter: Alembic migration, ORM mapping, translators, and repository round-trip coverage.
  * Added DB round-trip coverage using `session.expire_all()` to prove the audit flag survives a real database read, not just SQLAlchemy's identity map.

### Design decisions

* Compatibility is modeled as one invariant: the proposed contract must accept every dataset accepted by the previous contract.
* Column removal is treated as a separate consumer-surface rule: even if data could be ignored, dropping a queryable column removes a consumer capability and is breaking.
* Breaking changes are reported per column and per dimension, not collapsed per column. A single column can produce multiple breaking facts, such as type change plus nullable tightening.
* Compatibility reports preserve contract order instead of sorting, because the natural order mirrors the producer's schema and remains deterministic.
* The database keeps a `server_default=false()` for `breaking_override` to backfill existing rows. In a stricter production setup, I would use the server default for the migration/backfill, then drop it in a follow-up migration so the application remains the single source of truth.

### Validation

* `pytest tests/test_spec_compatibility.py -q` passed.
* `pytest tests/test_spec_versioning.py -q` passed.
* `pytest tests/test_spec_version_repository.py -q` passed after `alembic upgrade head`.
* `make check` passed.

### Talking point banked

"Keel lets producers evolve schemas without shattering consumers. Instead of a hand-maintained table of breaking-change rules, I reduced the taxonomy to one invariant — the new contract must accept every dataset the old one accepted — plus a consumer-surface rule that columns cannot be silently dropped. Breaking changes are rejected by default with a structured diff, and the override is explicit and audited, so 'move fast' is a deliberate, recorded decision, not an accident."

## Day 8 — Executable plan + executor port
- Date: 2026-07-08
- Done:
  - Added immutable execution-plan model as a DAG of typed ingest / transform / quality-check steps.
  - Added deterministic `compile_plan(spec)` that turns a `PipelineSpec` into desired executable state without runtime ids, timestamps, DB access, or executor side effects.
  - Added `ExecutionPlan` invariants for duplicate step keys and dangling dependencies using a Keel-owned plan error.
  - Added `PipelineExecutor` port only; no local executor implementation yet.
  - Left `RunPipeline` untouched intentionally — Day 9 will rewire the ad-hoc path to compile then execute.

### Design decisions
- `ExecutionPlan` lives in the application layer because it depends on `PipelineSpec` from `application.specs`; putting it in domain would violate the dependency direction.
- Duplicate quality checks are rejected loudly through the plan invariant instead of silently deduplicated. Silent dedup would hide user intent and make execution/run-step audit ambiguous.

### Talking point banked
"I model the platform as a reconciler — declarative desired state is compiled into a deterministic execution DAG, while runs remain observed actual state."

## Day 9 — Local topological runner + guarded run lifecycle

* Date: 2026-07-08
* Done:

  * Added deterministic topological ordering for execution plans using Kahn's algorithm.
  * Ready-step ties are broken by step key ascending for reproducible run histories.
  * Cycle detection raises `PlanValidationError` with the stuck step keys.
  * Added domain-owned guarded transitions for `Run` and `RunStep`.
  * Illegal lifecycle transitions raise `IllegalStateTransition`; terminal states remain terminal.
  * Added `StepHandler` port so step work is separate from execution ordering.
  * Added `LocalExecutor` adapter that runs steps in topo order, fails fast, and persists the terminal run once.

### Design decisions

* Cycle detection lives in `topological_order`, not `ExecutionPlan.__post_init__`, because the topo traversal already discovers cycles. `ExecutionPlan` keeps cheap structural validation; ordering pays for the graph walk once.
* Local execution lives under `adapters/` because it is one executor backend beside future Airflow, not privileged application logic.
* Step work lives behind `StepHandler`; the executor only knows whether a step succeeded or raised.

### Deferred seams

* Per-step timestamps are deferred. Adding `started_at` / `finished_at` to `RunStep` needs domain fields, persistence mapping, and an Alembic migration. Day 24 SLOs will force this.
* Single terminal persistence write is deliberate for now. A crash mid-run leaves no trace; Day 10 idempotency and Day 12 failure-path hardening will address it.
* Fail-fast is not rollback. Downstream steps halt, but already completed work is not undone. Rollback belongs to Day 12.

### Talking point banked

"Airflow is a pluggable backend — ordering is pure application logic, lifecycle rules live in the domain, step execution is a handler port, and the local runner is just one adapter behind the executor seam."

## Day 10 — Idempotency & re-runs
- Date: 2026-07-08
- Done:
  - Added `RunKey(pipeline_id, watermark)` as the logical identity for a batch.
  - Added nullable `runs.watermark` with a non-unique `(pipeline_id, watermark)` index so retries can share the same key.
  - Carried `watermark` through the domain model, ORM mapping, and SQL translators.
  - Implemented `SqlAlchemyRunRepository.latest_for_key`.
  - Added `TriggerRun` idempotency flow: first trigger executes; second successful trigger with the same key returns the existing run without invoking the executor.
  - Proved the real DB path with an integration test: same key triggered twice creates only one successful execution.

### Talking point banked
"Re-runs are idempotent at the logical batch level: `RunKey(pipeline_id, watermark)` separates 'what work is this?' from 'which attempt is this?', so a successful batch cannot be executed twice while failed attempts remain safely retryable."

## Day 11 — Drift detection
- Date: 2026-07-08
- Done:
  - Added pure drift detection that compares declared `PipelineSpec.contract` against observed warehouse schema.
  - Added `ObservedSchema`, `ObservedColumn`, `SchemaDrift`, and `DriftReport` as Keel-owned application types.
  - Reports missing table, missing columns, unexpected columns, and type mismatches.
  - Missing table is grouped as one root-cause drift and stops immediately instead of emitting one missing-column drift per contract column.
  - Extended the warehouse port with `describe_table`.
  - Implemented DuckDB schema observation behind the adapter seam, translating DuckDB physical types into Keel `ColumnType`.
  - DuckDB `CatalogException` is caught at the adapter boundary and returned as `None`; DuckDB exceptions do not cross into application logic.

### Design decisions
- Drift is desired-vs-actual, not desired-vs-desired. Compatibility blocks unsafe proposed specs before they land; drift observes the real warehouse after the world changes.
- Unexpected columns are treated as drift because they are undeclared consumer surface outside the governed contract.
- Nullability drift is deferred because DuckDB CTAS nullability inference is not reliable enough for an honest detector.
- Unknown physical warehouse types fail loudly with a Keel-owned `WarehouseError` instead of silently becoming an "unknown" type.
- Type projection is currently lossy around the exact-vs-approximate numeric boundary: DuckDB `DOUBLE` / `FLOAT` / `REAL` are projected to Keel `DECIMAL` because `ColumnType` has no floating-point logical type yet. That means a table storing money as floating point can appear in sync with a contract that promised decimal precision; future financial-grade enforcement should split exact decimal from approximate float.

### Talking point banked
"I separated compatibility from drift: compatibility compares desired spec to desired spec before a change lands; drift compares declared contract to observed warehouse state after the world changes, and detection is read-only."

## Day 12 — Compensating rollback for atomic rollout
- Date: 2026-07-08
- Done:
  - Evolved `StepHandler` so each successful step returns an opaque compensation callable.
  - Updated `LocalExecutor` to keep a LIFO compensation stack and run rollback on step failure.
  - Rollback is best-effort and exhaustive: compensation failures are swallowed so earlier successful steps still get their undo attempted.
  - Preserved audit semantics: a step that executed successfully remains `SUCCESS`; rollback is treated as a separate side-effect cleanup, not a new run-step state.
  - Added fake-only executor tests for happy path, reverse-order rollback, first-step failure, compensation failure, and single failed-run persistence.
  - Added DuckDB-backed compensation for ingest by dropping the materialized table on rollback.
  - Proved with integration coverage that a successful ingest followed by a failed downstream step does not leave `raw.orders` behind.
  

### Design decisions
- Atomicity is semantic, not ACID: Keel crosses resources that cannot share one transaction, so the executor uses Saga-style compensating actions.
- The executor does not know how to undo a step. Handlers own side-effect knowledge and return opaque compensations.
- Compensation failures do not abort rollback; rollback reports best effort by exhausting the undo stack.
- No `ROLLED_BACK` status yet. Run-step history records what executed; rollback visibility is deferred until the run-step lifecycle is revisited.

### Known limitations / future hardening
- Current DuckDB ingest compensation is correct for first-time table creation but incomplete for replacement semantics. `ingest_csv` uses replace behavior, so `undo(create) = drop`, but `undo(replace) = restore previous version`. Snapshot/restore is deferred; today’s compensation prevents first-time half-materialization but does not yet preserve a previously-good table on failed re-runs.
- Compensation failures are logged, not persisted as first-class rollback events yet. Day 24/25/35 can promote these logs into SLO/incident/observability surfaces.

### Talking point banked
"Reconciliation is atomic in the practical distributed-systems sense: when a rollout fails after mutating external systems, the executor unwinds successful steps with Saga-style compensating actions in reverse order. I also understand the limitation: undo depends on prior state — undo(create) is drop, but undo(replace) requires restore."


## Day 13 — dbt transform backend behind a port
- Date: 2026-07-08
- Done:
  - Added a Keel-owned `TransformRunner` port with structured per-model results.
  - Added `DbtTransformRunner` adapter that invokes dbt as a subprocess, with zero `import dbt` in `src/`.
  - Added dbt project scaffold under repo-root `transform/`.
  - Added warehouse `close()` lifecycle seam so DuckDB releases the file lock before dbt opens the same warehouse.
  - Tests cover successful staging materialization, model SQL failure as `TransformResult(ok=False)`, and tool failure as `TransformError`.

### Talking point banked
"I integrated dbt as a governed transform layer without coupling Keel to it — dbt runs as a subprocess behind a TransformRunner port, so the codebase contains zero import dbt, its dependency pins never touch the control plane, and a model failure is a structured result while only a tool failure raises. Swapping dbt for another SQL transformer is an adapter change."


## Day 13 — dbt as a transform backend behind a port

* Date: 2026-07-08
* Done:

  * Added a Keel-owned `TransformRunner` port with structured per-model transform results.
  * Added `DbtTransformRunner`, which invokes dbt as a subprocess and parses `target/run_results.json`.
  * Added the dbt project scaffold under repo-root `transform/`.
  * Added warehouse `close()` so DuckDB releases its file lock before the dbt subprocess opens the same warehouse.
  * Proved model SQL failure is a structured `TransformResult(ok=False)`, while tool failure raises `TransformError`.
  * Wired `TransformStep` into the local DuckDB step handler so `LocalExecutor` can run ingest → transform end to end.
  * Kept dbt out of Keel’s control-plane imports; `src/` contains zero `import dbt`.

### Talking point banked

"I integrated dbt as a governed transform layer without coupling Keel to it — dbt runs as a subprocess behind a TransformRunner port, so the codebase contains zero `import dbt`, its dependency pins never touch the control plane, and a model failure is a structured result while only a tool failure raises. Swapping dbt for another SQL transformer is an adapter change."


## Day 14 — Layered dbt transforms through one Keel step

* Date: 2026-07-08
* Done:

  * Added `mart_customer_orders` as a marts-layer dbt model sourced from `ref('stg_orders')`.
  * Keel transform steps now select the target model plus upstream dbt dependencies with `+model`.
  * Multi-model transform rollback now compensates every materialized model in reverse build order.
  * Verified both direct dbt runner behavior and LocalExecutor behavior: staging and marts materialize together, rollback drops both, and mart failures surface model-level detail.

### Talking point banked

"Keel owns the pipeline DAG, but dbt owns the SQL model DAG. A single Keel transform step materializes the requested mart and its upstream dbt models, while Keel still captures per-model status and rolls back every relation built by that step."


## Day 15 — dbt test gates + manifest capture

* Date: 2026-07-08
* Done:

  * Added dbt test execution as a separate `TransformRunner.test()` port method, keeping transform success distinct from data-contract success.
  * Added `TestStatus`, `TestResult`, and `TestReport` so dbt test statuses are modeled separately from dbt model statuses.
  * Enforced dbt tests as a transform-layer gate: `fail` and `error` fail closed; `pass`, `skipped`, and `warn` are non-blocking by default.
  * Wired the DuckDB step handler to run `dbt run` followed by `dbt test` for selected models.
  * On dbt test failure, the just-materialized model output is dropped before the transform step fails, preventing unvalidated tables from being left behind.
  * Added manifest capture via `TransformRunner.capture_manifest()`, parsing dbt `manifest.json` into Keel-owned `ManifestNode` / `TransformManifest` value objects.
  * Manifest parsing includes both dbt model nodes and source nodes, with `depends_on.nodes` edges preserved for future lineage work.
  * Added passing, failing, warning-severity, tool-failure, manifest, and executor cleanup tests.

### Design decisions

* dbt tests are treated as SQL-model-layer contracts enforced during transform.
* `severity: warn` is non-blocking by default because dbt intentionally distinguishes warning tests from error-level gates.
* Keel’s later quality-gate layer will provide the stricter quarantine surface at layer boundaries; Day 15 uses drop-on-fail as the temporary fail-closed behavior.
* Manifest parsing stays adapter-side so dbt artifact schema knowledge does not leak into `src/` inner layers.

### Talking point banked

"I separated dbt run telemetry from dbt test gates and manifest metadata: model execution, data-contract validation, and lineage metadata are three different surfaces, each crossing the transform port as Keel-owned value objects."

## Day 16 — Freshness clock ADR + pure evaluator
- Date: 2026-07-08
- Done:
  - Added ADR 0001 deciding Keel's freshness clock model: event-time watermark primary, wall-clock latest-successful-load fallback, business calendar deferred as a modifier.
  - Added pure freshness evaluator with `FRESH`, `STALE`, and `UNKNOWN` outcomes.
  - Made freshness arithmetic source-agnostic: the caller resolves `as_of`; the evaluator only judges age against the threshold.
  - Covered boundary and failure-path behavior: exact threshold is fresh, missing `as_of` is unknown, future `as_of` is unknown, and naive datetimes fail loudly.
  - Documented the future spec-hash implication of adding `event_time_column`.

### Checkpoint 2 — Event-time freshness wiring
- Done:
  - Extended `FreshnessSpec` with optional `event_time_column`.
  - Validated that declared event-time columns exist in the contract and use timestamp type.
  - Added `WarehouseAdapter.max_timestamp(table, column) -> datetime | None`.
  - Implemented DuckDB `MAX(timestamp_column)` resolution with timezone-aware UTC output and boundary error wrapping.
  - Added `resolve_as_of` policy: event-time watermark first, latest successful run `finished_at` fallback when no event-time column is declared.
  - Documented the Day 6 canonical-hash implication: adding `event_time_column: null` is an acceptable one-time DSL schema migration.

### Talking point banked
"Freshness is resolved in two layers: a policy layer chooses the as-of clock, then a pure evaluator applies the threshold. That separation lets Keel support event-time freshness, wall-clock fallback, and future business-calendar modifiers without rewriting the freshness arithmetic."


## Day 17 — Column quality checks on the measure-then-judge seam
- Date: 2026-07-08
- Done:
  - Added a pure quality-check evaluator for single-snapshot column predicates: `not_null` and `unique`.
  - Added warehouse-backed column measurements for row count, null count, and distinct non-null count.
  - Preserved the freshness pattern: measure facts at the adapter seam, judge them in pure application logic.
  - Missing/unobservable columns return `UNKNOWN`, not false `FAILED`.
  - Deferred referential integrity because the spec DSL has no foreign-key relationship yet.
  - Deferred volume anomaly because anomaly detection needs stored historical baselines.

### Talking point banked
"I classified quality checks by the state each one needs to judge — single-snapshot column predicates, cross-table relational checks, and stateful historical checks. I built the self-contained class on the same measure-facts-then-judge seam as freshness, so the evaluator is pure, warehouse-free, and testable. Referential integrity is deferred until the DSL can declare foreign keys; volume anomaly is deferred until Keel stores a historical baseline."


## Day 18 — Quality gates and quarantine

* Date: 2026-07-08
* Done:

  * Added fail-closed gate policy: PASSED proceeds, FAILED blocks, and UNKNOWN blocks because an unobservable just-materialized relation is unsafe.
  * Added `QualityResult` audit shape plus repository port.
  * Implemented `apply_gate`: always records the check result first, then returns PROCEED/BLOCK.
  * Threaded run context into step execution so quality results are tied to a run.
  * Wired quality steps into the DuckDB handler: measure column, evaluate check, persist result, and raise on block.
  * Reused Saga rollback for quarantine: blocking gates unwind upstream materialization so bad data does not reach the serving relation.
  * Persisted/queryable quality results and integration tests proving both failed quarantine and clean-data proceed paths.
  * All focused tests and `make check` green.

### Design decisions

* UNKNOWN is fail-closed: if the table/column cannot be measured at gate time, Keel blocks rather than letting potentially bad data through.
* Quality-result audit durability is independent of run success: the failed relation is rolled back, but the evidence of why the run failed survives.

### Known limitation

* Current per-check quality steps fail fast, so only the first blocking check is recorded before rollback. Production hardening would use one exhaustive gate boundary: evaluate all checks, persist all results, then block if any failed.

### Talking point banked

"Bad data is quarantined at the gate, not propagated. A quality check is a monitor that's allowed to say no: it always records a quality_result audit row, then returns a block/proceed decision. Blocking reuses my Saga rollback — the just-materialized relation is compensated away, so nothing reaches serving — while the audit row survives the rollback, because 'the run failed' and 'here's exactly which check failed and by how much' are separate durability guarantees. And it fails closed: even a check I couldn't run blocks, rather than waving data through."


## Day 19 — Exhaustive quality gate
- Date: 2026-07-09
- Done:
  - Collapsed per-check quality DAG nodes into one `QualityGateStep` per data layer.
  - Gate evaluates every declared check before deciding, so one failed/unknown check no longer prevents later checks from being measured.
  - `apply_gate` records all per-check `QualityResult` rows first, then blocks iff any result is FAILED or UNKNOWN.
  - Updated executor, compiler, and tests to the new topology: one quality step in the run DAG, many persisted audit rows.
  - Verified quarantine still happens through upstream compensation while quality audit rows survive for the failed run.
  - `make check` green.

### Design decision
- Chose compiler-owned gate collapse: one `QualityGateStep` carrying a tuple of checks. This keeps the Saga DAG focused on execution boundaries while `quality_results` owns per-check audit granularity.

### Talking point banked
"Quality is the complete, queryable output of every run — the gate evaluates and records every check, not just the first failure. I decoupled execution topology, one gate node per layer, from audit granularity, per-check verdict rows, so on-call sees the whole picture in one run instead of peeling failures off one re-run at a time — and it is exhaustive and fail-closed at once."
 
## Day 20 — Dataset registry / catalog
- Date: 2026-07-09
- Done:
  - Added an immutable `CatalogEntry` application model projected from an authoritative `SpecVersion`.
  - Keyed datasets by their consumer-facing destination (`schema.table`), with pipeline identity retained as producer metadata.
  - Denormalized owner, team, and contract columns into a queryable schema snapshot with source-spec provenance.
  - Added the `DatasetCatalog` port and an in-memory fake covering idempotent upsert, lookup, and listing behavior.
  - Added PostgreSQL persistence using a natural dataset primary key and JSONB contract columns.
  - Added ORM translators, `SqlAlchemyDatasetCatalog`, and an Alembic migration for the `datasets` table.
  - Wired catalog projection into `SubmitSpec` on every successful submit, including unchanged submissions, so missed catalog writes self-heal from the current spec head.
  - Added unit and integration coverage for projection, provenance, ownership updates, schema mapping, and one-row upsert semantics.
  - Verified formatting, lint, mypy, import-layer contracts, migration application, and all 195 tests.

### Design decisions
- The catalog is a rebuildable read model, not a second source of truth; identity, ownership, and schema always derive from the authoritative spec head.
- Destination is the dataset identity because it is the physical, consumer-facing product name; pipeline name is producer metadata.
- Re-projecting on every successful submit is deliberately idempotent and self-healing. A later destination-conflict policy can replace today's last-write-wins behavior.

### Talking point banked
"Datasets are products in a catalog keyed by their consumer-facing name, but the catalog is a projection of the authoritative spec head rather than a hand-maintained registry. Ownership and schema therefore cannot drift from what is declared: the view is queryable, denormalized, and rebuildable from source."

## Day 21 — Declared-and-verified lineage
- Date: 2026-07-09
- Done:
  - Added ADR 0002 selecting declared-and-verified table-level lineage.
  - Added immutable, hashable `LineageEdge` values and a pure `declared_edges` projection.
  - Represented external CSV nodes as `source:csv:<path>` so they cannot be confused with datasets.
  - Modeled transformed pipelines according to actual materialization: external source → raw destination → `main.<transform>`.
  - Added `edges_for_version` so lineage projects from the same authoritative spec heads as the catalog.
  - Documented the catalog/lineage identity conflict for transformed pipelines as a required reconciliation.

### Design decisions
- The spec is producer intent and therefore the lineage authority; the dbt manifest is an observation used to verify that intent.
- SQL parsing is deferred to column-level lineage or non-dbt SQL, where it adds information instead of duplicating dbt's Jinja and `ref()` resolution.
- An explicit cross-pipeline upstream field is deferred to avoid canonical-hash churn before the DSL can use it.

### Talking point banked
"I chose declared-and-verified lineage: the spec declares table-level edges as producer intent and the dbt manifest verifies them, rather than parsing SQL — because parsing gives me actual state with nothing to reconcile against, and re-parsing raw model SQL with sqlglot re-solves, worse, the Jinja/ref resolution dbt already did correctly in its manifest."

## Day 22 - Queryable lineage graph / impact analysis
- Date: 2026-07-09
- Done:
  - Added a pure immutable `LineageGraph` over `LineageEdge` values and string nodes.
  - Implemented cycle-safe BFS for downstream impact analysis and symmetric upstream `feeds` queries.
  - Defined impact as strictly downstream: unknown nodes return empty results, and the origin is excluded even when reachable through a cycle or self-loop.
  - Deduplicated repeated edges and diamond fan-out through set-backed adjacency maps.
  - Added `SpecVersionRepository.heads()` and implemented it for the in-memory fake and SQLAlchemy repository.
  - Added `build_lineage_graph(versions)` to union `edges_for_version` across authoritative spec heads.
  - Added integration coverage proving persisted pipeline heads can build a platform graph and recover transitive impact from real spec state.
  - Verified `ruff`, `black --check`, `mypy`, all 211 tests, and import-linter.

### Design decisions
- Kept `graph.py` dependency-clean inside `application.lineage`: it knows only `LineageEdge` and string nodes, not `PipelineSpec` or repository details.
- Put the version-to-graph builder beside the existing version-to-edge projection so spec parsing remains outside the graph data structure.
- Chose eager adjacency maps in both directions to make `impacted_by` and `feeds` symmetric, fast, and deterministic.

### Known limitation
- The current DSL still cannot declare cross-pipeline upstreams, so the platform graph is a union of disconnected per-pipeline chains. The engine is ready for the Day 36 blast-radius demo, but the dramatic cross-pipeline edges require the deferred explicit upstream field.

### Talking point banked
"Impact analysis is graph reachability, but the important production detail is termination. Even if lineage should be a DAG, specs are independently authored inputs, so the traversal treats cycles and self-loops as valid data it must survive. I seed `visited` with the origin, then BFS outward; that gives a strictly downstream casualty set where the changed node is the cause, not part of the answer."

## Day 23 - Manifest-verified lineage drift
- Date: 2026-07-09
- Done:
  - Extended captured dbt manifest nodes with physical identity: dbt `schema` plus model `alias` or source `identifier`, falling back to node name.
  - Added a pure lineage verifier that projects dbt `depends_on.nodes` into Keel `LineageEdge` values before diffing declared intent against observed manifest state.
  - Rejects corrupt manifests whose dependency list references an unknown unique id.
  - Scopes verification to dbt jurisdiction: Keel ingestion edges whose upstream starts with `source:` are reported as out of scope, not missing.
  - Scopes observed drift to the governed frontier: only manifest edges terminating at nodes named by the spec are considered, so unrelated dbt project models do not become false undeclared drift.
  - Classifies disagreement as `missing` for declared in-scope edges absent from dbt and `undeclared` for observed dependencies into governed nodes that the spec did not declare.
  - Covered projection, corrupt manifests, verified edges, missing edges, out-of-scope ingestion, unrelated manifest edges, swapped sources, and `ok` semantics.
  - Verified `ruff`, `black --check`, `mypy`, all 219 tests, and import-linter.

### Design decisions
- Verification compares one vocabulary: both declared and observed edges are normalized to physical `schema.table` identities before diffing.
- dbt is treated as an oracle with partial jurisdiction, not a universal lineage authority; ingestion edges remain Keel-owned.
- The verifier stays dependency-clean inside `application.lineage`, importing only lineage edges and the transform manifest contract.

### Deferred seams
- Use-case wiring that captures the manifest through `TransformRunner` and compares it with the authoritative spec head is still a stretch item.
- The catalog/lineage identity wrinkle from ADR 0002 remains explicitly deferred; Day 23 verifies table-level lineage and does not redefine dataset catalog identity.

### Talking point banked
"Declared lineage is verified against the dbt manifest, but the work is in the scoping, not the diff. I translate dbt's source/ref graph into the platform's physical-table vocabulary so both sides speak one language, then diff only within the frontier the spec governs - so an unrelated model in the same dbt project isn't false drift, and my CSV ingestion edge isn't flagged as missing just because dbt can't see it. A swapped upstream then reads as exactly one missing edge and one undeclared edge: desired-vs-actual, scoped to the oracle's jurisdiction."

## Day 24 - Pure SLO evaluator
- Date: 2026-07-09
- Done:
  - Added `application.slo` with pure SLO value objects for tri-state observations, unknown policy, SLO definitions, statuses, and evaluation results.
  - Implemented `evaluate_slo(slo, observations, now)` as source-agnostic arithmetic over dated observations with no persistence or I/O.
  - Enforced the time-window contract: `[now - window, now]`, lower bound inclusive, future observations excluded, and timezone-aware datetimes required.
  - Modeled unknown handling as policy: default `COUNT_AS_BAD` spends budget, while `EXCLUDE` shrinks the denominator.
  - Returned `NO_DATA` with `attainment=None` for empty valid windows, never a false-green `MEETING`.
  - Added error-budget accounting: allowed bad count, consumed budget, and remaining budget, including negative remaining budget when overspent.
  - Added projection helpers for freshness and quality results into SLO observations, keeping the evaluator source-agnostic.
  - Covered all Day 24 evaluator invariants in `tests/test_slo.py`.
  - Verified `ruff`, `black --check`, `mypy`, all 236 tests, and import-linter.

### Design decisions
- Window is wall-clock `timedelta`, not last-N observations, because SLOs should answer how healthy the dataset was over the period a consumer experienced.
- Empty windows return `NO_DATA`, not `MEETING`, matching the platform's fail-closed instinct around missing evidence.
- The evaluator knows only `GOOD` / `BAD` / `UNKNOWN` observations; freshness and quality are projected at the boundary instead of leaking source-specific meanings into SLO math.
- Freshness projection requires a dated result. A freshness result with no `as_of` has no honest observation timestamp, so the helper raises rather than inventing one.

### Talking point banked
"Data SLOs are not service SLOs with different labels. Keel first manufactures a dated observation stream, then applies pure SLO arithmetic over a wall-clock window, with UNKNOWN as an explicit policy choice. That keeps freshness and quality sources pluggable while preserving the part consumers actually feel: how much of the last period the dataset was trustworthy."

## Day 25 - Pure incident detection
- Date: 2026-07-09
- Done:
  - Added `application.incident` as a dependency-clean, pure incident detection module.
  - Modeled immutable `Incident` snapshots with injected surrogate identity, SLO breach evidence, run context, owner/team, downstream impact, and opened timestamp.
  - Added `IncidentContext` so enrichment inputs are explicit and caller-owned.
  - Implemented `detect_incident(...)` as a memoryless fold from one `SloEvaluation` plus context into an `Incident | None`.
  - Opened incidents only for `SloStatus.BREACHING`; `MEETING` and `NO_DATA` return `None`.
  - Snapshotted downstream lineage impact at open time via `LineageGraph.impacted_by(context.subject)`, preserving historical blast radius even if the graph later changes.
  - Preserved optional run context honestly: `run=None` becomes `run_id=None`.
  - Covered the Day 25 behavior in `tests/test_incident.py`, including BREACHING-only opening, NO_DATA non-opening, evaluation preservation, transitive impact, leaf impact, run enrichment, owner/team enrichment, injected id, and impact snapshot semantics.
  - Verified `ruff`, `black --check`, `mypy`, all 247 tests, and import-linter.

### Design decisions
- `NO_DATA` does not open a breach incident. Missing telemetry and known-bad data are different operational facts, so no-signal monitoring remains a separate future alert path.
- Detection has no clock or memory. The caller owns cadence and grouping; today deliberately leaves one breach -> one incident so Day 26 can solve repeated pages as its own concept.
- Incidents store historical evidence, not live pointers. The lineage blast radius, ownership, run id, and SLO evaluation are captured at open time so a post-mortem reflects what Keel knew when it paged.

### Talking point banked
"An incident is a historical snapshot, not a live view. When an SLO breaches, Keel captures the exact evaluation, run context, owner/team, and downstream blast radius at page time, because lineage and ownership drift. Three weeks later, the post-mortem should explain the world as it was when on-call got paged, not the graph as it happens to look today."

# Keel

Keel is a governed data-platform capstone: declarative pipeline specs, schema contracts, drift detection, dbt-backed transforms, quality gates, lineage, SLOs, incidents, read-only MCP tools, and a deterministic data-ops RCA agent.

> **Status:** Build complete through M9 with 310 tests. The remaining work is production hardening, not hidden milestone scope. See [PROGRESS.md](./PROGRESS.md) for the day-by-day build log.

## Why It Exists

At scale, bespoke pipelines produce inconsistent contracts, silent staleness, weak lineage, and noisy incident response. Keel is the paved road: producers declare the dataset they intend to publish, and the platform reconciles, runs, gates, observes, and diagnoses it.

The flagship scenario is failure-shaped: an upstream schema change tries to break downstream consumers. Keel rejects it by default. If someone forces it through with an audited override, the platform contains the damage with quarantine, one grouped incident, and a deterministic RCA dossier.

## Quickstart

```bash
make install   # install Keel with developer dependencies
make check     # lint, type-check src/evals, run tests, enforce imports
make demo      # run the narrated breaking-change demo
make seed      # alias for the demo, kept for the advertised seed path
make eval      # run the RCA evaluation gate
```

## Run The Demo

```bash
make demo
```

The demo walks the core governance story:

1. Submit `orders_raw` and a visible fan-out: `raw.orders -> {main.orders_stg, main.revenue_daily, main.customer_ltv, main.fulfillment_health, main.executive_revenue}`.
2. Drop `amount` from the upstream contract and show the compatibility rejection. Nothing ships.
3. Resubmit with `--allow-breaking` and print the audited override.
4. Materialize data missing `amount`, hit the downstream quality gate, quarantine the table, breach the SLO, and collapse the fan-out into one incident group.
5. Assemble the RCA dossier and diagnose the upstream subject.

The same stages are imported by [tests/test_demo_breaking_change.py](./tests/test_demo_breaking_change.py), so the demo is characterization-tested in CI.

## Architecture

Dependencies point inward and import-linter enforces the boundary:

```text
entrypoints  ->  adapters  ->  application  ->  domain
 API/CLI/MCP     DB/DuckDB     use cases        run state
                dbt/agent      specs/lineage
                              quality/SLO/RCA
```

Ports isolate the volatile seams: control-plane storage, warehouse execution, transform runner, MCP reader, telemetry, and the agent graph. DuckDB and dbt-duckdb are local adapters, not architectural commitments.

## Tech Stack

Python, FastAPI, Pydantic, SQLAlchemy + Alembic, Postgres, DuckDB, dbt-duckdb, sqlglot, LangGraph, MCP, pytest, ruff, black, mypy, import-linter, docker-compose, GitHub Actions.

## Roadmap

| Milestone | Theme | Result |
|-----------|-------|--------|
| M0 | Foundations | Clean architecture, CI, walking skeleton |
| M1 | Spec & Contract | Declarative specs, parser diagnostics, compatibility engine |
| M2 | Reconciler & Runner | Desired-to-actual planning, idempotent run state, drift checks |
| M3 | Transform | dbt-duckdb execution and manifest-backed verification |
| M4 | Quality & Gates | Freshness, column checks, quarantine semantics |
| M5 | Catalog & Lineage | Dataset catalog, declared lineage, impact traversal |
| M6 | SLO & Incident | Error-budget evaluation, incident routing, grouped blast radius |
| M7 | API & CLI | Self-serve control-plane surface over the application API |
| M8 | MCP + Agent | Read-only MCP tools and eval-gated deterministic RCA |
| M9 | Observability | Executor observer seam, RCA eval gate, packaged demo story |

## ADRs

- [ADR 0001: Freshness clock model](./docs/adr/0001-freshness-clock.md)
- [ADR 0002: Declared-and-verified lineage](./docs/adr/0002-lineage-source-of-truth.md)
- [ADR 0003: Compatibility rules](./docs/adr/0003-compatibility-rules.md)

## Productionization

Keel deliberately stops short of production platform concerns such as auth/SSO, tenant enforcement, multi-region DR, cloud deployment, and full contract-diff observability. Those are documented in [docs/PRODUCTIONIZATION.md](./docs/PRODUCTIONIZATION.md), including the seam where each real implementation plugs in.

## License

MIT

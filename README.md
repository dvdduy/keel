# Keel

A self-serve, governed data platform — built as a production-quality portfolio capstone.

Keel lets a team declare a data pipeline in a single file — source, schema contract, transforms, owner, freshness SLO, quality checks — and handles the rest: reconciling it into an executable pipeline, running ingest → transform → quality gates, capturing lineage, tracking freshness/quality SLOs, and opening context-enriched incidents when they breach. Data is treated as a product: every dataset has an owner, a contract, and an SLA.

> **Status:** In active development, built one focused PR at a time. See [`PROGRESS.md`](./PROGRESS.md) for current state; the roadmap below shows where it's headed.

## Why this exists

At scale, every team rolling its own bespoke pipelines produces inconsistent quality, no shared lineage, silent staleness, and ungoverned PII. Keel is the paved road: one platform that gives data producers self-serve pipelines with governance — contracts, quality gates, lineage, SLOs, and incident response — built in. Designed with fintech-grade concerns front of mind: correctness under re-runs, schema-change safety, and auditability.

## Tech stack

Python · FastAPI · Pydantic · SQLAlchemy + Alembic · Postgres (control plane) · DuckDB (warehouse, behind an adapter) · dbt-duckdb · sqlglot · LangGraph + MCP (data-ops agent) · pytest · ruff / black / mypy · import-linter · docker-compose · GitHub Actions

## Architecture

Clean-architecture layering with dependencies pointing inward: `domain` depends on nothing; adapters and interfaces depend on the core, never the reverse (enforced in CI with import-linter). The warehouse, orchestrator, and LLM are pluggable adapters behind interfaces — DuckDB today, a cloud warehouse tomorrow is a one-adapter swap.

_A full architecture doc and the ADR trail land as the build progresses (see [`docs/adr/`](./docs/adr))._

## Quickstart

_Lands with the Day 1–3 scaffold. Target shape:_

```bash
make up      # start Postgres + app via docker-compose
make test    # run the suite
make seed    # hello pipeline: seed CSV -> raw table + a recorded run
```

## Roadmap

Built across 10 milestones:

| Milestone | Theme |
|-----------|-------|
| M0 Foundations | Clean layering, CI, walking skeleton |
| M1 Spec & Contract | Declarative pipeline spec + schema-compatibility engine |
| M2 Reconciler & Runner | Desired→actual reconciliation, idempotent runs, drift detection |
| M3 Transform | dbt-duckdb ELT layer + manifest capture |
| M4 Quality & Gates | Freshness, integrity checks, quarantine |
| M5 Catalog & Lineage | Dataset registry, table-level lineage, impact analysis |
| M6 SLO & Incident | Error budgets, grouped incidents |
| M7 API & CLI | Self-serve control-plane surface |
| M8 MCP + Agent | Eval-gated, guardrailed data-ops agent |
| M9 Observability | Traces, demo, productionization story |

## Non-goals

Deliberately out of scope — documented, not built: real auth/SSO · DR/multi-region · regulatory certification · reverse-ETL · time-travel · tenant enforcement (quotas/RBAC) · cloud deploy. Each carries a "how I'd productionize this" note.

## License

MIT

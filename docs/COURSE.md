# KEEL_COURSE.md — The Keel Build Curriculum

A mentor-guided build of **Keel**, a self-serve governed data platform, as a production-quality portfolio capstone. You write the code; I review it like a senior. ~36 one-hour sessions across 10 milestones.

---

## How to use this

- **Resume any session in a fresh chat** with: **`Keel, Day N, let's go`**
- **One chat per session** (start fresh when a chat gets long). Keep all chats **inside this Project** so memory + past-chat search stay scoped to Keel.
- **The repo is the source of truth, not the chat.** At the start of each session, tell me where the repo is (and, if it's on GitHub, the URL — my sandbox can pull public repos so I review real code, not paste).
- **First line of every session:** point me at the repo and confirm the last committed state (or just say "see PROGRESS.md").

## The loop (every session)

- **Learn (~10 min)** — I teach the one concept + the design decision for the session, and why. Short. Analogous snippet at most, never the solution.
- **Build (~35 min)** — I hand you a scoped ticket: objective, the interface/contract to build against, the tests that must go green, definition of done. *You* write the implementation + tests. I'm on call for hints.
- **Commit (~5 min)** — you run the suite, commit, and update `PROGRESS.md`. I review the diff like a PR.
- **Earn (~5 min)** — we distill one concrete interview talking point and bank it in `PROGRESS.md`.

## Mentor/mentee contract

- I give you the *what*, *why*, and *shape* (interfaces, signatures, test names, the trade-off). You write the *how* (the bodies).
- Stuck? I go Socratic → analogous example → full solution **only if you say "just show me."**
- **Norm: stuck ~10 min → ping me, I escalate the hint.** Banking a smaller win beats grinding to a halt. End every session on green.
- Review is where most learning happens. When you commit, defend or revise.

## Continuity model

- **Learning spine** → this file (durable) + my project-scoped memory (a *summary*, not a transcript — don't rely on it for precision).
- **Code state** → your repo + `PROGRESS.md` (authoritative). Optionally GitHub so I can pull it.

## Tech stack

Python · FastAPI · Pydantic · SQLAlchemy + Alembic · DuckDB (warehouse, behind an adapter) · Postgres (control plane) · dbt-duckdb · LangGraph + MCP (agent) · pytest · ruff/black/mypy · import-linter · docker-compose · GitHub Actions.

## Non-goals (documented, not built)

Real auth/SSO · DR/multi-region · regulatory certification · reverse-ETL · time-travel · tenant enforcement (quotas/RBAC) · cloud deploy. Each gets a "how I'd productionize this" note instead.

## Deferred design decisions (decided via ADR mid-course)

- **Freshness clock** — event-time watermark vs. wall-clock-since-last-load vs. business-calendar-aware. Decided **Day 16**.
- **Lineage source of truth** — declared-and-verified vs. parsed-from-SQL. Decided **Day 21**.

---

## Milestone → session map

| Milestone | Days | Theme |
|-----------|------|-------|
| M0 Foundations | 1–3 | Clean layering, CI, walking skeleton |
| M1 Spec & Contract | 4–7 | The product surface + compatibility |
| M2 Reconciler & Runner | 8–12 | Desired→actual, idempotency, drift |
| M3 Transform (dbt) | 13–15 | ELT layer + manifest |
| M4 Quality & Gates | 16–19 | Freshness, integrity, quarantine |
| M5 Catalog & Lineage | 20–23 | Datasets, lineage, impact analysis |
| M6 SLO & Incident | 24–27 | Error budgets, grouped incidents |
| M7 API & CLI | 28–29 | Self-serve control-plane surface |
| M8 MCP + Agent | 30–34 | Eval-gated, guardrailed data-ops agent |
| M9 Observability & Polish | 35–36 | Traces, demo, productionization story |

---

## Session catalogue

Each entry: **Learn** (concept/decision) · **Build** (the deliverable) · **Earn** (the banked talking point). Full PR-level ticket detail is produced live at the start of each session.

### M0 — Foundations & walking skeleton

**Day 1 — Repo scaffold, tooling, CI**
- Learn: clean-architecture layering; why dependencies point inward; enforcing it with import-linter.
- Build: `src/` layout, pyproject, ruff/black/mypy, pytest, Makefile, GitHub Actions CI green on an empty skeleton.
- Earn: "I enforce architectural boundaries in CI with import-linter, not conventions."

**Day 2 — Config + persistence bootstrap**
- Learn: 12-factor config (pydantic-settings); migrations as versioned schema (Alembic).
- Build: docker-compose (Postgres + app), typed config, SQLAlchemy + Alembic, migration for `teams/pipelines/runs/run_steps`; repo round-trips a `Run`.
- Earn: "Control-plane state is migration-versioned from the first commit."

**Day 3 — Warehouse adapter + hello pipeline**
- Learn: ports & adapters (hexagonal); why the warehouse lives behind an interface.
- Build: `WarehouseAdapter` interface + DuckDB impl; ingest a seed CSV → `raw` table; end-to-end use-case (trigger → ingest → write run → materialize table); integration test asserts run row *and* table.
- Earn: "DuckDB now, Snowflake later is a one-adapter swap — I designed the seam on day one."

### M1 — Spec & Contract

**Day 4 — Spec DSL schema + parsing**
- Learn: declarative over imperative; YAML for reviewability; Pydantic as the validation boundary.
- Build: `PipelineSpec` schema (source, contract columns, transforms ref, destination, owner/team, freshness_slo, quality_checks); YAML parse + round-trip test.
- Earn: "The pipeline is data, not code — declarative specs are reviewable, diffable, testable."

**Day 5 — Structural validation + diagnostics**
- Learn: fail-fast; error UX as a product surface.
- Build: validation with field-level diagnostics; three malformed specs → three specific, readable errors.
- Earn: "Good platform errors are a feature — I invest in diagnostics, not stack traces."

**Day 6 — Immutable versioning**
- Learn: content-addressed versioning; immutability + audit.
- Build: content-hash spec versioning; `spec_versions` history with parent links; identical resubmit is a no-op.
- Earn: "Every spec change is an immutable, auditable version — the base layer of governance."

**Day 7 — Contract compatibility engine** ⭐ *flagship talking point*
- Learn: schema evolution; the breaking-change taxonomy.
- Build: compatibility engine (compatible: add-nullable, widen-type, relax-not-null; breaking: drop/rename, narrow-type, nullable→not-null); truth-table tests; reject breaking on update with a diff; `--allow-breaking` override, audited.
- Earn: "I let producers move fast without shattering consumers — compatibility rules block breaking changes by default."

### M2 — Reconciler & Runner

**Day 8 — Executable pipeline model + executor port**
- Learn: desired vs. actual state; the reconciliation pattern (borrowed from Kubernetes controllers).
- Build: compile a spec into an executable pipeline (DAG of steps); `PipelineExecutor` port.
- Earn: "I model the platform as a reconciler — declarative desired state materialized to an execution plan."

**Day 9 — Local topological runner**
- Learn: DAG topological execution; the step state machine.
- Build: local executor runs steps in topo order; run/step state machine (pending→running→success/failed), persisted.
- Earn: "Airflow is a pluggable backend — my runner is an interface, so I can swap orchestrators without touching domain logic."

**Day 10 — Idempotency & re-runs**
- Learn: idempotency in data pipelines; why re-runs must be safe.
- Build: idempotent run semantics (re-run → same state, no duplicate side effects); run keys/watermarks.
- Earn: "Re-runs are idempotent — essential for financial correctness where a double-run can't double-count."

**Day 11 — Drift detection**
- Learn: config drift; detecting desired ≠ actual.
- Build: reconcile detects and reports divergence between spec and running pipeline.
- Earn: "The reconciler continuously detects drift between declared and running state."

**Day 12 — Reconciler hardening + failure paths**
- Learn: partial-failure handling; safe rollout (never leave half-materialized).
- Build: atomic reconcile; rollback on failure; partial-failure tests.
- Earn: "Reconciliation is atomic — a failed rollout never leaves a pipeline half-built."

### M3 — Transform (dbt)

**Day 13 — dbt-duckdb integration**
- Learn: ELT and the transformation layer; dbt's role.
- Build: wire dbt-duckdb; run a staging model against raw; capture success/failure.
- Earn: "I integrated dbt as a SQL-based, testable, version-controlled transform layer."

**Day 14 — Spec-driven models + staging→marts**
- Learn: layered modeling (staging / intermediate / marts).
- Build: attach dbt models from spec transforms; run staging → marts.
- Earn: "Transformations are declared in the spec and materialized through dbt's layered model."

**Day 15 — Manifest capture + dbt tests**
- Learn: the dbt manifest as a metadata source; dbt tests as gates.
- Build: capture the manifest (feeds lineage later); run dbt tests; failures surface as run failures.
- Earn: "I capture the dbt manifest as metadata — it feeds lineage and impact analysis downstream."

### M4 — Quality & Gates

**Day 16 — Freshness-clock ADR + freshness check**
- Learn: the deferred decision — event-time watermark vs. wall-clock vs. business-calendar-aware.
- Build: ADR deciding the clock model + rationale; freshness check implementation.
- Earn: "I can articulate why freshness uses [chosen clock] and the failure modes of the alternatives."

**Day 17 — Volume & integrity checks**
- Learn: data-quality dimensions (volume anomaly, null, uniqueness, referential integrity).
- Build: the check library across those dimensions.
- Earn: "I built a quality-check library covering the core DQ dimensions."

**Day 18 — Quality gates & quarantine**
- Learn: gates vs. monitors; quarantine over propagation.
- Build: gates between layers that quarantine failing data; `quality_results` persisted.
- Earn: "Bad data is quarantined at the gate, not propagated — fail-closed, not fail-open."

**Day 19 — Quality results wired into runs**
- Learn: quality as a first-class run output.
- Build: quality results queryable; wired into the run lifecycle; a bad-data fixture proves quarantine.
- Earn: "Quality is a first-class, queryable output of every run."

### M5 — Catalog & Lineage

**Day 20 — Dataset registry / catalog**
- Learn: catalog concepts; datasets as products with owners.
- Build: dataset registry (name, owner, team, schema), populated from specs/runs.
- Earn: "Every dataset has an owner and lives in a catalog — data-as-a-product."

**Day 21 — Lineage source-of-truth ADR + table-level lineage**
- Learn: the deferred decision — declared-and-verified vs. parsed-from-SQL.
- Build: ADR; table-level lineage edges (declared in spec, verified against the dbt manifest).
- Earn: "I chose [approach] for lineage and can defend it against SQL-parsing's failure modes."

**Day 22 — Lineage graph + impact query**
- Learn: graph traversal for lineage; impact analysis.
- Build: lineage graph; "what's downstream of dataset D" via BFS.
- Earn: "I can answer 'what breaks if this changes' with graph impact analysis."

**Day 23 — Lineage verification against manifest**
- Learn: reconciling declared vs. actual lineage.
- Build: verify declared lineage matches the dbt manifest; flag mismatches.
- Earn: "Declared lineage is verified against actual dbt lineage — no silent drift."

### M6 — SLO & Incident

**Day 24 — SLO model + evaluation + error budget**
- Learn: SLIs/SLOs/error budgets applied to *data*, not services.
- Build: SLO definitions (freshness/quality), evaluation, error-budget tracking.
- Earn: "I applied SLO/error-budget thinking to data — and can explain why data SLOs are harder than service SLOs."

**Day 25 — Incident detection**
- Learn: turning an SLO breach into an incident; detection latency.
- Build: SLO breach → incident opened with run + lineage context.
- Earn: "SLO breaches automatically open incidents enriched with lineage context."

**Day 26 — Incident grouping / dedup**
- Learn: root-cause grouping — one cause must not page twenty times.
- Build: dedup/grouping so a single upstream break yields one incident.
- Earn: "I group incidents by root cause — the difference between an alerting system people use and one they mute."

**Day 27 — Incident lifecycle + routing**
- Learn: incident states, ownership routing, post-incident review.
- Build: lifecycle state machine (open→ack→resolved), owner routing, `incident_events` audit.
- Earn: "Incidents have a full lifecycle and route to the owning team automatically."

### M7 — API & CLI

**Day 28 — FastAPI control-plane surface**
- Learn: API design for a control plane; OpenAPI.
- Build: endpoints for specs/runs/catalog/lineage/incidents; OpenAPI docs.
- Earn: "The whole platform is drivable via a documented control-plane API."

**Day 29 — CLI (the self-serve surface)**
- Learn: CLI as developer UX; the paved road.
- Build: CLI (submit spec, trigger run, query incidents).
- Earn: "I built the self-serve surface — submit a spec, get a governed pipeline."

### M8 — MCP + AI data-ops agent

**Day 30 — MCP server, read-only tools**
- Learn: MCP; tool design; read-only-by-default.
- Build: MCP server exposing catalog/lineage/run-history/schema-diff/incident tools (read-only).
- Earn: "I exposed the platform to agents via MCP — read-only tools, safe by construction."

**Day 31 — LangGraph agent + context gathering**
- Learn: agent orchestration (state machine / ReAct); context assembly.
- Build: agent that, on an incident, gathers lineage + recent runs + schema diffs + correlated changes.
- Earn: "The agent assembles incident context from the same tools a human on-call would use."

**Day 32 — Hypothesis → verification loop**
- Learn: grounded reasoning; tool-verified hypotheses (anti-hallucination).
- Build: agent ranks hypotheses, verifies via tool calls, drafts a cited runbook.
- Earn: "The agent's conclusions are tool-verified and cited — not hallucinated root causes."

**Day 33 — Guardrails**
- Learn: agent guardrails — read-only default, human-in-the-loop on writes, PII redaction, output-schema validation, cost/rate caps.
- Build: guardrail layer; no write action without human approval.
- Earn: "I can trust the agent in an ops loop — HITL on writes, PII-redacted input, schema-validated output."

**Day 34 — Eval harness (CI-gated)** ⭐ *the senior AI signal*
- Learn: evaluating agents — labeled incidents, RCA top-1/top-3, false-positive rate, LLM-as-judge + ground truth.
- Build: synthetic labeled incident set; eval harness; threshold gate runnable in CI.
- Earn: "My agent is eval-gated in CI — changes can't silently regress RCA quality. That's the senior signal, not 'I called an LLM.'"

### M9 — Observability & Polish

**Day 35 — Observability**
- Learn: OpenTelemetry; data-specific SLIs; tracing across ingest→transform→quality.
- Build: structured logs, traces, run/SLI metrics, a minimal dashboard.
- Earn: "I can trace a datum from ingest to serve and answer 'why is this dashboard stale' in one place."

**Day 36 — Demo, docs, productionization story**
- Learn: telling the story — "what I stubbed and why / how I'd productionize."
- Build: seed the "upstream schema change breaks 20 downstream models" demo; README/architecture doc; consolidate ADRs; productionization section.
- Earn: "I can demo a real data incident end-to-end and say exactly what I'd change to run this at scale."

---

## Talking-point bank

Accumulates in `PROGRESS.md` as you complete each Earn step. By Day 36 you'll have ~36 concrete, defensible points spanning system design, data platforms, distributed-systems correctness, and trustworthy AI — enough to carry any senior interview loop.

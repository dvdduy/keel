# ADR 0002: Declared-and-verified lineage

## Status

Accepted

## Context

Keel needs table-level lineage that can answer impact questions across the whole
platform. That graph must include external ingestion, dbt transforms, future
cross-pipeline dependencies, and datasets not managed by dbt.

Lineage is also a governance surface. Keel must be able to distinguish producer
intent from observed implementation so that an omitted, unintended, or stale
dependency can be reported as drift. An observation alone cannot reveal a gap
between what was promised and what shipped.

The current compiler exposes an identity wrinkle. In a pipeline with a transform,
ingestion materializes `spec.destination` as the raw table and dbt materializes
`main.<transform>` as the final table. The Day 20 catalog currently projects
`spec.destination` as the consumer-facing dataset. Lineage node identities must
describe physical roles consistently with execution, even while that catalog
projection is reconciled later.

## Options considered

### Declared-and-verified

The spec declares producer intent and is authoritative for platform lineage.
Observed artifacts verify that intent. This spans non-dbt edges and creates the
desired-versus-actual comparison required for drift detection.

The present DSL can declare its external-source-to-raw edge and, when configured,
its raw-to-final transform edge. An explicit upstream-dataset field is deferred
until cross-pipeline lineage requires it.

### Manifest-derived

dbt's manifest is the strongest observation of dbt-managed table dependencies.
dbt has already rendered Jinja, expanded macros, resolved `ref()` and `source()`,
and applied adapter-specific semantics. Deriving dbt edges from it would be
accurate and inexpensive.

It is nevertheless incomplete as Keel's authority. It cannot represent Keel's
external CSV ingestion edge, non-dbt datasets, or dependencies outside a dbt
project. It also records actual implementation without an independent declaration
against which Keel can detect drift.

### Parsed from SQL

A parser such as sqlglot could cover SQL outside dbt and may eventually support
column-level lineage. It is attractive as a tool-neutral route from executable
text to observed dependencies.

SQL-parsing-via-sqlglot is rejected as Keel's lineage authority because parsed
lineage can drift silently from producer intent.

For dbt models, raw SQL is not the executable statement: it contains Jinja,
macros, `ref()` calls, dialect details, and ephemeral model expansion. Parsing it
duplicates dbt's work with less context and risks silently missing or inventing
edges. Like the manifest, parsed SQL describes actual behavior but not declared
intent.

## Decision

Keel uses declared-and-verified lineage.

`PipelineSpec` is authoritative for table-level producer intent. A CSV source node
uses the typed identity `source:csv:<path>`, keeping external nodes distinct from
dataset identities. A pipeline without a transform declares:

`source:csv:<path> -> spec.destination`

A pipeline with a transform declares the physical chain implemented by the
compiler:

`source:csv:<path> -> spec.destination -> main.<transform>`

The dbt manifest is a verification oracle, not the platform source of truth.

## Consequences

- Day 21 lineage extraction is pure and performs no I/O.
- Day 23 will compare declared edges with manifest-observed dbt edges and report
  disagreement.
- The DSL does not yet gain an explicit upstream dependency field. Adding one now
  would change every canonical Day 6 spec hash before cross-pipeline lineage can
  use it.
- The catalog and lineage currently disagree about the consumer-facing identity
  of transformed pipelines. Catalog projection must be reconciled with the
  compiler's raw `spec.destination` and final `main.<transform>` identities before
  catalog-keyed impact traversal is relied upon.
- Manifest parsing remains valuable and avoids reimplementing dbt resolution, but
  it is evidence rather than authority.

## Revisit when

Revisit SQL parsing when Keel adds column-level lineage or ingests non-dbt SQL.
sqlglot may then be an appropriate observation mechanism, without replacing
declared table-level intent as the governance authority.

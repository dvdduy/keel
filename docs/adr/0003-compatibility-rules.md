# ADR 0003: Compatibility rules

## Status

Accepted

## Context

Keel treats a dataset contract as a promise to downstream consumers. The platform
therefore needs a deterministic rule for deciding whether a proposed spec version
can replace the current one without forcing consumers to change.

The rule must be explainable in a review, stable in CI, and strict enough to stop
the common breakages: dropped columns, renamed columns, narrowed types, newly
required fields, and nullable fields becoming required.

## Decision

A contract change is breaking iff a dataset that is valid under the old contract
can become invalid under the new contract, or if a previously promised column is
removed.

Keel compares contract columns by name and reports every breaking change, not
just the first. The current taxonomy is:

- `column_dropped`: a previously promised column is absent.
- `column_type_changed`: a type change is not an allowed widening.
- `column_made_required`: a nullable column becomes non-nullable.
- `required_column_added`: a new non-nullable column is required.

The only built-in widening today is `integer -> decimal`. Adding nullable columns
is compatible. Reordering columns is compatible because consumers should bind by
name, not by ordinal position.

Breaking changes are rejected by default. `--allow-breaking` is an explicit,
audited escape hatch: Keel records `breaking_override=True` on the new spec
version and lets the rest of the governance system contain the risk.

## Consequences

The compatibility engine is conservative and deterministic. It catches rename as
a drop because the engine has no rename intent primitive yet; that is safer than
guessing based on shape.

The engine records all observed breakages so producers see a useful diff before
anything ships.

`--allow-breaking` is not a silent bypass. It is the place where a future approval
workflow, change window, or consumer-signoff policy can plug in without changing
the contract comparison rule.

## Rejected options

### Allow all additive changes

Rejected because adding a required column makes previously valid rows invalid.
The distinction between nullable and required additive changes matters.

### Infer renames heuristically

Rejected because name, type, and position heuristics are ambiguous. A future DSL
could add explicit rename intent, but the current platform should not invent it.

### Block every type change

Rejected because safe widenings are common and useful. The widening table stays
small and explicit so it can be reviewed as policy.

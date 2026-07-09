# ADR 0001: Freshness clock model

## Status

Accepted

## Context

Freshness sounds like one question, but it actually conflates two different checks:

1. Is the pipeline alive?
2. Is the data current?

Wall-clock freshness answers the first question: how long has it been since the last successful load?

Event-time freshness answers the second question: how old is the newest fact inside the data, usually measured from a dataset-specific timestamp column such as `MAX(order_created_at)`.

These clocks agree when the upstream source is healthy. They diverge during one of the most common data incidents: the upstream system silently stops emitting new facts, while the pipeline continues to run successfully on schedule. In that case, wall-clock freshness says the table is fresh because Keel loaded it recently, but event-time freshness says the data is stale because the newest fact is old.

## Decision

Keel defines freshness as the age of the newest fact in the dataset.

The primary clock is an event-time watermark when the pipeline declares a usable event-time column. The explicit fallback is wall-clock time from the latest successful load for sources that do not have a usable event-time signal.

Business-calendar awareness is deferred. It is a modifier on freshness arithmetic, not the foundation of the freshness clock model.

## Rationale

Event-time-primary freshness catches silent upstream stalls that wall-clock-since-load cannot detect. This makes freshness a data-currentness signal, not merely a pipeline-liveness signal.

Wall-clock fallback is still useful, but it is weaker. It can prove that Keel recently executed a load, but it cannot prove that the source is still producing current data.

Separating clock selection from clock arithmetic keeps the implementation clean. A policy layer chooses the `as_of` timestamp. The pure evaluator only decides whether that timestamp is within the allowed age.

## Rejected options

### Wall-clock as the primary definition

Rejected because it is blind to silent upstream stalls. A scheduled pipeline can keep succeeding while repeatedly loading the same stale tail. Wall-clock freshness would report this as healthy even though the newest business fact is old.

### Business-calendar-aware freshness as the base definition

Rejected as premature base complexity. Business calendars are real for financial and market data, where weekends and holidays should not count as expected production time. However, calendars require dataset-specific expectations, holidays, time zones, and operational policy. That belongs as a later modifier on top of the base clock, not as the foundation.

## Evaluator policy

The pure evaluator uses these rules:

- `as_of is None` returns `UNKNOWN`, not `STALE`. A missing signal means Keel has no data point to judge.
- `age == max_age_minutes` is `FRESH`. The freshness SLO is breached only when age is greater than the threshold.
- `as_of > now` returns `UNKNOWN`. A future timestamp indicates clock skew or bad source data, and Keel must not treat negative age as very fresh.
- `now` and `as_of` must be timezone-aware. Naive datetimes fail loudly at the boundary.

## Consequences

Checkpoint 1 implements pure freshness evaluation only. It does not perform I/O.

A future event-time wiring checkpoint should add:

- `FreshnessSpec.event_time_column: str | None = None`
- `WarehouseAdapter.max_timestamp(table: str, column: str) -> datetime | None`
- A clock-selection policy:
  - event-time column declared -> warehouse `MAX(column)`
  - otherwise -> latest successful run `finished_at`

Adding `event_time_column` to the spec schema may cause existing canonical spec JSON to include `event_time_column: null`, which changes content hashes for existing specs. That is acceptable as a one-time DSL schema evolution and platform migration. It is not a user-authored contract change.
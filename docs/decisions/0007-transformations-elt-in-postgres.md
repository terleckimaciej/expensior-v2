# 0007: Transformations — land raw, transform in Postgres, dbt deferred

- **Status:** Proposed
- **Date:** 2026-09-12

## Context

Transformation was the weakest part of legacy expensior: pandas doing row-by-row logic, parsing done in
flight so the original statement was lost, and database access scattered across endpoints.

Two different kinds of transformation are involved, and legacy treated them as one:

- **Operational** — statement CSV to normalized transactions, and rule-based classification. Triggered by
  a user action, writes to OLTP, carries product semantics (dry-run, conflict policy, undo a batch).
- **Analytical** — the dashboard aggregates: spend by category over time, monthly cashflow, category
  rollups. Read-only, and there will be many of them.

The owner uses dbt at work, so the question is whether it belongs here. See also
[ADR 0004](0004-analytics-bigquery-datastream.md), where BigQuery is already on the map.

## Decision

**Land raw first.** An import writes an immutable raw table — `batch_id`, line number, and the bank's
columns as text, exactly as received — before anything is interpreted. Normalized transactions are derived
from it. Fixing the parser then means reprocessing, not re-downloading statements, and "what actually
arrived?" is always answerable.

**Python owns what needs byte-level or product semantics:**

- decoding and mojibake repair — by the time text is in a column, cp1250-vs-broken-UTF-8 is no longer
  recoverable, so this happens at read time;
- deriving the stable `transaction_id`;
- conflict policy (`ignore | replace | abort`) and `--dry-run`, which are per-row decisions shown to the
  user before anything is written;
- the rules engine with typed (Pydantic) conditions, and the append-only classification history.

**SQL owns set-based work and all dashboard aggregation:** the transaction-type normalization map as a
lookup table, numeric casts (Polish decimal comma), regex extraction from free-form description cells,
and every aggregate the UI shows.

**Views model concepts, not screens:**

- one base view (transaction + its current classification + category path + flags);
- a few aggregate views by grain (month, month × category, month × subcategory);
- screen-specific arrangement stays in the query the app issues.

A view takes no parameters, so period and filter predicates come from the application as `WHERE` clauses
over these views. What stays in Python is choosing the view, passing parameters and shaping JSON for the
chart component — not computing metrics. Rule of thumb: if two screens need the same number computed the
same way it belongs in a view; if it is one screen's arrangement, it belongs in that screen's query.

**No materialization initially.** At this volume a view costs milliseconds on read, and materializing
introduces refresh scheduling and staleness — neither is worth taking on speculatively.

**Views are versioned in Alembic migrations**, with the SQL inlined in the migration rather than read from
a file that will later change; a migration is an immutable snapshot. Changing a view's column list needs
`DROP` + `CREATE`, not `CREATE OR REPLACE`.

**dbt stays out of the operational path**, and is the intended modelling layer if and when the BigQuery
track in ADR 0004 is picked up.

## Alternatives considered

| Option | Why not |
|---|---|
| dbt on Postgres for the operational path | Manual reclassifications are *source* data, but dbt models are rebuildable artifacts; undo-a-batch and dry-run are per-row product decisions dbt has no notion of; `dbt run` in a request path means a background job plus dbt-core in the image; and testing the rules engine would move from pytest on pure functions to database-backed tests, against `conventions.md` |
| Keep legacy's approach (pandas in the service layer) | Row-by-row logic in a dataframe library — the thing that made legacy hard to test and hard to follow |
| A dedicated view per dashboard | View sprawl and duplicated definitions; two screens end up computing the same number differently |
| Metrics computed in Python | Slower, untestable in isolation from the data, and scatters the definition of "monthly spend" across endpoints |
| Materialized views from the start | Buys speed that is not needed at thousands of rows per year, and costs a refresh mechanism and staleness semantics |
| SQL functions taking parameters instead of views + `WHERE` | Harder to version and test than a view; worth revisiting only if predicates get genuinely complex |

## Consequences

- Good: one definition per metric, in the database; the domain layer stays pure and unit-testable; no
  scheduler and no staleness anywhere in the system; raw data makes every derivation reproducible.
- Bad / accepted risks:
  - View DDL in Alembic is clunkier than a dbt model — `DROP`/`CREATE` dances on column changes.
  - Aggregate logic lives in SQL strings inside migrations, so it is not covered by mypy or ruff.
  - Raw tables duplicate storage. Negligible here (Neon free plan is 0.5 GB, statements are tiny).
- Follow-ups / when to revisit dbt — any one of these is a trigger, not the count of objects:
  - a view depends on a view depends on a view, and build order starts to matter;
  - aggregates need their own tests ("every transaction has exactly one current classification");
  - an aggregate becomes slow enough to need materialization — which brings a Cloud Run Job and
    Cloud Scheduler with it;
  - it stops being obvious where a number comes from, i.e. lineage is wanted.
  - Consider `alembic_utils` if views and functions multiply — it treats them as first-class entities
    with autogenerate support.
- Migration cost if the triggers fire is low: a dbt model is a `SELECT` with a materialization config, and
  so is a view. Starting this way keeps the dbt door open rather than closing it.

# Plan — direction and build order

This document carries **no status**: no checklists, no "done" markers ([ADR 0008](decisions/0008-open-work-in-github-issues.md)).
What is open, ready or finished is visible only in GitHub issues, the Project, milestones and merged pull
requests. Issues are created **per stage, when the stage starts**, not up front.

## Goal

A personal finance app: import PKO BP statements, classify transactions with a rules engine, review and fix
classifications by hand, and see where the money goes — running on GCP for ~0–5 PLN/month
(see the [README](../README.md) and the ADRs).

## Principle

Build the core as pure, testable Python and SQL first, usable from the command line against a local database,
and put the UI on top last. The UI is a thin layer with no domain logic
([ADR 0003](decisions/0003-ui-keyboard-first-htmx.md)), so the choice of framework — and the measurement it
needs — can wait until there is something to show.

## Stages

| # | Stage | What gets built | Why here |
|---|---|---|---|
| 0 | **Skeleton** | uv and `pyproject`, repository layout, pytest, ruff, mypy, pre-commit with detect-secrets, CI, local Postgres in `docker compose`, `pydantic-settings` | CI must be green from the first line of code. This is where the "code structure" item in [conventions](guides/conventions.md) gets decided |
| 1 | **Schema** | Alembic and the tables: import batches (with the original file bytes), raw rows (`jsonb`), transactions, categories, rules, classification history, flags; `NUMERIC(12,2)`; a partial unique index for "one current classification"; a repository layer | [ADR 0007](decisions/0007-transformations-elt-in-postgres.md); legacy had SQL scattered across endpoints ([legacy notes](domain/legacy-expensior.md)) |
| 2 | **Import** | A pure PKO BP parser: store the file bytes first, recognise the format version from the header, decode (incl. mojibake), land raw rows, derive transactions; stable `transaction_id`; idempotent re-import; conflict policy; dry-run; batch audit; undo a batch. A CLI first (`import <file> --dry-run`) that prints the target host and asks before writing | The largest piece of logic; fully testable on synthetic CSVs, no UI needed |
| 3 | **Classification** | Category tree; the rules engine with typed (Pydantic) conditions; running classification over unclassified transactions; append-only classification history; regex validated when a rule is saved | The domain core, plain Python over typed objects |
| 4 | **Views** | A base view plus aggregates by grain (month, month × category, month × subcategory), versioned in Alembic and tested against Postgres | Everything the dashboard shows, defined once in the database ([ADR 0007](decisions/0007-transformations-elt-in-postgres.md)) |
| 5 | **Query layer** | Service functions: filtered transaction lists, manual and bulk reclassification, dashboard queries | The whole backend is exercised by pytest before any UI exists |
| 6 | **UI** | The framework decision, then import, transactions and dashboard screens | Nothing earlier depends on it |
| 7 | **Deployment** | Dockerfile, Terraform, Cloud Run behind IAP, the Neon secret, CI/CD | [ADR 0002](decisions/0002-hosting-cloud-run-iap.md); the environment and deploy ADRs are settled by then |

All stages belong to one release, `0.1.0` — the MVP — because nothing is released before the deployment stage.
Finer-grained progress is the Project's job, not the milestone's. Milestones live on GitHub.

## Decisions that fall due inside the stages

- **Before stage 2:** accept or amend [ADR 0007](decisions/0007-transformations-elt-in-postgres.md) — the import
  design stands on it.
- **Before stage 2:** whether a bank API (Enable Banking) is a second source next to the CSV, and the rule that
  gives a transaction one id regardless of source. The answer comes from a research spike (a GitHub issue) and is
  recorded in ADR 0007 or a research note.
- **Before stage 6:** the UI framework. [ADR 0003](decisions/0003-ui-keyboard-first-htmx.md) makes NiceGUI the
  default, with the cost of an open WebSocket tab on Cloud Run to be measured (tracked as a GitHub issue); plan B
  is a Vue 3 + Vite SPA.
- **Before stage 7:** [ADR 0005](decisions/0005-environments-terraform-layout.md) and
  [ADR 0006](decisions/0006-deploy-ownership.md) are still proposed.

## Not planned yet

Anything not above — refunds and reimbursements, exports, a merchant dimension, BigQuery analytics
([ADR 0004](decisions/0004-analytics-bigquery-datastream.md)), a terminal client, keyboard navigation — is an
`idea` issue once someone wants it, or the legacy [backlog](domain/backlog.md) until then.

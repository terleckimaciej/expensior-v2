# Knowledge base

Everything decided, researched or learned about expensior-v2 lives here, in git, so it survives
context resets (human and AI).

## Plan

- [Plan — direction and build order](plan.md) (no status; open work is in GitHub issues)

## Decisions (`decisions/`)

| ADR | Title | Status |
|---|---|---|
| [0001](decisions/0001-database-neon-postgres.md) | Database: Neon serverless Postgres | Accepted |
| [0002](decisions/0002-hosting-cloud-run-iap.md) | Hosting: one Cloud Run service behind IAP | Accepted |
| [0003](decisions/0003-ui-keyboard-first-htmx.md) | UI: ready-made Python framework (NiceGUI) first, Vue SPA as plan B | Proposed (default: NiceGUI, pending spike) |
| [0004](decisions/0004-analytics-bigquery-datastream.md) | Analytics: Datastream CDC → BigQuery | Deferred |
| [0005](decisions/0005-environments-terraform-layout.md) | Environments (tagged revisions, Neon dev project) and Terraform layout | Proposed |
| [0006](decisions/0006-deploy-ownership.md) | Who owns the deploy — Terraform or CI | Proposed (no verdict) |
| [0007](decisions/0007-transformations-elt-in-postgres.md) | Transformations: land raw, transform in Postgres, dbt deferred | Proposed |
| [0008](decisions/0008-open-work-in-github-issues.md) | Open work in GitHub issues, a Project as the status view, docs carry no status | Accepted |
| [0009](decisions/0009-package-structure.md) | Code structure: a `src/` package in layers with one-way dependencies | Accepted |
| [0010](decisions/0010-database-schema.md) | Database schema: accounts, three layers, append-only classification history | Proposed |
| [0005](decisions/0005-environments-terraform-layout.md) | Environments (tagged revisions, Neon dev project) and Terraform layout | Proposed |
| [0006](decisions/0006-deploy-ownership.md) | Who owns the deploy — Terraform or CI | Proposed (no verdict) |

New decision → copy [`0000-template.md`](decisions/0000-template.md), next number, add a row above.

## Research (`research/`)

- [GCP & Neon costs, limits and gotchas (2026-09)](research/gcp-costs-2026-09.md)
- [UI frameworks: NiceGUI, Reflex, Vue SPA and Cloud Run WebSockets (2026-11)](research/ui-frameworks-2026-11.md)
- [Enable Banking and PKO BP: what the API returns, compared with the CSV (2026-11)](research/enable-banking-pko-2026-11.md)

## Domain (`domain/`)

- [Legacy expensior — what it did and what to keep](domain/legacy-expensior.md)
- [Feature backlog](domain/backlog.md) — legacy, frozen: open work lives in GitHub issues ([ADR 0008](decisions/0008-open-work-in-github-issues.md))

## Specs (`specs/`)

- [Keyboard UX](specs/keyboard-ux.md)

## Guides (`guides/`)

- [Engineering conventions](guides/conventions.md)

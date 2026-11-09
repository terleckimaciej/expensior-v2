# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, etc.) working in this repo.
`CLAUDE.md` imports this file, so this is the single source of truth.

## What this is

**expensior-v2** is a personal finance app: import bank statements (PKO BP CSV), classify
transactions with a rules engine, review/fix classifications by hand, and see where the money goes.

It is a **ground-up rewrite** of `../expensior` (FastAPI + Streamlit + SQLite prototype).
The old repo is **reference material only** — read it to understand the domain, do not copy code
from it wholesale. See `docs/domain/legacy-expensior.md` for what is worth keeping.

The owner builds this **their own way**, to a production-at-work standard, and uses it to practise
for the GCP Professional Data Engineer exam. Prefer explaining trade-offs and proposing small,
reviewable changes over large autonomous rewrites.

## Knowledge base — read before non-trivial work

| Path | What |
|---|---|
| `docs/decisions/` | Architecture Decision Records (ADRs). **Accepted ADRs are binding.** |
| `docs/research/` | Researched facts (prices, limits, gotchas) with sources and the date checked |
| `docs/domain/` | Domain model, legacy app analysis, feature backlog |
| `docs/specs/` | Behaviour specs (e.g. keyboard UX) |
| `docs/guides/` | Engineering conventions and tooling |

Rules:
- Do not change architecture (database, hosting, UI stack) without a new or updated ADR.
  If a task seems to need it, stop and say so.
- Prices and quotas go stale. Before relying on a number in `docs/research/`, check its date;
  if older than ~3 months, re-verify at the linked source and update the note.
- When a decision is made in conversation, write it down as an ADR (use `docs/decisions/0000-template.md`).

## Architecture at a glance (see ADRs for the why)

- **Database:** Neon serverless Postgres (free plan, scales to zero) — ADR 0001
- **Hosting:** single Cloud Run service, request-based billing, scale to zero, behind IAP — ADR 0002
- **UI:** a ready-made Python framework — NiceGUI is the default for the start, pending a spike on what its
  per-client WebSocket costs against scale-to-zero; plan B is a Vue 3 + Vite SPA (no Nuxt). HTMX and
  keyboard-first are dropped. Keep the UI layer thin: no domain logic in it — ADR 0003 (proposed)
- **Transformations:** land raw statement rows untouched, then derive; Python owns decoding, ids, conflict
  policy and the rules engine, SQL owns set-based work and every dashboard aggregate (views, not
  materialised); dbt stays out of the operational path — ADR 0007 (proposed)
- **Analytics:** optional later — Datastream CDC to BigQuery in a daily window, dbt as the modelling
  layer there — ADR 0004 (deferred)
- **Environments:** one GCP project, one Cloud Run service; pre-prod is a tagged no-traffic revision, not a
  second environment; separate Neon project for dev — ADR 0005 (proposed)
- **Budget target:** ~0–5 PLN/month. Anything that adds a fixed monthly cost needs an ADR.

## Engineering conventions (summary — full list in `docs/guides/conventions.md`)

- Python 3.12+, typed; config via `pydantic-settings`; no secrets in code or `.env` committed.
- SQLAlchemy 2.0 + Alembic for all schema changes — never edit the DB schema by hand.
- Tests with pytest; external HTTP mocked; domain logic (import parsing, rules engine) is pure and unit-tested.
- ruff (lint + format), mypy, detect-secrets via pre-commit. CI must be green before merge.
- Admin/CLI commands that write to a database print the target host and ask for confirmation.
- Conventional Commits (`feat:`, `fix:`, `docs:` …). Small PRs.

## Git and GitHub — the owner does it, not agents

- Never commit, push, create/switch/rename/delete branches, rebase, reset, tag, or open PRs.
  Leave all changes uncommitted in the working tree.
- The owner handles version control themselves, their own way (feature branch → PR into `master`).
- When work is ready, say so and suggest a Conventional Commit message — do not run it.

## Things that are easy to get wrong

- Money: never use float. Use `Decimal` in Python and `NUMERIC(12,2)` in Postgres.
- Dates: bank "Data waluty" is a date, not a timestamp; app timestamps are UTC (`timestamptz`).
- Import must be idempotent: re-importing the same statement must not duplicate transactions.
- Classification history is append-only: a new classification supersedes the old one, it does not overwrite it.
- Production data is real personal finance data. Never paste it into issues, logs, fixtures or prompts;
  test fixtures use synthetic data.

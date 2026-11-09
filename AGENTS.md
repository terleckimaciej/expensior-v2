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
- When a decision is made in conversation, write it down as an ADR (use `docs/decisions/0000-template.md`)
  and add a row to the table in `docs/README.md`.
- Do not rewrite accepted ADRs. A changed decision is a new ADR with `Accepted, supersedes NNNN`, and the old
  one gets `Superseded by NNNN`. Non-substantive fixes (an outdated phrase, a broken link) are fine.

## Architecture at a glance (see ADRs for the why)

- **Database:** Neon serverless Postgres (free plan, scales to zero) — ADR 0001
- **Hosting:** single Cloud Run service, request-based billing, scale to zero, behind IAP — ADR 0002
- **UI:** a ready-made Python framework — NiceGUI is the default for the start, pending a spike on what its
  per-client WebSocket costs against scale-to-zero; plan B is a Vue 3 + Vite SPA (no Nuxt). HTMX and
  keyboard-first are dropped. Keep the UI layer thin: no domain logic in it — ADR 0003 (proposed)
- **Code structure:** a `src/expensior/` package in layers `domain` (pure, no I/O) ← `db` ← `services` ← `cli`/`ui`;
  dependencies point one way, only `services` open transactions, the UI never touches `db`; the import
  rules are checked by import-linter in CI — ADR 0009
- **Transformations:** keep the original file bytes, land raw rows untouched, then derive; Python owns decoding, ids, conflict
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

## Workflow

- **Open work lives in GitHub issues, and a GitHub Project is the status view** ([ADR 0008](docs/decisions/0008-open-work-in-github-issues.md)).
  Start from `gh issue list`. A milestone is a release; labels are `enhancement` (planned), `idea` (a proposal,
  not planned), `bug`, `research`. Project statuses: Backlog → Ready → In progress → Done; *Ready* means the
  issue has Context, Plan, Tasks and Done when filled in.
- **Docs carry no status.** Never add checklists or "done" markers to them; progress is visible only in issues,
  the Project, milestones and merged pull requests. (An ADR's status describes a decision, not progress.)
- **Work starts from an issue.** Read it first (`gh issue view N`); its Tasks and Done when are the scope.
  A pull request that finishes it says `Closes #N` in its description. Small docs/chore changes (a typo, a
  broken link, formatting) may skip the issue; the PR then has no `Closes #` line.
- **Keep the issue in sync with the work.** When a decision changes the scope, propose a ready-to-paste
  `gh issue edit` that updates its Tasks. Before the pull request, propose ticking the finished tasks; anything
  done differently from the issue goes into a closing comment and into the PR description.
- **New work becomes an issue, not a note in the docs.** Propose a ready-to-paste `gh issue create` following the
  templates in `.github/ISSUE_TEMPLATE/` (feature: Context, Plan, Tasks, Done when; idea: Context, Proposal,
  Open questions). A time-boxed investigation is a `feature` issue labelled `research` whose Done when is
  "the answer is recorded in an ADR or a research note".
- **Docs change together with the code.** A pull request that changes behaviour updates the docs it affects;
  one that makes a decision adds an ADR in the same pull request.
- **Language:** everything committed is in English (code, comments, docs, commit messages, PR text);
  explanations to the owner in the chat are in Polish.

## Git and GitHub — the owner runs it, not agents

- Never run anything that writes to git or GitHub: `git add`, `commit`, `push`, creating/switching/renaming/
  deleting branches, rebase, reset, tag, `gh pr create`/`merge`, `gh issue create`/`edit`/`close`/`comment`,
  and changes to milestones, labels or the Project. Leave all changes uncommitted in the working tree.
- Read-only commands are fine: `git status`/`diff`/`log`, `gh issue list`/`view`, `gh pr view`.
- Instead, propose ready-to-paste commands together with the commit message and the PR title/description,
  so the owner can adjust them before running.
- Flow: a branch named `<type>/<short-description>` (e.g. `feat/import-pko-csv`) → pull request into `master`.
  Never commit directly to `master`.
- When work is ready, say so and propose the commit message — do not run it.

## Commits and pull requests

- [Conventional Commits](https://www.conventionalcommits.org/): `type: description` or `type(scope): description`.
  - Types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build` (packaging, dependencies, uv), `ci`, `chore`.
  - Scope is optional; use it only when it adds information (a layer such as `import`, `rules`, `ui`, `db`).
    Omit it for cross-cutting changes.
  - Description: imperative mood, lowercase, no trailing period, about 72 characters at most.
    Mark breaking changes with `!` (e.g. `feat(db)!: …`).
- **No AI attribution:** no `Co-Authored-By` and no "Generated with" lines in commit messages or PR descriptions.
- **Merging:** squash by default. The repo is set so the squash commit takes the PR **title** and the PR
  **description** (`squash_merge_commit_title=PR_TITLE`, `squash_merge_commit_message=PR_BODY`), so the PR is the
  one place to write them carefully. Commits on the branch are scratch and disappear in the squash. Use "rebase
  and merge" (or a merge commit) only when the PR holds several distinct commits worth keeping (e.g. a refactor
  separate from the feature); then *every* commit must follow the format and carry its own description, and the
  PR description does not reach git.
- **PR title:** the same format as a commit, about 72 characters at most (GitHub appends `(#N)`).
- **PR description** lands verbatim in the commit body on `master`, so write it as plain text: no markdown
  headings and no checkboxes (git drops lines starting with `#` when a message is edited in an editor). Follow
  the template in `.github/pull_request_template.md`: `Why:` first — the reason is what someone reading
  `git log` looks for — then `What:`, `Verification:`, and `Closes #N`. No "next steps": plans belong in issues,
  a commit records what happened. Fix the description before merging, not after.

## Things that are easy to get wrong

- Money: never use float. Use `Decimal` in Python and `NUMERIC(12,2)` in Postgres.
- Dates: bank "Data waluty" is a date, not a timestamp; app timestamps are UTC (`timestamptz`).
- Import must be idempotent: re-importing the same statement must not duplicate transactions.
- Classification history is append-only: a new classification supersedes the old one, it does not overwrite it.
- Production data is real personal finance data. Never paste it into issues, logs, fixtures or prompts;
  test fixtures use synthetic data.

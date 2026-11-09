# expensior-v2

Personal finance app — bank statement import, rule-based transaction classification and a
dashboard. Runs on GCP for ~0 PLN/month (Cloud Run + Neon Postgres).

Ground-up rewrite of the [`expensior`](../expensior) prototype.

## Where things are

- [`docs/`](docs/README.md): decisions (ADRs), research, domain notes, the [plan](docs/plan.md).
- Open work: GitHub issues and the project board (`gh issue list`).

## Local development

Needs [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 itself) and Docker.

```bash
uv sync                        # create .venv and install dependencies
cp .env.example .env           # local settings (gitignored)
docker compose up -d --wait    # local Postgres 16
uv run pre-commit install      # run the checks on every commit
uv run pytest                  # tests
uv run expensior --help        # the command-line entry point
```

Database: `uv run alembic upgrade head` applies the migrations to the database in `DATABASE_URL`, and
`uv run alembic revision -m "what changes"` creates a new one. Tests marked `db` need the local Postgres:
they use a separate database `expensior_test` (created on demand) and refuse any host but localhost, or a name
not ending in `_test`. Without Postgres they are skipped locally (and fail in CI); skip them explicitly with
`uv run pytest -m "not db"`. `TEST_DATABASE_URL` overrides the default test database.

Checks that CI also runs: `uv run pre-commit run --all-files` (ruff, mypy, import-linter, detect-secrets),
or one by one: `uv run ruff check`, `uv run mypy`, `uv run lint-imports`.

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

## Reading a bank account through the API

The main source of transactions is the bank API ([Enable Banking](https://enablebanking.com), free in its
restricted production mode for your own accounts); the CSV import is the second source
([research note](docs/research/enable-banking-pko-2026-11.md), [ADR 0011](docs/decisions/0011-bank-api-client.md)).

**Once, in the [Control Panel](https://enablebanking.com/sign-in/):**

1. Register an application in the **Production** environment. Let the browser generate the key, and move the
   downloaded `<application id>.pem` out of Downloads to `~/.config/expensior/enablebanking.pem` with
   `chmod 600`. It never goes into the repository.
2. Whitelist a redirect address of your choice (any `https://` address; nothing has to listen there).
3. Click *Activate by linking accounts* and approve your account in the bank's app.

**Settings** (in `.env`, see `.env.example`): `ENABLE_BANKING_APP_ID`, `ENABLE_BANKING_KEY_PATH` and
`ENABLE_BANKING_REDIRECT_URL`.

**Connect, then fetch** (the consent lasts up to 180 days; the commands warn two weeks before it ends):

```bash
uv run expensior bank connect        # one interactive run: approve in the bank's app, then name your accounts
uv run expensior bank fetch --dry-run   # what would be imported from every connected account, nothing written
uv run expensior bank fetch          # import; the first fetch takes the longest history
uv run expensior accounts list       # the accounts and where their consent stands
```

`bank connect` prints an address, waits while you approve access in the bank's app, and then asks you to paste
the address your browser ended up on (or only its `code`). It lists the bank accounts the consent covers and asks
what to call each one here; Enter skips an account. One bank account is one account of the application, so
`main`, `savings` and `usd` are three names for three bank accounts. Accounts are not added by hand: they come
into being here. Running `bank connect` again renews an ending consent and does not ask about the accounts that
are linked already. `bank fetch` takes every connected account, or one, `bank fetch main`.

Take the first fetch soon after approving: for about an hour the bank serves the whole history, later often
only the last 90 days. Every command that writes prints the target database host and asks first (`--yes` skips
the question).

# Engineering conventions

Baseline taken from `../menu_delivery`, which already works in production. Change deliberately.
Items marked **(under review)** are not settled — see the list at the bottom before relying on them.

## Tooling

| Concern | Tool |
|---|---|
| Python / deps | Python 3.12+, uv (`uv sync`, `uv run`) — a deliberate step up from Poetry, which `menu_delivery` uses. Flat layout, no `src/` |
| Config | `pydantic-settings`, `.env` locally (gitignored), `.env.example` committed |
| DB | SQLAlchemy 2.0 (typed ORM), psycopg 3, Alembic migrations **(under review)** |
| Web | **(under review)** — HTMX is out; NiceGUI is the leading candidate, pending the WebSocket cost check in [ADR 0003](../decisions/0003-ui-keyboard-first-htmx.md) |
| Lint / format | ruff (`ruff-check --fix`, `ruff-format`) |
| Types | mypy |
| Secrets scan | detect-secrets with `.secrets.baseline` |
| Tests | pytest; `responses` for HTTP mocks; synthetic fixtures only |
| Hooks | pre-commit (trailing whitespace, EOF, YAML, large files, merge conflicts, ruff, mypy, detect-secrets) |
| Container | Multi-stage Dockerfile (builder installs deps with uv, final image ships the venv + source) |
| Infra | Terraform |

## Local development

- Local Postgres via `docker compose` — `.env` points at local, never at prod.
- A throwaway Neon branch of production is the way to work against real-shaped data
  ([ADR 0005](../decisions/0005-environments-terraform-layout.md)).
- Write commands print the target DB host and ask for confirmation.
- How the CLI reaches production at all is **(under review)** — `menu_delivery` uses a one-off
  `DATABASE_URL=... uv run expensior <cmd>` override, which may not be the right answer here.

## Code structure

**(under review)** — the earlier `src/expensior/...` sketch is withdrawn: no `src/` layout, and the shape
needs rethinking now that [ADR 0007](../decisions/0007-transformations-elt-in-postgres.md) adds a raw
landing stage and SQL-owned aggregates, and `infra/` has a defined place
([ADR 0005](../decisions/0005-environments-terraform-layout.md)).

Settled so far: pure domain logic with no I/O stays separate from storage, and `alembic/`, `tests/`,
`infra/` and `docs/` sit at the repository root.

## Git & CI

- Conventional Commits; small PRs; `master` protected.
- CI on every push/PR: pre-commit + pytest.
- Releases are deliberate: build + deploy only on a `v*` tag (`gh release create vX.Y.Z --generate-notes`).
- Deploy to Cloud Run via Workload Identity Federation — no service account keys in GitHub.

## Under review

| Item | Question |
|---|---|
| DB stack | Are SQLAlchemy 2.0 + psycopg 3 + Alembic the right choices? Inherited from `menu_delivery`, not yet argued for this app — and [ADR 0007](../decisions/0007-transformations-elt-in-postgres.md) puts more weight on raw SQL than an ORM-first design assumes |
| UI stack | Keyboard-first is dropped and HTMX with it; NiceGUI leads, but its WebSocket-per-client model has to be costed against scale-to-zero first — see [ADR 0003](../decisions/0003-ui-keyboard-first-htmx.md) |
| CLI access to production | Whether a one-off env override is an acceptable mechanism at all |
| Code structure | Full layout, given raw landing, SQL views and `infra/` |

# Legacy expensior — what it did and what to keep

Source: `../expensior` (last commit 2026-02-16). FastAPI + Streamlit + SQLite, ~2.7k LOC,
raw `sqlite3` in every endpoint, pandas-based ETL, `manage.py` CLI.

## Domain model (legacy schema: `../expensior/sql/schema.sql`)

| Table | Role | Keep? |
|---|---|---|
| `import_batches` | Audit of each imported file (id = file sha256[:12] + UTC timestamp, row count, status) | Yes |
| `transactions` | Facts from the bank: date, type, amount, currency, description, city, country, batch | Yes — `amount` becomes `NUMERIC`, not `REAL` |
| `categories` | Tree via `parent_id` (category → subcategory) | Yes — clean up duplicates (`fast food`/`fast_food`/`fastfood`) |
| `rules` | Classification rules: pattern, `contains`/`regex`, source column, merchant, category, JSON `conditions`, priority | Yes — drop the text `category`/`subcategory` columns, keep only `category_id` |
| `transaction_classifications` | History of classifications per transaction, `method` = rule/manual, `is_current` flag | Yes — enforce "one current per transaction" with a partial unique index instead of app logic |
| `transaction_flags` | Multi-valued labels (`is_reimbursement`, `is_savings`, …) with history | Yes |

## Import (PKO BP CSV)

- Columns used: `Data waluty`, `Typ transakcji`, `Kwota` (Polish decimal comma, spaces), `Waluta`, plus
  free-form "description" cells with prefixes (`Tytuł:`, `Numer referencyjny:`, `Rachunek nadawcy:` …).
- Transaction type normalization map (Polish → snake_case), including **mojibake variants**
  (`Płatnoć kartš`, `Obcišżenie`) — encoding of exports is inconsistent; detect encoding explicitly.
- Stable `transaction_id` for idempotent import:
  - card payments → number from `Tytuł:`; BLIK terminal → `Numer referencyjny:`;
  - transfers → counterparty account number + short hash(date, amount, description);
  - fallback → short hash of row fields.
  Short hashes (4 hex chars) risk collisions — use longer hashes in v2.
- Conflict policy: `ignore | replace | abort`, plus `--dry-run`. Keep both.

## Rules engine (`../expensior/backend/app/services/classifier.py`)

- Rules sorted by `priority` desc; first match wins; only unclassified transactions are processed.
- `contains` is case-insensitive substring; `regex` is case-insensitive; invalid regex is skipped silently
  (v2: validate regex when the rule is saved).
- JSON `conditions`: `min_amount`, `max_amount`, `amount_range`, `amount_sign`, `effective_from/to`,
  IN-lists for `transaction_type`/`country`/`city`/`currency`, `not_contains`, `must_contain_any`, `must_contain_all`.
  v2: make this a typed Pydantic model, not free JSON.
- Seed data: `../expensior/data/rules.csv`, `../expensior/data/categories.csv`.

## Lessons / pain points

- DB access scattered across endpoints → v2 needs a repository layer from day one.
- pandas used for row-by-row logic → v2 rules engine should be plain Python over typed objects (easy to test).
- Streamlit UI was the weakest part (see ADR 0003).
- `legacy scripts/` shows the history: rollback of last import and duplicate diagnostics were needed —
  build "undo import batch" in from the start.

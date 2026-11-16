# 0011: The bank API client — a `bank` package, two dependencies, the key outside the repository

- **Status:** Proposed
- **Date:** 2026-11-16

## Context

The bank API (Enable Banking) is the main source of the application ([ADR 0007](0007-transformations-elt-in-postgres.md)).
Reading it needs things the code did not have: network calls, a signing key for the requests, and
two libraries. [ADR 0009](0009-package-structure.md) has no place for network I/O: `domain` must stay
pure and `db` is for the database. The spike
([findings](../research/enable-banking-pko-2026-11.md)) showed how the API behaves; this ADR decides where
the client lives and how it is kept safe.

## Decision

**A `bank` package, beside `db`.** `src/expensior/bank/` holds the clients of bank APIs. It sits under
`services` and above `domain`, independent of `db` (neither imports the other); import-linter enforces it, and
also that `cli` never imports `bank` and that `domain` imports no HTTP or JWT library. `services` use a client
through a small interface (`TransactionFetcher`), so the fetch service is tested with a fake.

**Two dependencies.** `httpx` for HTTP: it takes an injected client, so tests use its mock transport and never
touch the network. `PyJWT` with the `crypto` extra for the RS256 token the API wants (`kid` is the application id,
`iss` `enablebanking.com`, `aud` `api.enablebanking.com`).

**The private key stays in a file outside the repository.** Only its path (`ENABLE_BANKING_KEY_PATH`) and the
application id are settings; the key's text is read when the client is built and never appears in a message, a
log or an exception. Errors carry the HTTP status and the API's error code, not the request. The file should be
readable by its owner only (mode 600). On Cloud Run the key will come from Secret Manager as a mounted file, which
keeps the same setting.

**The network call runs outside any database transaction.** A fetch can take minutes (pages of history), so the
fetch service calls the API first and only then opens the import's transactions. What it fetched is stored as one
JSON document (the transactions as received) and imported by the same service as a file, so a fetch gets the dry
run, the conflict policy and the audit of every import.

**`accounts.source` is the bank, not the channel.** The CSV does not say which account it is from, and the API
knows an account by its identification hash. One real account must be one account in the application, or the
same transaction would get two ids and be stored twice. So an account is held at a bank (`pko_bp`), the hash is
linked to it as `external_ref` the first time the API is used (by name, to an account that exists from a CSV
import, or as a new one), and the channel a batch came by is `import_batches.source`. This clarifies the examples
in [ADR 0010](0010-database-schema.md), which listed the API as an account's source.

**The consent is stored on the account.** An account keeps the id of its bank session and when the consent ends
(`bank_session_id`, `consent_valid_until`). The bank's account ids change with every consent, so a fetch reads
the session and picks the account by its identification hash instead of storing an id. The commands warn two
weeks before the consent ends and, once it has ended, ask for a new one without calling the bank. One bank
account is one account of the application, so a consent that covers three bank accounts becomes three accounts.

**Connecting is three explicit steps, and the command line runs them in one interactive run.** The user approves
access in the bank's app, outside the application, so the flow crosses a step the application does not control:
`begin_connect` asks for the consent and returns the address and a `state`; `open_session` takes what the user
pasted back (the address or only the code), checks that its `state` is the one asked for and exchanges the code,
which works once, for a session; `link_accounts` links the bank accounts the user named, with the consent, in one
transaction. Every step takes and returns its values explicitly. `bank connect` is a thin client of the three in
one process: it keeps the `state` and the session in memory, so it needs no flags that carry them between runs.
This is enough while the command line is the only client. A web page cannot do it, since the two halves are
different requests: when the interface arrives, the pending approval (its `state`, and the session until the
accounts are named) is stored in the database behind the same three steps, and the redirect address becomes a
route of the application, so nothing is pasted. Fetching stays non-interactive, because it will run on a
schedule; renewing a consent cannot be automated, since the user must approve it.

## Alternatives considered

| Option | Why not |
|---|---|
| `requests` | Synchronous like `httpx`, but has no built-in mock transport; `httpx` is the same effort and easier to test |
| An async client (`aiohttp`, async `httpx`) | The CLI and the services are synchronous; async adds a second style for no gain at one fetch a day |
| An OAuth library (for example Authlib) | The API wants one self-signed JWT per request, not an OAuth flow; PyJWT is enough and smaller |
| The client inside `services` | Mixes network I/O with use cases and cannot be told apart from them by the import rules |
| The client inside `domain` | Breaks the rule that `domain` is pure and needs no I/O library |
| A separate account per channel (CSV, API) | The same transaction would get two ids; the CSV could not enrich what the API gave, and totals would double |
| The private key in an environment variable or in `.env` | It ends up in process listings, logs and backups; a file with restricted permissions is the conventional place |
| Several commands with flags that carry the session between runs (`connect`, then `--code`, then `--session --bank-account`) | The steps mirrored the API, not what the user does; the same command run twice with different flags was the confusing part, and the session id had to be copied between runs |
| Storing the pending approval in the database now | Needed only when a web page runs the steps as separate requests; a table and a migration for an interface that does not exist yet. The steps already take their values explicitly, so it can be added behind them |

## Consequences

- Good: the pure domain is untouched; the client is tested without a network; the key never enters the
  repository; one account carries both channels; a new bank is a new client in one package.
- Bad / accepted risks:
  - Two dependencies, one of them (`cryptography`) a compiled library, in the image and the lock file.
  - The key is a file on the owner's machine: losing the machine means revoking the application in the
    Control Panel.
  - Linking by name means a mistyped name creates a second account; the fetch service refuses to link an account
    that is already linked to another bank account.
- Follow-ups:
  - Commands and the consent's expiry (the consent lasts up to 180 days): [#29](https://github.com/terleckimaciej/expensior-v2/issues/29).
  - Fetching only new transactions after the first fetch: [#14](https://github.com/terleckimaciej/expensior-v2/issues/14).
  - Handling `429` (the bank limits background fetches to about four a day) when fetching becomes scheduled.

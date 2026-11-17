# Enable Banking and PKO BP — what the API returns, compared with the CSV

- **Checked:** 2026-11-09 (spike [#12](https://github.com/terleckimaciej/expensior-v2/issues/12), run against the
  owner's own PKO BP account); the inventory of fields and the other endpoints were checked on 2026-11-17 (see
  "Complete inventory"). Re-verify anything you rely on if this is older than ~3 months.
- Only aggregates and field names are recorded here. The raw responses stay on the owner's machine, outside the
  repository; production data never goes into issues, logs, fixtures or prompts (`AGENTS.md`).

## Why Enable Banking

- GoCardless Bank Account Data (formerly Nordigen) has had new signups disabled since July 2025, so its free tier is
  not available to a new user ([official notice](https://bankaccountdata.gocardless.com/new-signups-disabled)).
- Enable Banking offers a free **restricted production** mode: real bank data, but only for accounts the owner links
  to the application. Its terms allow it for evaluation or the personal use of private individuals, and say the
  right is limited and revocable ([terms](https://enablebanking.com/terms/)). Unrestricted production needs a
  contract and KYC, which a personal app does not need.

## Access and consent

- Register an application in the Control Panel with the **Production** environment; the browser generates the
  private key. Terms, privacy links and the data-protection e-mail are not checked in restricted mode
  ([FAQ](https://enablebanking.com/docs/faq/)).
- "Activate by linking accounts" whitelists the account for the application. It is **not** the bank consent: the
  data is released only after a separate authorisation through the API (`POST /auth`, then `POST /sessions`)
  ([linked accounts](https://enablebanking.com/docs/api/linked-accounts/)).
- Requests are authenticated with a JWT signed RS256 by the application's private key (`kid` = application id,
  `iss` = `enablebanking.com`, `aud` = `api.enablebanking.com`, lifetime up to 24 h)
  ([API reference](https://enablebanking.com/docs/api/reference/)).
- PKO Bank Polski is listed with `psu_types` `business` and `personal`; the maximum consent is **180 days**, after
  which a new authorisation is needed (new session id and account ids; the account is recognised by
  `identification_hash`).
- Many banks allow about 4 background fetches a day; a request made while the user is present is exempt
  ([FAQ](https://enablebanking.com/docs/faq/)).
- The redirect URL can be any HTTPS address whitelisted in the application: the authorisation `code` is copied from
  the address bar, so nothing needs to listen there.

## What PKO returns

Measured with `strategy=longest` and `transaction_status=BOOK`, one account, 2026-11-09:

| Measured | Result |
|---|---|
| History depth | **730 days** (exactly two years); older history is not available through the API |
| Time to fetch the full history | about 4 minutes, in pages (`continuation_key`) |
| `entry_reference` | present on every transaction, no duplicates, identical across two fetches in one session |
| `balance_after_transaction` | present on every transaction |
| `remittance_information` | always a list of exactly two lines |
| `creditor.name` / `debtor.name` | filled on only about 4% of transactions (mostly transfers) |
| Counterparty IBAN | filled on most incoming transfers and on a few outgoing ones |

Empty on every transaction: `value_date`, `transaction_date`, `bank_transaction_code`, `merchant_category_code`,
`note`, `reference_number`. The bank does not supply a category, so classification stays with our rules.

The first line of `remittance_information` is the description (the merchant name for card payments, the title or
counterparty for transfers); the second is the operation type, a fixed English code:

| CSV "Typ transakcji" | API second line |
|---|---|
| Płatność kartą | `CARD-PAYMENT` |
| Zwrot płatności kartą | `CARD-PAYMENT-RETURN` |
| Płatność web - kod mobilny | `MOBILE-PAYMENT-POS-NO-CARD-TX-CODE` |
| Zakup w terminalu - kod mobilny | `MOBILE-PAYMENT-POS-TX-CODE` |
| Przelew na konto | `TRANSFER-IN` |
| Przelew z rachunku | `TRANSFER` |
| Przelew na telefon przychodz. zew. | `MOBILE-PAYMENT-C2C-EXTERNAL` |
| Przelew na telefon przychodz. wew. | `MOBILE-PAYMENT-C2C` |
| Zlecenie stałe | `STANDING-ORDER` |
| TRANSPORT_TICKET_PAYMENT | `TRANSPORT-TICKET-PAYMENT` |
| WYMIANA W KANTORZE - OBCIĄŻENIE | `CURRENCY-EXCHANGE-DEBIT` |

`AUTOSAVER` is a further type (automatic transfers to savings, about a fifth of all transactions): it is not a
spending category and needs its own rule.

## API against the CSV export

Compared on the last three months of one account:

- **Matching:** every booked CSV row (276 of 276) has exactly one API counterpart on the pair *(signed amount,
  balance after the transaction)*; none ambiguous, none unmatched. The CSV carries no bank-assigned id, so this
  pair is what links the two sources.
- **Dates:** the API `booking_date` equals the CSV "Data operacji" on every row. The CSV "Data waluty" differs
  from it on about 85% of rows, and the API has no such field.
- **Holds:** the CSV contains `Blokada` rows (no operation date, balance "W rozliczeniu"). The same payment later
  appears as a booked row with a different type and date. The API returns booked transactions only.
- **Description, card payments:** the first line of `remittance_information` is the city, the merchant and a
  two-letter country code written together with no separator (in 215 of 218 card payments it fits that shape
  exactly). The CSV keeps merchant, city and country name apart, so from the API the merchant cannot be told from
  the city; a rule that looks for a phrase inside the description still matches.
- **Description, transfers and standing orders:** the first line equals the CSV title, once whitespace is
  collapsed (17 of 17 rows). For BLIK phone transfers the first line contains the CSV title and more text (8 of
  11), so it is longer than the CSV description.
- **Description, BLIK payments, tickets, refunds and currency exchange:** the first line is a reference number or
  other text, and no other field of the transaction carries the merchant (searched in every field). Those
  transactions (about 9% of the three months compared) have no merchant name from the API at all, while the CSV
  has it.
- **Type codes:** the eleven codes seen in the comparison map one to one to the CSV types (276 of 276). Four more
  appear in the two-year history and not in the CSV window: `MOBILE-PAYMENT-POS-RETURN` (12), `CARD-FEE` (4),
  `CARD-ATM` (3), `MOBILE-PAYMENT-ATM-TX-CODE` (1). They correspond by name to the legacy types `refund`,
  `card_fee`, `atm_withdrawal` and `atm_withdrawal`; that mapping is inferred, not checked against a CSV.
- **What follows:** the CSV is the richer source for descriptions (merchant, city, country), the API the fresher
  one. A CSV imported with the conflict policy `replace` therefore enriches transactions the API created first.
- **Encoding:** the CSV is `cp1250` (mojibake when read as UTF-8); the API is UTF-8.

## Complete inventory (2026-11-17)

Every key path of every stored raw row was scanned (3,391 rows, four accounts), not only the fields expected. The
only paths that carry data:

| Path | Rows | Note |
|---|---|---|
| `transaction_amount`, `balance_after_transaction`, `booking_date`, `credit_debit_indicator`, `status` | 3,391 | already in `transactions` |
| `remittance_information` | 3,391 | line 1 description, line 2 operation type |
| `transaction_id`, `entry_reference` | 3,391 | `transaction_id` is the Base64 encoding of `entry_reference`: no extra information |
| `creditor.name`, `creditor_account.iban` | 132 | transfers; the payee of an outgoing transaction |
| `debtor.name` | 152 | transfers; the payer of an incoming transaction |
| `creditor.postal_address.address_line` / `debtor.postal_address.address_line` | 5 / 197 | one line of the counterparty's address |
| `debtor_account.iban` | 2,784 | on outgoing rows this is **the owner's own account** |

Every other path is empty on every row: `bank_transaction_code`, `merchant_category_code`, `value_date`,
`transaction_date`, `exchange_rate`, `note`, `reference_number(_schema)`, both agents, `organisation_id`,
`private_id`, contact details and the rest of the postal address (street, post code, town, country).

- **The counterparty is chosen by direction:** `creditor` on a debit (`DBIT`), `debtor` on a credit (`CRDT`). The
  other side is empty, or on card and BLIK payments it is the owner's own account, so "the first non-empty side"
  returns the wrong party.
- **Counterparty is filled for transfers only** (282 rows: outgoing, incoming, BLIK phone, standing orders).
  Card payments, automatic savings, BLIK payments and refunds have no counterparty; their only text is
  `remittance_information`.

### Endpoints

The [API reference](https://enablebanking.com/docs/api/reference/) lists, for account data, `GET
/accounts/{id}/details`, `/balances`, `/transactions` and `/transactions/{transaction_id}`. The client uses only
the transaction list. The other three were called once each on one account (read-only) and compared by field
shape:

- **A single transaction** returns the same fields as the list, plus `resource_id` (equal to `entry_reference`).
  Nothing new; a BLIK terminal payment still has only a reference number. Tried on a card payment and a BLIK
  terminal payment.
- **Account details:** IBAN, BIC and name of the bank, the account's short description, usage, cash account type,
  currency, `uid` and identification hash(es). Nothing for classification.
- **Balances:** named balances with a type code. Not for classification; usable to reconcile the last
  `balance_after_transaction` against the bank.

### What is shared between banks

Enable Banking normalises the **names and structure** of the fields for every bank, not what a bank puts in them.
The documentation names what depends on the bank (the required `Psu-*` headers, whether the user picks accounts,
history older than 90 days, whether an account has a `uid`) and does not say which transaction fields are filled.
PKO leaves most of them empty and puts its own operation code in the second line of `remittance_information`
instead of `bank_transaction_code`, so there is no standard code to map to. How much another bank fills can only
be measured on that bank; the adapter is per source for that reason.

## Open

- Whether `entry_reference` stays stable after the consent is renewed (the documentation says it does for the same
  `identification_hash`; only testable at the first renewal).
- Whether older history can be fetched again later, or only inside the first hour after authorisation (the FAQ
  suggests the latter); the first fetch of a new session should therefore always use `strategy=longest` and keep the
  response.
- Whether the terms cover accounts of other people (restricted mode is described as the owner's own accounts).
- Whether the single-transaction endpoint returns more for other types (only a card payment and a BLIK terminal
  payment were tried), and whether calling it per transaction counts against the background-fetch limit.
- The part of the API reference after the account data endpoints (about the second half of the page) was not read.

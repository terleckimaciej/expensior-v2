# Enable Banking and PKO BP — what the API returns, compared with the CSV

- **Checked:** 2026-11-09 (spike [#12](https://github.com/terleckimaciej/expensior-v2/issues/12), run against the
  owner's own PKO BP account). Re-verify anything you rely on if this is older than ~3 months.
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
- **Description:** for card payments the API line equals the merchant part of the CSV "Lokalizacja: Adres:". The CSV
  also has city and country as separate parts and a "Tytuł" that is only a reference code for cards; the API has
  neither. For transfers the API line corresponds to the title or counterparty cells of the CSV.
- **Encoding:** the CSV is `cp1250` (mojibake when read as UTF-8); the API is UTF-8.

## Open

- Whether `entry_reference` stays stable after the consent is renewed (the documentation says it does for the same
  `identification_hash`; only testable at the first renewal).
- Whether older history can be fetched again later, or only inside the first hour after authorisation (the FAQ
  suggests the latter); the first fetch of a new session should therefore always use `strategy=longest` and keep the
  response.
- Whether the terms cover accounts of other people (restricted mode is described as the owner's own accounts).

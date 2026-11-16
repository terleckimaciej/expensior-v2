"""The Enable Banking source for PKO BP (``enable_banking_pko_v1``): the bank API's transactions.

The stored bytes of an API batch are one JSON document, built by ``make_document`` from what the
client received: a format marker, when it was fetched, the account's ``identification_hash`` and
the transactions exactly as they came. Reading it gives one raw row per transaction, whose cells
are the transaction object itself (ADR 0007). Adapting a row follows what the spike found when it
compared the API with the CSV (docs/research/enable-banking-pko-2026-11.md).
"""

import json
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from expensior.domain.identity import transaction_id_for
from expensior.domain.records import Transaction
from expensior.domain.statements.adapted import AdaptedStatement, Hold, Invalid, Parsed, collect
from expensior.domain.statements.formats import Unrecognised
from expensior.domain.statements.raw import RawBatch, RawRow
from expensior.domain.statements.source import Source
from expensior.domain.statements.transaction_types import normalise_enable_banking_type
from expensior.domain.statements.values import parse_date, parse_money

SOURCE = "enable_banking_pko"
VERSION = "enable_banking_pko_v1"


def make_document(
    transactions: list[dict[str, Any]], *, fetched_at: str, identification_hash: str | None
) -> bytes:
    """The bytes to store for a fetch: the transactions as received, plus what identifies it."""
    document = {
        "format": VERSION,
        "fetched_at": fetched_at,
        "account": {"identification_hash": identification_hash},
        "transactions": transactions,
    }
    return json.dumps(document, ensure_ascii=False).encode("utf-8")


def read_enable_banking(data: bytes) -> RawBatch | Unrecognised:
    """Read the stored document into one raw row per transaction, or say it is not one."""
    try:
        document = json.loads(data.decode("utf-8"))
    except ValueError:  # includes UnicodeDecodeError and JSONDecodeError
        return Unrecognised(header=())
    if not isinstance(document, dict) or document.get("format") != VERSION:
        return Unrecognised(header=())
    transactions = document.get("transactions")
    if not isinstance(transactions, list) or not all(isinstance(t, dict) for t in transactions):
        return Unrecognised(header=())
    rows = tuple(
        RawRow(line_no=position, cells=transaction)
        for position, transaction in enumerate(transactions, start=1)
    )
    return RawBatch(header=(), keys=(), rows=rows)


def _path(transaction: dict[str, Any], *keys: str) -> Any:
    """A value inside nested objects, or ``None`` when any step is missing."""
    value: Any = transaction
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _required(transaction: dict[str, Any], *keys: str) -> Any:
    value = _path(transaction, *keys)
    if value is None or value == "":
        raise ValueError("missing " + ".".join(keys))
    return value


def _signed_amount(transaction: dict[str, Any]) -> Decimal:
    magnitude = abs(parse_money(_required(transaction, "transaction_amount", "amount")))
    indicator = _required(transaction, "credit_debit_indicator")
    if indicator == "DBIT":
        return -magnitude
    if indicator == "CRDT":
        return magnitude
    raise ValueError(f"unknown credit_debit_indicator {indicator!r}")


def adapt_row(row: RawRow, account_id: int, batch_id: int) -> Parsed | Hold | Invalid:
    """Turn one API transaction into a transaction of the account, or say why it is not one."""
    tx = row.cells
    if tx.get("status") != "BOOK":
        return Hold(line_no=row.line_no)
    try:
        operation_date = parse_date(_required(tx, "booking_date"))
        value_date = parse_date(tx["value_date"]) if tx.get("value_date") else None
        amount = _signed_amount(tx)
        balance_after = parse_money(_required(tx, "balance_after_transaction", "amount"))
        currency = str(_required(tx, "transaction_amount", "currency")).strip().upper()
        remittance = tx.get("remittance_information")
        lines = remittance if isinstance(remittance, list) else []
        code = str(lines[1]).strip() if len(lines) > 1 else ""
        if not code:
            raise ValueError("missing the operation type (remittance_information, line 2)")
    except ValueError as error:
        return Invalid(line_no=row.line_no, reason=str(error))
    canonical = normalise_enable_banking_type(code)
    description = " ".join(str(lines[0]).replace("\xa0", " ").split()).upper() if lines else ""
    transaction = Transaction(
        transaction_id=transaction_id_for(account_id, operation_date, amount, balance_after),
        account_id=account_id,
        raw_batch_id=batch_id,
        raw_line_no=row.line_no,
        operation_date=operation_date,
        value_date=value_date,
        transaction_type=canonical or code,
        amount=amount,
        balance_after=balance_after,
        currency=currency,
        description=description,
        country=None,
        city=None,
    )
    return Parsed(transaction=transaction, unknown_type=None if canonical else code)


def adapt_rows(rows: Iterable[RawRow], account_id: int, batch_id: int) -> AdaptedStatement:
    """Adapt every transaction and count what was left out."""
    return collect(adapt_row(row, account_id, batch_id) for row in rows)


ENABLE_BANKING_PKO_V1_SOURCE = Source(
    source=SOURCE,
    version=VERSION,
    read=read_enable_banking,
    adapt=adapt_rows,
)

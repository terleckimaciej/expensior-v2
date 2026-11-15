"""The adapter for the PKO BP CSV (``pko_bp_v1``): a raw row becomes a transaction (ADR 0007).

A pure function over one row. A row is a transaction, a hold, or invalid; nothing raises for bad
data, so one broken row does not hide the rest and the import can report it.
"""

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from expensior.domain.identity import transaction_id_for
from expensior.domain.records import Transaction
from expensior.domain.statements.raw import RawRow
from expensior.domain.statements.transaction_types import HOLD_TYPE, normalise_pko_csv_type

# The columns with a name of their own; every other cell of a row belongs to the description.
_NAMED_COLUMNS = {
    "Data operacji",
    "Data waluty",
    "Typ transakcji",
    "Kwota",
    "Waluta",
    "Saldo po transakcji",
}
_CENT = Decimal("0.01")
_LOCATION_ADDRESS = re.compile(r"Adres:\s*(.*?)\s*Miasto:")
_LOCATION_ADDRESS_ANY = re.compile(r"Adres:\s*(.*)")
_LOCATION_CITY = re.compile(r"Miasto:\s*(.*?)\s*Kraj:")
_LOCATION_COUNTRY = re.compile(r"Kraj:\s*(.*)")
_TITLE_END = re.compile(r"\s+OD:")


@dataclass(frozen=True)
class Parsed:
    """A transaction; ``unknown_type`` is the bank's type text when it is not in the vocabulary."""

    transaction: Transaction
    unknown_type: str | None


@dataclass(frozen=True)
class Hold:
    """A hold ("Blokada"): not a transaction, the payment arrives later as a booked row."""

    line_no: int


@dataclass(frozen=True)
class Invalid:
    """A row that cannot be read, with the reason."""

    line_no: int
    reason: str


@dataclass(frozen=True)
class AdaptedStatement:
    """All rows of a statement: the transactions and what was left out, for the batch audit."""

    transactions: tuple[Transaction, ...]
    holds: int
    invalid: tuple[Invalid, ...]
    unknown_types: dict[str, int]


def _date(text: str) -> date:
    return date.fromisoformat(text.strip())


def _money(text: str) -> Decimal:
    """An amount as the bank writes it: a sign, spaces, a point or a comma; at most two decimals."""
    cleaned = text.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        value = Decimal(cleaned)
        if not value.is_finite() or value != value.quantize(_CENT):
            raise ValueError(f"not an amount with at most two decimals: {text!r}")
    except InvalidOperation as error:
        raise ValueError(f"not an amount: {text!r}") from error
    return value


def _labelled(row: RawRow) -> dict[str, str]:
    """The description cells as ``label -> value`` for cells written as ``Label: value``."""
    labelled: dict[str, str] = {}
    for key, cell in row.cells.items():
        if key in _NAMED_COLUMNS or ":" not in cell:
            continue
        label, value = cell.split(":", 1)
        labelled[label.strip()] = value.strip()
    return labelled


def _description(labelled: dict[str, str]) -> tuple[str, str | None, str | None]:
    """The description, city and country, written as legacy did so existing rules still match.

    A payment has a location: its address is the merchant. Anything else (a transfer, a standing
    order) is described by its title.
    """
    location = labelled.get("Lokalizacja")
    if location is not None:
        address = _LOCATION_ADDRESS.search(location) or _LOCATION_ADDRESS_ANY.search(location)
        city = _LOCATION_CITY.search(location)
        country = _LOCATION_COUNTRY.search(location)
        return (
            address.group(1).strip().upper() if address else "",
            city.group(1).strip().upper() if city else None,
            country.group(1).strip().upper() if country else None,
        )
    title = _TITLE_END.split(labelled.get("Tytuł", ""))[0].strip().upper()
    if title != "PRZELEW NA TELEFON":
        title = title.replace("PRZELEW NA TELEFON", "").strip()
    return title, None, None


def adapt_row(row: RawRow, account_id: int, batch_id: int) -> Parsed | Hold | Invalid:
    """Turn one raw row into a transaction of the account, or say why it is not one."""
    cells = row.cells
    csv_type = cells.get("Typ transakcji", "").strip()
    if csv_type == HOLD_TYPE:
        return Hold(line_no=row.line_no)
    try:
        operation_date = _date(cells.get("Data operacji", ""))
        value_text = cells.get("Data waluty", "").strip()
        value_date = _date(value_text) if value_text else None
        amount = _money(cells.get("Kwota", ""))
        balance_after = _money(cells.get("Saldo po transakcji", ""))
    except ValueError as error:
        return Invalid(line_no=row.line_no, reason=str(error))
    currency = cells.get("Waluta", "").strip().upper()
    if not currency:
        return Invalid(line_no=row.line_no, reason="the currency is missing")
    canonical = normalise_pko_csv_type(csv_type)
    description, city, country = _description(_labelled(row))
    transaction = Transaction(
        transaction_id=transaction_id_for(account_id, operation_date, amount, balance_after),
        account_id=account_id,
        raw_batch_id=batch_id,
        raw_line_no=row.line_no,
        operation_date=operation_date,
        value_date=value_date,
        transaction_type=canonical or csv_type,
        amount=amount,
        balance_after=balance_after,
        currency=currency,
        description=description,
        country=country,
        city=city,
    )
    return Parsed(transaction=transaction, unknown_type=None if canonical else csv_type)


def adapt_rows(rows: Iterable[RawRow], account_id: int, batch_id: int) -> AdaptedStatement:
    """Adapt every row and count what was left out."""
    transactions: list[Transaction] = []
    invalid: list[Invalid] = []
    unknown: Counter[str] = Counter()
    holds = 0
    for row in rows:
        result = adapt_row(row, account_id, batch_id)
        if isinstance(result, Parsed):
            transactions.append(result.transaction)
            if result.unknown_type is not None:
                unknown[result.unknown_type] += 1
        elif isinstance(result, Hold):
            holds += 1
        else:
            invalid.append(result)
    return AdaptedStatement(
        transactions=tuple(transactions),
        holds=holds,
        invalid=tuple(invalid),
        unknown_types=dict(unknown),
    )

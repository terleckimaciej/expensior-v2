"""The adapter for the PKO BP CSV (``pko_bp_v1``): a raw row becomes a transaction (ADR 0007).

A pure function over one row. A row is a transaction, a hold, or invalid; nothing raises for bad
data, so one broken row does not hide the rest and the import can report it.
"""

import csv
import re
from collections.abc import Iterable

from expensior.domain.identity import transaction_id_for
from expensior.domain.records import Transaction
from expensior.domain.statements.adapted import AdaptedStatement, Hold, Invalid, Parsed, collect
from expensior.domain.statements.decoding import DecodingError, decode
from expensior.domain.statements.formats import (
    PKO_BP_V1,
    StatementFormat,
    Unrecognised,
    detect_format,
)
from expensior.domain.statements.raw import RawBatch, RawRow, parse_raw
from expensior.domain.statements.source import Source
from expensior.domain.statements.transaction_types import HOLD_TYPE, normalise_pko_csv_type
from expensior.domain.statements.values import parse_date, parse_money

# The columns with a name of their own; every other cell of a row belongs to the description.
_NAMED_COLUMNS = {
    "Data operacji",
    "Data waluty",
    "Typ transakcji",
    "Kwota",
    "Waluta",
    "Saldo po transakcji",
}
_LOCATION_ADDRESS = re.compile(r"Adres:\s*(.*?)\s*Miasto:")
_LOCATION_ADDRESS_ANY = re.compile(r"Adres:\s*(.*)")
_LOCATION_CITY = re.compile(r"Miasto:\s*(.*?)\s*Kraj:")
_LOCATION_COUNTRY = re.compile(r"Kraj:\s*(.*)")
_TITLE_END = re.compile(r"\s+OD:")


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
        operation_date = parse_date(cells.get("Data operacji", ""))
        value_text = cells.get("Data waluty", "").strip()
        value_date = parse_date(value_text) if value_text else None
        amount = parse_money(cells.get("Kwota", ""))
        balance_after = parse_money(cells.get("Saldo po transakcji", ""))
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
    return collect(adapt_row(row, account_id, batch_id) for row in rows)


def read_pko_csv(data: bytes) -> RawBatch | Unrecognised:
    """Read the bytes as a PKO BP CSV, or say that they are not one.

    Bytes that cannot be decoded or split are "not recognised" too: the import keeps them anyway.
    """
    try:
        batch = parse_raw(decode(data).text)
    except (DecodingError, csv.Error):
        return Unrecognised(header=())
    known = detect_format(batch.header)
    if isinstance(known, StatementFormat) and known.version == PKO_BP_V1.version:
        return batch
    return Unrecognised(header=batch.header)


PKO_BP_V1_SOURCE = Source(
    source=PKO_BP_V1.source,
    version=PKO_BP_V1.version,
    read=read_pko_csv,
    adapt=adapt_rows,
)

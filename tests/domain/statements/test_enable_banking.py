"""The Enable Banking source reads the stored document and adapts the bank API's transactions."""

import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from eb_samples import api_transaction
from pko_samples import CSV_CP1250

from expensior.domain.statements.adapted import Hold, Invalid, Parsed
from expensior.domain.statements.enable_banking import (
    VERSION,
    adapt_row,
    adapt_rows,
    make_document,
    read_enable_banking,
)
from expensior.domain.statements.formats import Unrecognised
from expensior.domain.statements.pko_csv import adapt_row as adapt_csv_row
from expensior.domain.statements.raw import RawBatch, RawRow, parse_raw
from expensior.domain.statements.registry import Identified, identify

ACCOUNT = 1
BATCH = 7


def _row(**changes: Any) -> RawRow:
    return RawRow(line_no=1, cells=api_transaction(**changes))


def _parsed(**changes: Any) -> Parsed:
    result = adapt_row(_row(**changes), ACCOUNT, BATCH)
    assert isinstance(result, Parsed)
    return result


def _document(*transactions: dict[str, Any]) -> bytes:
    return make_document(
        list(transactions), fetched_at="2026-11-15T10:00:00Z", identification_hash="hash-1"
    )


def test_a_stored_document_reads_back_as_one_raw_row_per_transaction() -> None:
    first, second = api_transaction(), api_transaction(booking_date="2026-01-16")

    batch = read_enable_banking(_document(first, second))

    assert isinstance(batch, RawBatch)
    assert [row.line_no for row in batch.rows] == [1, 2]
    assert batch.rows[0].cells == first
    assert batch.rows[1].cells["booking_date"] == "2026-01-16"


def test_polish_letters_survive_the_document() -> None:
    batch = read_enable_banking(_document(api_transaction()))

    assert isinstance(batch, RawBatch)
    assert "PRZYKŁAD" in batch.rows[0].cells["remittance_information"][0]


@pytest.mark.parametrize(
    "data",
    [
        b"not json at all",
        b"\x81\x8d",
        b'{"format": "something_else", "transactions": []}',
        json.dumps({"format": VERSION, "transactions": "no"}).encode(),
        json.dumps({"format": VERSION, "transactions": [1, 2]}).encode(),
        b"[]",
        CSV_CP1250,
    ],
)
def test_anything_that_is_not_the_document_is_unrecognised(data: bytes) -> None:
    assert isinstance(read_enable_banking(data), Unrecognised)


def test_a_card_payment_becomes_a_signed_transaction() -> None:
    transaction = _parsed().transaction

    assert transaction.amount == Decimal("-12.34")
    assert transaction.balance_after == Decimal("100.00")
    assert transaction.operation_date == date(2026, 1, 15)
    assert transaction.value_date is None
    assert transaction.transaction_type == "card_payment"
    assert transaction.description == "WARSZAWASKLEP PRZYKŁADPL"
    assert (transaction.city, transaction.country) == (None, None)
    assert (transaction.raw_batch_id, transaction.raw_line_no) == (BATCH, 1)


def test_a_credit_is_positive() -> None:
    transaction = _parsed(
        credit_debit_indicator="CRDT",
        transaction_amount={"amount": "1700.00", "currency": "PLN"},
        remittance_information=["CZYNSZ ZA WRZESIEŃ", "TRANSFER-IN"],
    ).transaction

    assert transaction.amount == Decimal("1700.00")
    assert transaction.transaction_type == "transfer_to_account"


def test_the_same_transaction_from_the_api_and_from_the_csv_has_the_same_id() -> None:
    csv_row = parse_raw(CSV_CP1250.decode("cp1250")).rows[0]  # -12.34, balance 100.00, 2026-01-15
    from_csv = adapt_csv_row(csv_row, ACCOUNT, BATCH)
    from_api = adapt_row(_row(), ACCOUNT, BATCH)

    assert isinstance(from_csv, Parsed) and isinstance(from_api, Parsed)
    assert from_api.transaction.transaction_id == from_csv.transaction.transaction_id


@pytest.mark.parametrize(
    ("code", "canonical"),
    [
        ("MOBILE-PAYMENT-POS-RETURN", "refund"),
        ("CARD-FEE", "card_fee"),
        ("CARD-ATM", "atm_withdrawal"),
        ("MOBILE-PAYMENT-ATM-TX-CODE", "atm_withdrawal"),
        ("AUTOSAVER", "auto_savings"),
        ("INTEREST", "interest_accrued"),
        ("CREDIT", "pko_credit"),
        ("DEBIT", "pko_charge"),
        ("FEE", "bank_fee"),
        ("TAX", "tax"),
        ("CURRENCY-EXCHANGE-CREDIT", "currency_exchange_credit"),
    ],
)
def test_the_codes_map_to_the_legacy_vocabulary(code: str, canonical: str) -> None:
    result = _parsed(remittance_information=["X", code])

    assert result.transaction.transaction_type == canonical
    assert result.unknown_type is None


def test_an_unknown_code_is_kept_as_written_and_reported() -> None:
    result = _parsed(remittance_information=["X", "NEW-KIND-OF-THING"])

    assert result.transaction.transaction_type == "NEW-KIND-OF-THING"
    assert result.unknown_type == "NEW-KIND-OF-THING"


def test_a_transaction_that_is_not_booked_is_skipped() -> None:
    assert adapt_row(_row(status="PDNG"), ACCOUNT, BATCH) == Hold(line_no=1)


def test_a_value_date_is_kept_when_the_bank_gives_one() -> None:
    assert _parsed(value_date="2026-01-14").transaction.value_date == date(2026, 1, 14)


def test_the_description_collapses_whitespace_and_is_upper_case() -> None:
    result = _parsed(remittance_information=["  Sklep\xa0 przykład   x ", "CARD-PAYMENT"])

    assert result.transaction.description == "SKLEP PRZYKŁAD X"


@pytest.mark.parametrize(
    "changes",
    [
        {"booking_date": None},
        {"booking_date": "15.01.2026"},
        {"transaction_amount": {"amount": "12.345", "currency": "PLN"}},
        {"transaction_amount": {"amount": None, "currency": "PLN"}},
        {"credit_debit_indicator": "XXXX"},
        {"balance_after_transaction": None},
        {"transaction_amount": {"amount": "1.00", "currency": ""}},
        {"remittance_information": ["only one line"]},
    ],
)
def test_rows_that_cannot_be_read_say_why(changes: dict[str, Any]) -> None:
    result = adapt_row(_row(**changes), ACCOUNT, BATCH)

    assert isinstance(result, Invalid)
    assert result.reason


def test_a_whole_response_is_summed_up_for_the_audit() -> None:
    rows = [
        RawRow(1, api_transaction()),
        RawRow(2, api_transaction(status="PDNG")),
        RawRow(3, api_transaction(booking_date=None)),
        RawRow(4, api_transaction(remittance_information=["X", "NEW"], booking_date="2026-01-17")),
    ]

    adapted = adapt_rows(rows, ACCOUNT, BATCH)

    assert len(adapted.transactions) == 2
    assert adapted.holds == 1
    assert [item.line_no for item in adapted.invalid] == [3]
    assert adapted.unknown_types == {"NEW": 1}


def test_the_registry_recognises_the_document_and_still_the_csv() -> None:
    api = identify(_document(api_transaction()))
    csv = identify(CSV_CP1250)

    assert isinstance(api, Identified) and api.source.version == VERSION
    assert isinstance(csv, Identified) and csv.source.version == "pko_bp_v1"

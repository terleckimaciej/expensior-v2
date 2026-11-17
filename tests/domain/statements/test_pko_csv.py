"""The PKO adapter turns a raw row into a transaction, a hold or an invalid row."""

from datetime import date
from decimal import Decimal

from pko_samples import CSV_TEXT

from expensior.domain.identity import transaction_id_for
from expensior.domain.statements.adapted import Hold, Invalid, Parsed
from expensior.domain.statements.pko_csv import adapt_row, adapt_rows
from expensior.domain.statements.raw import RawRow, parse_raw

ACCOUNT = 1
BATCH = 7


def _row(overrides: dict[str, str] | None = None, line_no: int = 2) -> RawRow:
    cells = {
        "Data operacji": "2026-01-15",
        "Data waluty": "2026-01-15",
        "Typ transakcji": "Płatność kartą",
        "Kwota": "-12.34",
        "Waluta": "PLN",
        "Saldo po transakcji": "+100.00",
        "Opis transakcji": "Lokalizacja: Adres: SKLEP Miasto: WARSZAWA Kraj: POLSKA",
    }
    return RawRow(line_no=line_no, cells={**cells, **(overrides or {})})


def _parsed(row: RawRow) -> Parsed:
    result = adapt_row(row, ACCOUNT, BATCH)
    assert isinstance(result, Parsed)
    return result


def test_a_card_payment_becomes_a_transaction_with_its_merchant_and_place() -> None:
    row = parse_raw(CSV_TEXT).rows[0]

    result = _parsed(row)

    transaction = result.transaction
    assert transaction.transaction_type == "card_payment"
    assert transaction.description == "SKLEP PRZYKŁAD"
    assert (transaction.city, transaction.country) == ("WARSZAWA", "POLSKA")
    assert transaction.amount == Decimal("-12.34")
    assert transaction.balance_after == Decimal("100.00")
    assert transaction.operation_date == date(2026, 1, 15)
    assert (transaction.raw_batch_id, transaction.raw_line_no) == (BATCH, 2)
    assert transaction.transaction_id == transaction_id_for(
        ACCOUNT, date(2026, 1, 15), Decimal("-12.34"), Decimal("100.00")
    )
    assert result.unknown_type is None


def test_a_transfer_is_described_by_its_title() -> None:
    row = parse_raw(CSV_TEXT).rows[1]

    transaction = _parsed(row).transaction

    assert transaction.transaction_type == "transfer_to_account"
    assert transaction.description == "CZYNSZ ZA WRZESIEŃ"
    assert transaction.amount == Decimal("1700.00")
    assert (transaction.city, transaction.country) == (None, None)


def test_a_hold_is_not_a_transaction() -> None:
    row = parse_raw(CSV_TEXT).rows[2]

    assert adapt_row(row, ACCOUNT, BATCH) == Hold(line_no=4)


def test_a_payment_without_a_city_keeps_the_whole_address() -> None:
    row = _row({"Opis transakcji": "Lokalizacja: Adres: ALLEGRO.PL"})

    transaction = _parsed(row).transaction

    assert transaction.description == "ALLEGRO.PL"
    assert transaction.city is None


def test_a_title_ends_at_od_and_loses_the_phone_transfer_label() -> None:
    row = _row(
        {
            "Typ transakcji": "Przelew na telefon przychodz. zew.",
            "Opis transakcji": "Tytuł: PRZELEW NA TELEFON obiad OD: JAN KOWALSKI",
        }
    )

    assert _parsed(row).transaction.description == "OBIAD"


def test_the_bare_phone_transfer_label_is_kept() -> None:
    row = _row({"Opis transakcji": "Tytuł: PRZELEW NA TELEFON"})

    assert _parsed(row).transaction.description == "PRZELEW NA TELEFON"


def test_a_spelling_with_lost_letters_maps_to_the_same_type() -> None:
    row = _row({"Typ transakcji": "Płatnoć kartš"})

    result = _parsed(row)

    assert result.transaction.transaction_type == "card_payment"
    assert result.unknown_type is None


def test_an_unknown_type_is_kept_as_written_and_reported() -> None:
    row = _row({"Typ transakcji": "Nowy typ operacji"})

    result = _parsed(row)

    assert result.transaction.transaction_type == "Nowy typ operacji"
    assert result.unknown_type == "Nowy typ operacji"


def test_an_amount_with_spaces_and_a_decimal_comma_is_read() -> None:
    row = _row({"Kwota": "-1 234,50", "Saldo po transakcji": "+2 000,00"})

    transaction = _parsed(row).transaction

    assert transaction.amount == Decimal("-1234.50")
    assert transaction.balance_after == Decimal("2000.00")


def test_a_missing_value_date_is_none() -> None:
    assert _parsed(_row({"Data waluty": ""})).transaction.value_date is None


def test_rows_that_cannot_be_read_say_why() -> None:
    cases = {
        "operation date": {"Data operacji": "15.01.2026"},
        "amount": {"Kwota": "-12.345"},
        "not a number": {"Kwota": "abc"},
        "balance": {"Saldo po transakcji": "W rozliczeniu"},
        "currency": {"Waluta": ""},
    }

    for overrides in cases.values():
        result = adapt_row(_row(overrides, line_no=9), ACCOUNT, BATCH)

        assert isinstance(result, Invalid)
        assert result.line_no == 9
        assert result.reason


def test_the_same_row_gives_the_same_id_and_another_account_another_id() -> None:
    first = _parsed(_row()).transaction.transaction_id
    again = _parsed(_row()).transaction.transaction_id
    other_account = adapt_row(_row(), ACCOUNT + 1, BATCH)

    assert first == again
    assert isinstance(other_account, Parsed)
    assert other_account.transaction.transaction_id != first


def test_a_whole_statement_is_summed_up_for_the_audit() -> None:
    batch = parse_raw(CSV_TEXT)

    adapted = adapt_rows(batch.rows, ACCOUNT, BATCH)

    assert len(adapted.transactions) == 2
    assert adapted.holds == 1
    assert adapted.invalid == ()
    assert adapted.unknown_types == {}


def test_unknown_types_and_invalid_rows_are_counted_not_raised() -> None:
    rows = [
        _row({"Typ transakcji": "Nowy typ"}, line_no=2),
        _row({"Typ transakcji": "Nowy typ", "Kwota": "-1.00", "Saldo po transakcji": "+9.00"}, 3),
        _row({"Kwota": "abc"}, line_no=4),
    ]

    adapted = adapt_rows(rows, ACCOUNT, BATCH)

    assert len(adapted.transactions) == 2
    assert adapted.unknown_types == {"Nowy typ": 2}
    assert [item.line_no for item in adapted.invalid] == [4]

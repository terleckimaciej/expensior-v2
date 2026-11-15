"""Raw rows are the file's text, keyed by its header, with no interpretation."""

from pko_samples import CSV_TEXT, HEADER

from expensior.domain.statements.raw import RawBatch, header_keys, parse_raw


def test_the_header_and_the_rows_are_split() -> None:
    batch = parse_raw(CSV_TEXT)

    assert len(batch.header) == 13
    assert batch.header[:3] == ("Data operacji", "Data waluty", "Typ transakcji")
    assert len(batch.rows) == 3


def test_unnamed_columns_get_distinct_keys_by_position() -> None:
    batch = parse_raw(CSV_TEXT)

    assert len(set(batch.keys)) == 13
    assert batch.keys[6] == "Opis transakcji"
    assert batch.keys[7:] == tuple(f"column_{position}" for position in range(8, 14))
    assert all(len(row.cells) == 13 for row in batch.rows)


def test_rows_are_numbered_by_the_line_they_start_on() -> None:
    batch = parse_raw(CSV_TEXT)

    assert [row.line_no for row in batch.rows] == [2, 3, 4]


def test_values_are_kept_exactly_as_they_came() -> None:
    first = parse_raw(CSV_TEXT).rows[0]

    assert first.cells["Kwota"] == "-12.34"
    assert first.cells["Opis transakcji"] == "Tytuł: 000000000000000000000001  "


def test_blank_lines_are_skipped_but_still_counted() -> None:
    batch = parse_raw(f'{HEADER}\n\n"a","b"\n')

    assert [row.line_no for row in batch.rows] == [3]


def test_a_quoted_field_over_two_lines_moves_the_next_line_number() -> None:
    batch = parse_raw('Kwota,Opis\n"-1.00","first\nsecond"\n"-2.00","third"\n')

    assert [row.line_no for row in batch.rows] == [2, 4]
    assert batch.rows[0].cells["Opis"] == "first\nsecond"


def test_a_semicolon_separated_file_is_split_on_semicolons() -> None:
    batch = parse_raw("Kwota;Opis\n-1.00;shop\n")

    assert batch.header == ("Kwota", "Opis")
    assert batch.rows[0].cells == {"Kwota": "-1.00", "Opis": "shop"}


def test_an_empty_text_gives_an_empty_batch() -> None:
    assert parse_raw("") == RawBatch(header=(), keys=(), rows=())


def test_repeated_header_names_are_told_apart_by_position() -> None:
    assert header_keys(["Kwota", "Opis", "Opis", ""]) == ("Kwota", "Opis", "Opis_3", "column_4")


def test_a_short_row_is_not_padded_and_a_long_row_gets_extra_keys() -> None:
    batch = parse_raw("a,b\n1\n1,2,3\n")

    assert batch.rows[0].cells == {"a": "1"}
    assert batch.rows[1].cells == {"a": "1", "b": "2", "column_3": "3"}

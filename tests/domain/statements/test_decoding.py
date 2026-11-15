"""Decoding reads cp1250 and UTF-8, keeps the Polish letters, and refuses anything else."""

import pytest
from pko_samples import CSV_CP1250, CSV_TEXT

from expensior.domain.statements.decoding import DecodingError, decode


def test_cp1250_bytes_decode_with_the_polish_letters_intact() -> None:
    decoded = decode(CSV_CP1250)

    assert decoded.encoding == "cp1250"
    assert decoded.text == CSV_TEXT
    assert "Płatność kartą" in decoded.text


def test_utf_8_is_read_as_utf_8() -> None:
    decoded = decode(CSV_TEXT.encode("utf-8"))

    assert decoded.encoding == "utf-8"
    assert decoded.text == CSV_TEXT


def test_a_utf_8_byte_order_mark_is_dropped() -> None:
    decoded = decode(b"\xef\xbb\xbfKwota")

    assert decoded.text == "Kwota"


def test_plain_ascii_is_read_as_utf_8() -> None:
    assert decode(b"Kwota,Waluta").encoding == "utf-8"


def test_bytes_that_are_neither_utf_8_nor_cp1250_are_refused() -> None:
    # 0x81 is not valid UTF-8 on its own and is undefined in cp1250.
    with pytest.raises(DecodingError):
        decode(b"\x81\x8d\x8f")

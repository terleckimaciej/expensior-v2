"""The registry finds the source that recognises the bytes; a new source is one more entry."""

from collections.abc import Iterable

from pko_samples import CSV_CP1250

from expensior.domain.statements.adapted import AdaptedStatement
from expensior.domain.statements.formats import Unrecognised
from expensior.domain.statements.raw import RawBatch, RawRow
from expensior.domain.statements.registry import SOURCES, Identified, identify
from expensior.domain.statements.source import Source


def _fake_read(data: bytes) -> RawBatch | Unrecognised:
    if data.startswith(b"FAKE"):
        return RawBatch(header=("fake",), keys=("fake",), rows=())
    return Unrecognised(header=("seen by the fake",))


def _fake_adapt(rows: Iterable[RawRow], account_id: int, batch_id: int) -> AdaptedStatement:
    return AdaptedStatement(transactions=(), holds=0, invalid=(), unknown_types={})


FAKE = Source(source="fake", version="fake_v1", read=_fake_read, adapt=_fake_adapt)


def test_pko_bytes_are_recognised_and_read() -> None:
    result = identify(CSV_CP1250)

    assert isinstance(result, Identified)
    assert result.source.version == "pko_bp_v1"
    assert len(result.batch.rows) == 3


def test_the_recognised_source_adapts_the_rows_it_read() -> None:
    result = identify(CSV_CP1250)

    assert isinstance(result, Identified)
    adapted = result.source.adapt(result.batch.rows, 1, 1)
    assert len(adapted.transactions) == 2
    assert adapted.holds == 1


def test_an_unknown_header_is_unrecognised_and_keeps_the_header() -> None:
    result = identify(b"Date,Amount\n2026-01-01,1.00\n")

    assert result == Unrecognised(header=("Date", "Amount"))


def test_bytes_that_cannot_be_decoded_are_unrecognised_not_an_error() -> None:
    assert identify(b"\x81\x8d\x8f") == Unrecognised(header=())


def test_a_source_added_to_the_registry_is_asked_too() -> None:
    result = identify(b"FAKE payload", (*SOURCES, FAKE))

    assert isinstance(result, Identified)
    assert result.source is FAKE


def test_the_first_source_that_recognises_the_bytes_wins() -> None:
    result = identify(CSV_CP1250, (FAKE, *SOURCES))

    assert isinstance(result, Identified)
    assert result.source.version == "pko_bp_v1"


def test_when_no_source_recognises_the_bytes_the_first_miss_is_reported() -> None:
    result = identify(b"nothing known", (FAKE, *SOURCES))

    assert result == Unrecognised(header=("seen by the fake",))

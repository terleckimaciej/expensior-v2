"""Undo removes what a batch brought and keeps its bytes; reprocess re-derives it from them.

The sources are fakes, so that a "fixed parser" can be tried: the same bytes, read and adapted
differently the second time.
"""

from collections.abc import Callable, Iterable
from datetime import date
from decimal import Decimal

import pytest

from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.identity import transaction_id_for
from expensior.domain.records import Transaction
from expensior.domain.statements.adapted import AdaptedStatement, Hold, Invalid, Parsed, collect
from expensior.domain.statements.formats import Unrecognised
from expensior.domain.statements.raw import RawBatch, RawRow
from expensior.domain.statements.source import Source
from expensior.domain.types import ClassificationMethod, ImportStatus, TransactionId
from expensior.services.accounts import add_account
from expensior.services.import_statement import import_statement
from expensior.services.reprocess_batch import (
    BatchNotReprocessableError,
    IdsChangedError,
    reprocess_batch,
)
from expensior.services.undo_batch import BatchNotFoundError, BatchNotUndoableError, undo_batch

pytestmark = pytest.mark.db

UowFactory = Callable[[], UnitOfWork]
DAY = date(2026, 3, 1)


def make_source(
    *,
    variant: str,
    adapt_lines: tuple[int, ...] = (1,),
    description: str,
    amount: str = "-1.00",
    overrides: dict[int, str] | None = None,
) -> Source:
    """A source that reads ``FAKE n`` as n raw rows and adapts the lines in ``adapt_lines``.

    ``overrides`` gives single lines a description of their own.
    """

    def read(data: bytes) -> RawBatch | Unrecognised:
        if not data.startswith(b"FAKE"):
            return Unrecognised(header=())
        count = int(data.split()[1])
        rows = tuple(
            RawRow(line_no=n, cells={"variant": variant, "line": str(n)})
            for n in range(1, count + 1)
        )
        return RawBatch(header=("variant", "line"), keys=("variant", "line"), rows=rows)

    def adapt(rows: Iterable[RawRow], account_id: int, batch_id: int) -> AdaptedStatement:
        results: list[Parsed | Hold | Invalid] = []
        for row in rows:
            if row.line_no not in adapt_lines:
                results.append(Hold(row.line_no))
                continue
            balance = Decimal(100 + row.line_no)
            money = Decimal(amount) - row.line_no
            results.append(
                Parsed(
                    Transaction(
                        transaction_id=transaction_id_for(account_id, DAY, money, balance),
                        account_id=account_id,
                        raw_batch_id=batch_id,
                        raw_line_no=row.line_no,
                        operation_date=DAY,
                        value_date=None,
                        transaction_type="card_payment",
                        amount=money,
                        balance_after=balance,
                        currency="PLN",
                        description=(overrides or {}).get(row.line_no, description),
                        country=None,
                        city=None,
                    ),
                    None,
                )
            )
        return collect(results)

    return Source(source="fake", version=f"fake_{variant}", read=read, adapt=adapt)


def _setup(uow_factory: UowFactory, source: Source, data: bytes = b"FAKE 2") -> int:
    add_account(uow_factory, "main")
    result = import_statement(uow_factory, data=data, account_name="main", sources=(source,))
    assert result.status is ImportStatus.IMPORTED and result.batch_id is not None
    return result.batch_id


def _classify(uow_factory: UowFactory, batch_id: int) -> TransactionId:
    with uow_factory() as uow:
        transaction = uow.transactions.for_batch(batch_id)[0]
        food = uow.categories.add("Food")
        uow.classifications.add(transaction.transaction_id, food.id, ClassificationMethod.MANUAL)
        uow.commit()
        return transaction.transaction_id


def _state(uow_factory: UowFactory, batch_id: int) -> tuple[list[tuple[int, str]], int]:
    """The batch's transactions as (line, description) and the number of its raw rows."""
    with uow_factory() as uow:
        rows = [(t.raw_line_no, t.description) for t in uow.transactions.for_batch(batch_id)]
        return rows, uow.raw_rows.count(batch_id)


# --- undo -------------------------------------------------------------------------------------


def test_undo_removes_transactions_rows_and_history_but_keeps_the_bytes(
    uow_factory: UowFactory,
) -> None:
    batch_id = _setup(uow_factory, make_source(variant="a", adapt_lines=(1, 2), description="X"))
    _classify(uow_factory, batch_id)

    result = undo_batch(uow_factory, batch_id)

    assert (result.transactions, result.raw_rows, result.classifications) == (2, 2, 1)
    assert _state(uow_factory, batch_id) == ([], 0)
    with uow_factory() as uow:
        batch = uow.batches.get(batch_id)
        assert batch is not None and batch.status is ImportStatus.UNDONE
        assert uow.batches.source_bytes(batch_id) == b"FAKE 2"


def test_an_undo_dry_run_counts_and_changes_nothing(uow_factory: UowFactory) -> None:
    batch_id = _setup(uow_factory, make_source(variant="a", adapt_lines=(1, 2), description="X"))

    result = undo_batch(uow_factory, batch_id, dry_run=True)

    assert result.dry_run and result.transactions == 2
    assert _state(uow_factory, batch_id) == ([(1, "X"), (2, "X")], 2)


def test_only_an_imported_batch_can_be_undone_and_only_once(uow_factory: UowFactory) -> None:
    source = make_source(variant="a", description="X")
    batch_id = _setup(uow_factory, source)
    undo_batch(uow_factory, batch_id)
    unrecognised = import_statement(
        uow_factory, data=b"junk", account_name="main", sources=(source,)
    )

    with pytest.raises(BatchNotUndoableError):
        undo_batch(uow_factory, batch_id)
    assert unrecognised.batch_id is not None
    with pytest.raises(BatchNotUndoableError):
        undo_batch(uow_factory, unrecognised.batch_id)
    with pytest.raises(BatchNotFoundError):
        undo_batch(uow_factory, 999_999)


def test_after_an_undo_the_same_file_imports_again_and_is_not_called_a_repeat(
    uow_factory: UowFactory,
) -> None:
    source = make_source(variant="a", description="X")
    batch_id = _setup(uow_factory, source)
    undo_batch(uow_factory, batch_id)

    again = import_statement(uow_factory, data=b"FAKE 2", account_name="main", sources=(source,))

    assert again.inserted == 1 and again.already_imported_batch_ids == ()


def test_undoing_one_batch_leaves_the_transactions_of_another(uow_factory: UowFactory) -> None:
    source = make_source(variant="a", description="X")
    first = _setup(uow_factory, source)
    second = import_statement(
        uow_factory, data=b"FAKE 2 again", account_name="main", sources=(source,)
    )
    assert second.batch_id is not None and second.skipped_existing == 1

    undo_batch(uow_factory, second.batch_id)

    assert _state(uow_factory, first) == ([(1, "X")], 2)


# --- reprocess --------------------------------------------------------------------------------


def test_reprocessing_an_unchanged_batch_changes_nothing_and_keeps_the_classification(
    uow_factory: UowFactory,
) -> None:
    source = make_source(variant="a", description="X")
    batch_id = _setup(uow_factory, source)
    transaction_id = _classify(uow_factory, batch_id)

    result = reprocess_batch(uow_factory, batch_id, sources=(source,))

    assert (result.replaced, result.unchanged, result.inserted) == (0, 1, 0)
    assert _state(uow_factory, batch_id) == ([(1, "X")], 2)
    with uow_factory() as uow:
        assert uow.classifications.current(transaction_id) is not None


def test_a_fixed_parser_updates_the_transactions_and_keeps_the_classification(
    uow_factory: UowFactory,
) -> None:
    batch_id = _setup(uow_factory, make_source(variant="a", description="OLD"))
    transaction_id = _classify(uow_factory, batch_id)
    fixed = make_source(variant="a", description="NEW")

    result = reprocess_batch(uow_factory, batch_id, sources=(fixed,))

    assert (result.replaced, result.unchanged, result.inserted) == (1, 0, 0)
    assert _state(uow_factory, batch_id)[0] == [(1, "NEW")]
    with uow_factory() as uow:
        assert uow.classifications.current(transaction_id) is not None


def test_only_the_transactions_that_differ_are_counted_as_changed(uow_factory: UowFactory) -> None:
    batch_id = _setup(uow_factory, make_source(variant="a", adapt_lines=(1, 2), description="X"))
    fixed = make_source(variant="a", adapt_lines=(1, 2), description="X", overrides={2: "Y"})

    result = reprocess_batch(uow_factory, batch_id, sources=(fixed,))

    assert (result.replaced, result.unchanged, result.inserted) == (1, 1, 0)
    assert _state(uow_factory, batch_id)[0] == [(1, "X"), (2, "Y")]


def test_a_fix_that_would_change_an_id_is_refused_and_writes_nothing(
    uow_factory: UowFactory,
) -> None:
    batch_id = _setup(uow_factory, make_source(variant="a", description="OLD"))
    changes_the_id = make_source(variant="b", description="NEW", amount="-9.00")

    with pytest.raises(IdsChangedError) as error:
        reprocess_batch(uow_factory, batch_id, sources=(changes_the_id,))

    assert (error.value.changed, error.value.vanished) == (1, 0)
    assert _state(uow_factory, batch_id) == ([(1, "OLD")], 2)


def test_a_fix_that_would_make_a_transaction_vanish_is_refused(uow_factory: UowFactory) -> None:
    batch_id = _setup(uow_factory, make_source(variant="a", description="OLD"))
    drops_it = make_source(variant="b", adapt_lines=(), description="NEW")

    with pytest.raises(IdsChangedError) as error:
        reprocess_batch(uow_factory, batch_id, sources=(drops_it,))

    assert (error.value.changed, error.value.vanished) == (0, 1)
    assert _state(uow_factory, batch_id) == ([(1, "OLD")], 2)


def test_a_row_that_now_yields_a_transaction_gets_one(uow_factory: UowFactory) -> None:
    batch_id = _setup(uow_factory, make_source(variant="a", adapt_lines=(1,), description="X"))
    reads_more = make_source(variant="a", adapt_lines=(1, 2), description="X")

    result = reprocess_batch(uow_factory, batch_id, sources=(reads_more,))

    assert (result.replaced, result.unchanged, result.inserted) == (0, 1, 1)
    assert _state(uow_factory, batch_id)[0] == [(1, "X"), (2, "X")]


def test_the_raw_rows_are_read_again_from_the_bytes(uow_factory: UowFactory) -> None:
    batch_id = _setup(uow_factory, make_source(variant="a", description="X"), b"FAKE 3")
    reads_less = make_source(variant="b", description="X")

    reprocess_batch(uow_factory, batch_id, sources=(reads_less,))

    with uow_factory() as uow:
        rows = uow.raw_rows.for_batch(batch_id)
    assert rows == [
        (1, {"variant": "b", "line": "1"}),
        (2, {"variant": "b", "line": "2"}),
        (3, {"variant": "b", "line": "3"}),
    ]


def test_a_reprocess_dry_run_changes_nothing(uow_factory: UowFactory) -> None:
    batch_id = _setup(uow_factory, make_source(variant="a", description="OLD"))
    fixed = make_source(variant="a", description="NEW")

    result = reprocess_batch(uow_factory, batch_id, dry_run=True, sources=(fixed,))

    assert result.dry_run and result.replaced == 1
    assert _state(uow_factory, batch_id)[0] == [(1, "OLD")]


def test_a_batch_that_cannot_be_reprocessed_says_why(uow_factory: UowFactory) -> None:
    source = make_source(variant="a", description="X")
    batch_id = _setup(uow_factory, source)

    with pytest.raises(BatchNotFoundError):
        reprocess_batch(uow_factory, 999_999, sources=(source,))
    with pytest.raises(BatchNotReprocessableError, match="not recognised"):
        reprocess_batch(uow_factory, batch_id, sources=())
    undo_batch(uow_factory, batch_id)
    with pytest.raises(BatchNotReprocessableError, match="undone"):
        reprocess_batch(uow_factory, batch_id, sources=(source,))

"""The import service keeps the bytes first, is idempotent, and a dry run writes nothing."""

from collections.abc import Callable, Iterable
from datetime import date
from decimal import Decimal

import pytest
from pko_samples import CSV_CP1250
from sqlalchemy import func, select

from expensior.db import models
from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.identity import transaction_id_for
from expensior.domain.records import Transaction
from expensior.domain.statements.adapted import AdaptedStatement
from expensior.domain.statements.formats import Unrecognised
from expensior.domain.statements.pko_csv import PKO_BP_V1_SOURCE
from expensior.domain.statements.raw import RawBatch, RawRow
from expensior.domain.statements.source import Source
from expensior.domain.types import (
    ClassificationMethod,
    ConflictPolicy,
    ImportStatus,
    TransactionId,
)
from expensior.services.import_statement import AccountNotFoundError, import_statement

pytestmark = pytest.mark.db

UowFactory = Callable[[], UnitOfWork]


def _add_account(uow_factory: UowFactory, name: str = "main") -> None:
    with uow_factory() as uow:
        uow.accounts.add(name, "pko_bp")
        uow.commit()


def _count(uow_factory: UowFactory, model: type[models.Base]) -> int:
    with uow_factory() as uow:
        return uow.session.scalar(select(func.count()).select_from(model)) or 0


def test_an_import_stores_the_bytes_the_raw_rows_and_the_transactions(
    uow_factory: UowFactory,
) -> None:
    _add_account(uow_factory)

    result = import_statement(uow_factory, data=CSV_CP1250, account_name="main")

    assert result.status is ImportStatus.IMPORTED
    assert result.format_version == "pko_bp_v1"
    assert (result.row_count, result.inserted, result.holds) == (3, 2, 1)
    assert result.batch_id is not None
    with uow_factory() as uow:
        assert uow.batches.source_bytes(result.batch_id) == CSV_CP1250
        assert uow.raw_rows.count(result.batch_id) == 3
        batch = uow.batches.get(result.batch_id)
        assert batch is not None and batch.status is ImportStatus.IMPORTED
    assert _count(uow_factory, models.Transaction) == 2


def test_importing_the_same_file_twice_does_not_duplicate_transactions(
    uow_factory: UowFactory,
) -> None:
    _add_account(uow_factory)
    first = import_statement(uow_factory, data=CSV_CP1250, account_name="main")

    second = import_statement(uow_factory, data=CSV_CP1250, account_name="main")

    assert (second.inserted, second.skipped_existing) == (0, 2)
    assert second.already_imported_batch_ids == (first.batch_id,)
    assert _count(uow_factory, models.Transaction) == 2


def test_a_dry_run_writes_nothing(uow_factory: UowFactory) -> None:
    _add_account(uow_factory)

    result = import_statement(uow_factory, data=CSV_CP1250, account_name="main", dry_run=True)

    assert result.dry_run and result.batch_id is None and result.status is None
    assert (result.inserted, result.holds) == (2, 1)
    assert _count(uow_factory, models.ImportBatch) == 0
    assert _count(uow_factory, models.RawRow) == 0
    assert _count(uow_factory, models.Transaction) == 0


def test_a_dry_run_after_an_import_reports_what_would_be_skipped(
    uow_factory: UowFactory,
) -> None:
    _add_account(uow_factory)
    import_statement(uow_factory, data=CSV_CP1250, account_name="main")

    result = import_statement(uow_factory, data=CSV_CP1250, account_name="main", dry_run=True)

    assert (result.inserted, result.skipped_existing) == (0, 2)
    assert _count(uow_factory, models.ImportBatch) == 1


def test_an_unrecognised_file_keeps_its_bytes_and_reports_the_header(
    uow_factory: UowFactory,
) -> None:
    _add_account(uow_factory)
    data = b"Date,Amount\n2026-01-01,1.00\n"

    result = import_statement(uow_factory, data=data, account_name="main")

    assert result.status is ImportStatus.UNRECOGNISED
    assert result.error is not None and "Date, Amount" in result.error
    assert result.batch_id is not None
    with uow_factory() as uow:
        assert uow.batches.source_bytes(result.batch_id) == data
    assert _count(uow_factory, models.Transaction) == 0


def test_an_unknown_account_stops_before_anything_is_written(uow_factory: UowFactory) -> None:
    with pytest.raises(AccountNotFoundError):
        import_statement(uow_factory, data=CSV_CP1250, account_name="nobody")

    assert _count(uow_factory, models.ImportBatch) == 0


def test_abort_on_a_stored_transaction_fails_the_batch_and_writes_nothing_more(
    uow_factory: UowFactory,
) -> None:
    _add_account(uow_factory)
    import_statement(uow_factory, data=CSV_CP1250, account_name="main")

    result = import_statement(
        uow_factory, data=CSV_CP1250, account_name="main", policy=ConflictPolicy.ABORT
    )

    assert result.status is ImportStatus.FAILED
    assert result.error is not None and "already stored" in result.error
    assert _count(uow_factory, models.Transaction) == 2
    assert _count(uow_factory, models.ImportBatch) == 2
    assert _count(uow_factory, models.RawRow) == 3


def test_replace_overwrites_transactions_but_keeps_their_classification(
    uow_factory: UowFactory,
) -> None:
    _add_account(uow_factory)
    import_statement(uow_factory, data=CSV_CP1250, account_name="main")
    with uow_factory() as uow:
        first_id = uow.session.scalars(select(models.Transaction.transaction_id)).first()
        assert first_id is not None
        stored = TransactionId(first_id)
        food = uow.categories.add("Food")
        uow.classifications.add(stored, food.id, ClassificationMethod.MANUAL)
        uow.commit()

    result = import_statement(
        uow_factory, data=CSV_CP1250, account_name="main", policy=ConflictPolicy.REPLACE
    )

    assert (result.inserted, result.replaced) == (0, 2)
    with uow_factory() as uow:
        current = uow.classifications.current(stored)
        assert current is not None and current.category_id == food.id


def _boom(rows: Iterable[RawRow], account_id: int, batch_id: int) -> AdaptedStatement:
    raise RuntimeError("the adapter broke")


def _fake_read(data: bytes) -> RawBatch | Unrecognised:
    if not data.startswith(b"FAKE"):
        return Unrecognised(header=())
    return RawBatch(
        header=("fake",), keys=("fake",), rows=(RawRow(line_no=2, cells={"fake": "row"}),)
    )


def test_a_failure_after_the_bytes_are_stored_leaves_a_failed_batch_and_raises(
    uow_factory: UowFactory,
) -> None:
    _add_account(uow_factory)
    broken = Source(source="fake", version="fake_v1", read=_fake_read, adapt=_boom)

    with pytest.raises(RuntimeError):
        import_statement(uow_factory, data=b"FAKE data", account_name="main", sources=(broken,))

    with uow_factory() as uow:
        (batch,) = uow.session.scalars(select(models.ImportBatch)).all()
        assert batch.status == ImportStatus.FAILED.value
        assert batch.error == "the adapter broke"
        assert uow.batches.source_bytes(batch.id) == b"FAKE data"
    assert _count(uow_factory, models.Transaction) == 0


def test_the_service_does_not_know_the_format(uow_factory: UowFactory) -> None:
    _add_account(uow_factory)

    def adapt(rows: Iterable[RawRow], account_id: int, batch_id: int) -> AdaptedStatement:
        day, amount, balance = date(2026, 3, 1), Decimal("-1.00"), Decimal("9.00")
        transaction = Transaction(
            transaction_id=transaction_id_for(account_id, day, amount, balance),
            account_id=account_id,
            raw_batch_id=batch_id,
            raw_line_no=2,
            operation_date=day,
            value_date=None,
            transaction_type="card_payment",
            amount=amount,
            balance_after=balance,
            currency="PLN",
            description="FROM ANOTHER SOURCE",
            country=None,
            city=None,
        )
        return AdaptedStatement((transaction,), 0, (), {})

    other = Source(source="fake", version="fake_v1", read=_fake_read, adapt=adapt)

    result = import_statement(
        uow_factory,
        data=b"FAKE data",
        account_name="main",
        sources=(PKO_BP_V1_SOURCE, other),
    )

    assert result.status is ImportStatus.IMPORTED
    assert result.format_version == "fake_v1"
    assert _count(uow_factory, models.Transaction) == 1

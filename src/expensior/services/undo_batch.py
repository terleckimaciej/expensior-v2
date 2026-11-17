"""Undo an import: remove what a batch brought, keep its original bytes.

Legacy needed a rollback of the last import, so undo is built in from the start (ADR 0007). The
bytes stay, so the batch can be looked at, reprocessed, or imported again.
"""

from collections.abc import Callable
from dataclasses import dataclass

from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.records import ImportBatch
from expensior.domain.types import ImportStatus

UnitOfWorkFactory = Callable[[], UnitOfWork]


class BatchNotFoundError(LookupError):
    """There is no import batch with that id."""


class BatchNotUndoableError(ValueError):
    """Only an imported batch brought anything that could be undone."""


@dataclass(frozen=True)
class UndoResult:
    """What an undo removes (``dry_run``) or removed."""

    batch: ImportBatch
    transactions: int
    raw_rows: int
    classifications: int
    dry_run: bool


def undo_batch(
    uow_factory: UnitOfWorkFactory, batch_id: int, *, dry_run: bool = False
) -> UndoResult:
    """Delete the transactions and raw rows of an imported batch and mark it ``undone``.

    Deleting a transaction deletes its classification history too, so the counts are what the
    caller should show before it asks. A transaction that a later import with the replace policy
    took over from another batch points at this batch now and goes with it; reprocessing the
    earlier batch brings it back.
    """
    with uow_factory() as uow:
        batch = uow.batches.get(batch_id)
        if batch is None:
            raise BatchNotFoundError(f"there is no import batch {batch_id}")
        if batch.status is not ImportStatus.IMPORTED:
            raise BatchNotUndoableError(
                f"batch {batch_id} is {batch.status.value}: only an imported batch can be undone"
            )
        result = UndoResult(
            batch=batch,
            transactions=uow.transactions.count_for_batch(batch_id),
            raw_rows=uow.raw_rows.count(batch_id),
            classifications=uow.classifications.count_for_batch(batch_id),
            dry_run=dry_run,
        )
        if dry_run:
            return result
        uow.transactions.delete_for_batch(batch_id)
        uow.raw_rows.delete_for_batch(batch_id)
        uow.batches.update_status(batch_id, ImportStatus.UNDONE)
        uow.commit()
        return result

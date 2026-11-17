"""Reprocess an import: derive its transactions again from the bytes that were stored (ADR 0007).

This is why the original bytes are kept: after a parser, a decoder or a type mapping is fixed, the
batch is read again instead of fetched again. Raw rows and transactions are rebuilt from the bytes;
the classification history of a transaction is never touched.

What if a fix changes a transaction's id (the id is made of the date, the amount and the balance)?
Transactions are matched to rows by the raw row they point at. When an id would change, or a
transaction would vanish, nothing is written: moving a classification history to a new id by itself
is too risky for a case this rare. The caller undoes the batch and imports it again, knowing that
the history of those transactions goes with it.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.records import ImportBatch, Transaction
from expensior.domain.statements.adapted import Invalid
from expensior.domain.statements.formats import Unrecognised
from expensior.domain.statements.registry import SOURCES, identify
from expensior.domain.statements.source import Source
from expensior.domain.types import ImportStatus, TransactionId
from expensior.services.undo_batch import BatchNotFoundError

UnitOfWorkFactory = Callable[[], UnitOfWork]


class BatchNotReprocessableError(ValueError):
    """Only an imported batch whose bytes are still recognised can be reprocessed."""


class IdsChangedError(ValueError):
    """The fix would change the id of some transactions, or make some of them vanish."""

    def __init__(self, changed: int, vanished: int) -> None:
        super().__init__(
            f"{changed} transactions would get a new id and {vanished} would disappear; nothing "
            "was written. Undo the batch and import it again if that is what you want: the "
            "classification history of those transactions goes with it"
        )
        self.changed = changed
        self.vanished = vanished


@dataclass(frozen=True)
class ReprocessResult:
    """What reprocessing does (``dry_run``) or did."""

    batch: ImportBatch
    format_version: str
    row_count: int
    replaced: int
    inserted: int
    skipped_elsewhere: int
    holds: int
    invalid: tuple[Invalid, ...]
    unknown_types: dict[str, int]
    dry_run: bool


def reprocess_batch(
    uow_factory: UnitOfWorkFactory,
    batch_id: int,
    *,
    dry_run: bool = False,
    sources: Sequence[Source] = SOURCES,
) -> ReprocessResult:
    """Read the stored bytes of an imported batch again and bring its transactions up to date."""
    with uow_factory() as uow:
        batch = uow.batches.get(batch_id)
        if batch is None:
            raise BatchNotFoundError(f"there is no import batch {batch_id}")
        if batch.status is not ImportStatus.IMPORTED:
            raise BatchNotReprocessableError(
                f"batch {batch_id} is {batch.status.value}: "
                "only an imported batch can be reprocessed"
            )
        identified = identify(uow.batches.source_bytes(batch_id) or b"", sources)
        if isinstance(identified, Unrecognised):
            raise BatchNotReprocessableError(
                f"the stored bytes of batch {batch_id} are not recognised by any known format"
            )
        adapted = identified.source.adapt(identified.batch.rows, batch.account_id, batch_id)

        unique: dict[TransactionId, Transaction] = {}
        for transaction in adapted.transactions:  # the first of a repeated id counts, as on import
            unique.setdefault(transaction.transaction_id, transaction)
        incoming = list(unique.values())

        stored = {t.raw_line_no: t for t in uow.transactions.for_batch(batch_id)}
        by_line = {t.raw_line_no: t for t in incoming}
        changed = sum(
            1
            for line, t in by_line.items()
            if line in stored and stored[line].transaction_id != t.transaction_id
        )
        vanished = sum(1 for line in stored if line not in by_line)
        if changed or vanished:
            raise IdsChangedError(changed, vanished)

        in_batch = {t.transaction_id for t in stored.values()}
        fresh = [t for t in incoming if t.transaction_id not in in_batch]
        elsewhere = uow.transactions.existing_ids([t.transaction_id for t in fresh])
        to_insert = [t for t in fresh if t.transaction_id not in elsewhere]
        to_replace = [t for t in incoming if t.transaction_id in in_batch]
        result = ReprocessResult(
            batch=batch,
            format_version=identified.source.version,
            row_count=len(identified.batch.rows),
            replaced=len(to_replace),
            inserted=len(to_insert),
            skipped_elsewhere=len(fresh) - len(to_insert),
            holds=adapted.holds,
            invalid=adapted.invalid,
            unknown_types=adapted.unknown_types,
            dry_run=dry_run,
        )
        if dry_run:
            return result
        uow.raw_rows.sync_batch(batch_id, [(r.line_no, r.cells) for r in identified.batch.rows])
        uow.transactions.replace_many(to_replace)
        uow.transactions.add_many(to_insert)
        uow.batches.update_status(
            batch_id,
            ImportStatus.IMPORTED,
            format_version=identified.source.version,
            header=list(identified.batch.header),
            row_count=len(identified.batch.rows),
        )
        uow.commit()
        return result

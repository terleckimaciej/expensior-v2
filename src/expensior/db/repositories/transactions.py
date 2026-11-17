"""Reading and writing transactions. Takes and returns domain records, never ORM objects."""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import asdict
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from expensior.db import models
from expensior.domain.records import Transaction
from expensior.domain.types import TransactionId

# Postgres accepts up to 65535 bind parameters in one statement; stay well below it.
_ID_CHUNK = 5000


def _record(row: models.Transaction) -> Transaction:
    return Transaction(
        transaction_id=TransactionId(row.transaction_id),
        account_id=row.account_id,
        raw_batch_id=row.raw_batch_id,
        raw_line_no=row.raw_line_no,
        operation_date=row.operation_date,
        value_date=row.value_date,
        transaction_type=row.transaction_type,
        amount=row.amount,
        balance_after=row.balance_after,
        currency=row.currency,
        description=row.description,
        country=row.country,
        city=row.city,
    )


def _chunks(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class TransactionRepository:
    """Transactions of one session; the caller owns the transaction and the commit."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_many(self, transactions: Sequence[Transaction]) -> None:
        """Insert transactions in one statement. Does not commit."""
        if not transactions:
            return
        rows: list[dict[str, Any]] = [asdict(transaction) for transaction in transactions]
        self._session.execute(insert(models.Transaction), rows)

    def replace_many(self, transactions: Sequence[Transaction]) -> None:
        """Overwrite the stored fields of existing transactions, matched by id. Does not commit.

        Only the ``transactions`` table is touched: the classification history stays as it is.
        """
        if not transactions:
            return
        rows: list[dict[str, Any]] = [asdict(transaction) for transaction in transactions]
        self._session.execute(update(models.Transaction), rows)

    def existing_ids(self, ids: Collection[TransactionId]) -> set[TransactionId]:
        """Which of the given ids are already stored: what an idempotent import needs to know."""
        found: set[TransactionId] = set()
        for chunk in _chunks(sorted(ids), _ID_CHUNK):
            stored = self._session.scalars(
                select(models.Transaction.transaction_id).where(
                    models.Transaction.transaction_id.in_(chunk)
                )
            )
            found.update(TransactionId(value) for value in stored)
        return found

    def get(self, transaction_id: TransactionId) -> Transaction | None:
        row = self._session.get(models.Transaction, transaction_id)
        return _record(row) if row else None

    def for_batch(self, batch_id: int) -> list[Transaction]:
        """The transactions that point at a raw row of the batch, by line."""
        rows = self._session.scalars(
            select(models.Transaction)
            .where(models.Transaction.raw_batch_id == batch_id)
            .order_by(models.Transaction.raw_line_no)
        )
        return [_record(row) for row in rows]

    def count_for_batch(self, batch_id: int) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(models.Transaction)
                .where(models.Transaction.raw_batch_id == batch_id)
            )
            or 0
        )

    def delete_for_batch(self, batch_id: int) -> int:
        """Delete the batch's transactions (and, by cascade, their classification history)."""
        result = self._session.execute(
            delete(models.Transaction).where(models.Transaction.raw_batch_id == batch_id)
        )
        return int(getattr(result, "rowcount", 0) or 0)

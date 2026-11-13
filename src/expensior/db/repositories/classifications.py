"""The classification history of transactions: append-only, one entry current. Never commits."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from expensior.db import models
from expensior.domain.records import Classification
from expensior.domain.types import ClassificationMethod, TransactionId


def _record(row: models.Classification) -> Classification:
    return Classification(
        id=row.id,
        transaction_id=TransactionId(row.transaction_id),
        category_id=row.category_id,
        merchant=row.merchant,
        method=ClassificationMethod(row.method),
        rule_id=row.rule_id,
        is_current=row.is_current,
        created_at=row.created_at,
    )


class ClassificationRepository:
    """Classifications of one session; the caller owns the transaction and the commit."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        transaction_id: TransactionId,
        category_id: int,
        method: ClassificationMethod,
        *,
        merchant: str | None = None,
        rule_id: int | None = None,
    ) -> Classification:
        """Classify a transaction: the new entry supersedes the current one, which is kept.

        The previous current entry is marked not current first, then the new one is inserted, in
        the transaction of the caller. The order matters: the database allows only one current
        entry per transaction. Marking the old entry is the only update that ever happens here.
        """
        self._session.execute(
            update(models.Classification)
            .where(
                models.Classification.transaction_id == transaction_id,
                models.Classification.is_current.is_(True),
            )
            .values(is_current=False)
        )
        row = models.Classification(
            transaction_id=transaction_id,
            category_id=category_id,
            merchant=merchant,
            method=method.value,
            rule_id=rule_id,
            is_current=True,
        )
        self._session.add(row)
        self._session.flush()
        return _record(row)

    def current(self, transaction_id: TransactionId) -> Classification | None:
        row = self._session.scalar(
            select(models.Classification).where(
                models.Classification.transaction_id == transaction_id,
                models.Classification.is_current.is_(True),
            )
        )
        return _record(row) if row else None

    def history(self, transaction_id: TransactionId) -> list[Classification]:
        """Every classification of the transaction, oldest first, the current one last."""
        rows = self._session.scalars(
            select(models.Classification)
            .where(models.Classification.transaction_id == transaction_id)
            .order_by(models.Classification.id)
        )
        return [_record(row) for row in rows]

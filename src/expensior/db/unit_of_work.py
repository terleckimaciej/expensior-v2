"""The unit of work: one database transaction, with the repositories that work inside it.

Used as a context manager with an explicit commit::

    with UnitOfWork(session_factory) as uow:
        uow.transactions.add_many(transactions)
        uow.commit()

Leaving the block without a commit, or with an exception, rolls everything back. Only ``services``
open a unit of work (ADR 0009, rule 3); repositories never commit.
"""

from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session

from expensior.db.repositories.batches import BatchRepository
from expensior.db.repositories.categories import CategoryRepository
from expensior.db.repositories.classifications import ClassificationRepository
from expensior.db.repositories.raw_rows import RawRowRepository
from expensior.db.repositories.rules import RuleRepository
from expensior.db.repositories.transactions import TransactionRepository


class UnitOfWork:
    """One session and its repositories; commit is explicit, anything else rolls back."""

    session: Session
    batches: BatchRepository
    raw_rows: RawRowRepository
    transactions: TransactionRepository
    categories: CategoryRepository
    rules: RuleRepository
    classifications: ClassificationRepository

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> Self:
        self.session = self._session_factory()
        self.batches = BatchRepository(self.session)
        self.raw_rows = RawRowRepository(self.session)
        self.transactions = TransactionRepository(self.session)
        self.categories = CategoryRepository(self.session)
        self.rules = RuleRepository(self.session)
        self.classifications = ClassificationRepository(self.session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Not committed, or failed: undo whatever is pending. After a commit this does nothing.
        try:
            self.session.rollback()
        finally:
            self.session.close()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

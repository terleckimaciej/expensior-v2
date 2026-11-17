"""The import batches, listed with the account each one belongs to."""

from collections.abc import Callable
from dataclasses import dataclass

from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.records import ImportBatch
from expensior.services.import_statement import AccountNotFoundError

UnitOfWorkFactory = Callable[[], UnitOfWork]


@dataclass(frozen=True)
class BatchSummary:
    """A batch and the name of its account."""

    batch: ImportBatch
    account_name: str


def list_batches(
    uow_factory: UnitOfWorkFactory, account_name: str | None = None
) -> list[BatchSummary]:
    """All batches, oldest first, or only those of one account."""
    with uow_factory() as uow:
        names = {account.id: account.name for account in uow.accounts.list_all()}
        account_id: int | None = None
        if account_name is not None:
            account = uow.accounts.get_by_name(account_name)
            if account is None:
                raise AccountNotFoundError(f"there is no account named {account_name!r}")
            account_id = account.id
        return [
            BatchSummary(batch, names[batch.account_id])
            for batch in uow.batches.list_all(account_id)
        ]

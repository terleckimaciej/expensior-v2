"""The accounts of the application: add one, list them."""

from collections.abc import Callable

from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.records import Account
from expensior.services.fetch_transactions import BANK_SOURCE

UnitOfWorkFactory = Callable[[], UnitOfWork]


class AccountExistsError(ValueError):
    """An account with that name exists already."""


def add_account(uow_factory: UnitOfWorkFactory, name: str, source: str = BANK_SOURCE) -> Account:
    """Add an account held at a bank (``source``), e.g. one a CSV will be imported into."""
    with uow_factory() as uow:
        if uow.accounts.get_by_name(name) is not None:
            raise AccountExistsError(f"there is an account named {name!r} already")
        account = uow.accounts.add(name, source)
        uow.commit()
        return account


def list_accounts(uow_factory: UnitOfWorkFactory) -> list[Account]:
    """All accounts by name, with the state of their bank consent."""
    with uow_factory() as uow:
        return uow.accounts.list_all()

"""The accounts of the application: add one, list them."""

from collections.abc import Callable
from dataclasses import dataclass

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


class AccountChoiceError(ValueError):
    """It is not clear which account a statement is for."""


@dataclass(frozen=True)
class AccountChoice:
    """The account a statement goes to: its name, and the account itself if it exists yet."""

    name: str
    account: Account | None


def choose_account(uow_factory: UnitOfWorkFactory, requested: str | None) -> AccountChoice:
    """The account for a statement: the one named, or the only account there is.

    A name that does not exist yet is allowed (the caller offers to create it); without a name the
    choice must be unambiguous, because a CSV does not say which account it belongs to.
    """
    accounts = list_accounts(uow_factory)
    if requested is not None:
        return AccountChoice(requested, next((a for a in accounts if a.name == requested), None))
    if len(accounts) == 1:
        return AccountChoice(accounts[0].name, accounts[0])
    if not accounts:
        raise AccountChoiceError("there are no accounts yet: name one with --account to create it")
    names = ", ".join(account.name for account in accounts)
    raise AccountChoiceError(f"there are several accounts ({names}): choose one with --account")

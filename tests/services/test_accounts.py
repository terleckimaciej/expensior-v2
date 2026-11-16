"""Adding and listing accounts."""

from collections.abc import Callable

import pytest

from expensior.db.unit_of_work import UnitOfWork
from expensior.services.accounts import AccountExistsError, add_account, list_accounts
from expensior.services.fetch_transactions import BANK_SOURCE

pytestmark = pytest.mark.db

UowFactory = Callable[[], UnitOfWork]


def test_an_added_account_is_held_at_the_bank_and_not_connected(uow_factory: UowFactory) -> None:
    account = add_account(uow_factory, "main")

    assert (account.source, account.external_ref, account.consent_valid_until) == (
        BANK_SOURCE,
        None,
        None,
    )


def test_a_name_that_is_taken_is_refused(uow_factory: UowFactory) -> None:
    add_account(uow_factory, "main")

    with pytest.raises(AccountExistsError):
        add_account(uow_factory, "main")

    assert len(list_accounts(uow_factory)) == 1


def test_accounts_are_listed_by_name(uow_factory: UowFactory) -> None:
    add_account(uow_factory, "savings")
    add_account(uow_factory, "main")

    assert [account.name for account in list_accounts(uow_factory)] == ["main", "savings"]

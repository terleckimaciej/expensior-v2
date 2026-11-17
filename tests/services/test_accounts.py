"""Adding and listing accounts."""

from collections.abc import Callable

import pytest

from expensior.db.unit_of_work import UnitOfWork
from expensior.services.accounts import (
    AccountChoiceError,
    AccountExistsError,
    add_account,
    choose_account,
    list_accounts,
)
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


def test_a_named_account_is_chosen_whether_or_not_it_exists(uow_factory: UowFactory) -> None:
    add_account(uow_factory, "main")

    existing = choose_account(uow_factory, "main")
    new = choose_account(uow_factory, "brand-new")

    assert existing.account is not None and existing.name == "main"
    assert new.account is None and new.name == "brand-new"


def test_without_a_name_the_only_account_is_chosen(uow_factory: UowFactory) -> None:
    add_account(uow_factory, "main")

    choice = choose_account(uow_factory, None)

    assert choice.name == "main" and choice.account is not None


def test_without_a_name_and_without_accounts_it_says_how_to_create_one(
    uow_factory: UowFactory,
) -> None:
    with pytest.raises(AccountChoiceError, match="--account"):
        choose_account(uow_factory, None)


def test_without_a_name_and_with_several_accounts_it_lists_them(uow_factory: UowFactory) -> None:
    add_account(uow_factory, "main")
    add_account(uow_factory, "savings")

    with pytest.raises(AccountChoiceError, match=r"main, savings"):
        choose_account(uow_factory, None)

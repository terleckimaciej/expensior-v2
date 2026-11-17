"""Fetch an account's transactions from the bank API and import them.

The fetch is a slow network call, so it runs outside any database transaction. Its result is packed
into the document of ``domain.statements.enable_banking`` and handed to ``import_statement``, which
gives the dry run, the conflict policy and the audit of every import (ADR 0007).
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any, Protocol

from expensior.bank.enable_banking import BankAccount
from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.records import Account
from expensior.domain.statements.enable_banking import make_document
from expensior.domain.types import ConflictPolicy
from expensior.services.import_statement import (
    AccountNotFoundError,
    ImportResult,
    import_statement,
)

# What ``accounts.source`` holds: the bank the account is at, not the channel its data comes by.
# One account therefore takes data from the CSV and from the API alike (ADR 0010, ADR 0011).
BANK_SOURCE = "pko_bp"

UnitOfWorkFactory = Callable[[], UnitOfWork]


class TransactionFetcher(Protocol):
    """The part of a bank client this service needs."""

    def fetch_transactions(
        self,
        account_uid: str,
        *,
        date_from: date | None = None,
        on_page: Callable[[int, int], None] | None = None,
    ) -> list[dict[str, Any]]: ...


class AccountMismatchError(ValueError):
    """The named account is already linked to a different bank account."""


def _find_account(uow: UnitOfWork, bank_account: BankAccount, account_name: str) -> Account | None:
    assert bank_account.identification_hash is not None
    linked = uow.accounts.get_by_external_ref(BANK_SOURCE, bank_account.identification_hash)
    return linked or uow.accounts.get_by_name(account_name)


def link_in(uow: UnitOfWork, bank_account: BankAccount, account_name: str) -> Account:
    """The application's account for a bank account, in the caller's transaction (no commit).

    Found by the bank's hash; else an account of that name that is not linked yet is linked to it
    (one made for a CSV, say); else a new account is made, in the bank account's currency.
    """
    assert bank_account.identification_hash is not None
    account = _find_account(uow, bank_account, account_name)
    if account is None:
        return uow.accounts.add(
            account_name,
            BANK_SOURCE,
            external_ref=bank_account.identification_hash,
            currency=bank_account.currency or "PLN",
        )
    if account.external_ref is None:
        return uow.accounts.set_external_ref(account.id, bank_account.identification_hash)
    if account.external_ref != bank_account.identification_hash:
        raise AccountMismatchError(
            f"the account {account.name!r} is linked to a different bank account"
        )
    return account


def _resolve_account(
    uow_factory: UnitOfWorkFactory, bank_account: BankAccount, account_name: str, *, dry_run: bool
) -> Account:
    """The account a fetch imports into. A dry run changes nothing: the account must exist."""
    assert bank_account.identification_hash is not None
    with uow_factory() as uow:
        if dry_run:
            account = _find_account(uow, bank_account, account_name)
            if account is None:
                raise AccountNotFoundError(f"there is no account named {account_name!r}")
            return account
        account = link_in(uow, bank_account, account_name)
        uow.commit()
        return account


def fetch_transactions(
    uow_factory: UnitOfWorkFactory,
    client: TransactionFetcher,
    *,
    bank_account: BankAccount,
    account_name: str,
    date_from: date | None = None,
    policy: ConflictPolicy = ConflictPolicy.IGNORE,
    dry_run: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    on_page: Callable[[int, int], None] | None = None,
) -> ImportResult:
    """Fetch the booked transactions of a bank account and import them into ``account_name``.

    Without ``date_from`` the longest history is fetched: right for the first fetch after a new
    consent. The first call also links the named account (or creates it) to the bank account.
    """
    if bank_account.identification_hash is None:
        raise ValueError("the bank account has no identification hash to tell it by")
    account = _resolve_account(uow_factory, bank_account, account_name, dry_run=dry_run)
    transactions = client.fetch_transactions(bank_account.uid, date_from=date_from, on_page=on_page)
    fetched_at = clock().astimezone(UTC)
    document = make_document(
        transactions,
        fetched_at=fetched_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        identification_hash=bank_account.identification_hash,
    )
    return import_statement(
        uow_factory,
        data=document,
        account_name=account.name,
        file_name=f"enable_banking_pko_{fetched_at:%Y%m%dT%H%M%SZ}.json",
        policy=policy,
        dry_run=dry_run,
    )

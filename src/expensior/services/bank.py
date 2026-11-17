"""The bank commands as use cases: ask for a consent, link accounts to it, fetch with it.

Connecting is a flow across a step the user takes outside the application, in the bank's app:
``begin_connect`` asks for the consent and returns the address and the ``state``; ``open_session``
takes what the user pasted back, checks the ``state`` and exchanges the code for a session;
``link_accounts`` links the bank accounts the user named. Each step takes and returns its values
explicitly, so a command line can run them in one process and a web page in three requests
(ADR 0011). The consent lasts up to 180 days.
"""

import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from expensior.bank.enable_banking import Authorisation, BankSession

# Re-exported so that the command line can name the bank's account type and report its errors
# without importing the bank package itself (ADR 0009).
from expensior.bank.enable_banking import BankAccount as BankAccount
from expensior.bank.enable_banking import BankApiError as BankApiError
from expensior.bank.enable_banking import BankConfigError as BankConfigError
from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.callback import parse_callback
from expensior.domain.consent import ConsentStatus, consent_status, days_left
from expensior.domain.records import Account
from expensior.domain.types import ConflictPolicy
from expensior.services.fetch_transactions import BANK_SOURCE, fetch_transactions, link_in
from expensior.services.import_statement import AccountNotFoundError, ImportResult

BANK_NAME = "PKO Bank Polski"
BANK_COUNTRY = "PL"
CONSENT_DAYS = 170  # the bank allows 180; asking for less leaves room for the renewal

UnitOfWorkFactory = Callable[[], UnitOfWork]


class BankClient(Protocol):
    """What these use cases need from a bank client."""

    def start_authorisation(
        self,
        *,
        aspsp_name: str,
        country: str,
        redirect_url: str,
        valid_until: datetime,
        state: str,
        psu_type: str = "personal",
    ) -> Authorisation: ...

    def create_session(self, code: str) -> BankSession: ...

    def get_session(self, session_id: str) -> BankSession: ...

    def fetch_transactions(
        self,
        account_uid: str,
        *,
        date_from: date | None = None,
        on_page: Callable[[int, int], None] | None = None,
    ) -> list[dict[str, Any]]: ...


class StateMismatchError(ValueError):
    """The pasted address carries another ``state`` than the approval that was asked for."""


class NotConnectedError(LookupError):
    """The account has no consent to read, or the consent no longer covers it."""


class ConsentExpiredError(RuntimeError):
    """The consent ended; approving access again in the bank's app renews it."""


@dataclass(frozen=True)
class SessionAccount:
    """A bank account of a session, and the name it is already linked under, if any."""

    bank_account: BankAccount
    linked_as: str | None


@dataclass(frozen=True)
class Link:
    """The wish to link a bank account of the session to an account named ``account_name``."""

    bank_account: BankAccount
    account_name: str


@dataclass(frozen=True)
class LinkResult:
    """An account of the application after it was linked and given the session's consent."""

    account: Account
    bank_account: BankAccount


@dataclass(frozen=True)
class FetchOutcome:
    """The import of a fetch, and where the consent stands for the account."""

    result: ImportResult
    consent: ConsentStatus
    days_left: int | None


def begin_connect(
    client: BankClient, *, redirect_url: str, now: datetime, state: str | None = None
) -> Authorisation:
    """Ask for a consent; the user opens the returned address and approves it in the bank's app."""
    return client.start_authorisation(
        aspsp_name=BANK_NAME,
        country=BANK_COUNTRY,
        redirect_url=redirect_url,
        valid_until=now + timedelta(days=CONSENT_DAYS),
        state=state or secrets.token_urlsafe(16),
    )


def open_session(client: BankClient, *, expected_state: str, pasted: str) -> BankSession:
    """Exchange what the user pasted back (the address or the code) for a session.

    When the pasted address carries a ``state`` it must be the one asked for; a bare code has none
    to check. The code works once.
    """
    callback = parse_callback(pasted)
    if callback.state is not None and callback.state != expected_state:
        raise StateMismatchError("the pasted address belongs to a different approval")
    session = client.create_session(callback.code)
    if not session.accounts:
        raise ValueError("the consent covers no bank accounts")
    return session


def describe_session(uow_factory: UnitOfWorkFactory, session: BankSession) -> list[SessionAccount]:
    """The bank accounts of a session, each with the name it is linked under now (a renewal)."""
    with uow_factory() as uow:
        described: list[SessionAccount] = []
        for bank_account in session.accounts:
            linked = (
                uow.accounts.get_by_external_ref(BANK_SOURCE, bank_account.identification_hash)
                if bank_account.identification_hash
                else None
            )
            described.append(SessionAccount(bank_account, linked.name if linked else None))
        return described


def link_accounts(
    uow_factory: UnitOfWorkFactory, session: BankSession, links: Sequence[Link]
) -> list[LinkResult]:
    """Link bank accounts of a session to accounts of the application and store the consent.

    All of it or none: one transaction. An account that exists and is not linked yet (made for a
    CSV, say) is linked; one that does not exist is created.
    """
    names = [link.account_name for link in links]
    if len(set(names)) != len(names):
        raise ValueError("two bank accounts were given the same name")
    uids = [link.bank_account.uid for link in links]
    if len(set(uids)) != len(uids):
        raise ValueError("a bank account was linked twice")
    in_session = {account.uid for account in session.accounts}
    results: list[LinkResult] = []
    with uow_factory() as uow:
        for link in links:
            if link.bank_account.uid not in in_session:
                raise ValueError("a bank account is not part of this consent")
            if not link.bank_account.identification_hash:
                raise ValueError("the bank gave no identification for one of the accounts")
            account = link_in(uow, link.bank_account, link.account_name)
            account = uow.accounts.set_consent(account.id, session.session_id, session.valid_until)
            results.append(LinkResult(account=account, bank_account=link.bank_account))
        uow.commit()
    return results


def connected_accounts(uow_factory: UnitOfWorkFactory) -> list[Account]:
    """The accounts that are linked to the bank and have a consent, by name."""
    with uow_factory() as uow:
        return [a for a in uow.accounts.list_all() if a.external_ref and a.bank_session_id]


def fetch_for_account(
    uow_factory: UnitOfWorkFactory,
    client: BankClient,
    *,
    account_name: str,
    now: datetime,
    date_from: date | None = None,
    policy: ConflictPolicy = ConflictPolicy.IGNORE,
    dry_run: bool = False,
    on_page: Callable[[int, int], None] | None = None,
) -> FetchOutcome:
    """Fetch and import the transactions of a connected account.

    ``on_page`` is told the number of each page fetched and the transactions so far.
    """
    with uow_factory() as uow:
        account = uow.accounts.get_by_name(account_name)
    if account is None:
        raise AccountNotFoundError(f"there is no account named {account_name!r}")
    if not account.external_ref or not account.bank_session_id:
        raise NotConnectedError(f"the account {account_name!r} is not connected to the bank")
    status = consent_status(account.consent_valid_until, now)
    if status is ConsentStatus.EXPIRED:
        raise ConsentExpiredError(f"the consent for {account_name!r} has ended")
    try:
        session = client.get_session(account.bank_session_id)
    except BankApiError as error:
        if error.status_code in (401, 403):
            raise ConsentExpiredError(
                f"the bank refused the consent for {account_name!r}"
            ) from error
        raise
    bank_account = next(
        (a for a in session.accounts if a.identification_hash == account.external_ref), None
    )
    if bank_account is None:
        raise NotConnectedError(f"the consent no longer covers the account {account_name!r}")
    result = fetch_transactions(
        uow_factory,
        client,
        bank_account=bank_account,
        account_name=account.name,
        date_from=date_from,
        policy=policy,
        dry_run=dry_run,
        clock=lambda: now,
        on_page=on_page,
    )
    left = days_left(account.consent_valid_until, now) if account.consent_valid_until else None
    return FetchOutcome(result=result, consent=status, days_left=left)

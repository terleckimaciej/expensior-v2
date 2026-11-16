"""The bank use cases: connecting links accounts in three steps, fetching needs a living consent."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from eb_samples import api_transaction
from sqlalchemy import func, select

from expensior.bank.enable_banking import Authorisation, BankAccount, BankApiError, BankSession
from expensior.db import models
from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.consent import ConsentStatus
from expensior.domain.types import ConflictPolicy, ImportStatus
from expensior.services.bank import (
    BANK_NAME,
    CONSENT_DAYS,
    ConsentExpiredError,
    Link,
    NotConnectedError,
    StateMismatchError,
    begin_connect,
    connected_accounts,
    describe_session,
    fetch_for_account,
    link_accounts,
    open_session,
)
from expensior.services.fetch_transactions import BANK_SOURCE, AccountMismatchError
from expensior.services.import_statement import AccountNotFoundError

pytestmark = pytest.mark.db

UowFactory = Callable[[], UnitOfWork]
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
FIRST = BankAccount(uid="uid-1", identification_hash="hash-1", name="Main", currency="PLN")
SECOND = BankAccount(uid="uid-2", identification_hash="hash-2", name="Dollars", currency="USD")


class FakeBank:
    """Stands in for the bank client and remembers how it was called."""

    def __init__(self, accounts: tuple[BankAccount, ...] = (FIRST,), days: int = 170) -> None:
        self.session = BankSession("session-1", NOW + timedelta(days=days), accounts)
        self.calls: list[str] = []
        self.get_session_error: BankApiError | None = None
        self.authorisation: dict[str, Any] = {}

    def start_authorisation(self, **options: Any) -> Authorisation:
        self.calls.append("start_authorisation")
        self.authorisation = options
        return Authorisation(url="https://bank.example/approve", state=options["state"])

    def create_session(self, code: str) -> BankSession:
        self.calls.append(f"create_session:{code}")
        return self.session

    def get_session(self, session_id: str) -> BankSession:
        self.calls.append(f"get_session:{session_id}")
        if self.get_session_error:
            raise self.get_session_error
        return self.session

    def fetch_transactions(
        self, account_uid: str, *, date_from: date | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append(f"fetch:{account_uid}")
        return [api_transaction()]


def _count(uow_factory: UowFactory, model: type[models.Base]) -> int:
    with uow_factory() as uow:
        return uow.session.scalar(select(func.count()).select_from(model)) or 0


# --- step 1: ask for the consent ----------------------------------------------------------------


def test_a_consent_is_asked_for_at_the_bank_and_for_170_days() -> None:
    bank = FakeBank()

    authorisation = begin_connect(bank, redirect_url="https://example.com/cb", now=NOW)

    assert bank.authorisation["aspsp_name"] == BANK_NAME
    assert bank.authorisation["valid_until"] == NOW + timedelta(days=CONSENT_DAYS)
    assert bank.authorisation["redirect_url"] == "https://example.com/cb"
    assert authorisation.state and authorisation.state == bank.authorisation["state"]


# --- step 2: exchange what the user pasted for a session ---------------------------------------


def test_the_code_of_a_pasted_address_is_exchanged_when_the_state_matches() -> None:
    bank = FakeBank()

    session = open_session(
        bank, expected_state="abc", pasted="https://example.com/cb?state=abc&code=the-code"
    )

    assert session.session_id == "session-1"
    assert bank.calls == ["create_session:the-code"]


def test_a_bare_code_is_exchanged_without_a_state_to_check() -> None:
    bank = FakeBank()

    open_session(bank, expected_state="abc", pasted="the-code")

    assert bank.calls == ["create_session:the-code"]


def test_an_address_of_another_approval_is_refused_before_the_code_is_used() -> None:
    bank = FakeBank()

    with pytest.raises(StateMismatchError):
        open_session(bank, expected_state="abc", pasted="https://example.com/cb?state=zzz&code=c")

    assert bank.calls == []


@pytest.mark.parametrize("pasted", ["", "https://example.com/cb?state=abc"])
def test_a_paste_without_a_code_is_refused(pasted: str) -> None:
    bank = FakeBank()

    with pytest.raises(ValueError):
        open_session(bank, expected_state="abc", pasted=pasted)

    assert bank.calls == []


def test_a_consent_that_covers_no_accounts_is_refused() -> None:
    with pytest.raises(ValueError, match="no bank accounts"):
        open_session(FakeBank(accounts=()), expected_state="abc", pasted="the-code")


# --- step 3: link the accounts the user named ---------------------------------------------------


def test_the_accounts_of_a_session_show_which_are_linked_already(uow_factory: UowFactory) -> None:
    bank = FakeBank((FIRST, SECOND))
    link_accounts(uow_factory, bank.session, [Link(FIRST, "main")])

    described = describe_session(uow_factory, bank.session)

    assert [(d.bank_account.uid, d.linked_as) for d in described] == [
        ("uid-1", "main"),
        ("uid-2", None),
    ]


def test_several_accounts_are_linked_at_once_with_their_currency_and_the_consent(
    uow_factory: UowFactory,
) -> None:
    bank = FakeBank((FIRST, SECOND))

    results = link_accounts(uow_factory, bank.session, [Link(FIRST, "main"), Link(SECOND, "usd")])

    by_name = {r.account.name: r.account for r in results}
    assert by_name["main"].external_ref == "hash-1" and by_name["main"].currency == "PLN"
    assert by_name["usd"].external_ref == "hash-2" and by_name["usd"].currency == "USD"
    assert {a.bank_session_id for a in by_name.values()} == {"session-1"}
    assert {a.consent_valid_until for a in by_name.values()} == {NOW + timedelta(days=170)}


def test_a_mistake_at_the_second_account_leaves_the_first_unlinked(uow_factory: UowFactory) -> None:
    with uow_factory() as uow:
        uow.accounts.add("taken", BANK_SOURCE, external_ref="another-hash")
        uow.commit()
    bank = FakeBank((FIRST, SECOND))

    with pytest.raises(AccountMismatchError):
        link_accounts(uow_factory, bank.session, [Link(FIRST, "main"), Link(SECOND, "taken")])

    with uow_factory() as uow:
        assert uow.accounts.get_by_name("main") is None
    assert _count(uow_factory, models.Account) == 1


@pytest.mark.parametrize(
    "links",
    [
        [Link(FIRST, "same"), Link(SECOND, "same")],
        [Link(FIRST, "main"), Link(FIRST, "other")],
        [Link(BankAccount("uid-9", "hash-9", None), "stranger")],
        [Link(BankAccount("uid-1", None, None), "nameless")],
    ],
)
def test_wrong_links_are_refused(uow_factory: UowFactory, links: list[Link]) -> None:
    bank = FakeBank((FIRST, SECOND, BankAccount("uid-1", None, None)))

    with pytest.raises(ValueError):
        link_accounts(uow_factory, bank.session, links)

    assert _count(uow_factory, models.Account) == 0


def test_an_account_made_for_the_csv_is_linked_by_name(uow_factory: UowFactory) -> None:
    with uow_factory() as uow:
        uow.accounts.add("main", BANK_SOURCE)
        uow.commit()

    results = link_accounts(uow_factory, FakeBank().session, [Link(FIRST, "main")])

    assert results[0].account.external_ref == "hash-1"
    assert _count(uow_factory, models.Account) == 1


def test_linking_again_with_a_new_consent_renews_it(uow_factory: UowFactory) -> None:
    link_accounts(uow_factory, FakeBank().session, [Link(FIRST, "main")])
    renewed = BankSession("session-2", NOW + timedelta(days=300), (FIRST,))

    results = link_accounts(uow_factory, renewed, [Link(FIRST, "main")])

    assert results[0].account.bank_session_id == "session-2"
    assert results[0].account.consent_valid_until == NOW + timedelta(days=300)
    assert _count(uow_factory, models.Account) == 1


def test_only_accounts_with_a_consent_are_connected(uow_factory: UowFactory) -> None:
    with uow_factory() as uow:
        uow.accounts.add("csv-only", BANK_SOURCE)
        uow.commit()
    link_accounts(uow_factory, FakeBank((FIRST, SECOND)).session, [Link(SECOND, "usd")])
    link_accounts(uow_factory, FakeBank().session, [Link(FIRST, "main")])

    assert [a.name for a in connected_accounts(uow_factory)] == ["main", "usd"]


# --- fetching ---------------------------------------------------------------------------------


def _connected(uow_factory: UowFactory, bank: FakeBank) -> None:
    link_accounts(uow_factory, bank.session, [Link(FIRST, "main")])
    bank.calls.clear()


def test_fetching_imports_the_transactions_of_a_connected_account(uow_factory: UowFactory) -> None:
    bank = FakeBank()
    _connected(uow_factory, bank)

    outcome = fetch_for_account(uow_factory, bank, account_name="main", now=NOW)

    assert outcome.result.status is ImportStatus.IMPORTED and outcome.result.inserted == 1
    assert outcome.consent is ConsentStatus.OK and outcome.days_left == 170
    assert bank.calls == ["get_session:session-1", "fetch:uid-1"]


def test_a_dry_run_fetches_but_writes_nothing(uow_factory: UowFactory) -> None:
    bank = FakeBank()
    _connected(uow_factory, bank)

    outcome = fetch_for_account(uow_factory, bank, account_name="main", now=NOW, dry_run=True)

    assert outcome.result.dry_run and outcome.result.inserted == 1
    assert _count(uow_factory, models.Transaction) == 0


def test_an_account_that_does_not_exist_or_is_not_connected_is_refused(
    uow_factory: UowFactory,
) -> None:
    with pytest.raises(AccountNotFoundError):
        fetch_for_account(uow_factory, FakeBank(), account_name="nobody", now=NOW)
    with uow_factory() as uow:
        uow.accounts.add("main", BANK_SOURCE)
        uow.commit()

    with pytest.raises(NotConnectedError):
        fetch_for_account(uow_factory, FakeBank(), account_name="main", now=NOW)


def test_an_ended_consent_stops_before_the_bank_is_asked(uow_factory: UowFactory) -> None:
    bank = FakeBank()
    _connected(uow_factory, bank)

    with pytest.raises(ConsentExpiredError):
        fetch_for_account(uow_factory, bank, account_name="main", now=NOW + timedelta(days=171))

    assert bank.calls == []


def test_a_refusal_by_the_bank_means_the_consent_ended(uow_factory: UowFactory) -> None:
    bank = FakeBank()
    _connected(uow_factory, bank)
    bank.get_session_error = BankApiError(401, "EXPIRED_SESSION", "the session ended")

    with pytest.raises(ConsentExpiredError):
        fetch_for_account(uow_factory, bank, account_name="main", now=NOW)


def test_another_error_of_the_bank_is_not_taken_for_an_ended_consent(
    uow_factory: UowFactory,
) -> None:
    bank = FakeBank()
    _connected(uow_factory, bank)
    bank.get_session_error = BankApiError(500, None, "the bank is down")

    with pytest.raises(BankApiError):
        fetch_for_account(uow_factory, bank, account_name="main", now=NOW)


def test_a_consent_that_no_longer_covers_the_account_is_refused(uow_factory: UowFactory) -> None:
    bank = FakeBank()
    _connected(uow_factory, bank)
    bank.session = BankSession("session-1", NOW + timedelta(days=170), (SECOND,))

    with pytest.raises(NotConnectedError):
        fetch_for_account(uow_factory, bank, account_name="main", now=NOW)


def test_a_consent_near_its_end_is_reported_with_the_days_left(uow_factory: UowFactory) -> None:
    bank = FakeBank()
    _connected(uow_factory, bank)

    outcome = fetch_for_account(
        uow_factory,
        bank,
        account_name="main",
        now=NOW + timedelta(days=160),
        policy=ConflictPolicy.IGNORE,
    )

    assert outcome.consent is ConsentStatus.EXPIRING and outcome.days_left == 10

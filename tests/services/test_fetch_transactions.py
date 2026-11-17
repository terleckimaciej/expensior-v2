"""Fetching from the bank API links the account, imports like any source, and never duplicates."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import pytest
from eb_samples import api_transaction
from pko_samples import CSV_CP1250
from sqlalchemy import func, select

from expensior.bank.enable_banking import BankAccount
from expensior.db import models
from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.statements.enable_banking import read_enable_banking
from expensior.domain.statements.raw import RawBatch
from expensior.domain.types import ImportStatus
from expensior.services.fetch_transactions import (
    BANK_SOURCE,
    AccountMismatchError,
    fetch_transactions,
)
from expensior.services.import_statement import AccountNotFoundError, import_statement

pytestmark = pytest.mark.db

UowFactory = Callable[[], UnitOfWork]
BANK_ACCOUNT = BankAccount(uid="uid-1", identification_hash="hash-1", name="Main")
CLOCK = lambda: datetime(2026, 11, 15, 10, 0, tzinfo=UTC)  # noqa: E731


class FakeFetcher:
    """Stands in for the bank client and remembers how it was called."""

    def __init__(self, transactions: list[dict[str, Any]]) -> None:
        self.transactions = transactions
        self.calls: list[tuple[str, date | None]] = []

    def fetch_transactions(
        self,
        account_uid: str,
        *,
        date_from: date | None = None,
        on_page: Callable[[int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append((account_uid, date_from))
        if on_page is not None:
            on_page(1, len(self.transactions))
        return self.transactions


def _transactions() -> list[dict[str, Any]]:
    """The two transactions of the synthetic CSV, as the bank API gives them."""
    transfer = api_transaction(
        booking_date="2026-01-16",
        credit_debit_indicator="CRDT",
        transaction_amount={"amount": "1700.00", "currency": "PLN"},
        balance_after_transaction={"amount": "1800.00", "currency": "PLN"},
        remittance_information=["CZYNSZ ZA WRZESIEŃ", "TRANSFER-IN"],
    )
    return [api_transaction(), transfer]


def _fetch(uow_factory: UowFactory, fetcher: FakeFetcher, **options: Any) -> Any:
    return fetch_transactions(
        uow_factory,
        fetcher,
        bank_account=options.pop("bank_account", BANK_ACCOUNT),
        account_name=options.pop("account_name", "main"),
        clock=CLOCK,
        **options,
    )


def _count(uow_factory: UowFactory, model: type[models.Base]) -> int:
    with uow_factory() as uow:
        return uow.session.scalar(select(func.count()).select_from(model)) or 0


def test_the_first_fetch_creates_a_linked_account_and_imports(uow_factory: UowFactory) -> None:
    fetcher = FakeFetcher(_transactions())

    result = _fetch(uow_factory, fetcher)

    assert result.status is ImportStatus.IMPORTED and result.inserted == 2
    assert result.format_version == "enable_banking_pko_v1"
    with uow_factory() as uow:
        account = uow.accounts.get_by_external_ref(BANK_SOURCE, "hash-1")
        assert account is not None and account.name == "main"


def test_a_new_account_gets_the_currency_of_the_bank_account(uow_factory: UowFactory) -> None:
    dollars = BankAccount(uid="uid-9", identification_hash="hash-9", name="USD", currency="USD")

    _fetch(uow_factory, FakeFetcher(_transactions()), bank_account=dollars, account_name="usd")

    with uow_factory() as uow:
        account = uow.accounts.get_by_name("usd")
        assert account is not None and account.currency == "USD"


def test_fetching_again_does_not_duplicate(uow_factory: UowFactory) -> None:
    fetcher = FakeFetcher(_transactions())
    _fetch(uow_factory, fetcher)

    second = _fetch(uow_factory, fetcher)

    assert (second.inserted, second.skipped_existing) == (0, 2)
    assert _count(uow_factory, models.Transaction) == 2
    assert _count(uow_factory, models.Account) == 1


def test_an_account_made_from_the_csv_is_linked_and_shares_its_transactions(
    uow_factory: UowFactory,
) -> None:
    with uow_factory() as uow:
        uow.accounts.add("main", BANK_SOURCE)
        uow.commit()
    import_statement(uow_factory, data=CSV_CP1250, account_name="main")

    result = _fetch(uow_factory, FakeFetcher(_transactions()))

    assert (result.inserted, result.skipped_existing) == (0, 2)
    assert _count(uow_factory, models.Account) == 1
    with uow_factory() as uow:
        linked = uow.accounts.get_by_name("main")
        assert linked is not None and linked.external_ref == "hash-1"


def test_an_account_linked_to_another_bank_account_is_refused(uow_factory: UowFactory) -> None:
    with uow_factory() as uow:
        uow.accounts.add("main", BANK_SOURCE, external_ref="another-hash")
        uow.commit()

    with pytest.raises(AccountMismatchError):
        _fetch(uow_factory, FakeFetcher(_transactions()))

    assert _count(uow_factory, models.ImportBatch) == 0


def test_a_dry_run_writes_and_links_nothing(uow_factory: UowFactory) -> None:
    with uow_factory() as uow:
        uow.accounts.add("main", BANK_SOURCE)
        uow.commit()

    result = _fetch(uow_factory, FakeFetcher(_transactions()), dry_run=True)

    assert result.dry_run and result.inserted == 2
    assert _count(uow_factory, models.ImportBatch) == 0
    assert _count(uow_factory, models.Transaction) == 0
    with uow_factory() as uow:
        account = uow.accounts.get_by_name("main")
        assert account is not None and account.external_ref is None


def test_a_dry_run_needs_an_existing_account_and_does_not_fetch(uow_factory: UowFactory) -> None:
    fetcher = FakeFetcher(_transactions())

    with pytest.raises(AccountNotFoundError):
        _fetch(uow_factory, fetcher, dry_run=True)

    assert fetcher.calls == []


def test_the_start_date_goes_to_the_client(uow_factory: UowFactory) -> None:
    fetcher = FakeFetcher([])

    _fetch(uow_factory, fetcher, date_from=date(2026, 11, 1))
    _fetch(uow_factory, fetcher)

    assert fetcher.calls == [("uid-1", date(2026, 11, 1)), ("uid-1", None)]


def test_the_progress_callback_reaches_the_client(uow_factory: UowFactory) -> None:
    pages: list[tuple[int, int]] = []

    _fetch(
        uow_factory,
        FakeFetcher(_transactions()),
        on_page=lambda page, total: pages.append((page, total)),
    )

    assert pages == [(1, 2)]


def test_a_bank_account_without_a_hash_is_refused(uow_factory: UowFactory) -> None:
    unknown = BankAccount(uid="uid-1", identification_hash=None, name=None)

    with pytest.raises(ValueError, match="identification hash"):
        _fetch(uow_factory, FakeFetcher([]), bank_account=unknown)


def test_the_stored_bytes_are_the_document_that_was_fetched(uow_factory: UowFactory) -> None:
    result = _fetch(uow_factory, FakeFetcher(_transactions()))

    assert result.batch_id is not None
    with uow_factory() as uow:
        data = uow.batches.source_bytes(result.batch_id)
        batch = uow.batches.get(result.batch_id)
    assert data is not None and batch is not None
    document = read_enable_banking(data)
    assert isinstance(document, RawBatch) and len(document.rows) == 2
    assert batch.file_name == "enable_banking_pko_20261115T100000Z.json"

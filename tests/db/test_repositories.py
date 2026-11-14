"""The repositories read and write domain records; classification history stays append-only."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from expensior.db import models
from expensior.db.repositories.batches import BatchRepository
from expensior.db.repositories.categories import CategoryRepository
from expensior.db.repositories.classifications import ClassificationRepository
from expensior.db.repositories.raw_rows import RawRowRepository
from expensior.db.repositories.rules import RuleRepository
from expensior.db.repositories.transactions import TransactionRepository
from expensior.domain.identity import transaction_id_for
from expensior.domain.records import ImportBatch, Transaction
from expensior.domain.types import ClassificationMethod, ImportStatus, MatchType

pytestmark = pytest.mark.db


def _account_id(session: Session) -> int:
    account = models.Account(name="main", source="pko_bp")
    session.add(account)
    session.flush()
    return account.id


def _batch(session: Session, account_id: int | None = None, sha256: str = "a" * 64) -> ImportBatch:
    return BatchRepository(session).add(
        account_id=account_id or _account_id(session),
        source="pko_bp",
        sha256=sha256,
        source_bytes=b"abc",
        file_name="statement.csv",
    )


def _transaction(batch: ImportBatch, line_no: int, amount: str = "-12.34") -> Transaction:
    operation_date = date(2026, 1, 15)
    balance = Decimal("100.00")
    return Transaction(
        transaction_id=transaction_id_for(
            batch.account_id, operation_date, Decimal(amount), balance
        ),
        account_id=batch.account_id,
        raw_batch_id=batch.id,
        raw_line_no=line_no,
        operation_date=operation_date,
        value_date=None,
        transaction_type="CARD-PAYMENT",
        amount=Decimal(amount),
        balance_after=balance,
        currency="PLN",
        description="SHOP",
        country=None,
        city=None,
    )


def _stored_transaction(session: Session) -> Transaction:
    batch = _batch(session)
    RawRowRepository(session).add_many(batch.id, [(1, {"Kwota": "-12.34"})])
    transaction = _transaction(batch, 1)
    TransactionRepository(session).add_many([transaction])
    return transaction


def test_a_new_batch_is_received_and_keeps_its_bytes(db_session: Session) -> None:
    batches = BatchRepository(db_session)

    batch = _batch(db_session)

    assert batch.status is ImportStatus.RECEIVED
    assert batch.size_bytes == 3
    assert batch.imported_at is not None
    assert batches.source_bytes(batch.id) == b"abc"
    assert batches.get(batch.id) == batch


def test_batches_with_the_same_content_are_found_oldest_first(db_session: Session) -> None:
    first = _batch(db_session)
    second = _batch(db_session, account_id=first.account_id, sha256=first.sha256)

    found = BatchRepository(db_session).find_by_sha256(first.sha256)

    assert [batch.id for batch in found] == [first.id, second.id]


def test_update_status_sets_the_given_values(db_session: Session) -> None:
    batches = BatchRepository(db_session)
    batch = _batch(db_session)

    batches.update_status(
        batch.id, ImportStatus.IMPORTED, format_version="pko_bp_v1", header=["a", "b"], row_count=2
    )

    updated = batches.get(batch.id)
    assert updated is not None
    assert updated.status is ImportStatus.IMPORTED
    assert (updated.format_version, updated.row_count) == ("pko_bp_v1", 2)


def test_update_status_of_an_unknown_batch_fails(db_session: Session) -> None:
    with pytest.raises(LookupError):
        BatchRepository(db_session).update_status(999_999, ImportStatus.FAILED)


def test_raw_rows_come_back_in_line_order(db_session: Session) -> None:
    batch = _batch(db_session)
    raw_rows = RawRowRepository(db_session)

    raw_rows.add_many(batch.id, [(3, {"x": "c"}), (1, {"x": "a"}), (2, {"x": "b"})])

    assert raw_rows.for_batch(batch.id) == [(1, {"x": "a"}), (2, {"x": "b"}), (3, {"x": "c"})]
    assert raw_rows.count(batch.id) == 3


def test_adding_no_raw_rows_is_a_no_op(db_session: Session) -> None:
    batch = _batch(db_session)
    raw_rows = RawRowRepository(db_session)

    raw_rows.add_many(batch.id, [])

    assert raw_rows.count(batch.id) == 0


def test_a_transaction_round_trips_without_losing_the_amount(db_session: Session) -> None:
    stored = _stored_transaction(db_session)

    loaded = TransactionRepository(db_session).get(stored.transaction_id)

    assert loaded == stored
    assert isinstance(loaded.amount, Decimal) if loaded else False


def test_existing_ids_returns_only_the_stored_ones(db_session: Session) -> None:
    stored = _stored_transaction(db_session)
    unknown = transaction_id_for(1, date(2026, 2, 1), Decimal("-1.00"), Decimal("5.00"))

    found = TransactionRepository(db_session).existing_ids([stored.transaction_id, unknown])

    assert found == {stored.transaction_id}


def test_category_path_runs_from_the_root_down(db_session: Session) -> None:
    categories = CategoryRepository(db_session)
    food = categories.add("Food")
    groceries = categories.add("Groceries", food.id)
    bakery = categories.add("Bakery", groceries.id)

    path = categories.path(bakery.id)

    assert [category.name for category in path] == ["Food", "Groceries", "Bakery"]
    assert [category.name for category in categories.children(None)] == ["Food"]
    assert [category.name for category in categories.children(food.id)] == ["Groceries"]


def test_enabled_rules_come_back_by_priority(db_session: Session) -> None:
    category = CategoryRepository(db_session).add("Food")
    rules = RuleRepository(db_session)
    low = rules.add(
        pattern="a",
        match_type=MatchType.CONTAINS,
        source_column="description",
        category_id=category.id,
        priority=1,
    )
    high = rules.add(
        pattern="b",
        match_type=MatchType.REGEX,
        source_column="description",
        category_id=category.id,
        priority=50,
    )
    rules.add(
        pattern="c",
        match_type=MatchType.CONTAINS,
        source_column="description",
        category_id=category.id,
        priority=99,
        enabled=False,
    )

    assert [rule.id for rule in rules.list_enabled()] == [high.id, low.id]


def test_classifying_again_keeps_the_history_and_one_current_entry(db_session: Session) -> None:
    transaction = _stored_transaction(db_session)
    categories = CategoryRepository(db_session)
    food, home, fun = categories.add("Food"), categories.add("Home"), categories.add("Fun")
    classifications = ClassificationRepository(db_session)

    for category in (food, home, fun):
        classifications.add(transaction.transaction_id, category.id, ClassificationMethod.MANUAL)

    history = classifications.history(transaction.transaction_id)
    current = classifications.current(transaction.transaction_id)
    assert [entry.category_id for entry in history] == [food.id, home.id, fun.id]
    assert [entry.is_current for entry in history] == [False, False, True]
    assert current == history[-1]

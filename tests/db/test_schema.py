"""The constraints of the schema hold: they are enforced by the database, not by convention."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from expensior.db.models import (
    Account,
    Category,
    Classification,
    ImportBatch,
    RawRow,
    Transaction,
    TransactionFlag,
)

pytestmark = pytest.mark.db


def _account(session: Session, name: str = "main") -> Account:
    account = Account(name=name, source="pko_bp")
    session.add(account)
    session.flush()
    return account


def _batch(session: Session, account: Account | None = None) -> ImportBatch:
    account = account or _account(session)
    batch = ImportBatch(
        account_id=account.id,
        source="pko_bp",
        sha256="0" * 64,
        size_bytes=3,
        source_bytes=b"abc",
    )
    session.add(batch)
    session.flush()
    return batch


def _category(session: Session, name: str, parent: Category | None = None) -> Category:
    category = Category(name=name, parent_id=parent.id if parent else None)
    session.add(category)
    session.flush()
    return category


def _transaction(
    session: Session, batch: ImportBatch, transaction_id: str = "t1", line_no: int = 1
) -> Transaction:
    """A transaction in the batch's account, derived from a raw row created for it."""
    session.add(RawRow(batch_id=batch.id, line_no=line_no, cells={"Kwota": "-12.34"}))
    session.flush()
    transaction = Transaction(
        transaction_id=transaction_id,
        account_id=batch.account_id,
        raw_batch_id=batch.id,
        raw_line_no=line_no,
        operation_date=date(2026, 1, 15),
        transaction_type="CARD-PAYMENT",
        amount=Decimal("-12.34"),
        balance_after=Decimal("100.00"),
        description="SHOP",
    )
    session.add(transaction)
    session.flush()
    return transaction


def test_decimal_amount_round_trips_without_loss(db_session: Session) -> None:
    transaction = _transaction(db_session, _batch(db_session))
    transaction.amount = Decimal("-1234567.89")
    db_session.flush()
    db_session.expire(transaction)

    assert transaction.amount == Decimal("-1234567.89")
    assert isinstance(transaction.amount, Decimal)


def test_second_current_classification_is_rejected(db_session: Session) -> None:
    transaction = _transaction(db_session, _batch(db_session))
    category = _category(db_session, "Food")
    db_session.add(
        Classification(
            transaction_id=transaction.transaction_id, category_id=category.id, method="rule"
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            Classification(
                transaction_id=transaction.transaction_id, category_id=category.id, method="manual"
            )
        )
        db_session.flush()


def test_classification_history_keeps_superseded_rows(db_session: Session) -> None:
    transaction = _transaction(db_session, _batch(db_session))
    category = _category(db_session, "Food")
    for is_current in (False, False, True):
        db_session.add(
            Classification(
                transaction_id=transaction.transaction_id,
                category_id=category.id,
                method="manual",
                is_current=is_current,
            )
        )
    db_session.flush()

    total = db_session.scalar(select(func.count()).select_from(Classification))

    assert total == 3


def test_second_current_flag_is_rejected_per_flag(db_session: Session) -> None:
    transaction = _transaction(db_session, _batch(db_session))
    db_session.add(
        TransactionFlag(transaction_id=transaction.transaction_id, flag="a", method="manual")
    )
    db_session.add(
        TransactionFlag(transaction_id=transaction.transaction_id, flag="b", method="manual")
    )
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            TransactionFlag(transaction_id=transaction.transaction_id, flag="a", method="rule")
        )
        db_session.flush()


def test_deleting_a_batch_removes_its_raw_rows(db_session: Session) -> None:
    batch = _batch(db_session)
    db_session.add(RawRow(batch_id=batch.id, line_no=1, cells={"Kwota": "-1.00"}))
    db_session.flush()

    db_session.execute(delete(ImportBatch).where(ImportBatch.id == batch.id))

    assert db_session.scalar(select(func.count()).select_from(RawRow)) == 0


def test_a_batch_that_still_has_transactions_cannot_be_deleted(db_session: Session) -> None:
    batch = _batch(db_session)
    _transaction(db_session, batch)

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(delete(ImportBatch).where(ImportBatch.id == batch.id))


def test_a_category_with_children_cannot_be_deleted(db_session: Session) -> None:
    parent = _category(db_session, "Food")
    _category(db_session, "Groceries", parent)

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(delete(Category).where(Category.id == parent.id))


def test_duplicate_root_category_is_rejected(db_session: Session) -> None:
    _category(db_session, "Food")

    with pytest.raises(IntegrityError), db_session.begin_nested():
        _category(db_session, "Food")


def test_same_name_under_different_parents_is_allowed(db_session: Session) -> None:
    food = _category(db_session, "Food")
    home = _category(db_session, "Home")
    _category(db_session, "Other", food)
    _category(db_session, "Other", home)

    names = db_session.scalars(select(Category.name).where(Category.name == "Other")).all()

    assert len(names) == 2


def test_unknown_batch_status_is_rejected(db_session: Session) -> None:
    account = _account(db_session)

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            ImportBatch(
                account_id=account.id,
                source="pko_bp",
                sha256="0" * 64,
                size_bytes=1,
                source_bytes=b"x",
                status="bogus",
            )
        )
        db_session.flush()


def test_an_account_that_has_transactions_cannot_be_deleted(db_session: Session) -> None:
    batch = _batch(db_session)
    _transaction(db_session, batch)

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(delete(Account).where(Account.id == batch.account_id))


def test_a_raw_row_that_has_a_transaction_cannot_be_deleted(db_session: Session) -> None:
    batch = _batch(db_session)
    _transaction(db_session, batch, line_no=7)

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(delete(RawRow).where(RawRow.batch_id == batch.id, RawRow.line_no == 7))


def test_a_transaction_must_point_at_an_existing_raw_row(db_session: Session) -> None:
    batch = _batch(db_session)

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            Transaction(
                transaction_id="orphan",
                account_id=batch.account_id,
                raw_batch_id=batch.id,
                raw_line_no=99,
                operation_date=date(2026, 1, 15),
                transaction_type="CARD-PAYMENT",
                amount=Decimal("-1.00"),
                balance_after=Decimal("1.00"),
                description="SHOP",
            )
        )
        db_session.flush()


def test_duplicate_account_name_is_rejected(db_session: Session) -> None:
    _account(db_session, "main")

    with pytest.raises(IntegrityError), db_session.begin_nested():
        _account(db_session, "main")


def test_the_same_api_account_is_not_stored_twice(db_session: Session) -> None:
    db_session.add(Account(name="a", source="enable_banking_pko", external_ref="hash-1"))
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(Account(name="b", source="enable_banking_pko", external_ref="hash-1"))
        db_session.flush()


def test_csv_only_accounts_without_an_external_reference_can_coexist(db_session: Session) -> None:
    _account(db_session, "first")
    _account(db_session, "second")

    assert db_session.scalar(select(func.count()).select_from(Account)) == 2

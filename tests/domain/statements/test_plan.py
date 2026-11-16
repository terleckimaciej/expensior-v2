"""The import plan splits incoming transactions by whether they are already stored."""

from datetime import date
from decimal import Decimal

import pytest

from expensior.domain.identity import transaction_id_for
from expensior.domain.records import Transaction
from expensior.domain.statements.plan import ConflictError, ImportPlan, plan_import
from expensior.domain.types import ConflictPolicy


def _transaction(day: int, line_no: int = 2) -> Transaction:
    operation_date = date(2026, 1, day)
    amount, balance = Decimal("-1.00"), Decimal("10.00")
    return Transaction(
        transaction_id=transaction_id_for(1, operation_date, amount, balance),
        account_id=1,
        raw_batch_id=1,
        raw_line_no=line_no,
        operation_date=operation_date,
        value_date=None,
        transaction_type="card_payment",
        amount=amount,
        balance_after=balance,
        currency="PLN",
        description="SHOP",
        country=None,
        city=None,
    )


FIRST, SECOND, THIRD = _transaction(1), _transaction(2), _transaction(3)


def test_new_transactions_are_inserted() -> None:
    plan = plan_import([FIRST, SECOND], set(), ConflictPolicy.IGNORE)

    assert plan == ImportPlan((FIRST, SECOND), (), 0, 0)


def test_ignore_skips_what_is_stored_and_counts_it() -> None:
    plan = plan_import([FIRST, SECOND], {FIRST.transaction_id}, ConflictPolicy.IGNORE)

    assert plan == ImportPlan((SECOND,), (), 1, 0)


def test_replace_plans_the_stored_ones_for_replacement() -> None:
    plan = plan_import([FIRST, SECOND], {FIRST.transaction_id}, ConflictPolicy.REPLACE)

    assert plan == ImportPlan((SECOND,), (FIRST,), 0, 0)


def test_abort_refuses_a_stored_transaction_and_says_how_many() -> None:
    stored = {FIRST.transaction_id, SECOND.transaction_id}

    with pytest.raises(ConflictError) as error:
        plan_import([FIRST, SECOND, THIRD], stored, ConflictPolicy.ABORT)

    assert error.value.count == 2


def test_abort_without_a_conflict_plans_normally() -> None:
    plan = plan_import([FIRST], set(), ConflictPolicy.ABORT)

    assert plan.to_insert == (FIRST,)


def test_a_repeated_id_inside_the_file_counts_as_a_duplicate() -> None:
    repeated = _transaction(1, line_no=9)

    plan = plan_import([FIRST, SECOND, repeated], set(), ConflictPolicy.IGNORE)

    assert plan.to_insert == (FIRST, SECOND)
    assert plan.duplicates_in_file == 1


def test_an_empty_statement_gives_an_empty_plan() -> None:
    assert plan_import([], {FIRST.transaction_id}, ConflictPolicy.IGNORE) == ImportPlan(
        (), (), 0, 0
    )

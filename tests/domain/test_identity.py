"""The identity of a transaction is deterministic and depends on exactly what ADR 0010 says."""

from datetime import date
from decimal import Decimal

import pytest

from expensior.domain.identity import transaction_id_for
from expensior.domain.types import TransactionId


def _id(
    account_id: int = 1,
    operation_date: date = date(2026, 1, 15),
    amount: Decimal = Decimal("-12.34"),
    balance_after: Decimal = Decimal("100.00"),
) -> TransactionId:
    return transaction_id_for(account_id, operation_date, amount, balance_after)


def test_the_same_values_give_the_same_id() -> None:
    assert _id() == _id()


def test_the_id_is_pinned() -> None:
    # Changing the rule changes every id, which would break idempotency for data already
    # imported; this value must only change on purpose, with a migration of the ids.
    assert _id() == "537a69da77ad141b25a0b9574e13212121a40722bd212dc515deb132fdc4a318"


def test_each_part_of_the_identity_matters() -> None:
    ids = {
        _id(),
        _id(account_id=2),
        _id(operation_date=date(2026, 1, 16)),
        _id(amount=Decimal("12.34")),
        _id(balance_after=Decimal("100.01")),
    }

    assert len(ids) == 5


def test_the_scale_of_a_decimal_does_not_matter() -> None:
    assert _id(amount=Decimal("-12.3")) == _id(amount=Decimal("-12.30"))
    assert _id(amount=Decimal("-12.30")) == _id(amount=Decimal("-12.300"))


def test_zero_has_no_sign() -> None:
    assert _id(amount=Decimal("0.00")) == _id(amount=Decimal("-0.00"))


def test_an_amount_with_more_than_two_decimals_is_rejected() -> None:
    with pytest.raises(ValueError, match="more than two decimal places"):
        _id(amount=Decimal("-12.345"))

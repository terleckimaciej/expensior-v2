"""The identity of a transaction (ADR 0007, ADR 0010).

A transaction has one id whichever source it came from, so the same transaction read from a CSV
and from the bank's API is recognised as one. The id is derived from what both sources share: the
account, the operation date, the signed amount and the balance after the transaction.
"""

import hashlib
from datetime import date
from decimal import Decimal

from expensior.domain.types import Money, TransactionId

_CENT = Decimal("0.01")


def _money_text(amount: Money) -> str:
    """The canonical text of an amount: two decimals, and zero without a sign."""
    cents = amount.quantize(_CENT)
    if cents != amount:
        raise ValueError(f"amount {amount} has more than two decimal places")
    if cents == 0:
        return "0.00"
    return f"{cents:.2f}"


def transaction_id_for(
    account_id: int, operation_date: date, amount: Money, balance_after: Money
) -> TransactionId:
    """The id of a transaction: a SHA-256 of its account, operation date, amount and balance.

    ``amount`` is signed (debits are negative). The same values always give the same id, and the
    scale of a ``Decimal`` does not matter (``12.3`` and ``12.30`` are one amount).
    """
    key = "|".join(
        (
            str(account_id),
            operation_date.isoformat(),
            _money_text(amount),
            _money_text(balance_after),
        )
    )
    return TransactionId(hashlib.sha256(key.encode()).hexdigest())

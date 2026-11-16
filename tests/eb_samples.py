"""Synthetic Enable Banking transactions for tests: the real response's shape, invented content.

Nothing here comes from a real account (AGENTS.md). The empty fields are the ones PKO BP leaves
empty.
"""

from copy import deepcopy
from typing import Any

_BASE: dict[str, Any] = {
    "status": "BOOK",
    "booking_date": "2026-01-15",
    "value_date": None,
    "transaction_date": None,
    "credit_debit_indicator": "DBIT",
    "transaction_amount": {"amount": "12.34", "currency": "PLN"},
    "balance_after_transaction": {"amount": "100.00", "currency": "PLN"},
    "remittance_information": ["WARSZAWASKLEP PRZYKŁADPL", "CARD-PAYMENT"],
    "entry_reference": "000000000001",
    "transaction_id": None,
    "bank_transaction_code": None,
    "merchant_category_code": None,
    "note": None,
    "reference_number": None,
    "creditor": {"name": None},
    "debtor": {"name": None},
    "creditor_account": {"iban": None},
    "debtor_account": {"iban": "PL00000000000000000000000000"},
}


def api_transaction(**changes: Any) -> dict[str, Any]:
    """A fresh transaction in the API's shape, with the given top-level fields replaced."""
    return {**deepcopy(_BASE), **changes}

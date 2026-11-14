"""The records the domain logic works with: frozen, plain data, no ORM objects (ADR 0009, rule 4).

Not a mirror of every table: a record carries what the logic needs. Repositories map database rows
to these types, so nothing from SQLAlchemy crosses a layer boundary.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from expensior.domain.types import (
    ClassificationMethod,
    ImportStatus,
    MatchType,
    Money,
    TransactionId,
)


@dataclass(frozen=True)
class Account:
    """A bank account."""

    id: int
    name: str
    source: str
    external_ref: str | None
    currency: str


@dataclass(frozen=True)
class ImportBatch:
    """One import; the original bytes are loaded separately, on demand."""

    id: int
    account_id: int
    source: str
    format_version: str | None
    file_name: str | None
    sha256: str
    size_bytes: int
    status: ImportStatus
    error: str | None
    row_count: int | None
    imported_at: datetime


@dataclass(frozen=True)
class Transaction:
    """A bank transaction, derived from the raw row it points at."""

    transaction_id: TransactionId
    account_id: int
    raw_batch_id: int
    raw_line_no: int
    operation_date: date
    value_date: date | None
    transaction_type: str
    amount: Money
    balance_after: Money
    currency: str
    description: str
    country: str | None
    city: str | None


@dataclass(frozen=True)
class Category:
    """A node of the category tree; a root has no parent."""

    id: int
    name: str
    parent_id: int | None


@dataclass(frozen=True)
class Rule:
    """A classification rule: a pattern matched on one column of a transaction."""

    id: int
    pattern: str
    match_type: MatchType
    source_column: str
    merchant: str | None
    category_id: int
    conditions: dict[str, Any] | None
    priority: int
    enabled: bool


@dataclass(frozen=True)
class Classification:
    """One entry in the classification history of a transaction; one entry is current."""

    id: int
    transaction_id: TransactionId
    category_id: int
    merchant: str | None
    method: ClassificationMethod
    rule_id: int | None
    is_current: bool
    created_at: datetime

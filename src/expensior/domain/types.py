"""Plain types the domain logic works with: identifiers, money and the enumerations of the schema.

Pure Python (ADR 0009): no database, no framework. The enumeration values are the strings that the
database stores in its ``CHECK`` constraints (ADR 0010); a db test keeps the two in step.
"""

from decimal import Decimal
from enum import StrEnum
from typing import NewType

# An amount of money. Never a float (AGENTS.md); the database column is NUMERIC(12,2).
Money = Decimal

# The primary key of a transaction: a hash of its account, operation date, amount and balance
# (ADR 0007, ADR 0010). A NewType so that it is not mixed up with any other string.
TransactionId = NewType("TransactionId", str)


class ImportStatus(StrEnum):
    """Where an import batch is in its life (``import_batches.status``)."""

    RECEIVED = "received"
    UNRECOGNISED = "unrecognised"
    IMPORTED = "imported"
    FAILED = "failed"
    UNDONE = "undone"


class ClassificationMethod(StrEnum):
    """How a classification or a flag came about (``classifications.method``)."""

    RULE = "rule"
    MANUAL = "manual"


class MatchType(StrEnum):
    """How a rule's pattern is matched (``rules.match_type``)."""

    CONTAINS = "contains"
    REGEX = "regex"

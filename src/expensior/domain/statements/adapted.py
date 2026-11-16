"""What any source adapter returns for a whole statement, whatever the format (ADR 0007)."""

from dataclasses import dataclass

from expensior.domain.records import Transaction


@dataclass(frozen=True)
class Invalid:
    """A row that cannot be read, with the reason."""

    line_no: int
    reason: str


@dataclass(frozen=True)
class AdaptedStatement:
    """All rows of a statement: the transactions and what was left out, for the batch audit."""

    transactions: tuple[Transaction, ...]
    holds: int
    invalid: tuple[Invalid, ...]
    unknown_types: dict[str, int]

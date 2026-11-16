"""What any source adapter returns, whatever the format (ADR 0007).

An adapter turns one raw row into a ``Parsed`` transaction, a ``Hold`` (a row that is not a
transaction) or an ``Invalid`` row; ``collect`` sums the rows of a statement up for the batch audit.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from expensior.domain.records import Transaction


@dataclass(frozen=True)
class Parsed:
    """A transaction; ``unknown_type`` is the source's type text when the vocabulary lacks it."""

    transaction: Transaction
    unknown_type: str | None


@dataclass(frozen=True)
class Hold:
    """A row that is not a transaction (a hold, or not booked yet): skipped and counted."""

    line_no: int


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


def collect(results: Iterable[Parsed | Hold | Invalid]) -> AdaptedStatement:
    """Sum up the result of every row of a statement."""
    transactions: list[Transaction] = []
    invalid: list[Invalid] = []
    unknown: Counter[str] = Counter()
    holds = 0
    for result in results:
        if isinstance(result, Parsed):
            transactions.append(result.transaction)
            if result.unknown_type is not None:
                unknown[result.unknown_type] += 1
        elif isinstance(result, Hold):
            holds += 1
        else:
            invalid.append(result)
    return AdaptedStatement(
        transactions=tuple(transactions),
        holds=holds,
        invalid=tuple(invalid),
        unknown_types=dict(unknown),
    )

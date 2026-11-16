"""The plan of an import: what would be inserted, replaced or skipped (ADR 0009).

Pure: it takes the incoming transactions and the ids already stored, and decides. A dry run prints
this plan; a real run executes it.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from expensior.domain.records import Transaction
from expensior.domain.types import ConflictPolicy, TransactionId


class ConflictError(ValueError):
    """The policy is ``abort`` and some incoming transactions are already stored."""

    def __init__(self, count: int) -> None:
        super().__init__(f"{count} incoming transaction(s) are already stored; nothing was written")
        self.count = count


@dataclass(frozen=True)
class ImportPlan:
    """What an import would do; ``duplicates_in_file`` counts repeats of an id inside the file."""

    to_insert: tuple[Transaction, ...]
    to_replace: tuple[Transaction, ...]
    skipped_existing: int
    duplicates_in_file: int


def plan_import(
    incoming: Sequence[Transaction],
    existing_ids: Collection[TransactionId],
    policy: ConflictPolicy,
) -> ImportPlan:
    """Split the incoming transactions by whether their id is already stored.

    The first occurrence of an id in the file counts; later ones are duplicates. With ``abort`` any
    stored id is an error, raised before anything is planned.
    """
    unique: dict[TransactionId, Transaction] = {}
    duplicates = 0
    for transaction in incoming:
        if transaction.transaction_id in unique:
            duplicates += 1
        else:
            unique[transaction.transaction_id] = transaction

    stored = [transaction for key, transaction in unique.items() if key in existing_ids]
    if stored and policy is ConflictPolicy.ABORT:
        raise ConflictError(len(stored))

    to_insert = tuple(t for key, t in unique.items() if key not in existing_ids)
    if policy is ConflictPolicy.REPLACE:
        return ImportPlan(to_insert, tuple(stored), 0, duplicates)
    return ImportPlan(to_insert, (), len(stored), duplicates)

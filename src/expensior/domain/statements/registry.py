"""The registry of sources: which one recognises a given set of bytes (ADR 0007).

Adding a source is one more entry in ``SOURCES``.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from expensior.domain.statements.enable_banking import ENABLE_BANKING_PKO_V1_SOURCE
from expensior.domain.statements.formats import Unrecognised
from expensior.domain.statements.pko_csv import PKO_BP_V1_SOURCE
from expensior.domain.statements.raw import RawBatch
from expensior.domain.statements.source import Source

SOURCES: tuple[Source, ...] = (PKO_BP_V1_SOURCE, ENABLE_BANKING_PKO_V1_SOURCE)


@dataclass(frozen=True)
class Identified:
    """The source that recognised the bytes, and what it read from them."""

    source: Source
    batch: RawBatch


def identify(data: bytes, sources: Sequence[Source] = SOURCES) -> Identified | Unrecognised:
    """The first source that recognises the bytes, or what the first one saw when none does."""
    first_miss: Unrecognised | None = None
    for source in sources:
        result = source.read(data)
        if isinstance(result, RawBatch):
            return Identified(source=source, batch=result)
        first_miss = first_miss or result
    return first_miss or Unrecognised(header=())

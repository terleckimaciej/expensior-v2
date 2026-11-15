"""Recognising the format of a statement from its header (ADR 0007).

An unknown header is a result, not an exception: the import keeps the bytes and reports the header
it saw, and once a parser exists for the new format the batch is reprocessed.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class StatementFormat:
    """A known format: where it comes from, its version, and the header cells that identify it."""

    source: str
    version: str
    signature: tuple[str, ...]


@dataclass(frozen=True)
class Unrecognised:
    """The header matched no known format; it is kept for the error message."""

    header: tuple[str, ...]


# The named columns of the PKO BP export. The unnamed cells after them (the description is spread
# over several) are not part of the signature.
PKO_BP_V1 = StatementFormat(
    source="pko_bp",
    version="pko_bp_v1",
    signature=(
        "Data operacji",
        "Data waluty",
        "Typ transakcji",
        "Kwota",
        "Waluta",
        "Saldo po transakcji",
        "Opis transakcji",
    ),
)

FORMATS: tuple[StatementFormat, ...] = (PKO_BP_V1,)


def detect_format(header: Sequence[str]) -> StatementFormat | Unrecognised:
    """The format whose signature starts the header, or ``Unrecognised`` with the header seen."""
    cells = tuple(cell.strip() for cell in header)
    for known in FORMATS:
        if cells[: len(known.signature)] == known.signature:
            return known
    return Unrecognised(header=cells)

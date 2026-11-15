"""Splitting a decoded statement into a header and raw rows: text, no interpretation (ADR 0007).

Each row is a dict keyed by the file's own header, so a column that the bank adds or renames does
not break landing the data. Values are kept exactly as they came (no trimming); a cell that is
missing from a short row is absent rather than an empty string: the two mean different things.
"""

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RawRow:
    """One record of the file: the line it starts on and its cells, keyed by the header."""

    line_no: int
    cells: dict[str, str]


@dataclass(frozen=True)
class RawBatch:
    """A parsed file: the header as it was written, the keys used for the cells, and the rows."""

    header: tuple[str, ...]
    keys: tuple[str, ...]
    rows: tuple[RawRow, ...]


def header_keys(header: Sequence[str]) -> tuple[str, ...]:
    """One distinct key per header cell: its name, or its position when it has none or repeats."""
    keys: list[str] = []
    used: set[str] = set()
    for position, cell in enumerate(header, start=1):
        key = cell.strip() or f"column_{position}"
        if key in used:
            key = f"{key}_{position}"
        while key in used:
            key += "_"
        used.add(key)
        keys.append(key)
    return tuple(keys)


def _delimiter(text: str) -> str:
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    return ";" if first_line.count(";") > first_line.count(",") else ","


def parse_raw(text: str) -> RawBatch:
    """Split the text into the header and the rows after it; blank lines are skipped.

    An empty text gives an empty batch, whose header no format recognises. A malformed record
    raises ``csv.Error``.
    """
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(text))
    header: tuple[str, ...] = ()
    keys: tuple[str, ...] = ()
    rows: list[RawRow] = []
    seen_header = False
    while True:
        start = reader.line_num + 1
        try:
            record = next(reader)
        except StopIteration:
            break
        if not record:
            continue
        if not seen_header:
            header = tuple(cell.strip() for cell in record)
            keys = header_keys(record)
            seen_header = True
            continue
        cells = {
            (keys[position] if position < len(keys) else f"column_{position + 1}"): value
            for position, value in enumerate(record)
        }
        rows.append(RawRow(line_no=start, cells=cells))
    return RawBatch(header=header, keys=keys, rows=tuple(rows))

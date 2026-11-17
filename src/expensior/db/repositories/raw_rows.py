"""Reading and writing raw rows (layer 1 of ADR 0007), untouched. Never commits.

A raw row is a pair: the line number in the file (or the position in an API response) and the cells
as they arrived, keyed by the file's own header. The typed ``RawRow`` of the parser arrives with
stage 2.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from expensior.db import models

# Rows per statement: each carries three bind parameters, and Postgres allows 65535 in one.
_CHUNK = 5000


class RawRowRepository:
    """Raw rows of one session; the caller owns the transaction and the commit."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_many(self, batch_id: int, rows: Iterable[tuple[int, Mapping[str, Any]]]) -> None:
        """Insert the rows of a batch in one statement. Does not commit."""
        values: list[dict[str, Any]] = [
            {"batch_id": batch_id, "line_no": line_no, "cells": dict(cells)}
            for line_no, cells in rows
        ]
        if values:
            self._session.execute(insert(models.RawRow), values)

    def for_batch(self, batch_id: int) -> list[tuple[int, dict[str, Any]]]:
        """The rows of a batch in line order: what reprocessing starts from."""
        result = self._session.execute(
            select(models.RawRow.line_no, models.RawRow.cells)
            .where(models.RawRow.batch_id == batch_id)
            .order_by(models.RawRow.line_no)
        )
        return [(line_no, cells) for line_no, cells in result]

    def count(self, batch_id: int) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(models.RawRow)
                .where(models.RawRow.batch_id == batch_id)
            )
            or 0
        )

    def delete_for_batch(self, batch_id: int) -> int:
        """Delete the rows of a batch; the transactions that point at them must be gone first."""
        result = self._session.execute(
            delete(models.RawRow).where(models.RawRow.batch_id == batch_id)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    def sync_batch(self, batch_id: int, rows: Iterable[tuple[int, Mapping[str, Any]]]) -> None:
        """Make the stored rows of a batch match ``rows``, read again from the stored bytes.

        Cells are updated, new lines are added, lines no longer in ``rows`` are dropped. A line a
        transaction points at must be among the given ones, or the database refuses the delete.
        """
        values = [
            {"batch_id": batch_id, "line_no": line_no, "cells": dict(cells)}
            for line_no, cells in rows
        ]
        for start in range(0, len(values), _CHUNK):
            statement = pg_insert(models.RawRow).values(values[start : start + _CHUNK])
            self._session.execute(
                statement.on_conflict_do_update(
                    index_elements=["batch_id", "line_no"],
                    set_={"cells": statement.excluded.cells},
                )
            )
        kept = [value["line_no"] for value in values]
        self._session.execute(
            delete(models.RawRow).where(
                models.RawRow.batch_id == batch_id, models.RawRow.line_no.not_in(kept)
            )
        )

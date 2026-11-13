"""Reading and writing raw rows (layer 1 of ADR 0007), untouched. Never commits.

A raw row is a pair: the line number in the file (or the position in an API response) and the cells
as they arrived, keyed by the file's own header. The typed ``RawRow`` of the parser arrives with
stage 2.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from expensior.db import models


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

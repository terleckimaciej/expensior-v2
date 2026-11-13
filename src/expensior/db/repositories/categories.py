"""Reading and writing the category tree. Never commits."""

from sqlalchemy import literal, select
from sqlalchemy.orm import Session, aliased

from expensior.db import models
from expensior.domain.records import Category


def _record(row: models.Category) -> Category:
    return Category(id=row.id, name=row.name, parent_id=row.parent_id)


class CategoryRepository:
    """Categories of one session; the caller owns the transaction and the commit."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, name: str, parent_id: int | None = None) -> Category:
        """Add a category; the database rejects a duplicate name under the same parent."""
        row = models.Category(name=name, parent_id=parent_id)
        self._session.add(row)
        self._session.flush()
        return _record(row)

    def get(self, category_id: int) -> Category | None:
        row = self._session.get(models.Category, category_id)
        return _record(row) if row else None

    def children(self, parent_id: int | None) -> list[Category]:
        """The direct children of a category, or the roots when ``parent_id`` is ``None``."""
        parent_column = models.Category.parent_id
        condition = parent_column.is_(None) if parent_id is None else parent_column == parent_id
        rows = self._session.scalars(
            select(models.Category).where(condition).order_by(models.Category.name)
        )
        return [_record(row) for row in rows]

    def path(self, category_id: int) -> list[Category]:
        """The chain from the root down to the category, in one recursive query."""
        ancestors = (
            select(
                models.Category.id,
                models.Category.name,
                models.Category.parent_id,
                literal(0).label("depth"),
            )
            .where(models.Category.id == category_id)
            .cte("ancestors", recursive=True)
        )
        parent = aliased(models.Category)
        ancestors = ancestors.union_all(
            select(parent.id, parent.name, parent.parent_id, ancestors.c.depth + 1).where(
                parent.id == ancestors.c.parent_id
            )
        )
        rows = self._session.execute(select(ancestors).order_by(ancestors.c.depth.desc()))
        return [Category(id=row.id, name=row.name, parent_id=row.parent_id) for row in rows]

"""Reading and writing classification rules. Never commits."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from expensior.db import models
from expensior.domain.records import Rule
from expensior.domain.types import MatchType


def _record(row: models.Rule) -> Rule:
    return Rule(
        id=row.id,
        pattern=row.pattern,
        match_type=MatchType(row.match_type),
        source_column=row.source_column,
        merchant=row.merchant,
        category_id=row.category_id,
        conditions=row.conditions,
        priority=row.priority,
        enabled=row.enabled,
    )


class RuleRepository:
    """Rules of one session; the caller owns the transaction and the commit."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        pattern: str,
        match_type: MatchType,
        source_column: str,
        category_id: int,
        merchant: str | None = None,
        conditions: dict[str, Any] | None = None,
        priority: int = 10,
        enabled: bool = True,
    ) -> Rule:
        row = models.Rule(
            pattern=pattern,
            match_type=match_type.value,
            source_column=source_column,
            category_id=category_id,
            merchant=merchant,
            conditions=conditions,
            priority=priority,
            enabled=enabled,
        )
        self._session.add(row)
        self._session.flush()
        return _record(row)

    def get(self, rule_id: int) -> Rule | None:
        row = self._session.get(models.Rule, rule_id)
        return _record(row) if row else None

    def list_enabled(self) -> list[Rule]:
        """Enabled rules in the order the engine tries them: higher priority first, then oldest."""
        rows = self._session.scalars(
            select(models.Rule)
            .where(models.Rule.enabled.is_(True))
            .order_by(models.Rule.priority.desc(), models.Rule.id)
        )
        return [_record(row) for row in rows]

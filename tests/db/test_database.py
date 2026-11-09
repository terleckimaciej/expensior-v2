"""The database test infrastructure works: a connection, and the migrations were applied."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.db


def test_session_can_query(db_session: Session) -> None:
    assert db_session.execute(text("select 1")).scalar() == 1


def test_migrations_were_applied(db_session: Session) -> None:
    exists = db_session.execute(text("select to_regclass('alembic_version') is not null")).scalar()

    assert exists is True

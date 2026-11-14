"""The unit of work commits only when told to, and rolls back otherwise."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from expensior.db.unit_of_work import UnitOfWork

pytestmark = pytest.mark.db


@pytest.fixture
def session_factory(migrated_engine: Engine) -> Iterator[sessionmaker[Session]]:
    """Sessions on one connection inside an outer transaction that is rolled back after the test.

    A real ``commit()`` in the test releases a savepoint only, so the next unit of work sees the
    result and the test database stays clean.
    """
    connection = migrated_engine.connect()
    transaction = connection.begin()
    try:
        yield sessionmaker(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
    finally:
        transaction.rollback()
        connection.close()


def _root_names(factory: sessionmaker[Session]) -> list[str]:
    with UnitOfWork(factory) as uow:
        return [category.name for category in uow.categories.children(None)]


def test_commit_makes_the_changes_visible_to_the_next_unit_of_work(
    session_factory: sessionmaker[Session],
) -> None:
    with UnitOfWork(session_factory) as uow:
        uow.categories.add("Food")
        uow.commit()

    assert _root_names(session_factory) == ["Food"]


def test_leaving_without_a_commit_rolls_back(session_factory: sessionmaker[Session]) -> None:
    with UnitOfWork(session_factory) as uow:
        uow.categories.add("Food")  # the repository call alone persists nothing

    assert _root_names(session_factory) == []


def test_an_exception_rolls_back(session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(RuntimeError), UnitOfWork(session_factory) as uow:
        uow.categories.add("Food")
        raise RuntimeError("something went wrong before the commit")

    assert _root_names(session_factory) == []


def test_an_exception_after_the_commit_keeps_what_was_committed(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(RuntimeError), UnitOfWork(session_factory) as uow:
        uow.categories.add("Food")
        uow.commit()
        raise RuntimeError("something went wrong after the commit")

    assert _root_names(session_factory) == ["Food"]

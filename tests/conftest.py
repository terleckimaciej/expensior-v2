"""Shared fixtures. The ``db`` fixtures run against a throwaway local Postgres, never a real one."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from expensior.db.session import database_host, make_engine

# The credentials of the throwaway Postgres from docker-compose.yml.
DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://expensior:expensior@localhost:5432/expensior_test"  # noqa: E501  # pragma: allowlist secret
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
REPO_ROOT = Path(__file__).resolve().parent.parent


def ensure_safe_test_database(url: str) -> None:
    """Refuse a URL that is not a local database named ``*_test``.

    Database tests migrate the schema and roll back; they must never reach a real database,
    even when an environment variable is set wrongly.
    """
    host = database_host(url)
    if host not in LOCAL_HOSTS:
        raise RuntimeError(f"refusing to run database tests against host {host!r}: only localhost")
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        raise RuntimeError(
            f"refusing to run database tests against {name!r}: the name must end in _test"
        )


def _database_unavailable(reason: str) -> None:
    """Skip locally; fail in CI, where a missing database must not hide a problem."""
    if os.environ.get("CI"):
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """The URL of the test database: ``TEST_DATABASE_URL``, or the local docker-compose one."""
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    ensure_safe_test_database(url)
    return url


@pytest.fixture(scope="session")
def migrated_engine(test_database_url: str) -> Iterator[Engine]:
    """An engine for the test database, created if missing and migrated to head once per session."""
    url = make_url(test_database_url)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("select 1 from pg_database where datname = :name"), {"name": url.database}
            ).scalar()
            if not exists:
                quoted = connection.dialect.identifier_preparer.quote(str(url.database))
                connection.execute(text(f"create database {quoted}"))
    except OperationalError:
        _database_unavailable("no local Postgres; start it with `docker compose up -d --wait`")
    finally:
        admin.dispose()

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    config.attributes["url"] = test_database_url
    config.attributes["configure_logging"] = False
    command.upgrade(config, "head")

    engine = make_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    """A session inside an outer transaction that is rolled back after the test.

    ``create_savepoint`` makes a ``commit()`` inside the test release a savepoint instead of
    committing for real, so tests can exercise commit logic and still leave no trace.
    """
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()

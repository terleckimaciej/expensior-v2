"""Database tests must refuse anything that is not a local ``*_test`` database."""

import pytest
from conftest import ensure_safe_test_database

from expensior.db.session import database_host

LOCAL_URL = "postgresql+psycopg://u:p@localhost:5432/expensior_test"  # pragma: allowlist secret


def test_a_local_test_database_is_accepted() -> None:
    ensure_safe_test_database(LOCAL_URL)


def test_a_remote_host_is_refused() -> None:
    url = "postgresql+psycopg://u:p@ep-example.neon.tech/expensior_test"  # pragma: allowlist secret

    with pytest.raises(RuntimeError, match="only localhost"):
        ensure_safe_test_database(url)


def test_a_database_not_named_test_is_refused() -> None:
    url = "postgresql+psycopg://u:p@localhost:5432/expensior"  # pragma: allowlist secret

    with pytest.raises(RuntimeError, match="must end in _test"):
        ensure_safe_test_database(url)


def test_database_host_hides_the_credentials() -> None:
    assert database_host(LOCAL_URL) == "localhost"

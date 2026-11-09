"""Settings are read from the environment, loaded lazily, and have no default database."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from expensior.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_database_url_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")

    assert get_settings().database_url == "postgresql+psycopg://test:test@localhost/test"


def test_missing_database_url_is_an_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)  # an empty directory, so no real .env is picked up

    with pytest.raises(ValidationError):
        Settings()

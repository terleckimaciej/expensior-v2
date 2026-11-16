"""Application settings, read from environment variables and an optional ``.env`` file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Nothing here has a default that points at a real database."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str

    # The bank API (Enable Banking). Optional: only the bank commands need them. The private key
    # lives in a file outside the repository, and only its path is configured here.
    enable_banking_app_id: str | None = None
    enable_banking_key_path: Path | None = None
    enable_banking_redirect_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the settings, loaded on first use.

    Loading is lazy on purpose: importing the package must not require environment variables, so
    the pure domain code and its tests run without any configuration.
    """
    return Settings()

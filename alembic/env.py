"""Alembic environment: where the database URL and the model metadata come from."""

import logging
from logging.config import fileConfig

from alembic import context

from expensior.config import get_settings
from expensior.db import models  # noqa: F401  (registers the tables on Base.metadata)
from expensior.db.models import Base
from expensior.db.session import database_host, make_engine

config = context.config

# Logging is configured from alembic.ini only when run from the command line; tests pass
# `configure_logging=False` so that they keep pytest's own logging.
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# Importing the models registers every table on Base.metadata (the tables arrive in stage 1b).
target_metadata = Base.metadata


def _database_url() -> str:
    """The URL a test passes in `config.attributes["url"]`, otherwise DATABASE_URL from settings."""
    url = config.attributes.get("url") or get_settings().database_url
    return str(url)


def run_migrations_offline() -> None:
    """Emit the SQL to the output instead of running it (``alembic upgrade head --sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run the migrations against the database."""
    url = _database_url()
    logger.info("target database host: %s", database_host(url))
    engine = make_engine(url)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

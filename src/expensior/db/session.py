"""Engine and session factory, plus a helper that names the database a URL points at."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from expensior.config import get_settings


def database_host(url: str) -> str:
    """Return the host of a database URL, to show the target before anything is written."""
    return make_url(url).host or "(local socket)"


def make_engine(url: str | None = None) -> Engine:
    """Create an engine; with no URL, use ``DATABASE_URL`` from the settings.

    ``pool_pre_ping`` makes the pool test a connection before using it. Neon suspends an idle
    database, and the first query after that must not run on a connection the server has dropped.
    """
    return create_engine(url or get_settings().database_url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to ``engine``.

    ``expire_on_commit=False`` keeps objects readable after a commit instead of reloading them.
    """
    return sessionmaker(engine, expire_on_commit=False)

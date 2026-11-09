"""SQLAlchemy models. The tables arrive in stage 1b; this module holds the declarative base."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Explicit names for constraints and indexes: without them Postgres invents names, and migrations
# that drop or alter a constraint depend on a name nobody chose. `ck` needs a name on each CHECK.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class of all models; its metadata is what Alembic compares the database against."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

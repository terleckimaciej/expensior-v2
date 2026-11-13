"""SQLAlchemy models: the tables of ADR 0007 (bytes, raw rows, transactions, classifications).

Money is ``NUMERIC(12,2)`` (``Decimal``, never float), dates are ``date``, timestamps are
``timestamptz``. Enumerations are ``text`` with a ``CHECK`` rather than Postgres enums, which are
awkward to migrate.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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


def _timestamp() -> Mapped[datetime]:
    """A ``timestamptz`` column set by the database when the row is created."""
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    """A bank account. Balances and transaction ids make sense within one account (ADR 0010)."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("name", name="uq_accounts_name"),
        # An API account is recognised by its external reference; CSV-only accounts have none.
        UniqueConstraint("source", "external_ref", name="uq_accounts_source_external_ref"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)  # e.g. "pko_bp", "enable_banking_pko"
    external_ref: Mapped[str | None] = mapped_column(Text)  # the API's identification hash
    currency: Mapped[str] = mapped_column(String(3), server_default="PLN")


class ImportBatch(Base):
    """One import: a file or an API response. Layer 0 of ADR 0007, stored before any parsing."""

    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(
            "status in ('received', 'unrecognised', 'imported', 'failed', 'undone')",
            name="status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    source: Mapped[str] = mapped_column(Text)  # e.g. "pko_bp", "enable_banking_pko"
    format_version: Mapped[str | None] = mapped_column(Text)  # set once the format is recognised
    file_name: Mapped[str | None] = mapped_column(Text)
    # Indexed, not unique: the same file may be imported again after an undo.
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    # Deferred: an API response is megabytes, and an ordinary read of a batch should not load it.
    source_bytes: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    header: Mapped[list[str] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, server_default="received")
    error: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    imported_at: Mapped[datetime] = _timestamp()


class RawRow(Base):
    """One line of an imported file (or one API transaction), untouched. Layer 1 of ADR 0007."""

    __tablename__ = "raw_rows"

    batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), primary_key=True
    )
    line_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    cells: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Category(Base):
    """A node of the category tree (category -> subcategory)."""

    __tablename__ = "categories"
    __table_args__ = (
        # NULLS NOT DISTINCT: two root categories (parent_id NULL) cannot share a name either.
        UniqueConstraint("parent_id", "name", postgresql_nulls_not_distinct=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))


class Transaction(Base):
    """A bank transaction derived from a raw row. Layer 2 of ADR 0007, for every source."""

    __tablename__ = "transactions"
    __table_args__ = (
        # RESTRICT: a raw row that has a transaction cannot be deleted, so neither can its batch.
        ForeignKeyConstraint(
            ["raw_batch_id", "raw_line_no"],
            ["raw_rows.batch_id", "raw_rows.line_no"],
            ondelete="RESTRICT",
        ),
        Index("ix_transactions_raw_batch_id", "raw_batch_id"),
    )

    # A hash of account, operation date, signed amount and balance after (ADR 0007), set by the
    # importer.
    transaction_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    raw_batch_id: Mapped[int] = mapped_column(BigInteger)
    raw_line_no: Mapped[int] = mapped_column(Integer)
    operation_date: Mapped[date] = mapped_column(Date, index=True)  # places it in a month
    value_date: Mapped[date | None] = mapped_column(Date)  # only the CSV has it
    transaction_type: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # signed: debits are negative
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), server_default="PLN")
    description: Mapped[str] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)  # only the CSV has it
    city: Mapped[str | None] = mapped_column(Text)  # only the CSV has it
    created_at: Mapped[datetime] = _timestamp()


class Rule(Base):
    """A classification rule: a pattern on one column, with optional extra conditions."""

    __tablename__ = "rules"
    __table_args__ = (
        CheckConstraint("match_type in ('contains', 'regex')", name="match_type_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    pattern: Mapped[str] = mapped_column(Text)
    match_type: Mapped[str] = mapped_column(Text)
    source_column: Mapped[str] = mapped_column(Text)
    merchant: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    # Validated by a typed Pydantic model in `domain`, stored as JSON.
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    priority: Mapped[int] = mapped_column(Integer, server_default="10")
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Classification(Base):
    """The classification history of a transaction. Append-only: exactly one row is current."""

    __tablename__ = "classifications"
    __table_args__ = (
        CheckConstraint("method in ('rule', 'manual')", name="method_valid"),
        # The rule "one current classification per transaction", enforced by the database.
        Index(
            "uq_classifications_current",
            "transaction_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index(
            "ix_classifications_category_current",
            "category_id",
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.transaction_id", ondelete="CASCADE")
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    merchant: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id", ondelete="SET NULL"))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = _timestamp()


class TransactionFlag(Base):
    """A label on a transaction (``is_reimbursement``, ...), with history like classifications."""

    __tablename__ = "transaction_flags"
    __table_args__ = (
        CheckConstraint("method in ('rule', 'manual')", name="method_valid"),
        Index(
            "uq_transaction_flags_current",
            "transaction_id",
            "flag",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.transaction_id", ondelete="CASCADE")
    )
    flag: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id", ondelete="SET NULL"))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = _timestamp()

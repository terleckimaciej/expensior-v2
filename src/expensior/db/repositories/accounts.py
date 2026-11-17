"""Reading and writing bank accounts. Never commits."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from expensior.db import models
from expensior.domain.records import Account


def _record(row: models.Account) -> Account:
    return Account(
        id=row.id,
        name=row.name,
        source=row.source,
        external_ref=row.external_ref,
        currency=row.currency,
        bank_session_id=row.bank_session_id,
        consent_valid_until=row.consent_valid_until,
    )


class AccountRepository:
    """Accounts of one session; the caller owns the transaction and the commit."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        name: str,
        source: str,
        *,
        external_ref: str | None = None,
        currency: str = "PLN",
    ) -> Account:
        """Add an account; the database rejects a repeated name or a repeated API reference."""
        row = models.Account(name=name, source=source, external_ref=external_ref, currency=currency)
        self._session.add(row)
        self._session.flush()
        return _record(row)

    def set_external_ref(self, account_id: int, external_ref: str) -> Account:
        """Link an account to the bank API's identification of it; the database keeps it unique."""
        row = self._session.get(models.Account, account_id)
        if row is None:
            raise LookupError(f"no account with id {account_id}")
        row.external_ref = external_ref
        self._session.flush()
        return _record(row)

    def set_consent(
        self, account_id: int, bank_session_id: str, valid_until: datetime | None
    ) -> Account:
        """Record the bank session of a new or renewed consent and when it ends."""
        row = self._session.get(models.Account, account_id)
        if row is None:
            raise LookupError(f"no account with id {account_id}")
        row.bank_session_id = bank_session_id
        row.consent_valid_until = valid_until
        self._session.flush()
        return _record(row)

    def get_by_name(self, name: str) -> Account | None:
        row = self._session.scalar(select(models.Account).where(models.Account.name == name))
        return _record(row) if row else None

    def get_by_external_ref(self, source: str, external_ref: str) -> Account | None:
        """The account the bank API knows by this reference (its identification hash)."""
        row = self._session.scalar(
            select(models.Account).where(
                models.Account.source == source, models.Account.external_ref == external_ref
            )
        )
        return _record(row) if row else None

    def list_all(self) -> list[Account]:
        rows = self._session.scalars(select(models.Account).order_by(models.Account.name))
        return [_record(row) for row in rows]

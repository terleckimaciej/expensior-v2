"""Wiring: the pieces a command needs, built from the settings when the command runs.

The command line asks for a ``Runtime`` and never imports the database or the bank packages itself
(ADR 0009). The bank client is built on demand, so a command that does not use the bank needs none
of its settings.
"""

from collections.abc import Callable
from dataclasses import dataclass

from expensior.bank.enable_banking import EnableBankingClient
from expensior.config import get_settings
from expensior.db.session import database_host, make_engine, make_session_factory
from expensior.db.unit_of_work import UnitOfWork
from expensior.services.bank import BankClient


@dataclass(frozen=True)
class Runtime:
    """What a command works with: the database, where it is, and the bank."""

    uow_factory: Callable[[], UnitOfWork]
    database_host: str
    redirect_url: str | None
    bank_client: Callable[[], BankClient]


def build_runtime() -> Runtime:
    """Build the runtime from ``DATABASE_URL`` and the optional bank settings."""
    settings = get_settings()
    session_factory = make_session_factory(make_engine(settings.database_url))
    return Runtime(
        uow_factory=lambda: UnitOfWork(session_factory),
        database_host=database_host(settings.database_url),
        redirect_url=settings.enable_banking_redirect_url,
        bank_client=lambda: EnableBankingClient.from_settings(settings),
    )

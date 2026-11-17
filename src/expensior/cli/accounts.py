"""The ``expensior accounts`` command: what accounts there are and where their bank consent stands.

Accounts are not added by hand: one is made when a bank account is named in ``bank connect`` (and,
for a CSV, on the first import).
"""

import argparse

from expensior.cli.context import Context
from expensior.cli.output import consent_text
from expensior.services.accounts import list_accounts


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Add ``accounts list`` to the parser."""
    accounts = subparsers.add_parser("accounts", help="the accounts of the application")
    commands = accounts.add_subparsers(dest="accounts_command", required=True)
    listing = commands.add_parser("list", help="list the accounts and their bank consent")
    listing.set_defaults(handler=_list)


def _list(args: argparse.Namespace, context: Context) -> int:
    accounts = list_accounts(context.runtime().uow_factory)
    if not accounts:
        print("No accounts yet. Connect to the bank with: expensior bank connect")
        return 0
    now = context.now()
    width = max(len(account.name) for account in accounts)
    for account in accounts:
        print(f"{account.name:<{width}}  {account.source:<8}  {consent_text(account, now)}")
    return 0

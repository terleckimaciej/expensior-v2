"""The ``expensior bank`` commands: connect to the bank API, fetch transactions through it.

``connect`` is one interactive run: it asks the bank for a consent, waits while the user approves
it in the bank's app, then asks what to call each bank account here. It is a thin client of three
service steps, so a web page can run the same steps later (ADR 0011).
"""

import argparse
import sys
from datetime import date

from expensior.cli.confirm import confirm
from expensior.cli.context import Context
from expensior.cli.output import describe_import
from expensior.domain.consent import ConsentStatus
from expensior.domain.types import ConflictPolicy
from expensior.services.bank import (
    BankAccount,
    BankApiError,
    BankClient,
    BankConfigError,
    ConsentExpiredError,
    Link,
    NotConnectedError,
    SessionAccount,
    StateMismatchError,
    begin_connect,
    connected_accounts,
    describe_session,
    fetch_for_account,
    link_accounts,
    open_session,
)
from expensior.services.import_statement import AccountNotFoundError
from expensior.services.runtime import Runtime


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Add ``bank connect`` and ``bank fetch`` to the parser."""
    bank = subparsers.add_parser("bank", help="read your accounts' transactions from the bank API")
    commands = bank.add_subparsers(dest="bank_command", required=True)

    connect = commands.add_parser(
        "connect", help="approve access in the bank's app and name your bank accounts here"
    )
    connect.add_argument("--yes", action="store_true", help="do not ask before writing")
    connect.set_defaults(handler=_connect)

    fetch = commands.add_parser("fetch", help="fetch transactions from the bank and import them")
    fetch.add_argument("account", nargs="?", help="one account (default: every connected account)")
    fetch.add_argument(
        "--since", type=date.fromisoformat, help="only from this date (default: all the bank has)"
    )
    fetch.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
    fetch.add_argument(
        "--on-conflict",
        choices=[policy.value for policy in ConflictPolicy],
        default=ConflictPolicy.IGNORE.value,
        help="what to do with a transaction that is already stored (default: ignore)",
    )
    fetch.add_argument("--yes", action="store_true", help="do not ask before writing")
    fetch.set_defaults(handler=_fetch)


def _error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def _label(bank_account: BankAccount) -> str:
    if bank_account.iban:
        known_by = f"account ...{bank_account.iban[-4:]}"  # as the bank's own app shows it
    else:
        known_by = f"id ...{(bank_account.identification_hash or '')[-6:]}"
    parts = [
        bank_account.name or "(no name)",
        known_by,
        bank_account.currency,
        bank_account.details,
    ]
    return "  ".join(part for part in parts if part)


def _name_accounts(described: list[SessionAccount], context: Context) -> list[Link]:
    """Show the bank accounts and ask what to call each; one already linked keeps its name."""
    print(f"The bank gave access to {len(described)} account(s):")
    for number, item in enumerate(described, start=1):
        already = f"  (already linked as {item.linked_as!r})" if item.linked_as else ""
        print(f"  {number}. {_label(item.bank_account)}{already}")
    if any(item.linked_as is None for item in described):
        print("Name each one you want to use here (press Enter to skip it):")
    links: list[Link] = []
    for number, item in enumerate(described, start=1):
        if item.linked_as:
            links.append(Link(item.bank_account, item.linked_as))
            continue
        name = context.ask(f"  {number} > ").strip()
        if name:
            links.append(Link(item.bank_account, name))
    return links


def _connect(args: argparse.Namespace, context: Context) -> int:
    runtime = context.runtime()
    if not runtime.redirect_url:
        return _error(
            "set ENABLE_BANKING_REDIRECT_URL to the address registered for the application"
        )
    try:
        client = runtime.bank_client()
        authorisation = begin_connect(client, redirect_url=runtime.redirect_url, now=context.now())
        print("Open this address and approve access in the bank's app:")
        print(f"  {authorisation.url}")
        pasted = context.ask(
            "Then paste the address your browser ended up on (or just the code):\n> "
        )
        session = open_session(client, expected_state=authorisation.state, pasted=pasted)
        links = _name_accounts(describe_session(runtime.uow_factory, session), context)
        if not links:
            print("Nothing to link.")
            return 0
        print("Will link:")
        for link in links:
            print(f"  {link.account_name} <- {_label(link.bank_account)}")
        if not confirm(runtime.database_host, assume_yes=args.yes, ask=context.ask):
            print("Cancelled.")
            return 1
        results = link_accounts(runtime.uow_factory, session, links)
    except (BankConfigError, BankApiError, StateMismatchError, ValueError) as error:
        return _error(str(error))
    valid_until = session.valid_until
    until = f", consent until {valid_until:%Y-%m-%d}" if valid_until else ""
    print(f"Linked {len(results)} account(s){until}.")
    print("Fetch their transactions with: expensior bank fetch")
    return 0


def _fetch_one(
    name: str, args: argparse.Namespace, runtime: Runtime, client: BankClient, context: Context
) -> int:
    try:
        outcome = fetch_for_account(
            runtime.uow_factory,
            client,
            account_name=name,
            now=context.now(),
            date_from=args.since,
            policy=ConflictPolicy(args.on_conflict),
            dry_run=args.dry_run,
        )
    except (AccountNotFoundError, NotConnectedError) as error:
        return _error(f"{error}; connect it with: expensior bank connect")
    except ConsentExpiredError as error:
        return _error(f"{error}; renew it with: expensior bank connect")
    except BankApiError as error:
        return _error(str(error))
    for line in describe_import(outcome.result):
        print(line)
    if outcome.consent is ConsentStatus.EXPIRING:
        print(
            f"Warning: the consent ends in {outcome.days_left} days; "
            "renew it with: expensior bank connect"
        )
    return 1 if outcome.result.error else 0


def _fetch(args: argparse.Namespace, context: Context) -> int:
    runtime = context.runtime()
    try:
        client = runtime.bank_client()
    except BankConfigError as error:
        return _error(str(error))
    names = (
        [args.account]
        if args.account
        else [a.name for a in connected_accounts(runtime.uow_factory)]
    )
    if not names:
        return _error(
            "no account is connected to the bank; connect one with: expensior bank connect"
        )
    if not args.dry_run and not confirm(
        runtime.database_host, assume_yes=args.yes, ask=context.ask
    ):
        print("Cancelled.")
        return 1
    failed = 0
    for name in names:
        if len(names) > 1:
            print(f"== {name} ==")
        failed += _fetch_one(name, args, runtime, client, context)
    return 1 if failed else 0

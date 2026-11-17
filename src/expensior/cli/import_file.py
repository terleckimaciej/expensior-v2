"""The ``expensior import`` command: load a bank statement file (a CSV) into an account.

A CSV does not say which account it belongs to, so the account is the one named with ``--account``
or, without a name, the only account there is. An account that does not exist yet is created on
the first import, after asking.
"""

import argparse
from pathlib import Path

from expensior.cli.confirm import confirm
from expensior.cli.context import Context
from expensior.cli.output import describe_import, print_error
from expensior.domain.types import ConflictPolicy, ImportStatus
from expensior.services.accounts import AccountChoiceError, add_account, choose_account
from expensior.services.import_statement import import_statement


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Add ``import`` to the parser."""
    command = subparsers.add_parser("import", help="import a bank statement file (CSV)")
    command.add_argument("file", type=Path, help="the statement, e.g. a CSV exported from PKO BP")
    command.add_argument("--account", help="the account it belongs to (default: the only account)")
    command.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
    command.add_argument(
        "--on-conflict",
        choices=[policy.value for policy in ConflictPolicy],
        default=ConflictPolicy.IGNORE.value,
        help="what to do with a transaction that is already stored (default: ignore)",
    )
    command.add_argument(
        "--yes", action="store_true", help="do not ask before writing or creating the account"
    )
    command.set_defaults(handler=_import)


def _import(args: argparse.Namespace, context: Context) -> int:
    try:
        data = args.file.read_bytes()
    except OSError as error:
        return print_error(f"cannot read {args.file}: {error.strerror}")
    runtime = context.runtime()
    try:
        choice = choose_account(runtime.uow_factory, args.account)
    except AccountChoiceError as error:
        return print_error(str(error))

    if args.dry_run and choice.account is None:
        return print_error(
            f"there is no account named {choice.name!r}; a real import offers to create it"
        )
    if not args.dry_run:
        if not confirm(runtime.database_host, assume_yes=args.yes, ask=context.ask):
            print("Cancelled.")
            return 1
        if choice.account is None:
            question = f"There is no account named {choice.name!r}. Create it? [y/N] "
            if not args.yes and context.ask(question).strip().lower() not in {"y", "yes"}:
                print("Cancelled.")
                return 1
            add_account(runtime.uow_factory, choice.name)

    result = import_statement(
        runtime.uow_factory,
        data=data,
        account_name=choice.name,
        file_name=args.file.name,
        policy=ConflictPolicy(args.on_conflict),
        dry_run=args.dry_run,
    )
    for line in describe_import(result):
        print(line)
    failed = result.error is not None or result.status in {
        ImportStatus.FAILED,
        ImportStatus.UNRECOGNISED,
    }
    return 1 if failed else 0

"""The commands about imports already made: list them, undo one, reprocess one.

``undo`` and ``reprocess`` show what they would do first, and only then ask for the confirmation
that names the database host.
"""

import argparse

from expensior.cli.confirm import confirm
from expensior.cli.context import Context
from expensior.cli.output import print_error
from expensior.services.batches import list_batches
from expensior.services.import_statement import AccountNotFoundError
from expensior.services.reprocess_batch import (
    BatchNotReprocessableError,
    IdsChangedError,
    ReprocessResult,
    reprocess_batch,
)
from expensior.services.undo_batch import (
    BatchNotFoundError,
    BatchNotUndoableError,
    UndoResult,
    undo_batch,
)


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Add ``batches``, ``undo`` and ``reprocess`` to the parser."""
    batches = subparsers.add_parser("batches", help="list the imports that were made")
    batches.add_argument("--account", help="only the imports of this account")
    batches.set_defaults(handler=_list)

    undo = subparsers.add_parser(
        "undo", help="undo an import: remove its transactions, keep its original bytes"
    )
    undo.add_argument("batch", type=int, help="the number of the import (see: expensior batches)")
    undo.add_argument("--dry-run", action="store_true", help="show what would be removed only")
    undo.add_argument("--yes", action="store_true", help="do not ask before writing")
    undo.set_defaults(handler=_undo)

    reprocess = subparsers.add_parser(
        "reprocess", help="derive an import's transactions again from its stored bytes"
    )
    reprocess.add_argument("batch", type=int, help="the number of the import")
    reprocess.add_argument("--dry-run", action="store_true", help="show the plan only")
    reprocess.add_argument("--yes", action="store_true", help="do not ask before writing")
    reprocess.set_defaults(handler=_reprocess)


def _list(args: argparse.Namespace, context: Context) -> int:
    try:
        summaries = list_batches(context.runtime().uow_factory, args.account)
    except AccountNotFoundError as error:
        return print_error(str(error))
    if not summaries:
        print("No imports yet.")
        return 0
    width = max(len(summary.account_name) for summary in summaries)
    for summary in summaries:
        batch = summary.batch
        print(
            f"{batch.id:>4}  {summary.account_name:<{width}}  {batch.source:<18}  "
            f"{batch.status.value:<12}  {batch.row_count or 0:>6} rows  "
            f"{batch.imported_at:%Y-%m-%d %H:%M}  {batch.file_name or ''}"
        )
    return 0


def _describe_undo(result: UndoResult) -> list[str]:
    batch = result.batch
    return [
        f"Batch {batch.id} ({batch.source}, {batch.row_count or 0} rows) "
        f"{'would be' if result.dry_run else 'was'} undone:",
        f"  {result.transactions} transactions, {result.raw_rows} raw rows and "
        f"{result.classifications} classification entries "
        f"{'would be deleted' if result.dry_run else 'were deleted'}; the original bytes stay.",
    ]


def _undo(args: argparse.Namespace, context: Context) -> int:
    runtime = context.runtime()
    try:
        preview = undo_batch(runtime.uow_factory, args.batch, dry_run=True)
    except (BatchNotFoundError, BatchNotUndoableError) as error:
        return print_error(str(error))
    for line in _describe_undo(preview):
        print(line)
    if args.dry_run:
        print("Dry run, nothing written.")
        return 0
    if not confirm(runtime.database_host, assume_yes=args.yes, ask=context.ask):
        print("Cancelled.")
        return 1
    done = undo_batch(runtime.uow_factory, args.batch)
    print(f"Batch {done.batch.id} is undone.")
    return 0


def _describe_reprocess(result: ReprocessResult) -> list[str]:
    lines = [
        f"Batch {result.batch.id} read again as {result.format_version} ({result.row_count} rows): "
        f"{'would change' if result.dry_run else 'changed'} {result.replaced} transactions, "
        f"{result.unchanged} stay as they are, "
        f"{'would add' if result.dry_run else 'added'} {result.inserted}."
    ]
    if result.skipped_elsewhere:
        lines.append(f"{result.skipped_elsewhere} belong to another import and are left alone.")
    if result.holds:
        lines.append(f"Skipped {result.holds} rows that are not booked transactions.")
    if result.invalid:
        lines.append(f"{len(result.invalid)} rows could not be read.")
    if result.unknown_types:
        names = ", ".join(f"{name} ({count})" for name, count in result.unknown_types.items())
        lines.append(f"Unknown transaction types: {names}.")
    return lines


def _reprocess(args: argparse.Namespace, context: Context) -> int:
    runtime = context.runtime()
    try:
        preview = reprocess_batch(runtime.uow_factory, args.batch, dry_run=True)
    except (BatchNotFoundError, BatchNotReprocessableError, IdsChangedError) as error:
        return print_error(str(error))
    for line in _describe_reprocess(preview):
        print(line)
    if args.dry_run:
        print("Dry run, nothing written.")
        return 0
    if not confirm(runtime.database_host, assume_yes=args.yes, ask=context.ask):
        print("Cancelled.")
        return 1
    reprocess_batch(runtime.uow_factory, args.batch)
    print(f"Batch {args.batch} is reprocessed.")
    return 0

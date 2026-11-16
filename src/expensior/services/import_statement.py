"""Import a statement: store the bytes first, then land raw rows and transactions.

The flow of ADR 0009: transaction 1 keeps the original bytes and the batch (so a statement is never
lost, even when the parser cannot read it); transaction 2 writes the raw rows and the transactions
and marks the batch imported. A dry run writes nothing at all. The service knows no format: the
registry of sources recognises the bytes (ADR 0007).
"""

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.records import Account
from expensior.domain.statements.adapted import AdaptedStatement, Invalid
from expensior.domain.statements.formats import Unrecognised
from expensior.domain.statements.plan import ConflictError, ImportPlan, plan_import
from expensior.domain.statements.registry import SOURCES, Identified, identify
from expensior.domain.statements.source import Source
from expensior.domain.types import ConflictPolicy, ImportStatus

UnitOfWorkFactory = Callable[[], UnitOfWork]


class AccountNotFoundError(LookupError):
    """The account named for the import does not exist; nothing was written."""


@dataclass(frozen=True)
class ImportResult:
    """What an import did, or, for a dry run, what it would do.

    ``batch_id`` and ``status`` are ``None`` for a dry run. ``error`` is set when the import could
    not complete; the batch and its bytes are then stored with that status.
    """

    dry_run: bool
    batch_id: int | None
    status: ImportStatus | None
    format_version: str | None
    row_count: int
    inserted: int
    replaced: int
    skipped_existing: int
    duplicates_in_file: int
    holds: int
    invalid: tuple[Invalid, ...]
    unknown_types: dict[str, int]
    already_imported_batch_ids: tuple[int, ...]
    error: str | None


def _unrecognised_message(missed: Unrecognised) -> str:
    if missed.header:
        return "unrecognised format; header: " + ", ".join(missed.header)
    return "unrecognised format: the bytes could not be read as a known statement"


def _result(
    *,
    dry_run: bool,
    batch_id: int | None,
    status: ImportStatus | None,
    already: tuple[int, ...],
    error: str | None = None,
    format_version: str | None = None,
    row_count: int = 0,
    adapted: AdaptedStatement | None = None,
    plan: ImportPlan | None = None,
) -> ImportResult:
    return ImportResult(
        dry_run=dry_run,
        batch_id=batch_id,
        status=status,
        format_version=format_version,
        row_count=row_count,
        inserted=len(plan.to_insert) if plan else 0,
        replaced=len(plan.to_replace) if plan else 0,
        skipped_existing=plan.skipped_existing if plan else 0,
        duplicates_in_file=plan.duplicates_in_file if plan else 0,
        holds=adapted.holds if adapted else 0,
        invalid=adapted.invalid if adapted else (),
        unknown_types=adapted.unknown_types if adapted else {},
        already_imported_batch_ids=already,
        error=error,
    )


def _account(uow: UnitOfWork, name: str) -> Account:
    account = uow.accounts.get_by_name(name)
    if account is None:
        raise AccountNotFoundError(f"there is no account named {name!r}")
    return account


def _set_status(
    uow_factory: UnitOfWorkFactory, batch_id: int, status: ImportStatus, error: str
) -> None:
    with uow_factory() as uow:
        uow.batches.update_status(batch_id, status, error=error)
        uow.commit()


def _dry_run(
    uow_factory: UnitOfWorkFactory,
    identified: Identified | Unrecognised,
    *,
    sha256: str,
    account_name: str,
    policy: ConflictPolicy,
) -> ImportResult:
    """Read the account and the stored ids, and return the plan; nothing is written."""
    with uow_factory() as uow:
        account = _account(uow, account_name)
        already = tuple(batch.id for batch in uow.batches.find_by_sha256(sha256))
        if isinstance(identified, Unrecognised):
            return _result(
                dry_run=True,
                batch_id=None,
                status=None,
                already=already,
                error=_unrecognised_message(identified),
            )
        adapted = identified.source.adapt(identified.batch.rows, account.id, 0)
        existing = uow.transactions.existing_ids([t.transaction_id for t in adapted.transactions])
        version = identified.source.version
        rows = len(identified.batch.rows)
        try:
            plan = plan_import(adapted.transactions, existing, policy)
        except ConflictError as error:
            return _result(
                dry_run=True,
                batch_id=None,
                status=None,
                already=already,
                error=str(error),
                format_version=version,
                row_count=rows,
                adapted=adapted,
            )
        return _result(
            dry_run=True,
            batch_id=None,
            status=None,
            already=already,
            format_version=version,
            row_count=rows,
            adapted=adapted,
            plan=plan,
        )


def import_statement(
    uow_factory: UnitOfWorkFactory,
    *,
    data: bytes,
    account_name: str,
    file_name: str | None = None,
    policy: ConflictPolicy = ConflictPolicy.IGNORE,
    dry_run: bool = False,
    sources: Sequence[Source] = SOURCES,
) -> ImportResult:
    """Import the bytes of a statement into an account; with ``dry_run`` only report the plan."""
    sha256 = hashlib.sha256(data).hexdigest()
    identified = identify(data, sources)
    if dry_run:
        return _dry_run(
            uow_factory, identified, sha256=sha256, account_name=account_name, policy=policy
        )

    # Transaction 1: the original bytes and the batch, before anything is parsed further.
    with uow_factory() as uow:
        account = _account(uow, account_name)
        already = tuple(batch.id for batch in uow.batches.find_by_sha256(sha256))
        source_name = (
            identified.source.source if isinstance(identified, Identified) else account.source
        )
        batch = uow.batches.add(
            account_id=account.id,
            source=source_name,
            sha256=sha256,
            source_bytes=data,
            file_name=file_name,
        )
        uow.commit()

    if isinstance(identified, Unrecognised):
        message = _unrecognised_message(identified)
        _set_status(uow_factory, batch.id, ImportStatus.UNRECOGNISED, message)
        return _result(
            dry_run=False,
            batch_id=batch.id,
            status=ImportStatus.UNRECOGNISED,
            already=already,
            error=message,
        )

    # Transaction 2: raw rows and transactions together, all of it or none.
    rows = identified.batch.rows
    version = identified.source.version
    try:
        with uow_factory() as uow:
            adapted = identified.source.adapt(rows, account.id, batch.id)
            existing = uow.transactions.existing_ids(
                [t.transaction_id for t in adapted.transactions]
            )
            plan = plan_import(adapted.transactions, existing, policy)
            uow.raw_rows.add_many(batch.id, ((row.line_no, row.cells) for row in rows))
            uow.transactions.add_many(plan.to_insert)
            uow.transactions.replace_many(plan.to_replace)
            uow.batches.update_status(
                batch.id,
                ImportStatus.IMPORTED,
                format_version=version,
                header=list(identified.batch.header),
                row_count=len(rows),
            )
            uow.commit()
    except ConflictError as error:
        _set_status(uow_factory, batch.id, ImportStatus.FAILED, str(error))
        return _result(
            dry_run=False,
            batch_id=batch.id,
            status=ImportStatus.FAILED,
            already=already,
            error=str(error),
            format_version=version,
            row_count=len(rows),
        )
    except Exception as error:
        # The bytes stay stored; record why, then let the error surface.
        _set_status(uow_factory, batch.id, ImportStatus.FAILED, str(error))
        raise

    return _result(
        dry_run=False,
        batch_id=batch.id,
        status=ImportStatus.IMPORTED,
        already=already,
        format_version=version,
        row_count=len(rows),
        adapted=adapted,
        plan=plan,
    )

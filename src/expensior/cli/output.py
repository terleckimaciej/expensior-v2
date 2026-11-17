"""How a command reports an import to the terminal: counts and names, never transaction contents."""

import sys
from datetime import datetime

from expensior.domain.consent import ConsentStatus, consent_status, days_left
from expensior.domain.records import Account
from expensior.services.import_statement import ImportResult

_SHOWN_INVALID = 5


def print_error(message: str) -> int:
    """Print ``error: ...`` on stderr and return the exit code of a failed command."""
    print(f"error: {message}", file=sys.stderr)
    return 1


def describe_import(result: ImportResult) -> list[str]:
    """The lines that say what an import did, or for a dry run what it would do."""
    lines: list[str] = []
    if result.format_version:
        lines.append(f"Format: {result.format_version}, {result.row_count} rows")
    if result.dry_run:
        lines.append(
            f"Dry run, nothing written. Would insert {result.inserted}, "
            f"replace {result.replaced}, skip {result.skipped_existing} already stored."
        )
    elif result.status is not None:
        lines.append(
            f"Batch {result.batch_id} is {result.status.value}: inserted {result.inserted}, "
            f"replaced {result.replaced}, skipped {result.skipped_existing} already stored."
        )
    if result.duplicates_in_file:
        lines.append(f"{result.duplicates_in_file} repeated in the file itself.")
    if result.holds:
        lines.append(f"Skipped {result.holds} rows that are not booked transactions.")
    if result.invalid:
        shown = ", ".join(str(item.line_no) for item in result.invalid[:_SHOWN_INVALID])
        more = "" if len(result.invalid) <= _SHOWN_INVALID else ", ..."
        lines.append(f"{len(result.invalid)} rows could not be read (lines {shown}{more}).")
    if result.unknown_types:
        names = ", ".join(f"{name} ({count})" for name, count in result.unknown_types.items())
        lines.append(f"Unknown transaction types: {names}.")
    if result.already_imported_batch_ids:
        ids = ", ".join(str(batch_id) for batch_id in result.already_imported_batch_ids)
        lines.append(f"The same content was imported before in batch {ids}.")
    if result.error:
        lines.append(f"Error: {result.error}")
    return lines


def consent_text(account: Account, now: datetime) -> str:
    """The state of an account's bank consent in a few words."""
    if not account.external_ref:
        return "not linked to the bank"
    status = consent_status(account.consent_valid_until, now)
    if status is ConsentStatus.NONE or account.consent_valid_until is None:
        return "linked, no consent"
    left = days_left(account.consent_valid_until, now)
    if status is ConsentStatus.EXPIRED:
        return "consent ended"
    if status is ConsentStatus.EXPIRING:
        return f"consent ends in {left} days, renew it"
    return f"consent ok, {left} days left"

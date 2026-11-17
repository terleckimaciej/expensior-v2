"""The confirmation names the host first; the output reports counts, never contents."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from expensior.cli.confirm import confirm
from expensior.cli.output import consent_text, describe_import
from expensior.domain.records import Account
from expensior.domain.statements.adapted import Invalid
from expensior.domain.types import ImportStatus
from expensior.services.import_statement import ImportResult

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


_IMPORTED = ImportResult(
    dry_run=False,
    batch_id=7,
    status=ImportStatus.IMPORTED,
    format_version="pko_bp_v1",
    row_count=281,
    inserted=276,
    replaced=0,
    skipped_existing=0,
    duplicates_in_file=0,
    holds=0,
    invalid=(),
    unknown_types={},
    already_imported_batch_ids=(),
    error=None,
)


def _result(**changes: Any) -> ImportResult:
    return replace(_IMPORTED, **changes)


@pytest.mark.parametrize("answer", ["y", "Y", "yes", " YES "])
def test_a_yes_confirms(answer: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert confirm("db.example", assume_yes=False, ask=lambda _: answer) is True
    assert "Target database host: db.example" in capsys.readouterr().out


@pytest.mark.parametrize("answer", ["", "n", "no", "maybe"])
def test_anything_but_yes_is_a_no(answer: str) -> None:
    assert confirm("db.example", assume_yes=False, ask=lambda _: answer) is False


def test_yes_skips_the_question_but_still_names_the_host(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def never(_: str) -> str:
        raise AssertionError("the user must not be asked")

    assert confirm("db.example", assume_yes=True, ask=never) is True
    assert "db.example" in capsys.readouterr().out


def test_a_real_import_reports_the_batch_and_the_counts() -> None:
    lines = describe_import(_result(skipped_existing=3, holds=5))

    assert "Format: pko_bp_v1, 281 rows" in lines
    assert any("Batch 7 is imported: inserted 276, replaced 0, skipped 3" in line for line in lines)
    assert "Skipped 5 rows that are not booked transactions." in lines


def test_a_dry_run_says_nothing_was_written() -> None:
    lines = describe_import(_result(dry_run=True, batch_id=None, status=None))

    assert any(line.startswith("Dry run, nothing written. Would insert 276") for line in lines)
    assert not any(line.startswith("Batch") for line in lines)


def test_unreadable_rows_unknown_types_and_earlier_imports_are_reported() -> None:
    invalid = tuple(Invalid(line_no=n, reason="x") for n in range(1, 9))

    lines = describe_import(
        _result(
            invalid=invalid,
            unknown_types={"NEW-KIND": 2},
            already_imported_batch_ids=(3, 4),
            duplicates_in_file=1,
        )
    )

    assert "8 rows could not be read (lines 1, 2, 3, 4, 5, ...)." in lines
    assert "Unknown transaction types: NEW-KIND (2)." in lines
    assert "The same content was imported before in batch 3, 4." in lines
    assert "1 repeated in the file itself." in lines


def test_an_error_is_the_last_word() -> None:
    lines = describe_import(_result(status=ImportStatus.FAILED, error="boom"))

    assert lines[-1] == "Error: boom"


def _account(**changes: Any) -> Account:
    base = Account(id=1, name="main", source="pko_bp", external_ref="hash", currency="PLN")
    return replace(base, **changes)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"external_ref": None}, "not linked to the bank"),
        ({}, "linked, no consent"),
        ({"consent_valid_until": NOW + timedelta(days=100, hours=1)}, "consent ok, 100 days left"),
        (
            {"consent_valid_until": NOW + timedelta(days=9, hours=1)},
            "consent ends in 9 days, renew it",
        ),
        ({"consent_valid_until": NOW - timedelta(days=1)}, "consent ended"),
    ],
)
def test_the_consent_of_an_account_in_a_few_words(changes: dict[str, Any], expected: str) -> None:
    assert consent_text(_account(**changes), NOW) == expected

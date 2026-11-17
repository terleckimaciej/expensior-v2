"""``batches``, ``undo`` and ``reprocess``: they show first, ask once, and advise on a refusal.

The services are replaced by fakes; nothing here touches a database.
"""

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from expensior.bank.enable_banking import BankConfigError
from expensior.cli import batches as batches_command
from expensior.cli.context import Context
from expensior.cli.main import main
from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.records import ImportBatch
from expensior.domain.types import ImportStatus
from expensior.services.bank import BankClient
from expensior.services.batches import BatchSummary
from expensior.services.import_statement import AccountNotFoundError
from expensior.services.reprocess_batch import (
    BatchNotReprocessableError,
    IdsChangedError,
    ReprocessResult,
)
from expensior.services.runtime import Runtime
from expensior.services.undo_batch import BatchNotFoundError, BatchNotUndoableError, UndoResult

NOW = datetime(2026, 11, 17, 9, 30, tzinfo=UTC)
BATCH = ImportBatch(
    id=4,
    account_id=1,
    source="enable_banking_pko",
    format_version="enable_banking_pko_v1",
    file_name="enable_banking_pko_20261116T120000Z.json",
    sha256="0" * 64,
    size_bytes=10,
    status=ImportStatus.IMPORTED,
    error=None,
    row_count=2658,
    imported_at=NOW,
)


def _no_database() -> UnitOfWork:
    raise AssertionError("a command test must not reach the database")


def _no_bank() -> BankClient:
    raise BankConfigError("these commands must not need the bank")


def _context(answers: list[str] | None = None) -> Context:
    queue = list(answers or [])

    def ask(_: str) -> str:
        assert queue, "the user was asked, but the test gave no answer"
        return queue.pop(0)

    runtime = Runtime(
        uow_factory=_no_database,
        database_host="db.example",
        redirect_url=None,
        bank_client=cast(Any, _no_bank),
    )
    return Context(runtime=lambda: runtime, ask=ask, now=lambda: NOW)


def _patch(monkeypatch: pytest.MonkeyPatch, name: str, replacement: Any) -> list[Any]:
    calls: list[Any] = []

    def fake(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return replacement(*args, **kwargs) if callable(replacement) else replacement

    monkeypatch.setattr(batches_command, name, fake)
    return calls


# --- batches ----------------------------------------------------------------------------------


def test_the_imports_are_listed_with_their_numbers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, "list_batches", [BatchSummary(BATCH, "penga")])

    assert main(["batches"], context=_context()) == 0

    out = capsys.readouterr().out
    assert "   4  penga  enable_banking_pko" in out
    assert "imported" in out and "2658 rows" in out and "2026-11-17 09:30" in out


def test_the_list_can_be_limited_to_an_account(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch(monkeypatch, "list_batches", [])

    assert main(["batches", "--account", "penga"], context=_context()) == 0
    assert calls[0][0][1] == "penga"


def test_no_imports_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, "list_batches", [])

    assert main(["batches"], context=_context()) == 0
    assert "No imports yet." in capsys.readouterr().out


def test_an_unknown_account_is_an_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unknown(*_: Any, **__: Any) -> list[BatchSummary]:
        raise AccountNotFoundError("there is no account named 'x'")

    _patch(monkeypatch, "list_batches", unknown)

    assert main(["batches", "--account", "x"], context=_context()) == 1
    assert "no account named 'x'" in capsys.readouterr().err


# --- undo -------------------------------------------------------------------------------------


def _undo_result(dry_run: bool) -> UndoResult:
    return UndoResult(BATCH, transactions=2658, raw_rows=2658, classifications=12, dry_run=dry_run)


def test_undo_shows_what_goes_then_asks_and_undoes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _patch(monkeypatch, "undo_batch", lambda *a, dry_run=False, **k: _undo_result(dry_run))

    code = main(["undo", "4"], context=_context(["y"]))

    out = capsys.readouterr().out
    assert code == 0
    assert "Batch 4 (enable_banking_pko, 2658 rows) would be undone:" in out
    assert "2658 transactions, 2658 raw rows and 12 classification entries would be deleted" in out
    assert out.index("would be undone") < out.index("Target database host") < out.index("is undone")
    assert [call[1].get("dry_run", False) for call in calls] == [True, False]


def test_declining_an_undo_only_shows_the_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch(monkeypatch, "undo_batch", lambda *a, dry_run=False, **k: _undo_result(dry_run))

    assert main(["undo", "4"], context=_context(["n"])) == 1
    assert [call[1].get("dry_run", False) for call in calls] == [True]


def test_an_undo_dry_run_does_not_ask(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _patch(monkeypatch, "undo_batch", lambda *a, dry_run=False, **k: _undo_result(dry_run))

    assert main(["undo", "4", "--dry-run"], context=_context()) == 0
    assert len(calls) == 1 and "Dry run, nothing written." in capsys.readouterr().out


def test_yes_undoes_without_asking(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch(monkeypatch, "undo_batch", lambda *a, dry_run=False, **k: _undo_result(dry_run))

    assert main(["undo", "4", "--yes"], context=_context()) == 0
    assert len(calls) == 2


@pytest.mark.parametrize(
    "error",
    [BatchNotFoundError("there is no import batch 4"), BatchNotUndoableError("batch 4 is undone")],
)
def test_a_batch_that_cannot_be_undone_says_why(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], error: Exception
) -> None:
    def refuse(*_: Any, **__: Any) -> UndoResult:
        raise error

    _patch(monkeypatch, "undo_batch", refuse)

    assert main(["undo", "4", "--yes"], context=_context()) == 1
    assert str(error) in capsys.readouterr().err


# --- reprocess --------------------------------------------------------------------------------


def _reprocess_result(dry_run: bool) -> ReprocessResult:
    return ReprocessResult(
        batch=BATCH,
        format_version="enable_banking_pko_v1",
        row_count=2658,
        replaced=3,
        unchanged=2654,
        inserted=1,
        skipped_elsewhere=0,
        holds=0,
        invalid=(),
        unknown_types={},
        dry_run=dry_run,
    )


def test_reprocess_shows_the_plan_then_asks_and_runs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _patch(
        monkeypatch, "reprocess_batch", lambda *a, dry_run=False, **k: _reprocess_result(dry_run)
    )

    code = main(["reprocess", "4"], context=_context(["y"]))

    out = capsys.readouterr().out
    assert code == 0
    assert "would change 3 transactions, 2654 stay as they are, would add 1" in out
    assert (
        out.index("would change") < out.index("Target database host") < out.index("is reprocessed")
    )
    assert [call[1].get("dry_run", False) for call in calls] == [True, False]


def test_a_reprocess_dry_run_does_not_ask(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _patch(
        monkeypatch, "reprocess_batch", lambda *a, dry_run=False, **k: _reprocess_result(dry_run)
    )

    assert main(["reprocess", "4", "--dry-run"], context=_context()) == 0
    assert len(calls) == 1 and "Dry run, nothing written." in capsys.readouterr().out


def test_declining_a_reprocess_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch(
        monkeypatch, "reprocess_batch", lambda *a, dry_run=False, **k: _reprocess_result(dry_run)
    )

    assert main(["reprocess", "4"], context=_context(["n"])) == 1
    assert len(calls) == 1


def test_a_fix_that_changes_ids_is_refused_with_advice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(*_: Any, **__: Any) -> ReprocessResult:
        raise IdsChangedError(3, 1)

    _patch(monkeypatch, "reprocess_batch", refuse)

    assert main(["reprocess", "4", "--yes"], context=_context()) == 1
    err = capsys.readouterr().err
    assert "3 transactions would get a new id" in err and "Undo the batch" in err


@pytest.mark.parametrize(
    "error",
    [
        BatchNotFoundError("there is no import batch 4"),
        BatchNotReprocessableError("batch 4 is undone"),
    ],
)
def test_a_batch_that_cannot_be_reprocessed_says_why(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], error: Exception
) -> None:
    def refuse(*_: Any, **__: Any) -> ReprocessResult:
        raise error

    _patch(monkeypatch, "reprocess_batch", refuse)

    assert main(["reprocess", "4", "--yes"], context=_context()) == 1
    assert str(error) in capsys.readouterr().err

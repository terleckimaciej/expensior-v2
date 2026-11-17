"""``expensior import`` picks the account, asks before writing and reports clearly.

The services are replaced by fakes; the statement is a real file in a temporary directory.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from expensior.bank.enable_banking import BankConfigError
from expensior.cli import import_file as import_command
from expensior.cli.context import Context
from expensior.cli.main import main
from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.records import Account
from expensior.domain.types import ConflictPolicy, ImportStatus
from expensior.services.accounts import AccountChoice, AccountChoiceError
from expensior.services.bank import BankClient
from expensior.services.import_statement import ImportResult
from expensior.services.runtime import Runtime

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
MAIN = Account(id=1, name="main", source="pko_bp", external_ref=None, currency="PLN")
IMPORTED = ImportResult(
    dry_run=False,
    batch_id=7,
    status=ImportStatus.IMPORTED,
    format_version="pko_bp_v1",
    row_count=281,
    inserted=276,
    replaced=0,
    skipped_existing=0,
    duplicates_in_file=0,
    holds=5,
    invalid=(),
    unknown_types={},
    already_imported_batch_ids=(),
    error=None,
)


def _no_database() -> UnitOfWork:
    raise AssertionError("a command test must not reach the database")


def _no_bank() -> BankClient:
    raise BankConfigError("the import must not need the bank")


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

    monkeypatch.setattr(import_command, name, fake)
    return calls


@pytest.fixture
def statement(tmp_path: Path) -> Path:
    path = tmp_path / "statement.csv"
    path.write_bytes(b"synthetic bytes")
    return path


def test_a_dry_run_reports_the_plan_and_does_not_ask(
    monkeypatch: pytest.MonkeyPatch, statement: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, "choose_account", AccountChoice("main", MAIN))
    dry = replace(IMPORTED, dry_run=True, batch_id=None, status=None)
    calls = _patch(monkeypatch, "import_statement", dry)

    code = main(["import", str(statement), "--dry-run"], context=_context())

    options = calls[0][1]
    assert code == 0 and options["dry_run"] is True
    assert options["data"] == b"synthetic bytes" and options["file_name"] == "statement.csv"
    assert "Dry run, nothing written. Would insert 276" in capsys.readouterr().out


def test_a_real_import_asks_once_and_passes_the_options(
    monkeypatch: pytest.MonkeyPatch, statement: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, "choose_account", AccountChoice("main", MAIN))
    calls = _patch(monkeypatch, "import_statement", IMPORTED)

    code = main(["import", str(statement), "--on-conflict", "replace"], context=_context(["y"]))

    out = capsys.readouterr().out
    assert code == 0 and calls[0][1]["policy"] is ConflictPolicy.REPLACE
    assert "Target database host: db.example" in out
    assert "Batch 7 is imported: inserted 276" in out


def test_declining_the_confirmation_imports_nothing(
    monkeypatch: pytest.MonkeyPatch, statement: Path
) -> None:
    _patch(monkeypatch, "choose_account", AccountChoice("main", MAIN))
    calls = _patch(monkeypatch, "import_statement", IMPORTED)

    assert main(["import", str(statement)], context=_context(["n"])) == 1
    assert calls == []


def test_an_account_that_does_not_exist_is_created_after_asking(
    monkeypatch: pytest.MonkeyPatch, statement: Path
) -> None:
    _patch(monkeypatch, "choose_account", AccountChoice("brand-new", None))
    created = _patch(monkeypatch, "add_account", MAIN)
    imported = _patch(monkeypatch, "import_statement", IMPORTED)

    code = main(["import", str(statement), "--account", "brand-new"], context=_context(["y", "y"]))

    assert code == 0
    assert created[0][0][1] == "brand-new"
    assert imported[0][1]["account_name"] == "brand-new"


def test_yes_answers_both_questions(monkeypatch: pytest.MonkeyPatch, statement: Path) -> None:
    _patch(monkeypatch, "choose_account", AccountChoice("brand-new", None))
    created = _patch(monkeypatch, "add_account", MAIN)
    _patch(monkeypatch, "import_statement", IMPORTED)

    assert (
        main(["import", str(statement), "--account", "brand-new", "--yes"], context=_context()) == 0
    )
    assert len(created) == 1


def test_declining_to_create_the_account_imports_nothing(
    monkeypatch: pytest.MonkeyPatch, statement: Path
) -> None:
    _patch(monkeypatch, "choose_account", AccountChoice("brand-new", None))
    created = _patch(monkeypatch, "add_account", MAIN)
    imported = _patch(monkeypatch, "import_statement", IMPORTED)

    code = main(["import", str(statement), "--account", "brand-new"], context=_context(["y", "n"]))

    assert code == 1 and created == [] and imported == []


def test_a_dry_run_for_an_account_that_does_not_exist_says_so(
    monkeypatch: pytest.MonkeyPatch, statement: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, "choose_account", AccountChoice("brand-new", None))

    code = main(
        ["import", str(statement), "--dry-run", "--account", "brand-new"], context=_context()
    )

    assert code == 1 and "offers to create it" in capsys.readouterr().err


def test_an_unclear_account_is_an_error(
    monkeypatch: pytest.MonkeyPatch, statement: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def unclear(*_: Any, **__: Any) -> AccountChoice:
        raise AccountChoiceError("there are several accounts (main, savings): choose one")

    _patch(monkeypatch, "choose_account", unclear)

    assert main(["import", str(statement)], context=_context()) == 1
    assert "several accounts (main, savings)" in capsys.readouterr().err


def test_a_file_that_cannot_be_read_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["import", str(tmp_path / "missing.csv")], context=_context()) == 1
    assert "cannot read" in capsys.readouterr().err


def test_an_unrecognised_statement_exits_with_an_error(
    monkeypatch: pytest.MonkeyPatch, statement: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, "choose_account", AccountChoice("main", MAIN))
    unrecognised = replace(
        IMPORTED,
        status=ImportStatus.UNRECOGNISED,
        format_version=None,
        inserted=0,
        error="unrecognised format; header: Date, Amount",
    )
    _patch(monkeypatch, "import_statement", unrecognised)

    assert main(["import", str(statement), "--yes"], context=_context()) == 1
    assert "Error: unrecognised format; header: Date, Amount" in capsys.readouterr().out

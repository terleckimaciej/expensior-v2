"""The commands ask before writing, report clearly and hint at what to do next.

The services are replaced by fakes and the context by a fake one: no database, no network, no
terminal, no real clock.
"""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

import pytest

from expensior.bank.enable_banking import Authorisation, BankAccount, BankSession
from expensior.cli import accounts as accounts_command
from expensior.cli import bank as bank_command
from expensior.cli.context import Context
from expensior.cli.main import main
from expensior.db.unit_of_work import UnitOfWork
from expensior.domain.consent import ConsentStatus
from expensior.domain.records import Account
from expensior.domain.types import ConflictPolicy, ImportStatus
from expensior.services.bank import (
    BankApiError,
    BankClient,
    BankConfigError,
    ConsentExpiredError,
    FetchOutcome,
    Link,
    LinkResult,
    NotConnectedError,
    SessionAccount,
    StateMismatchError,
)
from expensior.services.import_statement import ImportResult
from expensior.services.runtime import Runtime

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
MAIN = Account(id=1, name="main", source="pko_bp", external_ref="hash-1", currency="PLN")
SAVINGS = Account(id=2, name="savings", source="pko_bp", external_ref="hash-2", currency="PLN")
ACCOUNT_ONE = BankAccount(
    "uid-1",
    "hash-aaaaaa111111",
    "Main",
    "PLN",
    iban="PL00000000000000000000004821",
    details="Personal account",
)
ACCOUNT_TWO = BankAccount("uid-2", "hash-bbbbbb222222", None, "USD")
SESSION = BankSession("session-1", NOW + timedelta(days=170), (ACCOUNT_ONE, ACCOUNT_TWO))
PASTED = "https://example.com/cb?state=abc123&code=the-code"
IMPORTED = ImportResult(
    dry_run=False,
    batch_id=7,
    status=ImportStatus.IMPORTED,
    format_version="enable_banking_pko_v1",
    row_count=2,
    inserted=2,
    replaced=0,
    skipped_existing=0,
    duplicates_in_file=0,
    holds=0,
    invalid=(),
    unknown_types={},
    already_imported_batch_ids=(),
    error=None,
)


def _no_database() -> UnitOfWork:
    raise AssertionError("a command test must not reach the database")


def _no_bank() -> BankClient:
    raise BankConfigError(
        "set ENABLE_BANKING_APP_ID and ENABLE_BANKING_KEY_PATH to use the bank API"
    )


def _context(
    answers: list[str] | None = None,
    redirect_url: str | None = "https://example.com/cb",
    bank_configured: bool = True,
) -> Context:
    """A context whose user answers from ``answers`` and fails if asked more than that."""
    queue = list(answers or [])

    def ask(_: str) -> str:
        assert queue, "the user was asked, but the test gave no answer"
        return queue.pop(0)

    runtime = Runtime(
        uow_factory=_no_database,
        database_host="db.example",
        redirect_url=redirect_url,
        bank_client=(lambda: cast(BankClient, object())) if bank_configured else _no_bank,
    )
    return Context(runtime=lambda: runtime, ask=ask, now=lambda: NOW)


def _patch(monkeypatch: pytest.MonkeyPatch, module: Any, name: str, replacement: Any) -> list[Any]:
    """Replace a service function used by a command; returns the list of its calls."""
    calls: list[Any] = []

    def fake(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return replacement(*args, **kwargs) if callable(replacement) else replacement

    monkeypatch.setattr(module, name, fake)
    return calls


def _patch_connect(
    monkeypatch: pytest.MonkeyPatch, described: list[SessionAccount] | None = None
) -> dict[str, list[Any]]:
    """The services of the connect steps, replaced; returns their calls by name."""
    described = described or [SessionAccount(ACCOUNT_ONE, None), SessionAccount(ACCOUNT_TWO, None)]
    linked = [
        LinkResult(
            account=replace(MAIN, consent_valid_until=SESSION.valid_until), bank_account=ACCOUNT_ONE
        )
    ]
    return {
        "begin": _patch(
            monkeypatch,
            bank_command,
            "begin_connect",
            Authorisation(url="https://bank.example/approve", state="abc123"),
        ),
        "open": _patch(monkeypatch, bank_command, "open_session", SESSION),
        "describe": _patch(monkeypatch, bank_command, "describe_session", described),
        "link": _patch(monkeypatch, bank_command, "link_accounts", linked),
    }


# --- accounts ---------------------------------------------------------------------------------


def test_listing_shows_the_consent_of_each_account(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    linked = replace(MAIN, consent_valid_until=NOW + timedelta(days=100, hours=1))
    other = replace(MAIN, id=2, name="savings", external_ref=None)
    _patch(monkeypatch, accounts_command, "list_accounts", [linked, other])

    assert main(["accounts", "list"], context=_context()) == 0

    out = capsys.readouterr().out
    assert "main     pko_bp    consent ok, 100 days left" in out
    assert "savings  pko_bp    not linked to the bank" in out


def test_listing_no_accounts_says_how_to_connect(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, accounts_command, "list_accounts", [])

    assert main(["accounts", "list"], context=_context()) == 0
    assert "expensior bank connect" in capsys.readouterr().out


def test_accounts_are_not_added_by_hand() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["accounts", "add", "main"], context=_context())

    assert exit_info.value.code == 2


# --- bank connect -----------------------------------------------------------------------------


def test_connect_walks_through_the_steps_and_links_what_was_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _patch_connect(monkeypatch)

    code = main(["bank", "connect"], context=_context([PASTED, "main", "", "y"]))

    out = capsys.readouterr().out
    assert code == 0
    assert "https://bank.example/approve" in out
    assert "The bank gave access to 2 account(s):" in out
    assert "1. Main  account ...4821  PLN  Personal account" in out
    assert "2. (no name)  id ...222222  USD" in out
    assert "main <- Main  account ...4821  PLN  Personal account" in out
    assert "Target database host: db.example" in out
    assert "Linked 1 account(s), consent until 2027-05-05." in out
    assert calls["open"][0][1] == {"expected_state": "abc123", "pasted": PASTED}
    ((_, link_kwargs),) = calls["link"]
    assert link_kwargs == {} and calls["link"][0][0][2] == [Link(ACCOUNT_ONE, "main")]


def test_a_renewal_does_not_ask_for_names_of_accounts_that_are_linked(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    described = [SessionAccount(ACCOUNT_ONE, "main"), SessionAccount(ACCOUNT_TWO, "usd")]
    calls = _patch_connect(monkeypatch, described)

    assert main(["bank", "connect"], context=_context([PASTED, "y"])) == 0

    out = capsys.readouterr().out
    assert "(already linked as 'main')" in out and "Name each one" not in out
    assert calls["link"][0][0][2] == [Link(ACCOUNT_ONE, "main"), Link(ACCOUNT_TWO, "usd")]


def test_skipping_every_account_links_nothing_and_does_not_ask_to_write(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _patch_connect(monkeypatch)

    assert main(["bank", "connect"], context=_context([PASTED, "", ""])) == 0

    assert calls["link"] == [] and "Nothing to link." in capsys.readouterr().out


def test_declining_the_confirmation_links_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _patch_connect(monkeypatch)

    assert main(["bank", "connect"], context=_context([PASTED, "main", "", "n"])) == 1

    assert calls["link"] == [] and "Cancelled." in capsys.readouterr().out


def test_yes_skips_the_confirmation_but_not_the_names(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_connect(monkeypatch)

    assert main(["bank", "connect", "--yes"], context=_context([PASTED, "main", ""])) == 0
    assert len(calls["link"]) == 1


def test_connect_needs_the_redirect_address(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["bank", "connect"], context=_context(redirect_url=None)) == 1
    assert "ENABLE_BANKING_REDIRECT_URL" in capsys.readouterr().err


def test_connect_without_bank_settings_says_what_to_set(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["bank", "connect"], context=_context(bank_configured=False)) == 1
    assert "ENABLE_BANKING_APP_ID" in capsys.readouterr().err


def test_an_address_of_another_approval_stops_connect(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _patch_connect(monkeypatch)

    def wrong_state(*_: Any, **__: Any) -> BankSession:
        raise StateMismatchError("the pasted address belongs to a different approval")

    _patch(monkeypatch, bank_command, "open_session", wrong_state)

    assert main(["bank", "connect"], context=_context([PASTED])) == 1

    assert "different approval" in capsys.readouterr().err and calls["link"] == []


def test_connect_reports_an_error_of_the_bank(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refused(*_: Any, **__: Any) -> BankSession:
        raise BankApiError(422, "CODE_USED", "the code was used")

    _patch_connect(monkeypatch)
    _patch(monkeypatch, bank_command, "open_session", refused)

    assert main(["bank", "connect"], context=_context([PASTED])) == 1
    assert "422" in capsys.readouterr().err


# --- bank fetch -------------------------------------------------------------------------------


def _outcome(**changes: Any) -> FetchOutcome:
    return FetchOutcome(
        result=replace(IMPORTED, **changes.pop("result", {})),
        consent=changes.pop("consent", ConsentStatus.OK),
        days_left=changes.pop("days_left", 160),
    )


def test_a_fetch_without_a_name_takes_every_connected_account(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, bank_command, "connected_accounts", [MAIN, SAVINGS])
    calls = _patch(monkeypatch, bank_command, "fetch_for_account", _outcome())

    code = main(["bank", "fetch"], context=_context(["y"]))

    out = capsys.readouterr().out
    assert code == 0 and [c[1]["account_name"] for c in calls] == ["main", "savings"]
    assert (
        "== main ==" in out and "== savings ==" in out and out.count("Write to this database") == 0
    )


def test_a_slow_fetch_says_it_is_working_and_shows_its_progress(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fetch(*_: Any, on_page: Any, **__: Any) -> FetchOutcome:
        on_page(1, 120)
        on_page(2, 250)
        return _outcome()

    _patch(monkeypatch, bank_command, "fetch_for_account", fetch)

    assert main(["bank", "fetch", "main", "--yes"], context=_context()) == 0

    out = capsys.readouterr().out
    assert "Fetching main from the bank, this can take a few minutes..." in out
    assert "page 1, 120 transactions so far" in out
    assert "page 2, 250 transactions so far" in out
    assert out.index("page 2") < out.index("Batch 7 is imported")


def test_a_fetch_with_a_name_takes_only_that_account(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def never(*_: Any) -> list[Account]:
        raise AssertionError("the list of accounts is not needed for a named one")

    _patch(monkeypatch, bank_command, "connected_accounts", never)
    calls = _patch(monkeypatch, bank_command, "fetch_for_account", _outcome())

    assert main(["bank", "fetch", "savings"], context=_context(["y"])) == 0
    assert [c[1]["account_name"] for c in calls] == ["savings"]
    assert "==" not in capsys.readouterr().out


def test_one_account_failing_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, bank_command, "connected_accounts", [MAIN, SAVINGS])

    def fetch(*_: Any, account_name: str, **__: Any) -> FetchOutcome:
        if account_name == "main":
            raise ConsentExpiredError("the consent for 'main' has ended")
        return _outcome()

    calls = _patch(monkeypatch, bank_command, "fetch_for_account", fetch)

    assert main(["bank", "fetch", "--yes"], context=_context()) == 1

    captured = capsys.readouterr()
    assert len(calls) == 2 and "renew it with: expensior bank connect" in captured.err
    assert "Batch 7 is imported" in captured.out


def test_a_fetch_with_nothing_connected_says_how_to_connect(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, bank_command, "connected_accounts", [])

    assert main(["bank", "fetch"], context=_context()) == 1
    assert "no account is connected" in capsys.readouterr().err


def test_a_dry_run_fetch_does_not_ask_and_passes_the_options(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dry = _outcome(result={"dry_run": True, "batch_id": None, "status": None})
    calls = _patch(monkeypatch, bank_command, "fetch_for_account", dry)

    code = main(
        ["bank", "fetch", "main", "--dry-run", "--since", "2026-11-01", "--on-conflict", "replace"],
        context=_context(),
    )

    options = calls[0][1]
    assert code == 0 and options["dry_run"] is True
    assert options["date_from"] == date(2026, 11, 1) and options["policy"] is ConflictPolicy.REPLACE
    assert "Dry run, nothing written" in capsys.readouterr().out


def test_declining_a_fetch_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch(monkeypatch, bank_command, "fetch_for_account", _outcome())

    assert main(["bank", "fetch", "main"], context=_context(["n"])) == 1
    assert calls == []


def test_a_consent_near_its_end_is_a_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(
        monkeypatch,
        bank_command,
        "fetch_for_account",
        _outcome(consent=ConsentStatus.EXPIRING, days_left=9),
    )

    assert main(["bank", "fetch", "main", "--yes"], context=_context()) == 0
    assert "Warning: the consent ends in 9 days" in capsys.readouterr().out


def test_a_failed_import_exits_with_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(
        monkeypatch,
        bank_command,
        "fetch_for_account",
        _outcome(result={"status": ImportStatus.FAILED, "error": "boom"}),
    )

    assert main(["bank", "fetch", "main", "--yes"], context=_context()) == 1


@pytest.mark.parametrize(
    ("error", "hint"),
    [
        (ConsentExpiredError("the consent has ended"), "renew it with: expensior bank connect"),
        (NotConnectedError("not connected"), "connect it with: expensior bank connect"),
        (BankApiError(500, None, "the bank is down"), "500"),
    ],
)
def test_fetch_failures_say_what_to_do(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    hint: str,
) -> None:
    def fail(*_: Any, **__: Any) -> FetchOutcome:
        raise error

    _patch(monkeypatch, bank_command, "fetch_for_account", fail)

    assert main(["bank", "fetch", "main", "--yes"], context=_context()) == 1
    assert hint in capsys.readouterr().err


def test_fetch_without_bank_settings_says_what_to_set(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["bank", "fetch", "main"], context=_context(bank_configured=False)) == 1
    assert "ENABLE_BANKING_APP_ID" in capsys.readouterr().err


# --- the parser -------------------------------------------------------------------------------


def test_a_command_without_its_subcommand_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["accounts"], context=_context())

    assert exit_info.value.code == 2


def test_a_wrong_date_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["bank", "fetch", "main", "--since", "yesterday"], context=_context())

    assert exit_info.value.code == 2


def test_connect_takes_no_flags_about_codes_or_sessions() -> None:
    for flag in ("--code", "--session", "--bank-account"):
        with pytest.raises(SystemExit) as exit_info:
            main(["bank", "connect", flag, "x"], context=_context())
        assert exit_info.value.code == 2


def test_help_lists_the_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0

    out = capsys.readouterr().out
    assert "accounts" in out and "bank" in out

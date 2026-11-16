"""The Enable Banking client signs requests, pages through results and reports errors safely.

All HTTP goes through a mock transport; the signing key is generated here, never stored.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from expensior.bank import enable_banking
from expensior.bank.enable_banking import (
    BankApiError,
    BankConfigError,
    BankSession,
    EnableBankingClient,
)
from expensior.config import Settings

NOW = 1_800_000_000.0


@pytest.fixture(scope="module")
def keys() -> tuple[str, str]:
    """A throwaway RSA key pair as PEM text: the private key to sign with, the public to check."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private_pem, public_pem


def _client(handler: Any, private_key: str) -> EnableBankingClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return EnableBankingClient("app-id-123", private_key, http=http, clock=lambda: NOW)


def test_requests_carry_a_jwt_signed_with_the_application_key(keys: tuple[str, str]) -> None:
    private_pem, public_pem = keys
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"aspsps": []})

    _client(handler, private_pem).list_aspsps("PL")

    token = seen[0].headers["Authorization"].removeprefix("Bearer ")
    header = jwt.get_unverified_header(token)
    claims = jwt.decode(
        token,
        public_pem,
        algorithms=["RS256"],
        audience="api.enablebanking.com",
        issuer="enablebanking.com",
        options={"verify_exp": False, "verify_iat": False},
    )
    assert (header["alg"], header["kid"], header["typ"]) == ("RS256", "app-id-123", "JWT")
    assert claims["exp"] - claims["iat"] == 3600
    assert seen[0].url.params["country"] == "PL"


def test_starting_an_authorisation_sends_the_consent_request(keys: tuple[str, str]) -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200, json={"url": "https://bank.example/approve", "authorization_id": "a"}
        )

    result = _client(handler, keys[0]).start_authorisation(
        aspsp_name="PKO Bank Polski",
        country="PL",
        redirect_url="https://example.com/callback",
        valid_until=datetime(2027, 5, 1, 12, 0, tzinfo=UTC),
        state="state-1",
    )

    assert result.url == "https://bank.example/approve" and result.state == "state-1"
    assert bodies[0] == {
        "access": {"valid_until": "2027-05-01T12:00:00Z"},
        "aspsp": {"name": "PKO Bank Polski", "country": "PL"},
        "state": "state-1",
        "redirect_url": "https://example.com/callback",
        "psu_type": "personal",
    }


def test_a_session_carries_its_accounts_and_when_it_expires(keys: tuple[str, str]) -> None:
    payload = {
        "session_id": "session-1",
        "access": {"valid_until": "2027-05-01T12:00:00Z"},
        "accounts": [
            {"uid": "uid-1", "identification_hash": "hash-1", "name": "Main"},
            {"uid": "uid-2", "identification_hash": "hash-2", "name": None},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"code": "the-code"}
        return httpx.Response(200, json=payload)

    session = _client(handler, keys[0]).create_session("the-code")

    assert isinstance(session, BankSession)
    assert session.session_id == "session-1"
    assert session.valid_until == datetime(2027, 5, 1, 12, 0, tzinfo=UTC)
    assert [(a.uid, a.identification_hash) for a in session.accounts] == [
        ("uid-1", "hash-1"),
        ("uid-2", "hash-2"),
    ]


def test_transactions_are_fetched_page_by_page_with_the_longest_history_first(
    keys: tuple[str, str],
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "continuation_key" not in request.url.params:
            return httpx.Response(
                200, json={"transactions": [{"n": 1}, {"n": 2}], "continuation_key": "next"}
            )
        return httpx.Response(200, json={"transactions": [{"n": 3}], "continuation_key": None})

    transactions = _client(handler, keys[0]).fetch_transactions("uid-1")

    assert [t["n"] for t in transactions] == [1, 2, 3]
    first, second = requests
    assert first.url.path == "/accounts/uid-1/transactions"
    assert dict(first.url.params) == {"transaction_status": "BOOK", "strategy": "longest"}
    assert second.url.params["continuation_key"] == "next"


def test_a_start_date_asks_for_the_default_strategy_from_that_date(keys: tuple[str, str]) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"transactions": []})

    _client(handler, keys[0]).fetch_transactions("uid-1", date_from=date(2026, 11, 1))

    assert dict(seen[0].url.params) == {
        "transaction_status": "BOOK",
        "strategy": "default",
        "date_from": "2026-11-01",
    }


def test_an_error_carries_the_status_and_the_code_but_never_the_token(
    keys: tuple[str, str],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": "EXPIRED_SESSION", "message": "the session ended"}
        )

    with pytest.raises(BankApiError) as error:
        _client(handler, keys[0]).fetch_transactions("uid-1")

    assert (error.value.status_code, error.value.code) == (401, "EXPIRED_SESSION")
    assert "the session ended" in str(error.value)
    assert "Bearer" not in str(error.value) and "eyJ" not in str(error.value)


def test_an_error_without_a_json_body_is_still_reported(keys: tuple[str, str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    with pytest.raises(BankApiError) as error:
        _client(handler, keys[0]).list_aspsps("PL")

    assert error.value.status_code == 502 and "bad gateway" in str(error.value)


def test_endless_pagination_is_stopped(
    keys: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(enable_banking, "_MAX_PAGES", 3)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"transactions": [{}], "continuation_key": "again"})

    with pytest.raises(BankApiError, match="more than 3 pages"):
        _client(handler, keys[0]).fetch_transactions("uid-1")


def test_the_client_is_built_from_the_settings_and_the_key_file(
    keys: tuple[str, str], tmp_path: Path
) -> None:
    key_file = tmp_path / "key.pem"
    key_file.write_text(keys[0])
    settings = Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",
        enable_banking_app_id="app-id-123",
        enable_banking_key_path=key_file,
    )

    client = EnableBankingClient.from_settings(settings)

    assert isinstance(client, EnableBankingClient)


def test_missing_settings_say_what_to_set() -> None:
    settings = Settings(database_url="postgresql+psycopg://u:p@localhost/db")

    with pytest.raises(BankConfigError, match="ENABLE_BANKING_APP_ID"):
        EnableBankingClient.from_settings(settings)

"""A client for the Enable Banking API (https://enablebanking.com/docs/api/reference/).

Requests are authenticated with a JWT signed RS256 by the application's private key. The key is read
from a file outside the repository; it never appears in a message, a log or an exception here.
The HTTP client is injected, so tests give it a mock transport and never touch the network.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Self

import httpx
import jwt

from expensior.config import Settings

API_URL = "https://api.enablebanking.com"
_TOKEN_LIFETIME_SECONDS = 3600
_MAX_PAGES = 1000  # a guard against a bank that never stops returning a continuation key


class BankConfigError(RuntimeError):
    """The bank API is not configured: the application id or the key path is missing."""


class BankApiError(RuntimeError):
    """The API answered with an error: carries the status and the API's code, never the request."""

    def __init__(self, status_code: int, code: str | None, message: str) -> None:
        super().__init__(f"Enable Banking answered {status_code} {code or ''}: {message}".strip())
        self.status_code = status_code
        self.code = code


@dataclass(frozen=True)
class BankAccount:
    """An account of a session. ``uid`` is valid for the session only; the hash identifies it."""

    uid: str
    identification_hash: str | None
    name: str | None


@dataclass(frozen=True)
class Authorisation:
    """Where to send the user to approve access, and the ``state`` to expect back."""

    url: str
    state: str


@dataclass(frozen=True)
class BankSession:
    """A consent that was approved: its id, when it expires, and the accounts it covers."""

    session_id: str
    valid_until: datetime | None
    accounts: tuple[BankAccount, ...]


def _session(payload: dict[str, Any]) -> BankSession:
    valid_until = (payload.get("access") or {}).get("valid_until")
    accounts = tuple(
        BankAccount(
            uid=str(account["uid"]),
            identification_hash=account.get("identification_hash"),
            name=account.get("name"),
        )
        for account in payload.get("accounts") or []
    )
    return BankSession(
        session_id=str(payload["session_id"]),
        valid_until=datetime.fromisoformat(valid_until) if valid_until else None,
        accounts=accounts,
    )


class EnableBankingClient:
    """The calls the application needs: authorise, create a session, read transactions."""

    def __init__(
        self,
        app_id: str,
        private_key: str,
        *,
        base_url: str = API_URL,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key
        self._base_url = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=60)
        self._clock = clock

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build the client from the settings; reads the key file named there."""
        if not settings.enable_banking_app_id or not settings.enable_banking_key_path:
            raise BankConfigError(
                "set ENABLE_BANKING_APP_ID and ENABLE_BANKING_KEY_PATH to use the bank API"
            )
        key = Path(settings.enable_banking_key_path).expanduser().read_text()
        return cls(settings.enable_banking_app_id, key)

    def _token(self) -> str:
        now = int(self._clock())
        return jwt.encode(
            {
                "iss": "enablebanking.com",
                "aud": "api.enablebanking.com",
                "iat": now,
                "exp": now + _TOKEN_LIFETIME_SECONDS,
            },
            self._private_key,
            algorithm="RS256",
            headers={"typ": "JWT", "kid": self._app_id},
        )

    def _request(self, method: str, path: str, **options: Any) -> dict[str, Any]:
        response = self._http.request(
            method,
            self._base_url + path,
            headers={"Authorization": f"Bearer {self._token()}"},
            **options,
        )
        if response.status_code >= 400:
            code: str | None = None
            message = response.text[:300]
            try:
                body = response.json()
                code = body.get("error") or body.get("code")
                message = str(body.get("message") or message)[:300]
            except ValueError:
                pass
            raise BankApiError(response.status_code, code, message)
        result: dict[str, Any] = response.json()
        return result

    def list_aspsps(self, country: str) -> list[dict[str, Any]]:
        """The banks of a country, with the ids and limits the API gives for each."""
        aspsps: list[dict[str, Any]] = self._request("GET", "/aspsps", params={"country": country})[
            "aspsps"
        ]
        return aspsps

    def start_authorisation(
        self,
        *,
        aspsp_name: str,
        country: str,
        redirect_url: str,
        valid_until: datetime,
        state: str,
        psu_type: str = "personal",
    ) -> Authorisation:
        """Ask for a consent until ``valid_until``; the user approves it in the bank's app."""
        payload = self._request(
            "POST",
            "/auth",
            json={
                "access": {
                    "valid_until": valid_until.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                },
                "aspsp": {"name": aspsp_name, "country": country},
                "state": state,
                "redirect_url": redirect_url,
                "psu_type": psu_type,
            },
        )
        return Authorisation(url=str(payload["url"]), state=state)

    def create_session(self, code: str) -> BankSession:
        """Exchange the code from the redirect for a session; the code works once."""
        return _session(self._request("POST", "/sessions", json={"code": code}))

    def get_session(self, session_id: str) -> BankSession:
        """A session as it is now, with the current account ids."""
        return _session(self._request("GET", f"/sessions/{session_id}"))

    def fetch_transactions(
        self, account_uid: str, *, date_from: date | None = None
    ) -> list[dict[str, Any]]:
        """The booked transactions of an account, as the API gives them, all pages.

        Without ``date_from`` the longest available history is fetched, which is what the first
        fetch after a new consent should do: the bank may later serve only the last 90 days.
        """
        params: dict[str, str] = {"transaction_status": "BOOK"}
        if date_from is None:
            params["strategy"] = "longest"
        else:
            params["strategy"] = "default"
            params["date_from"] = date_from.isoformat()
        transactions: list[dict[str, Any]] = []
        for _ in range(_MAX_PAGES):
            page = self._request("GET", f"/accounts/{account_uid}/transactions", params=params)
            transactions.extend(page.get("transactions") or [])
            continuation_key = page.get("continuation_key")
            if not continuation_key:
                return transactions
            params["continuation_key"] = continuation_key
        raise BankApiError(0, None, f"more than {_MAX_PAGES} pages of transactions")

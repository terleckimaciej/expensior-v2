"""Reading what the bank sends the browser back with once the user has approved access.

The user pastes either the whole address from the browser's bar or only the code. Pure.
"""

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class Callback:
    """The code to exchange for a session and, when the address was pasted, its ``state``."""

    code: str
    state: str | None


def parse_callback(text: str) -> Callback:
    """The code (and state) in a pasted address, or the bare code.

    Raises ``ValueError`` for an empty paste, an address without a code, and an address in which the
    bank reports an error.
    """
    value = text.strip()
    if not value:
        raise ValueError("nothing was pasted")
    looks_like_address = "://" in value or "?" in value or "code=" in value
    if not looks_like_address:
        return Callback(code=value, state=None)
    query = parse_qs(urlparse(value).query) or parse_qs(value.lstrip("?"))
    if "error" in query:
        raise ValueError(f"the bank reported an error: {query['error'][0]}")
    codes = query.get("code")
    if not codes or not codes[0]:
        raise ValueError("the pasted address has no code")
    states = query.get("state")
    return Callback(code=codes[0], state=states[0] if states else None)

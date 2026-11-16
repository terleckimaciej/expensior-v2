"""What the user pastes after approving access: the whole address, or just the code."""

import pytest

from expensior.domain.callback import Callback, parse_callback


def test_the_code_and_the_state_are_read_from_the_address() -> None:
    pasted = "https://example.com/callback?state=abc123&code=9c22cb46-3a76"

    assert parse_callback(pasted) == Callback(code="9c22cb46-3a76", state="abc123")


def test_the_order_of_the_parameters_does_not_matter() -> None:
    pasted = "https://example.com/callback?code=the-code&state=abc"

    assert parse_callback(pasted) == Callback(code="the-code", state="abc")


def test_a_bare_code_is_accepted_but_has_no_state() -> None:
    assert parse_callback("  9c22cb46-3a76  ") == Callback(code="9c22cb46-3a76", state=None)


def test_only_the_query_part_is_accepted_too() -> None:
    assert parse_callback("?state=abc&code=the-code") == Callback(code="the-code", state="abc")


def test_an_address_without_a_state_gives_none() -> None:
    assert parse_callback("https://example.com/cb?code=the-code").state is None


@pytest.mark.parametrize(
    ("pasted", "message"),
    [
        ("", "nothing was pasted"),
        ("   ", "nothing was pasted"),
        ("https://example.com/callback", "no code"),
        ("https://example.com/callback?state=abc", "no code"),
        ("https://example.com/callback?error=access_denied&state=abc", "access_denied"),
    ],
)
def test_what_cannot_be_used_says_why(pasted: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_callback(pasted)

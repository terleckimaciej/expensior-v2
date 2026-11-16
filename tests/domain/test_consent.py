"""The consent status follows how many days are left, and warns before the end."""

from datetime import UTC, datetime, timedelta

import pytest

from expensior.domain.consent import ConsentStatus, consent_status, days_left

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def test_an_account_that_was_never_connected_has_no_consent() -> None:
    assert consent_status(None, NOW) is ConsentStatus.NONE


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (170, ConsentStatus.OK),
        (15, ConsentStatus.OK),
        (14, ConsentStatus.EXPIRING),
        (1, ConsentStatus.EXPIRING),
    ],
)
def test_a_valid_consent_is_ok_until_the_last_two_weeks(days: int, expected: ConsentStatus) -> None:
    assert consent_status(NOW + timedelta(days=days, hours=1), NOW) is expected


def test_a_consent_that_has_ended_is_expired() -> None:
    assert consent_status(NOW - timedelta(days=1), NOW) is ConsentStatus.EXPIRED
    assert consent_status(NOW, NOW) is ConsentStatus.EXPIRED


def test_days_left_is_negative_after_the_end() -> None:
    assert days_left(NOW + timedelta(days=10, hours=2), NOW) == 10
    assert days_left(NOW - timedelta(days=3), NOW) == -3


def test_the_warning_period_can_be_changed() -> None:
    soon = NOW + timedelta(days=30, hours=1)

    assert consent_status(soon, NOW, warn_days=45) is ConsentStatus.EXPIRING
    assert consent_status(soon, NOW) is ConsentStatus.OK

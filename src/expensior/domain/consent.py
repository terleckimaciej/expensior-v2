"""Whether the consent for reading a bank account still holds (ADR 0011).

A consent lasts up to 180 days and is renewed by approving access again in the bank's app, so the
application warns before it ends. Pure: the caller passes the dates.
"""

from datetime import datetime
from enum import StrEnum

WARN_DAYS = 14


class ConsentStatus(StrEnum):
    """Where an account's consent stands."""

    NONE = "none"  # the account was never connected to the bank API
    OK = "ok"
    EXPIRING = "expiring"  # still valid, but it ends soon
    EXPIRED = "expired"


def days_left(valid_until: datetime, now: datetime) -> int:
    """Whole days until the consent ends; negative once it has ended."""
    return (valid_until - now).days


def consent_status(
    valid_until: datetime | None, now: datetime, warn_days: int = WARN_DAYS
) -> ConsentStatus:
    """The status of a consent that ends at ``valid_until`` (``None``: never connected)."""
    if valid_until is None:
        return ConsentStatus.NONE
    if valid_until <= now:
        return ConsentStatus.EXPIRED
    if days_left(valid_until, now) <= warn_days:
        return ConsentStatus.EXPIRING
    return ConsentStatus.OK

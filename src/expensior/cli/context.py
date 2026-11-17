"""What a command needs from outside: the runtime, the user's answers and the clock.

Tests pass their own context, so a command is tried without a database, a terminal or the real
time. The runtime is built only when a command asks for it: ``--help`` needs no configuration.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from expensior.services.runtime import Runtime, build_runtime


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Context:
    """The runtime factory, how to ask the user, and the clock."""

    runtime: Callable[[], Runtime] = build_runtime
    ask: Callable[[str], str] = input
    now: Callable[[], datetime] = field(default=_utc_now)

"""The confirmation every command that writes to a database asks for (AGENTS.md).

It names the database host first, so a command never writes somewhere the user did not expect;
``--yes`` skips the question but still prints the host.
"""

from collections.abc import Callable


def confirm(host: str, *, assume_yes: bool, ask: Callable[[str], str] = input) -> bool:
    """Print the target host and ask; anything but ``y`` or ``yes`` is a no."""
    print(f"Target database host: {host}")
    if assume_yes:
        return True
    return ask("Write to this database? [y/N] ").strip().lower() in {"y", "yes"}

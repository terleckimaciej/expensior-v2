"""The ``expensior`` command-line entry point (declared in ``pyproject.toml``)."""

import argparse
from collections.abc import Sequence

from expensior import __version__
from expensior.cli import accounts, bank, batches, import_file
from expensior.cli.context import Context


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser; commands are added to it as the stages that need them land."""
    parser = argparse.ArgumentParser(
        prog="expensior",
        description="Import bank statements, classify transactions, see where the money goes.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    accounts.register(commands)
    bank.register(commands)
    import_file.register(commands)
    batches.register(commands)
    return parser


def main(argv: Sequence[str] | None = None, *, context: Context | None = None) -> int:
    """Run the CLI and return the process exit code.

    Args:
        argv: Arguments without the program name; ``None`` means ``sys.argv[1:]``.
        context: The runtime, the way to ask the user and the clock; tests pass their own.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return int(handler(args, context or Context()))

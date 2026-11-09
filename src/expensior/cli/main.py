"""The ``expensior`` command-line entry point (declared in ``pyproject.toml``)."""

import argparse
from collections.abc import Sequence

from expensior import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser; commands are added to it as the stages that need them land."""
    parser = argparse.ArgumentParser(
        prog="expensior",
        description="Import bank statements, classify transactions, see where the money goes.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code.

    Args:
        argv: Arguments without the program name; ``None`` means ``sys.argv[1:]``.
    """
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0

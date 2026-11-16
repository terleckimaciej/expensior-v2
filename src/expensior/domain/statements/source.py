"""A source of statements: how to read its bytes into raw rows and how to adapt them (ADR 0007).

The import service knows nothing about a format. It asks the registry for the source that
recognises the bytes and calls its two functions, so a bank API is one more source, not a second
design.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from expensior.domain.statements.adapted import AdaptedStatement
from expensior.domain.statements.formats import Unrecognised
from expensior.domain.statements.raw import RawBatch, RawRow


@dataclass(frozen=True)
class Source:
    """A format the import understands.

    ``read`` turns the stored bytes into a header and raw rows, or says it is not this format.
    ``adapt`` turns raw rows into transactions of an account, given the account and batch ids.
    """

    source: str
    version: str
    read: Callable[[bytes], RawBatch | Unrecognised]
    adapt: Callable[[Iterable[RawRow], int, int], AdaptedStatement]

"""Bytes to text: the one place that knows the encodings of the exports (ADR 0007).

Decoding happens here, when the bytes are read, because once text sits in a column the encoding can
no longer be told apart. The original bytes are never altered; fixing the decoder means reprocessing
the stored batch.
"""

from dataclasses import dataclass


class DecodingError(ValueError):
    """The bytes are in none of the supported encodings."""


@dataclass(frozen=True)
class DecodedText:
    """The text of a file and the encoding it was read with."""

    text: str
    encoding: str


def decode(data: bytes) -> DecodedText:
    """Read the bytes as UTF-8 (with or without a BOM), or else as cp1250, the PKO BP export.

    UTF-8 goes first and strictly: text in cp1250 that holds a Polish letter is almost never valid
    UTF-8, so a file that decodes as UTF-8 really is UTF-8.
    """
    try:
        return DecodedText(text=data.decode("utf-8-sig"), encoding="utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return DecodedText(text=data.decode("cp1250"), encoding="cp1250")
    except UnicodeDecodeError as error:
        raise DecodingError("the bytes are neither UTF-8 nor cp1250") from error

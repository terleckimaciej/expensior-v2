"""Reading dates and amounts the way the sources write them; shared by the adapters.

Both raise ``ValueError`` with a message that says what was wrong, so an adapter can report the row
instead of failing the whole import.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

_CENT = Decimal("0.01")


def parse_date(value: object) -> date:
    """An ISO date (``2026-01-15``)."""
    return date.fromisoformat(str(value).strip())


def parse_money(value: object) -> Decimal:
    """An amount: a sign, spaces, a point or a comma; at most two decimal places.

    Never a float: the text is read by ``Decimal`` directly.
    """
    text = str(value)
    cleaned = text.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        amount = Decimal(cleaned)
        if not amount.is_finite() or amount != amount.quantize(_CENT):
            raise ValueError(f"not an amount with at most two decimals: {text!r}")
    except InvalidOperation as error:
        raise ValueError(f"not an amount: {text!r}") from error
    return amount

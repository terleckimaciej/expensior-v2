"""The vocabulary of ``transaction_type`` and the lookup from the PKO BP CSV (ADR 0007).

The canonical names are those of legacy expensior, so the rules that already name a type keep
working (a rule's conditions can list types). Spellings with lost letters, which come from a file
that was read in the wrong encoding, are listed as variants: the letters cannot be restored, so a
lookup is the way.
"""

# A hold is not a transaction: the same payment arrives later as a booked row.
HOLD_TYPE = "Blokada"

_PKO_CSV_TYPES: dict[str, str] = {
    "Płatność kartą": "card_payment",
    "Płatnoć kartš": "card_payment",
    "Zakup w terminalu - kod mobilny": "terminal_payment_blik",
    "Autooszczędzanie": "auto_savings",
    "Płatność web - kod mobilny": "web_payment_blik",
    "Płatnoć web - kod mobilny": "web_payment_blik",
    "Przelew na telefon przychodz. zew.": "transfer_blik",
    "Przelew na telefon przychodz. wew.": "transfer_blik",
    "Przelew na konto": "transfer_to_account",
    "Przelew z rachunku": "transfer_from_account",
    "Opłata za użytkowanie karty": "card_fee",
    "Zwrot w terminalu": "refund",
    "Zwrot płatności kartą": "refund",
    "Zwrot płatnoci kartš": "refund",
    "Zlecenie stałe": "standing_order",
    "Wypłata z bankomatu": "atm_withdrawal",
    "Wypłata w bankomacie - kod mobilny": "atm_withdrawal",
    "Wypłata w bankomacie - czek": "atm_withdrawal",
    "Obciążenie": "pko_charge",
    "Obcišżenie": "pko_charge",
    "Uznanie": "pko_credit",
    "Naliczenie odsetek": "interest_accrued",
    # Seen in a real export, not in legacy.
    "TRANSPORT_TICKET_PAYMENT": "transport_ticket_payment",
    "WYMIANA W KANTORZE - OBCIĄŻENIE": "currency_exchange_debit",
}


def normalise_pko_csv_type(csv_type: str) -> str | None:
    """The canonical name of a type from the CSV, or ``None`` when it is not known.

    The caller keeps the original text of an unknown type and reports it, instead of failing.
    """
    return _PKO_CSV_TYPES.get(csv_type.strip())

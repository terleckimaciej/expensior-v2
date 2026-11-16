"""Synthetic PKO BP statements for tests: the shape of the real export, invented content.

Nothing here comes from a real account (AGENTS.md): names, addresses and account numbers are
invented.
"""

HEADER = (
    '"Data operacji","Data waluty","Typ transakcji","Kwota","Waluta","Saldo po transakcji",'
    '"Opis transakcji","","","","","",""'
)

CARD = (
    '"2026-01-15","2026-01-15","Płatność kartą","-12.34","PLN","+100.00",'
    '"Tytuł: 000000000000000000000001  ",'
    '"Lokalizacja: Adres: SKLEP PRZYKŁAD Miasto: WARSZAWA Kraj: POLSKA","","","","",""'
)

TRANSFER = (
    '"2026-01-16","2026-01-16","Przelew na konto","+1700.00","PLN","+1800.00",'
    '"Rachunek nadawcy: 00 0000 0000 0000 0000 0000 0000","Nazwa nadawcy: JAN KOWALSKI",'
    '"Adres nadawcy: 00-000 MIASTO","Tytuł: Czynsz za wrzesień","","",""'
)

HOLD = (
    '"","2026-01-17","Blokada","-5.00","PLN","W rozliczeniu",'
    '"Tytuł: 000000000000000000000002  ",'
    '"Lokalizacja: Adres: KAWIARNIA Miasto: KRAKÓW Kraj: POLSKA","","","","",""'
)

CSV_TEXT = "\n".join([HEADER, CARD, TRANSFER, HOLD]) + "\n"

# What the bank sends: the same text encoded as cp1250.
CSV_CP1250 = CSV_TEXT.encode("cp1250")

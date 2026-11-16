"""The adapter on the owner's real data, run locally; skipped when no file is named.

Set ``EXPENSIOR_REAL_API_RESPONSE`` to a saved response (``{"transactions": [...]}``) and,
optionally, ``EXPENSIOR_REAL_CSV`` to a PKO BP export. Only properties are checked, nothing is
printed, and no real data ever enters the repository or CI (AGENTS.md).
"""

import json
import os
from pathlib import Path

import pytest

from expensior.domain.statements.adapted import AdaptedStatement
from expensior.domain.statements.decoding import decode
from expensior.domain.statements.enable_banking import (
    adapt_rows,
    make_document,
    read_enable_banking,
)
from expensior.domain.statements.pko_csv import adapt_rows as adapt_csv_rows
from expensior.domain.statements.raw import RawBatch, parse_raw

API_PATH = os.environ.get("EXPENSIOR_REAL_API_RESPONSE")
CSV_PATH = os.environ.get("EXPENSIOR_REAL_CSV")

pytestmark = pytest.mark.skipif(not API_PATH, reason="EXPENSIOR_REAL_API_RESPONSE is not set")


def _adapted() -> AdaptedStatement:
    assert API_PATH
    transactions = json.loads(Path(API_PATH).read_text(encoding="utf-8"))["transactions"]
    document = make_document(transactions, fetched_at="local", identification_hash=None)
    batch = read_enable_banking(document)
    assert isinstance(batch, RawBatch)
    return adapt_rows(batch.rows, account_id=1, batch_id=1)


def test_every_real_transaction_is_read_with_a_known_type() -> None:
    adapted = _adapted()

    assert adapted.invalid == ()
    assert adapted.unknown_types == {}
    assert adapted.holds == 0
    assert len(adapted.transactions) > 0


def test_the_ids_of_the_real_transactions_are_distinct() -> None:
    adapted = _adapted()

    ids = [transaction.transaction_id for transaction in adapted.transactions]
    assert len(ids) == len(set(ids))


@pytest.mark.skipif(not CSV_PATH, reason="EXPENSIOR_REAL_CSV is not set")
def test_every_real_csv_transaction_is_also_in_the_api_data() -> None:
    assert CSV_PATH
    csv_batch = parse_raw(decode(Path(CSV_PATH).read_bytes()).text)
    from_csv = adapt_csv_rows(csv_batch.rows, account_id=1, batch_id=1)

    api_ids = {t.transaction_id for t in _adapted().transactions}

    missing = [t for t in from_csv.transactions if t.transaction_id not in api_ids]
    assert missing == []

"""The domain enumerations and the CHECK constraints of the schema list the same values."""

import re
from enum import StrEnum

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from expensior.domain.types import ClassificationMethod, ImportStatus, MatchType

pytestmark = pytest.mark.db

CASES: list[tuple[str, type[StrEnum]]] = [
    ("ck_import_batches_status_valid", ImportStatus),
    ("ck_classifications_method_valid", ClassificationMethod),
    ("ck_transaction_flags_method_valid", ClassificationMethod),
    ("ck_rules_match_type_valid", MatchType),
]


@pytest.mark.parametrize(("constraint", "enum"), CASES)
def test_enum_matches_check_constraint(
    db_session: Session, constraint: str, enum: type[StrEnum]
) -> None:
    definition = db_session.execute(
        text("select pg_get_constraintdef(oid) from pg_constraint where conname = :name"),
        {"name": constraint},
    ).scalar_one()

    in_database = set(re.findall(r"'([a-z_]+)'", definition))

    assert in_database == {member.value for member in enum}

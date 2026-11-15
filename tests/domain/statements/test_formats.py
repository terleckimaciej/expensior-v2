"""A format is recognised from the header; anything else is a result, not an exception."""

from expensior.domain.statements.formats import PKO_BP_V1, Unrecognised, detect_format

NAMED = list(PKO_BP_V1.signature)


def test_the_pko_header_is_recognised() -> None:
    assert detect_format(NAMED) is PKO_BP_V1


def test_the_unnamed_columns_after_the_signature_do_not_matter() -> None:
    assert detect_format([*NAMED, "", "", "", "", "", ""]) is PKO_BP_V1


def test_spaces_around_a_name_do_not_matter() -> None:
    assert detect_format([f" {name} " for name in NAMED]) is PKO_BP_V1


def test_an_unknown_header_is_unrecognised_and_keeps_what_was_seen() -> None:
    result = detect_format(["Date", "Amount", "Description"])

    assert result == Unrecognised(header=("Date", "Amount", "Description"))


def test_an_empty_header_is_unrecognised() -> None:
    assert detect_format([]) == Unrecognised(header=())


def test_the_columns_must_come_in_the_known_order() -> None:
    reordered = [NAMED[1], NAMED[0], *NAMED[2:]]

    assert isinstance(detect_format(reordered), Unrecognised)

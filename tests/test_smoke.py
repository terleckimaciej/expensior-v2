"""Smoke test: the installed package imports and knows its version."""

import expensior


def test_package_has_a_version() -> None:
    assert expensior.__version__

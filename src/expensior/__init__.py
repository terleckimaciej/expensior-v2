"""expensior: import bank statements, classify transactions, see where the money goes.

The package is split into layers with one-way dependencies (ADR 0009):
``cli`` / ``ui`` -> ``services`` -> ``db`` -> ``domain``. The root holds no logic.
"""

from importlib.metadata import version

__version__ = version("expensior")

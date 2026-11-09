"""Use cases: import, undo, reprocess, classify, reclassify, dashboard queries.

The only layer that opens a database transaction (through the unit of work). Imports ``domain``
and ``db``; never ``cli`` or ``ui`` (ADR 0009).
"""

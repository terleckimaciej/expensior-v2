"""Persistence: SQLAlchemy models, repositories, queries on the SQL views, the unit of work.

May import ``domain`` and ``config``; never ``services``, ``cli`` or ``ui`` (ADR 0009).
Repositories never commit: only ``services`` open and close transactions.
"""

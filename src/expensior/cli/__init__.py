"""Command-line entry point: argument parsing and output formatting only.

Talks to ``services``, and uses ``domain`` for read models and types; never imports ``db``
(ADR 0009).
"""

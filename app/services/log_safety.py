"""Helpers for safely logging values that originate from user input."""
from __future__ import annotations


def sanitize_for_log(value: object) -> str:
    """Strip CR/LF from a value before it's interpolated into a log message.

    Prevents log forging: without this, a value like "AAPL\\nFAKE ADMIN LOGIN"
    could inject a fabricated line into the log stream.
    """
    return str(value).replace("\r", "").replace("\n", "")

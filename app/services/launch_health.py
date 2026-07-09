"""Consecutive-failed-launch tracking, to proactively offer a rollback.

The desktop shell records a launch attempt before starting the server and marks
the launch healthy once the app is up. A launch that dies before that leaves the
counter incremented. After enough consecutive failures *and* with a rollback
point available, the app offers to restore the previous version — the safety net
for an update that won't run.

State is a tiny counter file in the data dir so it survives a crash (a
process-memory counter wouldn't). Everything is best-effort: a health-tracking
failure must never itself block the app.
"""
from __future__ import annotations

import logging

from app import paths

logger = logging.getLogger(__name__)

_COUNTER_FILE = "launch-health.txt"
OFFER_THRESHOLD = 2


def _counter_path():
    return paths.data_dir() / _COUNTER_FILE


def record_launch_attempt() -> int:
    """Increment and return the consecutive-failed-launch counter."""
    path = _counter_path()
    try:
        current = int(path.read_text(encoding="utf-8").strip()) if path.exists() else 0
    except (ValueError, OSError):
        current = 0
    current += 1
    try:
        path.write_text(str(current), encoding="utf-8")
    except OSError as exc:
        logger.debug("Could not persist launch counter: %s", type(exc).__name__)
    return current


def mark_launch_healthy() -> None:
    """Reset the counter once the app has started successfully."""
    try:
        path = _counter_path()
        if path.exists():
            path.unlink()
    except OSError as exc:
        logger.debug("Could not clear launch counter: %s", type(exc).__name__)


def failed_launch_count() -> int:
    path = _counter_path()
    try:
        return int(path.read_text(encoding="utf-8").strip()) if path.exists() else 0
    except (ValueError, OSError):
        return 0


def should_offer_rollback() -> bool:
    """True when consecutive failures crossed the threshold and rollback exists."""
    if failed_launch_count() < OFFER_THRESHOLD:
        return False
    try:
        from app import app_settings

        return bool(app_settings.load_settings().get("rollback_point"))
    except Exception:  # pylint: disable=broad-except
        return False

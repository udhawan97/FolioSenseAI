"""Filesystem locations that differ between a source checkout and a frozen app.

When FolioSenseAI runs from source, resources (``static/``, ``templates/``) and
writable data (``database/``, ``.env``) all live at the repo root, exactly as
before. When it runs as a PyInstaller-frozen desktop app, read-only resources
are unpacked into a temporary bundle directory while writable data must live in
the per-user application-data directory — an installed app must never write
inside its own install location (``/Applications/...`` or ``Program Files``).

This module depends only on the standard library plus ``platformdirs`` (already
a project dependency), so it is safe to import from ``config`` and ``database``
without creating an import cycle.
"""

import sys
from pathlib import Path

APP_NAME = "FolioSenseAI"


def is_frozen() -> bool:
    """True when running inside a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Directory holding bundled read-only resources (``static/``, ``templates/``).

    Frozen: PyInstaller unpacks ``datas`` under ``sys._MEIPASS``.
    Source: the repo root, one level above this ``app/`` package.
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Writable directory for the database and ``.env``.

    Frozen: the OS per-user data directory (created on first run).
    Source: the repo root, so source runs keep writing ``./database`` and
    ``./.env`` exactly as they always have.
    """
    if is_frozen():
        from platformdirs import user_data_dir

        directory = Path(user_data_dir(APP_NAME, APP_NAME))
    else:
        directory = Path(__file__).resolve().parent.parent
    directory.mkdir(parents=True, exist_ok=True)
    return directory

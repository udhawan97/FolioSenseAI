"""Orchestrates the download → verify → ready → install lifecycle.

Runs the download on a background thread, drives the shared update state machine
(see :mod:`app.services.update_service`), verifies the package's SHA-256 before it
is ever considered installable, and — on an explicit user click — hands the
verified installer off to the OS:

* Windows: run the per-user Inno installer silently; it closes the running app,
  updates in place, and relaunches (see ``packaging/windows/installer.iss``).
* macOS: open the verified DMG for the user to drag into Applications (an
  unsigned ``.app`` is not swapped in place in this phase).

The pre-update backup and previous-version archiving are wired into this flow in
the next phase; the ``backing_up`` state is reserved for it. Nothing here runs
without the user first pressing Update Now / Quit & Install.
"""
from __future__ import annotations

import logging
import subprocess  # noqa: S404 (used only to launch the verified, pinned installer)
import threading

from app.services import update_downloader, update_service
from app.services.update_service import UpdateStatus

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cancel = threading.Event()
# Mutable runtime handles kept in a dict so they can be reassigned without
# module-level `global` statements: the download thread, the verified package
# path, and the desktop shell's app-quit callback.
_rt: dict = {"thread": None, "path": None, "exit_hook": None}


def register_exit_hook(func) -> None:
    """Let the desktop shell provide a callable that quits the app on install."""
    _rt["exit_hook"] = func


def start_download() -> dict:
    """Begin downloading the available update on a background thread."""
    with _lock:
        state = update_service.get_state()
        info = state.get("available")
        if state.get("status") != "available" or not info:
            return state
        if not info.get("download_url") or not info.get("asset_name"):
            return update_service.mark(
                UpdateStatus.ERROR, error="No installer is available for this platform."
            )
        if _rt["thread"] and _rt["thread"].is_alive():
            return state
        _cancel.clear()
        _rt["thread"] = threading.Thread(
            target=_run, args=(info,), name="update-download", daemon=True
        )
        _rt["thread"].start()
        return update_service.mark(
            UpdateStatus.DOWNLOADING,
            downloaded_bytes=0,
            total_bytes=info.get("size_bytes") or 0,
        )


def _run(info: dict) -> None:
    fallback_total = info.get("size_bytes") or 0
    try:
        dest = update_downloader.pending_dir() / info["asset_name"]

        def on_progress(done, total):
            update_service.mark(
                UpdateStatus.DOWNLOADING,
                downloaded_bytes=done,
                total_bytes=total or fallback_total,
            )

        update_downloader.download_update(
            info["download_url"], dest, on_progress=on_progress, should_cancel=_cancel.is_set
        )

        update_service.mark(UpdateStatus.VERIFYING)
        sums = update_downloader.fetch_text(info["sha256_url"]) if info.get("sha256_url") else ""
        if not update_downloader.verify_download(dest, sums, info["asset_name"]):
            _safe_unlink(dest)
            update_service.mark(
                UpdateStatus.ERROR,
                error="The download couldn't be verified and was discarded.",
            )
            return

        _rt["path"] = dest
        update_service.mark(UpdateStatus.READY)
        logger.info("Update %s downloaded and verified; ready to install", info.get("version"))
    except update_downloader.DownloadCancelled:
        # Keep the partial file for a later resume; return to the available state.
        update_service.mark(UpdateStatus.AVAILABLE)
    except update_downloader.DownloadError:
        update_service.mark(UpdateStatus.ERROR, error="The download didn't complete.")
    except Exception:  # pylint: disable=broad-except
        logger.exception("Unexpected error during update download")
        update_service.mark(UpdateStatus.ERROR, error="The update didn't complete.")


def cancel_download() -> dict:
    """Signal the running download to stop; the partial file is kept."""
    _cancel.set()
    return update_service.get_state()


def install() -> dict:
    """Hand the verified installer to the OS and quit the app (if ready)."""
    with _lock:
        state = update_service.get_state()
        if state.get("status") != "ready" or _rt["path"] is None:
            return state
        try:
            _launch_installer(_rt["path"])
        except Exception:  # pylint: disable=broad-except
            logger.exception("Failed to launch installer")
            return update_service.mark(
                UpdateStatus.ERROR, error="Couldn't start the installer."
            )
        update_service.mark(UpdateStatus.INSTALLING)

    # Quit shortly after so the HTTP response flushes and the installer can
    # replace files that the running app would otherwise hold open.
    if _rt["exit_hook"]:
        threading.Timer(1.0, _rt["exit_hook"]).start()
    return update_service.get_state()


def _launch_installer(path) -> None:
    platform = update_service.current_platform_key()
    if platform == "windows":
        # Per-user, silent; installer closes the app and relaunches it. Detached
        # on purpose (we quit right after), so no `with` context.
        subprocess.Popen(  # noqa: S603  pylint: disable=consider-using-with
            [str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], close_fds=True
        )
    elif platform == "macos":
        subprocess.Popen(["open", str(path)])  # noqa: S603,S607  pylint: disable=consider-using-with
    else:
        raise RuntimeError("In-app install is not supported on this platform")


def _safe_unlink(path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _reset_for_tests() -> None:
    _cancel.clear()
    _rt.update({"thread": None, "path": None, "exit_hook": None})

"""Download → verify → ready orchestration and the OS install handoff.

The downloader functions are stubbed so the state-machine flow is exercised
without the network; subprocess and the exit hook are stubbed so the handoff is
asserted without launching anything or quitting the process.
"""
from pathlib import Path

import pytest

from app import paths
from app.services import update_downloader, update_installer, update_service
from app.services.update_service import UpdateStatus


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    update_service._reset_for_tests()
    update_installer._reset_for_tests()
    yield
    update_service._reset_for_tests()
    update_installer._reset_for_tests()


def _info():
    return {
        "version": "4.4.0",
        "asset_name": "FolioSenseAI-macOS-arm64-v4.4.0.dmg",
        "download_url": "https://github.com/x/releases/download/v4.4.0/app.dmg",
        "sha256_url": "https://github.com/x/releases/download/v4.4.0/SHA256SUMS.txt",
        "size_bytes": 4,
    }


def _stub_download(monkeypatch, contents=b"data"):
    def fake_dl(url, dest, on_progress=None, should_cancel=None):
        Path(dest).write_bytes(contents)
        if on_progress:
            on_progress(len(contents), len(contents))
        return Path(dest)

    monkeypatch.setattr(update_downloader, "download_update", fake_dl)
    monkeypatch.setattr(update_downloader, "fetch_text", lambda url: "sums-text")


def test_run_success_reaches_ready(monkeypatch):
    _stub_download(monkeypatch)
    monkeypatch.setattr(update_downloader, "verify_download", lambda p, s, f: True)

    update_installer._run(_info())

    assert update_service.get_state()["status"] == "ready"
    assert update_installer._rt["path"] is not None
    assert update_installer._rt["path"].exists()


def test_run_verify_failure_discards_and_errors(monkeypatch):
    _stub_download(monkeypatch)
    monkeypatch.setattr(update_downloader, "verify_download", lambda p, s, f: False)

    update_installer._run(_info())

    st = update_service.get_state()
    assert st["status"] == "error"
    assert update_installer._rt["path"] is None
    # The unverified file was removed.
    assert not (update_downloader.pending_dir() / _info()["asset_name"]).exists()


def test_run_cancel_returns_to_available(monkeypatch):
    def cancel_dl(url, dest, on_progress=None, should_cancel=None):
        raise update_downloader.DownloadCancelled()

    monkeypatch.setattr(update_downloader, "download_update", cancel_dl)
    update_installer._run(_info())
    assert update_service.get_state()["status"] == "available"


def test_launch_installer_windows_is_silent(monkeypatch):
    calls = []
    monkeypatch.setattr(update_installer.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(update_service, "current_platform_key", lambda: "windows")

    update_installer._launch_installer(Path("C:/x/Setup.exe"))

    args = calls[0][0][0]
    assert "/VERYSILENT" in args and "/SUPPRESSMSGBOXES" in args


def test_launch_installer_macos_opens_dmg(monkeypatch):
    calls = []
    monkeypatch.setattr(update_installer.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(update_service, "current_platform_key", lambda: "macos")

    update_installer._launch_installer(Path("/x/app.dmg"))

    assert calls[0][0][0][0] == "open"


def test_install_requires_ready_state():
    # Idle → nothing happens.
    assert update_installer.install()["status"] != "installing"


def test_install_launches_and_schedules_exit(monkeypatch):
    update_service.mark(UpdateStatus.READY)
    update_installer._rt["path"] = Path("/x/Setup.exe")

    launched = {}
    monkeypatch.setattr(update_installer, "_launch_installer", lambda p: launched.setdefault("p", p))

    fired = {}

    class FakeTimer:
        def __init__(self, delay, func):
            fired["func"] = func

        def start(self):
            fired["started"] = True

    monkeypatch.setattr(update_installer.threading, "Timer", FakeTimer)
    quit_calls = []
    update_installer.register_exit_hook(lambda: quit_calls.append(1))

    st = update_installer.install()

    assert st["status"] == "installing"
    assert launched["p"] == Path("/x/Setup.exe")
    assert fired["started"] is True
    # The scheduled callback is the registered exit hook.
    fired["func"]()
    assert quit_calls == [1]

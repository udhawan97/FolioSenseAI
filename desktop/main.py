"""Desktop entry point for the packaged FolioSenseAI app.

Runs the existing FastAPI application in-process on a loopback port and shows it
in a native window (WKWebView on macOS, WebView2 on Windows) via pywebview.
Closing the window shuts the server down. This is the target frozen by
PyInstaller — the browser-launching ``run.py`` remains the source/dev entry.

Run with ``--smoke`` to boot the server, confirm ``/health``, print the version,
and exit 0. CI uses this on the frozen binary to prove the bundle actually
starts before an installer is ever published.
"""

import os
import socket
import sys
import threading
import time
import urllib.request

# When run from a source checkout (python desktop/main.py), the repo root isn't
# on sys.path, so the `app` package can't be imported. A frozen build gets its
# path set up by PyInstaller, so only patch this in the non-frozen case.
if not getattr(sys, "frozen", False):
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)

HOST = "127.0.0.1"
PREFERRED_PORT = 8000
HEALTH_TIMEOUT_SECONDS = 40.0


def _find_free_port(preferred: int) -> int:
    """Return the preferred port if free, otherwise an OS-assigned free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((HOST, preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def _wait_for_health(base_url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # pylint: disable=broad-except
            time.sleep(0.25)
    return False


def _run_server(port: int) -> None:
    # Imported lazily and inside the thread so the CORS origin below is already
    # set in the environment before app.config builds its settings singleton.
    import uvicorn
    from app.main import app

    uvicorn.run(app, host=HOST, port=port, log_level="warning")


def main() -> int:
    smoke = "--smoke" in sys.argv
    port = _find_free_port(PREFERRED_PORT)
    base_url = f"http://{HOST}:{port}"

    # The window's origin must be allowed by CORS. Set this before the server
    # thread imports app.main (which reads CORS_ALLOWED_ORIGINS at import time).
    os.environ["CORS_ALLOWED_ORIGINS"] = f"http://127.0.0.1:{port},http://localhost:{port}"

    threading.Thread(target=_run_server, args=(port,), daemon=True).start()

    if not _wait_for_health(base_url, HEALTH_TIMEOUT_SECONDS):
        print("FolioSenseAI failed to start within the timeout.", file=sys.stderr)
        return 1

    if smoke:
        from app.version import __version__

        print(f"FolioSenseAI {__version__} started and healthy at {base_url}")
        return 0

    import webview

    webview.create_window(
        "FolioSenseAI",
        base_url,
        width=1440,
        height=920,
        min_size=(1024, 720),
    )
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

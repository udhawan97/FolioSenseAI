"""Shipped portfolio-switcher interaction wiring.

The desktop app runs inside WKWebView, so portfolio actions must not depend on
browser-native prompt dialogs that can silently return without showing UI.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _function_body(js: str, name: str, next_name: str) -> str:
    start = js.index(f"function {name}(")
    end = js.index(f"function {next_name}(", start)
    return js[start:end]


def test_portfolio_create_and_rename_use_in_app_name_dialog():
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")

    for marker in (
        'id="portfolio-name-dialog"',
        'id="portfolio-name-form"',
        'id="portfolio-name-input"',
        'id="portfolio-name-cancel"',
        'id="portfolio-delete-dialog"',
        'id="portfolio-delete-form"',
        'id="portfolio-delete-cancel"',
        'id="portfolio-delete-confirm"',
        'role="dialog"',
        'aria-modal="true"',
    ):
        assert marker in html, marker

    create = _function_body(js, "createNewPortfolio", "renamePortfolioPrompt")
    rename = _function_body(js, "renamePortfolioPrompt", "deletePortfolioConfirm")
    delete = _function_body(js, "deletePortfolioConfirm", "updateExportAnchor")
    assert "openPortfolioNameDialog" in create
    assert "openPortfolioNameDialog" in rename
    assert "openPortfolioDeleteDialog" in delete
    assert "window.prompt" not in create
    assert "window.prompt" not in rename
    assert "window.confirm" not in delete


def test_portfolio_name_dialog_has_keyboard_and_focus_handling():
    js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")

    assert "function openPortfolioNameDialog(" in js
    assert 'event.key === "Escape"' in js
    assert "portfolio-name-input" in js
    assert ".focus()" in js

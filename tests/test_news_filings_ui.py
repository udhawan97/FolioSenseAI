"""Tests for the SEC filings timeline markup in the news zone."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js() -> str:
    return (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")


def _html() -> str:
    return (ROOT / "templates/index.html").read_text(encoding="utf-8")


def test_news_zone_has_a_filings_container():
    html = _html()
    assert 'id="filings-wrap"' in html
    # Hidden until it has something to show, like the feed wrap above it.
    assert "hidden" in html.split('id="filings-wrap"')[1][:60]


def test_filings_are_loaded_from_the_local_endpoint():
    js = _js()
    assert '"/api/news/filings"' in js
    assert "_newsLoadFilings" in js


def test_filings_load_runs_without_claude():
    # The timeline is local-safe: it must not sit behind the Claude-mode gate.
    js = _js()
    zone = js.split("async function loadNewsZone")[1][:1200]
    assert "_newsLoadFilings" in zone
    gate = zone.split("isLocalIntelligenceMode")[0]
    assert "_newsLoadFilings" in gate


def test_filings_render_escapes_untrusted_text():
    js = _js()
    render = js.split("function _newsRenderFilings")[1][:2500]
    assert "escapeHtml" in render


def test_filings_render_links_to_the_source_document():
    js = _js()
    render = js.split("function _newsRenderFilings")[1][:2500]
    assert "sec.gov" in render or "filing.url" in render or "f.url" in render


def test_non_filers_are_labelled_not_silently_empty():
    js = _js()
    render = js.split("function _newsRenderFilings")[1][:2500]
    assert "is_filer" in render


def test_filings_failure_is_survivable():
    js = _js()
    loader = js.split("async function _newsLoadFilings")[1][:900]
    assert "catch" in loader


def test_only_sec_urls_are_turned_into_links():
    # escapeHtml stops attribute breakouts but would happily escape a
    # javascript: URL straight into an href. Filing links must be sec.gov.
    js = _js()
    render = js.split("function _newsRenderFilings")[1][:3000]
    assert "https://www.sec.gov/" in render
    assert "startsWith" in render

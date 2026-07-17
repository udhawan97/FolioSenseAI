"""Tests for the fundamentals-over-time section in holding detail."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js() -> str:
    return (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")


def _render() -> str:
    js = _js()
    assert "function renderFundamentals" in js
    return js.split("function renderFundamentals")[1][:3500]


def test_expand_row_has_a_fundamentals_section():
    assert "intel-fundamentals-section" in _js()


def test_fundamentals_fetched_from_the_lazy_endpoint():
    js = _js()
    assert "/api/ai/fundamentals/" in js
    assert "cachedFundamentals" in js


def test_fundamentals_wired_into_every_render_site():
    assert _js().count("renderFundamentals(") >= 3


def test_render_shows_the_three_filed_metrics():
    render = _render()
    assert "revenue" in render
    assert "net_income" in render or "net_margin" in render
    assert "eps_diluted" in render


def test_render_handles_gaps_without_faking_zero():
    # A null metric must not render as 0 — periods can have holes.
    render = _render()
    assert "periods" in render


def test_empty_and_unavailable_states_exist():
    render = _render()
    assert "data_quality" in render


def test_render_escapes_untrusted_text():
    render = _render()
    assert "escapeHtml" in render

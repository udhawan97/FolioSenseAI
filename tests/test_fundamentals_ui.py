"""Tests for the fundamentals-over-time section in holding detail."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js() -> str:
    return (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")


def _render() -> str:
    js = _js()
    assert "function renderFundamentals" in js
    return js.split("function renderFundamentals")[1][:3500]


def _panel_descriptor(sel: str) -> str:
    """The registerHoldingPanel({...}) block registered for `sel`.

    Registration is how a panel reaches a holding's expand-row, so this block is
    the panel's whole wiring — the selector it paints, the cache it reads, and
    the endpoint that fills that cache.
    """
    js = _js()
    marker = f'sel: "{sel}"'
    assert marker in js, f"no holding panel registered for {sel}"
    start = js.rindex("registerHoldingPanel({", 0, js.index(marker))
    return js[start : js.index("});", start)]


def _function_body(name: str) -> str:
    js = _js()
    start = js.index(f"function {name}(")
    return js[start : js.index("\n}\n", start)]


# The three places that repaint a holding's expand-row.
ROW_RENDER_SITES = ("injectSummaryRows", "renderExpandedTicker", "_renderAllExpandedIntelRows")


def test_expand_row_has_a_fundamentals_section():
    assert "intel-fundamentals-section" in _js()


def test_fundamentals_fetched_from_the_lazy_endpoint():
    js = _js()
    assert "/api/ai/fundamentals/" in js
    assert "cachedFundamentals" in js


def test_fundamentals_is_registered_as_a_holding_panel():
    # One descriptor is the whole wiring — there is no per-site render call to
    # forget. Lose any of these three and the panel goes blank, stops loading,
    # or paints into nothing.
    descriptor = _panel_descriptor(".intel-fundamentals-section")
    assert "renderFundamentals(" in descriptor
    assert "cachedFundamentals" in descriptor
    assert "/api/ai/fundamentals/" in descriptor


def test_fundamentals_reaches_every_site_that_repaints_a_row():
    # Each of these three used to render the panel by hand. They go through
    # renderHoldingPanels() now, which paints every registered panel; drop the
    # call from one site and that site silently stops updating.
    for site in ROW_RENDER_SITES:
        assert "renderHoldingPanels(" in _function_body(site), site


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

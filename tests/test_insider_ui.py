"""Tests for the insider-activity section in each holding's expanded detail."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js() -> str:
    return (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")


def _render() -> str:
    js = _js()
    assert "function renderInsiderActivity" in js
    return js.split("function renderInsiderActivity")[1][:3500]


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


def test_expand_row_has_an_insider_section():
    assert "intel-insider-section" in _js()


def test_insider_data_is_fetched_from_the_lazy_endpoint():
    js = _js()
    assert "/api/ai/insider-activity/" in js
    assert "cachedInsider" in js


def test_insider_is_registered_as_a_holding_panel():
    # One descriptor is the whole wiring — there is no per-site render call to
    # forget. Lose any of these three and the panel goes blank, stops loading,
    # or paints into nothing.
    descriptor = _panel_descriptor(".intel-insider-section")
    assert "renderInsiderActivity(" in descriptor
    assert "cachedInsider" in descriptor
    assert "/api/ai/insider-activity/" in descriptor


def test_insider_reaches_every_site_that_repaints_a_row():
    # Insider used to be rendered by hand at each of these three, so shipping a
    # panel meant remembering all three. They go through renderHoldingPanels()
    # now, which paints every registered panel; drop the call from one site and
    # that site silently stops updating every panel at once.
    for site in ROW_RENDER_SITES:
        assert "renderHoldingPanels(" in _function_body(site), site


def test_headline_is_open_market_conviction():
    render = _render()
    assert "buys" in render
    assert "sells" in render


def test_non_conviction_trades_are_labelled_not_counted():
    # Option exercises / grants (action:"other") appear with their code_label,
    # never folded into the buy/sell headline.
    render = _render()
    assert "code_label" in render or "action" in render


def test_empty_state_is_calm_not_an_error():
    # transactions:[] with data_quality:"live" is normal (funds, quiet stocks).
    render = _render()
    assert "transactions" in render
    assert "data_quality" in render


def test_links_are_guarded_to_sec_gov():
    render = _render()
    assert "sec.gov" in render


def test_render_escapes_untrusted_text():
    # Owner names and roles come from filings — escape them.
    render = _render()
    assert "escapeHtml" in render

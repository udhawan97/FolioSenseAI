"""Tests for the ETF-overlap card in the Analytics zone.

The service (tests/test_etf_overlap.py) is explicit that it only sees each
fund's top 10 published holdings. The card is only allowed to exist if it says
so too — an overlap number presented as full-holdings overlap would be a lie
the backend deliberately refused to tell.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js() -> str:
    return (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")


def _html() -> str:
    return (ROOT / "templates/index.html").read_text(encoding="utf-8")


def _css() -> str:
    return (ROOT / "static/css/style.css").read_text(encoding="utf-8")


def _render_block() -> str:
    js = _js()
    assert "function renderEtfOverlap" in js
    return js.split("function renderEtfOverlap")[1][:6000]


def _loader_block() -> str:
    """loadEtfOverlap's body — the descriptor it hands to the shared loader."""
    js = _js()
    assert "async function loadEtfOverlap" in js
    return js.split("async function loadEtfOverlap")[1].split("\n}")[0]


def _load_card_block() -> str:
    """loadCard's body — the load/show/hide rule every Analytics card shares."""
    js = _js()
    assert "async function loadCard" in js
    return js.split("async function loadCard")[1].split("\n}")[0]


# ── Wiring ──────────────────────────────────────────────────────────────────

def test_overlap_card_lives_in_the_analytics_exposure_pane():
    html = _html()
    assert 'id="etf-overlap-card"' in html
    exposure = html.split('id="analytics-pane-exposure"')[1].split("/exposure sub-pane")[0]
    assert 'id="etf-overlap-card"' in exposure
    assert 'id="etf-overlap-body"' in exposure
    assert 'id="etf-overlap-empty"' in exposure
    assert 'id="etf-overlap-loading"' in exposure


def test_overlap_is_fetched_from_the_local_endpoint():
    js = _js()
    assert "/api/portfolio/etf-overlap" in js


def test_overlap_loads_when_the_analytics_zone_opens():
    js = _js()
    zone = js.split('if (zone === "analytics")')[1][:700]
    assert "ensureEtfOverlapLoaded" in zone


def test_overlap_has_its_own_css_hooks():
    css = _css()
    assert ".etf-overlap-rows" in css
    assert ".etf-overlap-note" in css


# ── Honesty: the card may not overclaim ─────────────────────────────────────

def test_the_card_prints_the_backends_own_caveat():
    # Not a paraphrase — the service owns this sentence.
    block = _render_block()
    assert "caveat" in block


def test_the_card_names_its_basis_as_top_10_only():
    js = _js()
    assert "ETF_OVERLAP_BASIS_LABELS" in js
    labels = js.split("ETF_OVERLAP_BASIS_LABELS")[1][:200]
    # The label is keyed on the backend's own basis enum.
    assert "top_10_holdings" in labels
    assert "top 10" in labels.lower()


def test_the_basis_is_read_off_the_payload_not_assumed():
    # The top-10 wording is looked up from data.basis, so a backend that widened
    # its basis would change the card rather than be misreported by it.
    block = _render_block()
    assert "data.basis" in block
    assert "ETF_OVERLAP_BASIS_LABELS" in block


def test_overlap_is_never_called_full_holdings_overlap():
    block = _render_block()
    lowered = block.lower()
    assert "full overlap" not in lowered
    assert "true overlap" not in lowered
    assert "total overlap" not in lowered


# ── Honesty: coverage ───────────────────────────────────────────────────────

def test_funds_without_holdings_data_are_named_not_dropped_silently():
    block = _render_block()
    assert "uncovered_tickers" in block


def test_partial_coverage_is_stated_on_the_card():
    block = _render_block()
    assert "data_quality" in block
    assert "partial" in block


# ── Rendering ───────────────────────────────────────────────────────────────

def test_a_pair_names_both_funds_and_its_shared_names():
    block = _render_block()
    assert "overlap_pct" in block
    assert "shared_holdings" in block
    assert "pair.a" in block or "p.a" in block


def test_overlap_render_escapes_untrusted_text():
    block = _render_block()
    assert "escapeHtml" in block


# ── Failure modes ───────────────────────────────────────────────────────────

def test_a_single_etf_means_an_empty_state_not_a_blank_card():
    block = _render_block()
    assert "has_data" in block


def test_overlap_fetch_failure_is_survivable():
    # The loader names the card it owns; what happens to that card on a failed
    # read lives in loadCard, so it is asserted there once rather than copied
    # into every card's own loader.
    assert '"etf-overlap-card"' in _loader_block()
    helper = _load_card_block()
    assert "catch" in helper
    assert "_toggleAnalyticsCard(card, false)" in helper


def test_overlap_is_reloaded_when_the_holdings_change():
    # Which funds are paired depends entirely on which funds are held.
    js = _js()
    block = js.split("if (prevTickers !== nextTickers)")[1][:700]
    assert "_etfOverlapLoaded = false" in block
    assert "_etfOverlapLoadPromise = null" in block
    assert "ensureEtfOverlapLoaded" in block


def test_a_card_hidden_by_a_failed_fetch_comes_back_on_a_later_success():
    assert '"etf-overlap-card"' in _loader_block()
    helper = _load_card_block()
    assert "_toggleAnalyticsCard(card, true)" in helper
    assert "_toggleAnalyticsCard(card, false)" in helper

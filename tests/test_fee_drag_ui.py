"""Tests for the fee-drag card in the Analytics zone.

The backend (tests/test_fund_costs.py) already refuses to price a fee it does
not know. This file is about the UI keeping that promise: a fraction is never
double-converted, an unpriced fund is named rather than shown as free, and the
long-horizon number never appears without the assumption it rests on.
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
    assert "function renderFeeDrag" in js
    return js.split("function renderFeeDrag")[1][:6000]


def _code_only(block: str) -> str:
    """`block` with // comments stripped — a comment is not rendered output."""
    return "\n".join(
        line.split("//")[0] if "//" in line and "://" not in line else line
        for line in block.splitlines()
    )


def _loader_block() -> str:
    """loadFeeDrag's body — the descriptor it hands to the shared card loader."""
    js = _js()
    assert "async function loadFeeDrag" in js
    return js.split("async function loadFeeDrag")[1].split("\n}")[0]


def _load_card_block() -> str:
    """loadCard's body — the load/show/hide rule every Analytics card shares."""
    js = _js()
    assert "async function loadCard" in js
    return js.split("async function loadCard")[1].split("\n}")[0]


# ── Wiring ──────────────────────────────────────────────────────────────────

def test_fee_drag_card_lives_in_the_analytics_exposure_pane():
    html = _html()
    assert 'id="fee-drag-card"' in html
    exposure = html.split('id="analytics-pane-exposure"')[1].split("/exposure sub-pane")[0]
    assert 'id="fee-drag-card"' in exposure
    assert 'id="fee-drag-body"' in exposure
    assert 'id="fee-drag-empty"' in exposure
    assert 'id="fee-drag-loading"' in exposure


def test_fee_drag_is_fetched_from_the_local_endpoint():
    js = _js()
    assert "/api/portfolio/fee-drag" in js
    assert "horizon_years" in js


def test_fee_drag_loads_when_the_analytics_zone_opens():
    js = _js()
    zone = js.split('if (zone === "analytics")')[1][:700]
    assert "ensureFeeDragLoaded" in zone


def test_fee_drag_has_its_own_css_hooks():
    css = _css()
    assert ".fee-drag-rows" in css
    assert ".fee-drag-note" in css


# ── Honesty: units ──────────────────────────────────────────────────────────

def test_expense_ratio_is_reported_in_bps_the_backend_already_computed():
    # expense_ratio is a fraction (0.0003). The payload carries the bps form
    # alongside it; recomputing invites the classic double-convert.
    block = _render_block()
    assert "expense_ratio_bps" in block
    assert "expense_ratio * 10000" not in block
    assert "expense_ratio_bps * 100" not in block
    assert "expense_ratio_bps * 10000" not in block


def test_blended_ratio_is_shown_as_bps_not_a_raw_fraction():
    block = _render_block()
    assert "blended_expense_ratio_bps" in block
    assert "bps" in block


def test_a_fraction_rendered_as_a_percent_is_multiplied_once():
    # 0.0003 → "0.03%". Anything other than a single ×100 is a unit bug.
    js = _js()
    assert "function _feePct" in js
    helper = js.split("function _feePct")[1][:400]
    assert "* 100" in helper
    assert "* 10000" not in helper


# ── Honesty: coverage ───────────────────────────────────────────────────────

def test_unpriced_funds_are_named_not_silently_free():
    block = _render_block()
    assert "uncovered_tickers" in block
    assert "Fee unknown" in block


def test_an_unpriced_fund_gets_a_row_of_its_own_not_just_a_footnote():
    # A fund missing from the list reads as "no fee". Every uncovered fund is
    # listed alongside the priced ones, with the fee column explicitly unknown.
    block = _render_block()
    assert "fee-drag-row--unknown" in block
    unknown = block.split("fee-drag-row--unknown")[1][:500]
    assert "Fee unknown" in unknown
    # An em dash, not a dollar amount — the cost is unknown, not zero.
    assert "—" in unknown
    assert "formatCurrency" not in unknown


def test_the_uncovered_note_is_not_duplicated_by_hand():
    # coverage.uncovered_tickers drives the rows; the backend's flags[] carry the
    # reason. Restating the reason here would print it to the user twice.
    block = _code_only(_render_block())
    assert "not counted in the totals above" not in block


def test_uncovered_funds_are_never_reported_as_zero_cost():
    block = _code_only(_render_block())
    uncovered = block.split("uncovered_tickers")[1][:700]
    assert "$0" not in uncovered
    assert "free" not in uncovered.lower()


def test_backend_flags_are_surfaced_rather_than_swallowed():
    block = _render_block()
    assert "flags" in block


def test_partial_coverage_is_stated_on_the_card():
    block = _render_block()
    assert "data_quality" in block
    assert "partial" in block


# ── Honesty: the projection ─────────────────────────────────────────────────

def test_the_horizon_number_never_appears_without_its_assumption():
    block = _render_block()
    assert "horizon_fee_cost" in block
    # assumptions.note is the backend's own sentence about the growth rate the
    # figure rests on. It has to be built into the same markup as the figure —
    # merely mentioning it elsewhere in the renderer is not the same promise.
    assert "data.assumptions?.note" in block
    horizon = block.split("horizon_fee_cost")[1][:600]
    assert "escapeHtml(note)" in horizon
    assert "fee-drag-note" in horizon


def test_the_horizon_is_labelled_with_the_years_it_covers():
    block = _render_block()
    assert "horizon_years" in block


# ── Failure modes ───────────────────────────────────────────────────────────

def test_no_funds_means_an_empty_state_not_a_blank_card():
    block = _render_block()
    assert "has_data" in block


def test_fee_drag_fetch_failure_is_survivable():
    # A dead fetch hides the card; it must not break the Analytics zone. The
    # loader names the card it owns, and the rule for what happens to that card
    # on a failed read lives in loadCard — so it is asserted there, once, rather
    # than copied into every card's own loader.
    assert '"fee-drag-card"' in _loader_block()
    helper = _load_card_block()
    assert "catch" in helper
    assert "_toggleAnalyticsCard(card, false)" in helper


def test_fee_drag_render_escapes_untrusted_text():
    block = _render_block()
    assert "escapeHtml" in block


def test_fee_drag_is_reloaded_when_the_holdings_change():
    # The card is a function of the holdings set. The projection cache is already
    # dropped when the ticker set changes; this one goes stale the same way.
    js = _js()
    block = js.split("if (prevTickers !== nextTickers)")[1][:700]
    assert "_feeDragLoaded = false" in block
    assert "_feeDragLoadPromise = null" in block
    assert "ensureFeeDragLoaded" in block


def test_a_card_hidden_by_a_failed_fetch_comes_back_on_a_later_success():
    # A blip must not retire the card until the next full page load.
    assert '"fee-drag-card"' in _loader_block()
    helper = _load_card_block()
    assert "_toggleAnalyticsCard(card, true)" in helper
    assert "_toggleAnalyticsCard(card, false)" in helper

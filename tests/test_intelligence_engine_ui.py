"""Tests for intelligence engine dropdown UI consistency across pages."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_engine_scoped_markup_present():
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    dash_js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")

    assert 'data-engine-claude-only' in html
    assert 'data-engine-local-only' in html
    assert 'id="holdings-intel-hub"' in html
    assert 'id="btn-holdings-refresh"' in html
    assert 'onclick="refreshHoldingsTable()"' in html
    assert 'onclick="onHoldingsIntelHubClick()"' in html
    assert 'hub-line--claude' in html
    assert 'Claude Summaries' in html
    assert 'id="local-intel-guide"' in html
    assert 'data-engine-local-only' in html.split('id="local-intel-guide"')[1][:120]
    assert 'id="brand-cost-trigger"' in html
    assert 'id="hud-claude-row"' in html
    assert 'id="briefing-seg"' in html
    assert 'hidden' in html.split('id="briefing-seg"')[1][:80]

    assert "onHoldingsIntelHubClick" in dash_js
    assert "refreshHoldingsTable" in dash_js
    assert "updateHoldingsIntelHub" in dash_js
    assert "setEngineScopedVisibility" in dash_js
    assert "validateIntelligenceEngineUi" in dash_js
    assert "getIntelligenceEngineMode" in dash_js
    assert "intelligenceSignalsUrl" in dash_js
    assert 'dataset.intelligenceEngine' in dash_js

    assert '[data-intelligence-engine="local"] [data-engine-claude-only]' in css
    assert '[data-intelligence-engine="claude"] [data-engine-local-only]' in css
    assert '.holdings-intel-hub' in css
    assert '.btn-holdings-refresh' in css


def test_briefing_follows_global_engine():
    dash_js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")

    assert "function _briefingDefaultMode()" in dash_js
    assert 'return isLocalIntelligenceMode() ? "local" : "ai"' in dash_js
    assert "loadPortfolioBriefing(null, true)" in dash_js
    assert "seg.hidden = true" in dash_js


def test_hold_mode_strip_ui():
    dash_js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")

    assert "function _renderHoldModeStrip(" in dash_js
    assert "function _renderManageHoldModeSection(" in dash_js
    assert "function _syncManageHoldModeCard(" in dash_js
    assert "function setHoldMode(" in dash_js
    assert "function _syncHoldModeStrip(" in dash_js
    assert "_HOLD_MODE_META" in dash_js
    assert "_VERDICT_PILL_TIPS" in dash_js
    assert 'role="radiogroup"' in dash_js
    assert "manage-hold-mode-detail" in dash_js
    assert "tipBody:" in dash_js.split("_HOLD_MODE_META")[1][:1200]
    assert ".hold-mode-strip" in css
    assert ".hold-mode-seg.is-active" in css
    assert ".manage-hold-mode-grid" in css
    assert ".manage-hold-mode-detail" in css
    assert ".briefing-verdict-pill.tip-trigger" in css


def test_analytics_signals_respect_engine_mode():
    js = (ROOT / "static/js/analytics-charts.js").read_text(encoding="utf-8")

    assert "analyticsSignalsUrl" in js
    assert "isLocalIntelligenceMode" in js
    assert 'force_local=true' in js

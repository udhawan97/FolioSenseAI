"""Tests for Analytics sub-tab dashboard wiring."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_analytics_sub_tabs_present():
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/analytics-charts.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")

    assert 'id="analytics-zone-tabs"' in html
    assert 'data-analytics-pane="performance"' in html
    assert 'data-analytics-pane="risk"' in html
    assert 'data-analytics-pane="exposure"' in html
    assert 'data-analytics-pane="signals"' in html
    assert 'data-analytics-pane="markets"' in html
    assert 'id="risk-reward-chart"' in html
    assert 'id="markets-tape-track"' in html
    assert "AnalyticsCharts" in js
    assert "/api/portfolio/risk-metrics" in js
    assert "/api/portfolio/correlation" in js
    assert "/api/portfolio/drawdown" in js
    assert "/api/portfolio/contribution" in js
    assert ".analytics-zone-tabs" in css
    assert "prefers-reduced-motion" in css


def test_portfolio_analytics_endpoints_registered():
    router = (ROOT / "app/routers/portfolio.py").read_text(encoding="utf-8")
    assert '"/risk-metrics"' in router
    assert '"/correlation"' in router
    assert '"/drawdown"' in router
    assert '"/contribution"' in router

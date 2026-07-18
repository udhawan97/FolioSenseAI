"""Tests for the dividend-calendar strip inside the Analytics income card.

Static-assertion style, like tests/test_dividend_income_ui.py: the strip must
exist inside the income card, fetch from the calendar endpoint, disclose the
ex-date basis, and fail quietly (the income card must survive a calendar
outage untouched).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js() -> str:
    return (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")


def _render() -> str:
    js = _js()
    assert "function renderIncomeCalendar" in js
    return js.split("function renderIncomeCalendar")[1][:4000]


def test_income_card_hosts_the_calendar_strip():
    # The strip lives inside the income card body renderIncome writes.
    assert "income-calendar" in _js().split("function renderIncome")[1][:3000]


def test_calendar_is_fetched_from_the_lazy_endpoint():
    assert "/api/portfolio/income-calendar" in _js()


def test_calendar_discloses_the_ex_date_basis():
    # Months are ex-dividend months, not pay months — say so on the card.
    assert "ex-dividend months" in _render()


def test_unscheduled_payers_are_named_never_smeared():
    render = _render()
    assert "unscheduled" in render


def test_render_escapes_untrusted_text():
    assert "escapeHtml" in _render()


def test_calendar_failure_leaves_the_income_card_standing():
    js = _js()
    assert "function loadIncomeCalendar" in js
    # Slice to this function's body only — the neighbors legitimately toggle
    # the card; loadIncomeCalendar itself must not.
    load = js.split("function loadIncomeCalendar")[1]
    load = load.split("\nasync function")[0].split("\nfunction")[0]
    # A failed calendar fetch clears only the strip — no card teardown.
    assert "catch" in load
    assert "_toggleAnalyticsCard" not in load

"""Tests for EPS estimates and beat history on the earnings radar."""
# pylint: disable=protected-access
from datetime import date

import pytest

from app.services import earnings_radar
from app.services.event_calendar import _parse_earnings_quarters, fetch_earnings_estimate


def _quarters() -> list[dict]:
    """Shaped like the seam's earnings rows: newest first, no surprise yet ahead."""
    return [
        {"date": date(2026, 7, 30), "eps_estimate": 1.89, "surprise_pct": None},
        {"date": date(2026, 4, 30), "eps_estimate": 1.94, "surprise_pct": 3.46},
        {"date": date(2026, 1, 29), "eps_estimate": 2.67, "surprise_pct": 6.25},
        {"date": date(2025, 10, 30), "eps_estimate": 1.77, "surprise_pct": 4.52},
        {"date": date(2025, 7, 31), "eps_estimate": 1.40, "surprise_pct": -7.14},
    ]


def test_estimate_is_read_for_the_matching_date():
    parsed = _parse_earnings_quarters(_quarters(), date(2026, 7, 30))
    assert parsed["eps_estimate"] == 1.89


def test_no_estimate_when_the_rows_carry_no_such_date():
    assert _parse_earnings_quarters(_quarters(), date(2026, 12, 25)) is None


def test_beat_history_counts_only_reported_quarters():
    parsed = _parse_earnings_quarters(_quarters(), date(2026, 7, 30))
    # Four reported quarters; the upcoming one has no result yet.
    assert parsed["quarters"] == 4
    assert parsed["beats"] == 3  # one miss, at -7.14%


def test_beat_history_is_capped_to_recent_quarters():
    parsed = _parse_earnings_quarters(_quarters(), date(2026, 7, 30), lookback_quarters=2)
    assert parsed["quarters"] == 2
    assert parsed["beats"] == 2


def test_a_zero_surprise_is_not_a_beat():
    quarters = _quarters()
    quarters[1]["surprise_pct"] = 0.0
    parsed = _parse_earnings_quarters(quarters, date(2026, 7, 30))
    assert parsed["beats"] == 2


def test_a_quarter_with_no_estimate_is_survivable():
    quarters = [{**row, "eps_estimate": None} for row in _quarters()]
    parsed = _parse_earnings_quarters(quarters, date(2026, 7, 30))
    assert parsed is None or parsed["eps_estimate"] is None


def test_no_quarters():
    assert _parse_earnings_quarters([], date(2026, 7, 30)) is None


def test_none_instead_of_quarters():
    assert _parse_earnings_quarters(None, date(2026, 7, 30)) is None


def test_fetch_never_raises_when_the_read_is_unhappy(monkeypatch):
    def _boom(_ticker):
        raise RuntimeError("earnings read blocked")

    monkeypatch.setattr("app.services.event_calendar._fetch_earnings_quarters", _boom)
    assert fetch_earnings_estimate("AAPL", date(2026, 7, 30)) is None


def test_the_seam_supplies_the_quarters(fake_market_data):
    """End to end through the real fetch: rows in, estimate out, no vendor stub."""
    fake_market_data(earnings_estimates={"AAPL": _quarters()})

    parsed = fetch_earnings_estimate("AAPL", date(2026, 4, 30))

    assert parsed["eps_estimate"] == 1.94


# --- the radar surfaces the estimate alongside the date ---


@pytest.fixture
def _offline_radar(monkeypatch):
    earnings_radar._resolve_earnings.cache_clear()
    monkeypatch.setattr(
        earnings_radar, "get_ticker_info", lambda t: {"quoteType": "EQUITY"}
    )
    monkeypatch.setattr(
        earnings_radar,
        "classify_security",
        lambda *_a, **_k: earnings_radar.SecurityType.STOCK,
    )


def test_radar_event_carries_the_estimate(_offline_radar, monkeypatch):
    soon = date.today()
    monkeypatch.setattr(earnings_radar, "fetch_next_earnings", lambda _t: soon)
    monkeypatch.setattr(
        earnings_radar,
        "fetch_earnings_estimate",
        lambda _t, _d: {"eps_estimate": 1.89, "beats": 3, "quarters": 4},
    )
    events = earnings_radar.get_earnings_events(["AAPL"])
    assert events[0]["eps_estimate"] == 1.89
    assert events[0]["beats"] == 3
    assert events[0]["quarters"] == 4


def test_radar_event_survives_a_missing_estimate(_offline_radar, monkeypatch):
    # No estimate is not a reason to hide a known earnings date.
    soon = date.today()
    monkeypatch.setattr(earnings_radar, "fetch_next_earnings", lambda _t: soon)
    monkeypatch.setattr(earnings_radar, "fetch_earnings_estimate", lambda _t, _d: None)
    events = earnings_radar.get_earnings_events(["AAPL"])
    assert events[0]["ticker"] == "AAPL"
    assert events[0]["eps_estimate"] is None
    assert events[0]["beats"] is None

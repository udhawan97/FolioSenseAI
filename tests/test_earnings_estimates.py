"""Tests for EPS estimates and beat history on the earnings radar."""
from datetime import date

import pandas as pd
import pytest

from app.services import earnings_radar
from app.services.event_calendar import _parse_earnings_table, fetch_earnings_estimate


def _table() -> pd.DataFrame:
    """Shaped like yfinance's get_earnings_dates: tz-aware index, NaN ahead."""
    idx = pd.to_datetime(
        [
            "2026-07-30 16:00:00-04:00",
            "2026-04-30 16:00:00-04:00",
            "2026-01-29 16:00:00-05:00",
            "2025-10-30 16:00:00-04:00",
            "2025-07-31 16:00:00-04:00",
        ],
        utc=True,
    )
    return pd.DataFrame(
        {
            "EPS Estimate": [1.89, 1.94, 2.67, 1.77, 1.40],
            "Reported EPS": [float("nan"), 2.01, 2.84, 1.85, 1.30],
            "Surprise(%)": [float("nan"), 3.46, 6.25, 4.52, -7.14],
        },
        index=idx,
    ).rename_axis("Earnings Date")


def test_estimate_is_read_for_the_matching_date():
    parsed = _parse_earnings_table(_table(), date(2026, 7, 30))
    assert parsed["eps_estimate"] == 1.89


def test_no_estimate_when_the_table_has_no_row_for_that_date():
    assert _parse_earnings_table(_table(), date(2026, 12, 25)) is None


def test_beat_history_counts_only_reported_quarters():
    parsed = _parse_earnings_table(_table(), date(2026, 7, 30))
    # Four reported quarters; the upcoming one has no result yet.
    assert parsed["quarters"] == 4
    assert parsed["beats"] == 3  # one miss, at -7.14%


def test_beat_history_is_capped_to_recent_quarters():
    parsed = _parse_earnings_table(_table(), date(2026, 7, 30), lookback_quarters=2)
    assert parsed["quarters"] == 2
    assert parsed["beats"] == 2


def test_a_zero_surprise_is_not_a_beat():
    table = _table()
    table.iloc[1, table.columns.get_loc("Surprise(%)")] = 0.0
    parsed = _parse_earnings_table(table, date(2026, 7, 30))
    assert parsed["beats"] == 2


def test_missing_estimate_column_is_survivable():
    table = _table().drop(columns=["EPS Estimate"])
    parsed = _parse_earnings_table(table, date(2026, 7, 30))
    assert parsed is None or parsed["eps_estimate"] is None


def test_empty_table():
    assert _parse_earnings_table(pd.DataFrame(), date(2026, 7, 30)) is None


def test_none_table():
    assert _parse_earnings_table(None, date(2026, 7, 30)) is None


def test_fetch_never_raises_when_yfinance_is_unhappy(monkeypatch):
    def _boom(_ticker):
        raise RuntimeError("yfinance blocked")

    monkeypatch.setattr("app.services.event_calendar._fetch_earnings_table", _boom)
    assert fetch_earnings_estimate("AAPL", date(2026, 7, 30)) is None


# --- the radar surfaces the estimate alongside the date ---


@pytest.fixture
def _offline_radar(monkeypatch):
    monkeypatch.setattr(earnings_radar, "_RADAR_CACHE", {})
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

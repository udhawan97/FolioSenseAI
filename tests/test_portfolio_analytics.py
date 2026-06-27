"""Tests for portfolio analytics service."""

import numpy as np

from app.services import portfolio_analytics as pa


def test_annualize_stats_from_synthetic():
    rng = np.random.default_rng(0)
    closes = [100.0]
    for _ in range(100):
        closes.append(closes[-1] * np.exp(rng.normal(0.0005, 0.01)))
    rets = pa._log_returns(closes)
    ann_ret, ann_vol = pa._annualize_stats(rets)
    assert ann_vol > 0
    assert isinstance(ann_ret, float)


def test_compute_drawdown_series():
    history = [
        {"date": "2024-01-01", "total_value": 10000},
        {"date": "2024-01-02", "total_value": 11000},
        {"date": "2024-01-03", "total_value": 9900},
        {"date": "2024-01-04", "total_value": 10500},
    ]
    result = pa.compute_drawdown(history)
    assert result["has_data"] is True
    assert result["max_drawdown_pct"] < 0
    assert len(result["series"]) == 4
    assert result["series"][0]["drawdown_pct"] == 0.0


def test_compute_drawdown_empty():
    result = pa.compute_drawdown([])
    assert result["has_data"] is False
    assert result["series"] == []


def test_compute_contribution_day():
    holdings = [
        {
            "ticker": "AAPL",
            "shares": 10,
            "day_change": 2.0,
            "allocation_pct": 60,
            "is_watchlist": False,
        },
        {
            "ticker": "MSFT",
            "shares": 5,
            "day_change": -1.0,
            "allocation_pct": 40,
            "is_watchlist": False,
        },
    ]
    result = pa.compute_contribution(holdings, period="day")
    assert result["has_data"] is True
    assert result["total_contribution"] == 15.0  # 10*2 + 5*(-1)
    assert result["holdings"][0]["ticker"] == "AAPL"


def test_correlation_single_holding():
    holdings = [{"ticker": "VOO", "current_value": 5000, "is_watchlist": False}]
    result = pa.compute_correlation_matrix(holdings)
    assert result["tickers"] == ["VOO"]
    assert result["has_data"] is False

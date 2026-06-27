"""
Portfolio analytics — risk metrics, correlation, drawdown, and attribution.

Computes from cached/batched price history server-side (same cache as timing signals).
"""

from __future__ import annotations

import hashlib
import math
import time
from datetime import date, timedelta
from typing import Any

import numpy as np

from app.services.portfolio_projection import BENCHMARK_TICKER, TRADING_DAYS
from app.services.timing_signal import get_batched_history_closes

_CACHE_TTL_SEC = 300
_cache: dict[str, dict[str, Any]] = {}


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if not entry or entry["expires_at"] < time.time():
        return None
    return entry["payload"]


def _cache_set(key: str, payload: Any) -> Any:
    _cache[key] = {"payload": payload, "expires_at": time.time() + _CACHE_TTL_SEC}
    return payload


def _tickers_key(tickers: list[str], suffix: str = "") -> str:
    raw = ",".join(sorted(t.upper() for t in tickers if t)) + suffix
    return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()


def _log_returns(closes: list[float]) -> np.ndarray:
    if len(closes) < 2:
        return np.array([], dtype=float)
    prices = np.asarray(closes, dtype=float)
    return np.diff(np.log(prices))


def _annualize_stats(daily_log_returns: np.ndarray) -> tuple[float, float]:
    if daily_log_returns.size < 5:
        return 0.0, 0.0
    mu = float(np.mean(daily_log_returns)) * TRADING_DAYS
    sigma = float(np.std(daily_log_returns, ddof=1)) * math.sqrt(TRADING_DAYS)
    return round(mu * 100, 2), round(sigma * 100, 2)


def _aligned_daily_returns(
    series_map: dict[str, list[float]],
) -> tuple[list[str], np.ndarray]:
    """
    Build a matrix of daily log-returns with rows = tickers, cols = aligned days.
    Uses minimum overlapping length across series (tail-aligned).
    """
    tickers = [t for t, c in series_map.items() if len(c) >= 2]
    if not tickers:
        return [], np.array([])

    min_len = min(len(series_map[t]) for t in tickers)
    if min_len < 2:
        return [], np.array([])

    rows = []
    for t in tickers:
        closes = series_map[t][-min_len:]
        rows.append(_log_returns(closes))
    return tickers, np.vstack(rows)


def compute_risk_metrics(
    holdings: list[dict],
    total_value: float,
    *,
    signals: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """
    Per-holding annualized return & volatility for the risk/reward scatter.
    Includes portfolio-weighted aggregate and S&P 500 benchmark point.
    """
    active = [
        h for h in holdings
        if not h.get("is_watchlist") and float(h.get("current_value") or 0) > 0
    ]
    tickers = [h["ticker"] for h in active]
    cache_key = f"risk:{_tickers_key(tickers)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    signals = signals or {}
    history = get_batched_history_closes(tickers + [BENCHMARK_TICKER], period="1y")

    points: list[dict] = []
    weights: list[float] = []
    port_rets: list[float] = []

    for h in active:
        ticker = h["ticker"]
        closes = history.get(ticker, [])
        rets = _log_returns(closes)
        ann_ret, ann_vol = _annualize_stats(rets)
        w = float(h.get("allocation_pct") or 0)
        action = (signals.get(ticker) or {}).get("action", "hold")
        points.append({
            "ticker": ticker,
            "annual_return_pct": ann_ret,
            "annual_vol_pct": ann_vol,
            "allocation_pct": w,
            "action": action,
        })
        if rets.size:
            weights.append(w)
            port_rets.append(float(np.mean(rets)) * TRADING_DAYS * 100)

    portfolio_point: dict[str, Any] | None = None
    if active and total_value > 0:
        wsum = sum(float(h.get("allocation_pct") or 0) for h in active)
        if wsum > 0 and port_rets:
            weighted_ret = sum(
                float(h.get("allocation_pct") or 0) * _annualize_stats(
                    _log_returns(history.get(h["ticker"], []))
                )[0]
                for h in active
            ) / wsum
            # Portfolio vol from weighted daily returns
            series_map = {h["ticker"]: history.get(h["ticker"], []) for h in active}
            tickers_aligned, mat = _aligned_daily_returns(series_map)
            port_vol = 0.0
            if mat.size:
                w_vec = np.array([
                    float(h.get("allocation_pct") or 0) / wsum
                    for h in active if h["ticker"] in tickers_aligned
                ])
                if w_vec.size == mat.shape[0]:
                    port_daily = w_vec @ mat
                    port_vol = float(np.std(port_daily, ddof=1)) * math.sqrt(TRADING_DAYS) * 100
            portfolio_point = {
                "label": "Your portfolio",
                "annual_return_pct": round(weighted_ret, 2),
                "annual_vol_pct": round(port_vol, 2),
            }

    spy_closes = history.get(BENCHMARK_TICKER, [])
    spy_ret, spy_vol = _annualize_stats(_log_returns(spy_closes))
    benchmark_point = {
        "label": "S&P 500",
        "ticker": BENCHMARK_TICKER,
        "annual_return_pct": spy_ret,
        "annual_vol_pct": spy_vol,
    }

    payload = {
        "holdings": points,
        "portfolio": portfolio_point,
        "benchmark": benchmark_point,
        "has_data": bool(points),
    }
    return _cache_set(cache_key, payload)


def compute_correlation_matrix(holdings: list[dict]) -> dict[str, Any]:
    """Pearson correlation of daily log-returns for current holdings."""
    active = [
        h for h in holdings
        if not h.get("is_watchlist") and float(h.get("current_value") or 0) > 0
    ]
    tickers = [h["ticker"] for h in active]
    cache_key = f"corr:{_tickers_key(tickers)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if len(tickers) < 2:
        return _cache_set(cache_key, {"tickers": tickers, "matrix": [], "has_data": False})

    history = get_batched_history_closes(tickers, period="1y")
    aligned_tickers, mat = _aligned_daily_returns(history)

    if mat.size == 0 or mat.shape[1] < 5:
        n = len(aligned_tickers) or len(tickers)
        identity = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
        return _cache_set(cache_key, {
            "tickers": aligned_tickers or tickers,
            "matrix": identity,
            "has_data": False,
        })

    corr = np.corrcoef(mat)
    corr = np.nan_to_num(corr, nan=0.0)
    matrix = [[round(float(corr[i, j]), 3) for j in range(corr.shape[1])]
              for i in range(corr.shape[0])]

    return _cache_set(cache_key, {
        "tickers": aligned_tickers,
        "matrix": matrix,
        "has_data": True,
    })


def compute_drawdown(history: list[dict]) -> dict[str, Any]:
    """Drawdown series (% below running peak) from portfolio snapshot history."""
    rows = [r for r in (history or []) if r.get("date") and r.get("total_value") is not None]
    if len(rows) < 2:
        return {"series": [], "max_drawdown_pct": 0.0, "max_drawdown_date": None, "has_data": False}

    series: list[dict] = []
    peak = 0.0
    max_dd = 0.0
    max_dd_date: str | None = None

    for row in rows:
        value = float(row["total_value"])
        if value > peak:
            peak = value
        dd = ((value - peak) / peak * 100) if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
            max_dd_date = row["date"]
        series.append({"date": row["date"], "drawdown_pct": round(dd, 2)})

    return {
        "series": series,
        "max_drawdown_pct": round(max_dd, 2),
        "max_drawdown_date": max_dd_date,
        "has_data": True,
    }


def compute_contribution(
    holdings: list[dict],
    period: str = "day",
) -> dict[str, Any]:
    """
    Per-holding contribution to portfolio P&L for day / week / month.
    Day uses live day_change × shares; longer periods use price history.
    """
    period = period if period in ("day", "week", "month") else "day"
    active = [
        h for h in holdings
        if not h.get("is_watchlist") and float(h.get("shares") or 0) > 0
    ]
    tickers = [h["ticker"] for h in active]

    if period == "day":
        contributions = []
        total = 0.0
        for h in active:
            shares = float(h.get("shares") or 0)
            day_chg = float(h.get("day_change") or 0)
            contrib = round(shares * day_chg, 2)
            contributions.append({
                "ticker": h["ticker"],
                "contribution": contrib,
                "allocation_pct": float(h.get("allocation_pct") or 0),
            })
            total += contrib
        contributions.sort(key=lambda x: abs(x["contribution"]), reverse=True)
        return {
            "period": period,
            "total_contribution": round(total, 2),
            "holdings": contributions,
            "has_data": bool(contributions),
        }

    lookback = {"week": 7, "month": 30}[period]
    history = get_batched_history_closes(tickers, period="1mo")
    contributions = []
    total = 0.0

    for h in active:
        ticker = h["ticker"]
        shares = float(h.get("shares") or 0)
        closes = history.get(ticker, [])
        if len(closes) < 2:
            contrib = 0.0
        else:
            tail = closes[-min(lookback + 1, len(closes)):]
            if len(tail) < 2:
                contrib = 0.0
            else:
                contrib = round(shares * (tail[-1] - tail[0]), 2)
        contributions.append({
            "ticker": ticker,
            "contribution": contrib,
            "allocation_pct": float(h.get("allocation_pct") or 0),
        })
        total += contrib

    contributions.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    return {
        "period": period,
        "total_contribution": round(total, 2),
        "holdings": contributions,
        "has_data": bool(contributions),
    }

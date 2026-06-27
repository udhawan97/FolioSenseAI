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

from app.services.portfolio_projection import BENCHMARK_TICKER, TRADING_DAYS, _portfolio_daily_returns
from app.services.portfolio_exposure import build_portfolio_exposure
from app.services.stock_service import get_all_quotes, get_historical_prices
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


_CONTRIBUTION_TOP_EACH_SIDE = 5


def _contribution_row(
    h: dict,
    *,
    contrib: float,
    change_pct: float,
) -> dict[str, Any]:
    allocation = float(h.get("allocation_pct") or 0)
    return {
        "ticker": h["ticker"],
        "name": h.get("name") or h["ticker"],
        "contribution": contrib,
        "change_pct": round(change_pct, 2),
        "contribution_pp": round(allocation * change_pct / 100.0, 4),
        "allocation_pct": allocation,
        "current_value": round(float(h.get("current_value") or 0), 2),
    }


def _finalize_contribution_payload(
    contributions: list[dict[str, Any]],
    *,
    period: str,
    portfolio_value: float,
) -> dict[str, Any]:
    total = round(sum(c["contribution"] for c in contributions), 2)
    if total:
        for c in contributions:
            c["contribution_pct"] = round(c["contribution"] / total * 100, 1)
    else:
        for c in contributions:
            c["contribution_pct"] = 0.0

    gainers = sorted(
        [c for c in contributions if c["contribution"] > 0],
        key=lambda x: x["contribution"],
        reverse=True,
    )
    losers = sorted(
        [c for c in contributions if c["contribution"] < 0],
        key=lambda x: x["contribution"],
    )
    top_gainers = gainers[:_CONTRIBUTION_TOP_EACH_SIDE]
    top_losers = losers[:_CONTRIBUTION_TOP_EACH_SIDE]
    shown = {c["ticker"] for c in top_gainers + top_losers}
    rest = [c for c in contributions if c["ticker"] not in shown]
    others_contrib = round(sum(c["contribution"] for c in rest), 2)

    others: dict[str, Any] | None = None
    if rest and others_contrib != 0:
        others = {
            "ticker": "Other",
            "name": f"{len(rest)} other holding{'s' if len(rest) != 1 else ''}",
            "contribution": others_contrib,
            "contribution_pct": round(others_contrib / total * 100, 1) if total else 0.0,
            "change_pct": None,
            "contribution_pp": round(sum(c["contribution_pp"] for c in rest), 4),
            "allocation_pct": round(sum(c["allocation_pct"] for c in rest), 1),
            "current_value": round(sum(c["current_value"] for c in rest), 2),
            "count": len(rest),
        }

    portfolio_change_pct = (
        round(total / portfolio_value * 100, 2) if portfolio_value > 0 else 0.0
    )
    return {
        "period": period,
        "total_contribution": total,
        "portfolio_value": round(portfolio_value, 2),
        "portfolio_change_pct": portfolio_change_pct,
        "holdings_count": len(contributions),
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "others": others,
        "holdings": sorted(contributions, key=lambda x: abs(x["contribution"]), reverse=True),
        "has_data": bool(contributions),
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
    portfolio_value = sum(float(h.get("current_value") or 0) for h in active)
    tickers = [h["ticker"] for h in active]

    if period == "day":
        contributions = []
        for h in active:
            shares = float(h.get("shares") or 0)
            day_chg = float(h.get("day_change") or 0)
            change_pct = float(h.get("day_change_pct") or 0)
            contrib = round(shares * day_chg, 2)
            contributions.append(_contribution_row(h, contrib=contrib, change_pct=change_pct))
        return _finalize_contribution_payload(
            contributions, period=period, portfolio_value=portfolio_value
        )

    lookback = {"week": 7, "month": 30}[period]
    history = get_batched_history_closes(tickers, period="1mo")
    contributions = []

    for h in active:
        ticker = h["ticker"]
        shares = float(h.get("shares") or 0)
        closes = history.get(ticker, [])
        contrib = 0.0
        change_pct = 0.0
        if len(closes) >= 2:
            tail = closes[-min(lookback + 1, len(closes)):]
            if len(tail) >= 2 and tail[0] > 0:
                contrib = round(shares * (tail[-1] - tail[0]), 2)
                change_pct = (tail[-1] - tail[0]) / tail[0] * 100.0
        contributions.append(_contribution_row(h, contrib=contrib, change_pct=change_pct))

    return _finalize_contribution_payload(
        contributions, period=period, portfolio_value=portfolio_value
    )


_INDEX_GEO_KEYS: dict[str, list[str]] = {
    "^GSPC": ["united states"],
    "^IXIC": ["united states"],
    "^DJI": ["united states"],
    "^FTSE": ["united kingdom", "uk"],
    "^GDAXI": ["germany"],
    "^FCHI": ["france"],
    "^N225": ["japan"],
    "^HSI": ["hong kong", "china"],
    "^NSEI": ["india"],
    "^AXJO": ["australia"],
}


def _price_series(ticker: str) -> list[tuple[str, float]]:
    rows = get_historical_prices(ticker, "1y")
    return [(r["date"], float(r["close"])) for r in rows if r.get("close", 0) > 0]


def _geo_weight(country_exposure: list[dict], keywords: list[str]) -> float:
    for entry in country_exposure:
        name = str(entry.get("name") or "").lower()
        if any(kw in name for kw in keywords):
            return float(entry.get("weight_pct") or 0)
    return 0.0


def _correlation_label(value: float) -> str:
    if value >= 0.7:
        return "High"
    if value >= 0.4:
        return "Moderate"
    if value < 0:
        return "Inverse"
    if value < 0.15:
        return "Weak"
    return "Low"


def _market_insight(correlation: float, geo_weight: float, name: str) -> str:
    if geo_weight >= 25 and correlation >= 0.45:
        return f"~{geo_weight:.0f}% look-through exposure — tends to move with your book"
    if correlation >= 0.65:
        return "Moves closely with your portfolio day to day"
    if correlation >= 0.35:
        return "Some overlap with your daily moves"
    if correlation < -0.1:
        return "Often offsets your book — diversification ballast"
    return "Limited day-to-day link to your holdings"


def _portfolio_index_correlations(
    holdings: list[dict],
    index_tickers: list[str],
) -> dict[str, float]:
    active = [
        h for h in holdings
        if not h.get("is_watchlist") and float(h.get("current_value") or 0) > 0
    ]
    if not active:
        return {}

    weighted = [(h["ticker"], float(h["current_value"])) for h in active]
    series_map: dict[str, list[tuple[str, float]]] = {}
    for ticker, _ in weighted:
        series_map[ticker] = _price_series(ticker)
    for idx in index_tickers:
        if idx not in series_map:
            series_map[idx] = _price_series(idx)

    port_rets = _portfolio_daily_returns([
        (ticker, weight, series_map.get(ticker, []))
        for ticker, weight in weighted
    ])
    if port_rets.size < 5:
        return {}

    out: dict[str, float] = {}
    for idx in index_tickers:
        series = series_map.get(idx, [])
        if len(series) < 2:
            out[idx] = 0.0
            continue
        idx_rets = _log_returns([c for _d, c in series])
        n = min(port_rets.size, idx_rets.size)
        if n < 5:
            out[idx] = 0.0
            continue
        corr = float(np.corrcoef(port_rets[-n:], idx_rets[-n:])[0, 1])
        out[idx] = round(corr if np.isfinite(corr) else 0.0, 3)
    return out


def compute_market_context(
    holdings: list[dict],
    world_markets: list[dict],
) -> dict[str, Any]:
    """
    Enrich world indices with portfolio correlation and geographic alignment.
    """
    cache_key = f"mktctx:{_tickers_key([h['ticker'] for h in holdings if not h.get('is_watchlist')])}"
    cached = _cache_get(cache_key)
    if cached is not None:
        quote_map = {m["ticker"]: m for m in world_markets}
        markets = []
        for row in cached.get("markets", []):
            live = quote_map.get(row["ticker"], {})
            markets.append({
                **row,
                "price": live.get("price", row.get("price")),
                "day_change": live.get("day_change", row.get("day_change")),
                "day_change_pct": live.get("day_change_pct", row.get("day_change_pct")),
            })
        return {**cached, "markets": markets}

    active = [h for h in holdings if not h.get("is_watchlist") and float(h.get("allocation_pct") or 0) > 0]
    if not active:
        return _cache_set(cache_key, {
            "has_data": False,
            "markets": world_markets,
            "summary": None,
            "best_match": None,
        })

    quotes = get_all_quotes([h["ticker"] for h in active])
    exposure = build_portfolio_exposure(
        [
            {
                "ticker": h["ticker"],
                "allocation_pct": h.get("allocation_pct"),
                "is_watchlist": h.get("is_watchlist"),
            }
            for h in active
        ],
        quotes={q["ticker"]: q for q in quotes},
    )
    country_exposure = exposure.get("country_exposure") or []

    index_tickers = [m["ticker"] for m in world_markets]
    correlations = _portfolio_index_correlations(holdings, index_tickers)

    enriched: list[dict] = []
    for market in world_markets:
        ticker = market["ticker"]
        corr = correlations.get(ticker, 0.0)
        geo = _geo_weight(country_exposure, _INDEX_GEO_KEYS.get(ticker, []))
        enriched.append({
            **market,
            "correlation": corr,
            "correlation_label": _correlation_label(corr),
            "geo_weight_pct": round(geo, 1),
            "insight": _market_insight(corr, geo, market.get("name", ticker)),
        })

    enriched.sort(key=lambda m: m.get("correlation", 0), reverse=True)
    best = enriched[0] if enriched else None

    us_weight = _geo_weight(country_exposure, ["united states"])
    summary_parts: list[str] = []
    if best and best.get("correlation", 0) > 0.2:
        summary_parts.append(
            f"Your portfolio is most in sync with {best['name']} "
            f"({best['correlation'] * 100:.0f}% correlated over the past year)."
        )
    if us_weight >= 30:
        summary_parts.append(
            f"~{us_weight:.0f}% of your look-through exposure is US-linked — "
            "watch the US row when global markets move."
        )
    if not summary_parts:
        summary_parts.append(
            "Compare how each global index moves relative to your holdings — "
            "higher correlation means a bigger ripple effect on your book."
        )

    payload = {
        "has_data": True,
        "markets": enriched,
        "summary": " ".join(summary_parts),
        "best_match": (
            {
                "ticker": best["ticker"],
                "name": best["name"],
                "correlation": best["correlation"],
            }
            if best
            else None
        ),
        "us_exposure_pct": round(us_weight, 1),
    }
    return _cache_set(cache_key, payload)

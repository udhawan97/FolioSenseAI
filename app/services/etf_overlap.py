"""
ETF overlap-lite — how much two funds hold the same names, from top-10 data.

Yahoo exposes each fund's ten largest positions and nothing below them, so this
is *top-10* overlap: a floor on real duplication, never the whole story. Every
payload carries that limitation so the UI cannot overclaim it as full-holdings
overlap.
"""
from __future__ import annotations

import logging
import math
import time
from itertools import combinations
from typing import Any

from app.services.security_type import SecurityType, classify_security

logger = logging.getLogger(__name__)

TOP_N = 10

BASIS = "top_10_holdings"
SCORE_METHOD = "sum_of_min_shared_weight"
CAVEAT = (
    "Compares only each fund's top 10 published holdings — Yahoo exposes nothing "
    "below them. Shared weight further down the funds is invisible here, so treat "
    "this as a floor on real overlap, not the full picture."
)

# funds_data is a separate Yahoo scrape from the shared .info cache, so it gets
# its own small TTL cache — a dashboard refresh must not re-scrape every ETF.
_HOLDINGS_TTL_SEC = 900
_holdings_cache: dict[str, tuple[float, list[dict]]] = {}


def _fetch_top_holdings(ticker: str) -> list[dict]:
    """The module's only network edge: a fund's top-10 rows, or [] when unavailable.

    Returns dicts of {symbol, name, weight} with weight in percentage points.
    """
    symbol = ticker.strip().upper()
    now = time.monotonic()
    cached = _holdings_cache.get(symbol)
    if cached and cached[0] > now:
        return cached[1]

    rows: list[dict] = []
    try:
        import yfinance as yf  # noqa: PLC0415 — matches market_regime._fetch_closes
        frame = yf.Ticker(symbol).funds_data.top_holdings
        if frame is None or frame.empty:
            return []
        for holding_symbol, row in frame.iterrows():
            rows.append({
                "symbol": str(holding_symbol),
                "name": str(row.get("Name") or holding_symbol),
                # Yahoo publishes fractions (0.072); the app speaks percentage points.
                "weight": float(row.get("Holding Percent") or 0.0) * 100,
            })
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug(
            "Top-holdings fetch failed for %s; exception_type=%s",
            symbol, type(exc).__name__,
        )
        return []

    # Only a real answer is cached; a failed/empty fetch stays retryable.
    if rows:
        _holdings_cache[symbol] = (now + _HOLDINGS_TTL_SEC, rows)
    return rows


def _held_etfs(holdings_with_data: list[dict]) -> list[str]:
    """Unique, owned ETF tickers in input order."""
    tickers: list[str] = []
    for item in holdings_with_data:
        if item.get("is_watchlist"):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker or ticker in tickers:
            continue
        if classify_security(ticker, item) is SecurityType.ETF:
            tickers.append(ticker)
    return tickers


def normalize_top_holdings(rows: list[dict]) -> dict[str, float]:
    """Symbol → weight (%), upper-cased, de-duplicated, ten heaviest names only."""
    weights: dict[str, float] = {}
    for row in rows or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        try:
            weight = float(row.get("weight") or 0.0)
        except (TypeError, ValueError):
            continue
        # NaN slips past `<= 0` — a pandas NaN weight is missing data, not a name.
        if not math.isfinite(weight) or weight <= 0:
            continue
        weights[symbol] = weights.get(symbol, 0.0) + weight
    heaviest = sorted(weights.items(), key=lambda item: item[1], reverse=True)[:TOP_N]
    return dict(heaviest)


def overlap_between(a: dict[str, float], b: dict[str, float]) -> dict[str, Any]:
    """Shared names between two normalized top-10 maps, scored by min-weight."""
    shared = [
        {
            "symbol": symbol,
            "weight_a": round(a[symbol], 2),
            "weight_b": round(b[symbol], 2),
            "shared_weight": round(min(a[symbol], b[symbol]), 2),
        }
        for symbol in a
        if symbol in b
    ]
    shared.sort(key=lambda item: item["shared_weight"], reverse=True)
    return {
        "overlap_pct": round(sum(item["shared_weight"] for item in shared), 2),
        "shared_count": len(shared),
        "shared_holdings": shared,
    }


def compute_etf_overlap(holdings_with_data: list[dict]) -> dict[str, Any]:
    """Top-10 overlap for every pair of ETFs a portfolio actually owns."""
    covered: dict[str, dict[str, float]] = {}
    uncovered: list[str] = []
    for ticker in _held_etfs(holdings_with_data):
        weights = normalize_top_holdings(_fetch_top_holdings(ticker))
        if weights:
            covered[ticker] = weights
        else:
            uncovered.append(ticker)

    pairs = [
        {"a": a, "b": b, **overlap_between(covered[a], covered[b])}
        for a, b in combinations(sorted(covered), 2)
    ]
    pairs.sort(key=lambda pair: (-pair["overlap_pct"], pair["a"], pair["b"]))

    if not uncovered:
        data_quality = "complete"
    elif covered:
        data_quality = "partial"
    else:
        data_quality = "unavailable"

    return {
        "has_data": bool(pairs),
        "basis": BASIS,
        "score_method": SCORE_METHOD,
        "caveat": CAVEAT,
        "pairs": pairs,
        "etf_count": len(covered) + len(uncovered),
        "covered_tickers": sorted(covered),
        "uncovered_tickers": sorted(uncovered),
        "data_quality": data_quality,
    }

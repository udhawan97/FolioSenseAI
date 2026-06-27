"""
Peer-relative valuation — compare price zone vs own history AND vs peers.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.holding_intelligence import get_holding_intelligence
from app.services.timing_signal import get_cached_history_closes

logger = logging.getLogger(__name__)

_SECTOR_ETF_MAP: dict[str, str] = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Disc.": "XLY",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}


def _percentile_in_range(closes: list[float]) -> Optional[float]:
    if len(closes) < 20:
        return None
    current = closes[-1]
    window = closes[-252:] if len(closes) >= 252 else closes
    lo, hi = min(window), max(window)
    if hi <= lo:
        return 50.0
    return round((current - lo) / (hi - lo) * 100, 1)


def _peer_label(peers: list[str], sector_etf: Optional[str]) -> str:
    if peers:
        return f"vs {', '.join(peers[:3])}"
    if sector_etf:
        return f"vs {sector_etf} (sector)"
    return "vs market"


def compute_peer_relative(
    ticker: str,
    *,
    own_percentile: Optional[float] = None,
    zone: Optional[str] = None,
    stock_data: Optional[dict] = None,
    closes: Optional[list[float]] = None,
) -> dict:
    """
    Compare ticker valuation vs own range and vs peer set.
    """
    ticker = ticker.upper()
    intel = get_holding_intelligence(ticker, stock_data=stock_data)
    peers = list(intel.peer_tickers or [])[:3]

    if own_percentile is None and closes:
        own_percentile = _percentile_in_range(closes)
    if own_percentile is None and stock_data:
        price = stock_data.get("current_price")
        low = stock_data.get("fifty_two_week_low")
        high = stock_data.get("fifty_two_week_high")
        try:
            if price and low and high and float(high) > float(low):
                own_percentile = round(
                    (float(price) - float(low)) / (float(high) - float(low)) * 100, 1
                )
        except (TypeError, ValueError):
            pass

    vs_own = own_percentile
    vs_own_label = "Unavailable"
    if vs_own is not None:
        if vs_own <= 25:
            vs_own_label = "Cheap vs own history"
        elif vs_own >= 75:
            vs_own_label = "Rich vs own history"
        else:
            vs_own_label = "Mid-range vs own history"

    sector_etf = None
    if intel.sectors:
        sector_etf = _SECTOR_ETF_MAP.get(intel.sectors[0].name)
    if not sector_etf and stock_data:
        sector_etf = _SECTOR_ETF_MAP.get(str(stock_data.get("sector") or ""))

    peer_percentiles: list[float] = []
    compare_tickers = peers if peers else ([sector_etf] if sector_etf else [])
    for pt in compare_tickers:
        if pt.upper() == ticker:
            continue
        p_closes = get_cached_history_closes(pt.upper())
        pct = _percentile_in_range(p_closes)
        if pct is not None:
            peer_percentiles.append(pct)

    vs_peer_median: Optional[float] = None
    peer_comparison = "unavailable"
    if peer_percentiles and vs_own is not None:
        vs_peer_median = round(sum(peer_percentiles) / len(peer_percentiles), 1)
        diff = vs_own - vs_peer_median
        if diff <= -12:
            peer_comparison = "cheaper_than_peers"
        elif diff >= 12:
            peer_comparison = "richer_than_peers"
        else:
            peer_comparison = "in_line_with_peers"

    peer_label = _peer_label(peers, sector_etf)

    tip_body = (
        f"Own range percentile: {vs_own or 'n/a'}. "
        f"Peer median percentile: {vs_peer_median or 'n/a'}. "
        "Compares where price sits in each fund's recent trading band."
    )

    return {
        "vs_own_range": vs_own,
        "vs_own_label": vs_own_label,
        "vs_peer_median": vs_peer_median,
        "peer_comparison": peer_comparison,
        "peer_label": peer_label,
        "peer_tickers": compare_tickers[:3],
        "zone": zone,
        "tip_title": "Vs peers",
        "tip_body": tip_body,
        "source_fields": ["price_history", "peer_tickers"],
    }


def peer_valuation_nudge(peer: dict, action: str) -> int:
    """Small score adjustment for valuation component based on peer comparison."""
    comparison = peer.get("peer_comparison")
    if comparison == "cheaper_than_peers" and action == "add":
        return 6
    if comparison == "richer_than_peers" and action == "trim":
        return 6
    if comparison == "richer_than_peers" and action == "add":
        return -5
    if comparison == "cheaper_than_peers" and action == "trim":
        return -4
    return 0

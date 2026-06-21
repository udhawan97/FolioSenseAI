"""
app/services/analyst_recommendation.py

Analyst consensus recommendation for portfolio holdings.
Primary provider: yfinance (Yahoo Finance consensus data).
Swap _fetch_from_yfinance() to replace the provider without touching callers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# Quote types that carry no analyst coverage — treat as not-rated
_NO_COVERAGE_TYPES = {"etf", "mutualfund", "cryptocurrency", "fund"}

_REC_KEY_TO_ACTION: dict[str, str] = {
    "strong_buy":  "buy",
    "buy":         "buy",
    "hold":        "hold",
    "underperform": "sell",
    "sell":        "sell",
    "strong_sell": "sell",
}

_ACTION_LABEL: dict[str, str] = {
    "buy":       "Buy",
    "hold":      "Hold",
    "sell":      "Sell",
    "not-rated": "Not rated",
}


@dataclass
class AnalystRec:
    ticker: str
    action: str                      # buy | hold | sell | not-rated
    label: str                       # Buy | Hold | Sell | Not rated
    analyst_count: Optional[int]
    recommendation_mean: Optional[float]
    target_price: Optional[float]
    target_upside_pct: Optional[float]
    subtext: str                     # e.g. "18 analysts · PT +12%"
    source: str


def _not_rated(ticker: str) -> AnalystRec:
    return AnalystRec(
        ticker=ticker,
        action="not-rated",
        label="Not rated",
        analyst_count=None,
        recommendation_mean=None,
        target_price=None,
        target_upside_pct=None,
        subtext="Consensus unavailable",
        source="yfinance",
    )


def _build_subtext(count: Optional[int], upside_pct: Optional[float]) -> str:
    parts: list[str] = []
    if count:
        parts.append(f"{count} analyst{'s' if count != 1 else ''}")
    if upside_pct is not None:
        sign = "+" if upside_pct >= 0 else ""
        parts.append(f"PT {sign}{upside_pct:.0f}%")
    return " · ".join(parts) if parts else "Consensus unavailable"


def _action_from_mean(mean: float) -> str:
    if mean <= 2.0:
        return "buy"
    if mean <= 3.5:
        return "hold"
    return "sell"


def _fetch_from_yfinance(ticker: str) -> AnalystRec:
    """
    Pull analyst consensus from Yahoo Finance.
    Returns not-rated for ETFs, crypto, and any missing data.
    """
    info = yf.Ticker(ticker).info

    quote_type = str(info.get("quoteType") or "").lower()
    if quote_type in _NO_COVERAGE_TYPES:
        return _not_rated(ticker)

    # Determine action from recommendationKey (preferred) or mean score (fallback)
    rec_key = str(info.get("recommendationKey") or "").lower()
    action = _REC_KEY_TO_ACTION.get(rec_key, "")

    if not action:
        mean_raw = info.get("recommendationMean")
        if mean_raw is None:
            return _not_rated(ticker)
        action = _action_from_mean(float(mean_raw))

    count = info.get("numberOfAnalystOpinions")
    count = int(count) if count is not None else None

    target_raw = info.get("targetMeanPrice") or info.get("targetMedianPrice")
    target = round(float(target_raw), 2) if target_raw is not None else None

    current = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
    upside_pct: Optional[float] = None
    if target is not None and current > 0:
        upside_pct = round((target - current) / current * 100, 1)

    mean_val = info.get("recommendationMean")
    mean_val = round(float(mean_val), 2) if mean_val is not None else None

    return AnalystRec(
        ticker=ticker,
        action=action,
        label=_ACTION_LABEL[action],
        analyst_count=count,
        recommendation_mean=mean_val,
        target_price=target,
        target_upside_pct=upside_pct,
        subtext=_build_subtext(count, upside_pct),
        source="yfinance",
    )


def get_analyst_recommendation(ticker: str) -> AnalystRec:
    """
    Return analyst consensus for a single ticker.
    Always returns a result — falls back to not-rated on any error.
    """
    ticker = ticker.upper()
    try:
        return _fetch_from_yfinance(ticker)
    except Exception as exc:
        logger.warning("Analyst rec fetch failed for %s: %s", ticker, exc)
        return _not_rated(ticker)


def rec_to_dict(rec: AnalystRec) -> dict:
    """Serialize AnalystRec to a JSON-safe dict."""
    return {
        "ticker": rec.ticker,
        "action": rec.action,
        "label": rec.label,
        "analyst_count": rec.analyst_count,
        "recommendation_mean": rec.recommendation_mean,
        "target_price": rec.target_price,
        "target_upside_pct": rec.target_upside_pct,
        "subtext": rec.subtext,
        "source": rec.source,
    }

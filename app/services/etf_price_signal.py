"""
ETF price-zone signal from current price and historical closes.

Intentionally price-history based rather than analyst-target based:
ETFs rarely have useful target prices, but Yahoo reliably exposes quote
history and moving-average / range fields for most funds.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Iterable, Mapping

from app.services import market_data

logger = logging.getLogger(__name__)


def _first_number(data: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number > 0:
            return number
    return None


def _clean_numbers(values: Iterable[Any]) -> list[float]:
    cleaned: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number > 0:
            cleaned.append(number)
    return cleaned


def _label_from_percentile(percentile: float | None) -> str:
    if percentile is None:
        return "Unavailable"
    if percentile <= 25:
        return "Bargain"
    if percentile <= 60:
        return "Fair"
    if percentile <= 80:
        return "Elevated"
    return "Rich"


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 1)


def _build_data_warnings(
    current: float | None,
    close_values: list[float],
    basis: str,
) -> list[str]:
    """Return machine-readable warning keys for data quality issues."""
    warnings: list[str] = []
    n = len(close_values)
    if basis == "1Y percentile" and n < 50:
        warnings.append(f"sparse_history:{n}_days")
    if current is not None and close_values:
        hist_min = min(close_values)
        hist_max = max(close_values)
        if current < hist_min * 0.5:
            warnings.append("price_below_history_range")
            logger.warning(
                "ETF price signal: current=%.4f is below half the 1Y min=%.4f "
                "— possible split-adjustment mismatch",
                current,
                hist_min,
            )
        elif current > hist_max * 2.0:
            warnings.append("price_above_history_range")
            logger.warning(
                "ETF price signal: current=%.4f is above double the 1Y max=%.4f "
                "— possible split-adjustment mismatch",
                current,
                hist_max,
            )
    return warnings


def _change_vs_lookback(current: float | None, closes: list[float], days: int) -> float | None:
    if current is None or len(closes) < days:
        return None
    return _pct(current - closes[-days], closes[-days])


def calculate_etf_price_signal(
    etf_data: Mapping[str, Any],
    closes: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """
    Return a compact price-zone signal for ETF table display.

    Primary signal: current price percentile against the last year of closes.
    Fallback signal: current position inside the 52-week range.
    """
    data = dict(etf_data)
    close_values = _clean_numbers(closes if closes is not None else [])
    current = _first_number(
        data, "current_price", "currentPrice", "regularMarketPrice", "navPrice", "previousClose"
    )
    if current is None and close_values:
        current = close_values[-1]

    low_52 = _first_number(data, "fiftyTwoWeekLow", "fifty_two_week_low")
    high_52 = _first_number(data, "fiftyTwoWeekHigh", "fifty_two_week_high")
    if (low_52 is None or high_52 is None) and close_values:
        low_52 = low_52 or min(close_values)
        high_52 = high_52 or max(close_values)

    percentile: float | None = None
    basis = "Unavailable"
    if current is not None and len(close_values) >= 20:
        percentile = round(
            sum(1 for close in close_values if close <= current) / len(close_values) * 100,
            1,
        )
        basis = "1Y percentile"
    elif current is not None and low_52 is not None and high_52 is not None and high_52 > low_52:
        percentile = round(max(0, min(100, (current - low_52) / (high_52 - low_52) * 100)), 1)
        basis = "52W range"

    data_warnings = _build_data_warnings(current, close_values, basis)

    # range_position is always returned as a supplementary metric regardless of the
    # primary signal basis.  When basis == "52W range", range_position == percentile
    # by construction, which is intentional — the UI displays them independently.
    range_position = None
    if current is not None and low_52 is not None and high_52 is not None and high_52 > low_52:
        range_position = round(max(0, min(100, (current - low_52) / (high_52 - low_52) * 100)), 1)

    ma_200 = _first_number(data, "twoHundredDayAverage", "two_hundred_day_average")
    if ma_200 is None and len(close_values) >= 200:
        ma_200 = sum(close_values[-200:]) / 200
    ma_50 = _first_number(data, "fiftyDayAverage", "fifty_day_average")
    if ma_50 is None and len(close_values) >= 50:
        ma_50 = sum(close_values[-50:]) / 50

    vs_200d = _pct((current - ma_200), ma_200) if current is not None and ma_200 else None
    vs_50d = _pct((current - ma_50), ma_50) if current is not None and ma_50 else None
    vs_30d_change = _change_vs_lookback(current, close_values, 30)
    vs_200d_change = _change_vs_lookback(current, close_values, 200)
    label = _label_from_percentile(percentile)

    missing_fields = []
    if current is None:
        missing_fields.append("currentPrice")
    if not close_values:
        missing_fields.append("history")
    if low_52 is None or high_52 is None:
        missing_fields.append("fiftyTwoWeekRange")
    if ma_200 is None:
        missing_fields.append("twoHundredDayAverage")

    price_range_bad = any(
        w in data_warnings for w in ("price_below_history_range", "price_above_history_range")
    )
    if price_range_bad:
        label = "Unavailable"
        percentile = None

    return {
        "priceZoneLabel": label,
        "percentile": percentile,
        "currentPrice": current,
        "lowPrice": low_52,
        "highPrice": high_52,
        "rangePositionPct": range_position,
        "vs200dPct": vs_200d,
        "vs50dPct": vs_50d,
        "vs30dChangePct": vs_30d_change,
        "vs200dChangePct": vs_200d_change,
        "basis": basis,
        "source": "yfinance",
        "missingFields": missing_fields,
        "dataWarnings": data_warnings,
    }


def fetch_etf_price_signal(
    ticker: str,
    info: Mapping[str, Any],
    closes: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Calculate the ETF price-zone signal, fetching a year of closes if none are given.

    Callers that already hold the history — a verdict scan batches it — pass it
    in; everyone else gets the seam's read, which is empty rather than raising
    when Yahoo is unreachable.
    """
    close_values = (
        _clean_numbers(closes)
        if closes is not None
        else market_data.get_closes(ticker, period="1y")
    )
    return calculate_etf_price_signal({"ticker": ticker, **dict(info)}, close_values)

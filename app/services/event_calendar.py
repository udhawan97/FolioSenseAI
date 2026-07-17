"""
Earnings & event calendar — cap confidence near earnings for stocks.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from app.services.log_safety import sanitize_for_log

logger = logging.getLogger(__name__)

_EARNINGS_WINDOW_DAYS = 14
_ADD_CONF_CAP_NEAR_EARNINGS = 55
_EARNINGS_TABLE_LIMIT = 8
_BEAT_LOOKBACK_QUARTERS = 4


def _parse_earnings_date(info: dict) -> Optional[date]:
    for key in ("earningsDate", "earningsTimestamp", "mostRecentQuarter"):
        raw = info.get(key)
        if raw is None:
            continue
        try:
            if isinstance(raw, (list, tuple)) and raw:
                raw = raw[0]
            if hasattr(raw, "date"):
                return raw.date() if hasattr(raw, "date") else raw
            if isinstance(raw, (int, float)):
                return datetime.fromtimestamp(raw, tz=timezone.utc).date()
            if isinstance(raw, str):
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except (TypeError, ValueError, OSError):
            continue
    return None


def fetch_next_earnings(ticker: str) -> Optional[date]:
    """Fetch next earnings date from yfinance info (cached per call site)."""
    try:
        from app.services.stock_service import get_ticker_info
        info = get_ticker_info(ticker)
        return _parse_earnings_date(info)
    except Exception as exc:
        logger.debug(
            "Earnings fetch failed for %s: %s", sanitize_for_log(ticker), type(exc).__name__
        )
        return None


def _fetch_earnings_table(ticker: str):
    """yfinance's earnings table: one row per quarter, estimate + surprise."""
    import yfinance as yf

    return yf.Ticker(ticker).get_earnings_dates(limit=_EARNINGS_TABLE_LIMIT)


def _parse_earnings_table(
    table, on_date: date, *, lookback_quarters: int = _BEAT_LOOKBACK_QUARTERS
) -> dict | None:
    """Estimate for ``on_date`` plus how often the last quarters beat.

    Returns None unless the table actually carries a row for that date — an
    estimate attached to the wrong quarter is worse than no estimate.
    """
    if table is None or getattr(table, "empty", True):
        return None

    estimate = None
    matched = False
    for stamp, row in table.iterrows():
        try:
            row_date = stamp.date()
        except AttributeError:
            continue
        if row_date != on_date:
            continue
        matched = True
        raw = row.get("EPS Estimate")
        if raw is not None and not _is_nan(raw):
            estimate = round(float(raw), 4)
        break

    if not matched:
        return None

    # Surprise is only populated once a quarter has actually reported.
    surprises = [
        float(value)
        for value in table.get("Surprise(%)", [])
        if value is not None and not _is_nan(value)
    ][:lookback_quarters]

    return {
        "eps_estimate": estimate,
        "beats": sum(1 for s in surprises if s > 0),
        "quarters": len(surprises),
    }


def _is_nan(value) -> bool:
    try:
        return value != value  # NaN is the only value unequal to itself
    except Exception:  # pylint: disable=broad-except
        return False


def fetch_earnings_estimate(ticker: str, on_date: date) -> dict | None:
    """EPS estimate and recent beat record for a ticker's ``on_date`` report."""
    try:
        return _parse_earnings_table(_fetch_earnings_table(ticker), on_date)
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug(
            "Earnings estimate fetch failed for %s: %s",
            sanitize_for_log(ticker),
            type(exc).__name__,
        )
        return None


def build_event_context(
    ticker: str,
    *,
    security_type: str = "STOCK",
    earnings_date: Optional[date] = None,
) -> dict | None:
    """Return event context if earnings within window (stocks only)."""
    if security_type == "ETF":
        return None

    if earnings_date is None:
        earnings_date = fetch_next_earnings(ticker)
    if earnings_date is None:
        return None

    today = date.today()
    days_until = (earnings_date - today).days
    if days_until < 0 or days_until > _EARNINGS_WINDOW_DAYS:
        return None

    return {
        "event_type": "earnings",
        "date": earnings_date.isoformat(),
        "days_until": days_until,
        "label": f"Earnings in {days_until} day{'s' if days_until != 1 else ''}",
        "confidence_cap": _ADD_CONF_CAP_NEAR_EARNINGS,
        "risk_note": "Earnings within 2 weeks — volatility and gap risk are elevated",
        "wait_reason": "Consider waiting for earnings before adding",
        "tip_title": "Upcoming earnings",
        "tip_body": (
            f"Next earnings around {earnings_date.strftime('%b %d')}. "
            "Confidence is capped and Add calls may suggest waiting — "
            "post-earnings price often reveals the real trend."
        ),
        "source_fields": ["earningsDate"],
    }


def apply_earnings_cap(confidence: int, action: str, event: dict | None) -> tuple[int, list[str]]:
    """Cap confidence and return extra risks when near earnings."""
    if not event or action == "needs-data":
        return confidence, []
    risks: list[str] = []
    cap = event.get("confidence_cap")
    new_conf = confidence
    if cap is not None and action == "add" and confidence > cap:
        new_conf = cap
        risks.append(event.get("risk_note", "Earnings soon"))
    elif event.get("days_until", 99) <= _EARNINGS_WINDOW_DAYS:
        risks.append(event.get("risk_note", "Earnings soon"))
    return new_conf, risks

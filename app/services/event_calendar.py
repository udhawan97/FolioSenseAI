"""
Earnings & event calendar — cap confidence near earnings for stocks.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from app.services import market_data
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
    """Fetch next earnings date out of the shared `.info` record (cached there)."""
    try:
        from app.services.stock_service import get_ticker_info
        info = get_ticker_info(ticker)
        return _parse_earnings_date(info)
    except Exception as exc:
        logger.debug(
            "Earnings fetch failed for %s: %s", sanitize_for_log(ticker), type(exc).__name__
        )
        return None


def _fetch_earnings_quarters(ticker: str) -> list[dict]:
    """One row per reported/scheduled quarter, newest first: date, estimate, surprise."""
    return market_data.get_earnings_estimates(ticker, limit=_EARNINGS_TABLE_LIMIT)


def _parse_earnings_quarters(
    quarters: list[dict], on_date: date, *, lookback_quarters: int = _BEAT_LOOKBACK_QUARTERS
) -> dict | None:
    """Estimate for ``on_date`` plus how often the last quarters beat.

    Returns None unless the rows actually carry that date — an estimate attached
    to the wrong quarter is worse than no estimate. A quarter that has not
    reported yet carries no surprise, which the seam already reads as None.
    """
    matched = next((q for q in quarters or [] if q["date"] == on_date), None)
    if matched is None:
        return None

    estimate = matched["eps_estimate"]
    surprises = [
        q["surprise_pct"] for q in quarters if q["surprise_pct"] is not None
    ][:lookback_quarters]

    return {
        "eps_estimate": round(estimate, 4) if estimate is not None else None,
        "beats": sum(1 for s in surprises if s > 0),
        "quarters": len(surprises),
    }


def fetch_earnings_estimate(ticker: str, on_date: date) -> dict | None:
    """EPS estimate and recent beat record for a ticker's ``on_date`` report."""
    try:
        return _parse_earnings_quarters(_fetch_earnings_quarters(ticker), on_date)
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

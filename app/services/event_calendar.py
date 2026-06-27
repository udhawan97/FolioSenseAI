"""
Earnings & event calendar — cap confidence near earnings for stocks.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_EARNINGS_WINDOW_DAYS = 14
_ADD_CONF_CAP_NEAR_EARNINGS = 55


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
        import yfinance as yf
        info = yf.Ticker(ticker.upper()).info or {}
        return _parse_earnings_date(info)
    except Exception as exc:
        logger.debug("Earnings fetch failed for %s: %s", ticker, type(exc).__name__)
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

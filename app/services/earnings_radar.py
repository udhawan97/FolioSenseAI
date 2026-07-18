"""
Earnings radar — surface upcoming earnings dates for a set of tickers.

Reuses ``event_calendar``'s date fetching/parsing and ``stock_service``'s
cached yfinance info. Each ticker's next earnings date is cached as an ISO
string (or None) so the days-until countdown recomputes correctly on every
read — a date cached yesterday still reports the right "in N days" today.

Fully useful without any AI dependency; this is deterministic on-device data.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from app.services.event_calendar import fetch_earnings_estimate, fetch_next_earnings
from app.services.log_safety import sanitize_for_log
from app.services.security_type import SecurityType, classify_security
from app.services.stock_service import (
    get_ticker_info,
    normalize_ticker,
    ticker_shape_is_safe,
)
from app.services.ttl_cache import ttl_cache

logger = logging.getLogger(__name__)

_MAX_WORKERS = 8
_FETCH_TIMEOUT = 15.0             # seconds for the concurrent fan-out
_RADAR_TTL = 6 * 60 * 60         # 6 h — earnings dates move quarterly, not intraday
_DEFAULT_WINDOW_DAYS = 30


def _label(days_until: int) -> str:
    """Human-readable countdown for a non-negative day delta."""
    if days_until == 0:
        return "Today"
    if days_until == 1:
        return "Tomorrow"
    return f"In {days_until} days"


@ttl_cache(ttl=_RADAR_TTL)
def _resolve_earnings(symbol: str) -> dict | None:
    """Next earnings date and consensus estimate for one normalized symbol.

    Cached for ``_RADAR_TTL`` as one record — the date and the estimate come
    from different yfinance calls but are useless apart, and resolving them
    together keeps the fan-out to a single pass. The record holds the *date*,
    not the days-until, so an entry stays correct as the calendar advances.

    Non-stocks (ETFs/funds/cash/crypto) and tickers with no known date resolve
    to None, which is remembered like any other answer so a flaky or irrelevant
    ticker isn't re-classified or re-scraped on every call.
    """
    resolved: dict | None = None
    try:
        info = get_ticker_info(symbol)
        if classify_security(symbol, info) == SecurityType.STOCK:
            earnings = fetch_next_earnings(symbol)
            if earnings is not None:
                resolved = {
                    "iso": earnings.isoformat(),
                    # A date with no estimate is still worth showing.
                    "estimate": fetch_earnings_estimate(symbol, earnings),
                }
    except Exception as exc:  # pylint: disable=broad-except
        # One bad ticker must never break the fan-out. Swallowing it here also
        # means None is *returned*, so it gets remembered and isn't retried on
        # every call until the TTL lapses.
        logger.debug(
            "earnings_radar: resolve failed; ticker=%s exception_type=%s",
            sanitize_for_log(symbol), type(exc).__name__,
        )
    return resolved


def get_earnings_events(
    tickers: list[str], window_days: int = _DEFAULT_WINDOW_DAYS
) -> list[dict]:
    """Upcoming-earnings events within ``window_days``, soonest first.

    Each event is ``{ticker, date (ISO), days_until, label}``. A ticker is
    omitted when it is not a stock, has no known earnings date, or its next
    date falls outside ``[0, window_days]`` — the lower bound intentionally
    drops the *past* dates that yfinance's ``mostRecentQuarter`` fallback can
    return. One bad ticker never blocks or crashes the others.
    """
    seen: set[str] = set()
    symbols: list[str] = []
    for raw in tickers:
        if not ticker_shape_is_safe(raw):
            continue
        symbol = normalize_ticker(raw)
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    if not symbols:
        return []

    resolved: dict[str, dict | None] = {}
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(symbols))) as pool:
        futures = {pool.submit(_resolve_earnings, s): s for s in symbols}
        try:
            for future in as_completed(futures, timeout=_FETCH_TIMEOUT):
                symbol = futures[future]
                try:
                    resolved[symbol] = future.result()
                except Exception as exc:  # pylint: disable=broad-except
                    logger.debug(
                        "earnings_radar: future exception; ticker=%s exception_type=%s",
                        sanitize_for_log(symbol), type(exc).__name__,
                    )
                    resolved[symbol] = None
        except TimeoutError:
            logger.warning(
                "earnings_radar: fan-out timed out after %ss; %d/%d tickers completed",
                _FETCH_TIMEOUT, len(resolved), len(symbols),
            )

    today = date.today()
    events: list[dict] = []
    for symbol in symbols:
        record = resolved.get(symbol)
        iso = (record or {}).get("iso")
        if not iso:
            continue
        try:
            earnings_date = date.fromisoformat(iso)
        except ValueError:
            continue
        days_until = (earnings_date - today).days
        if days_until < 0 or days_until > window_days:
            continue
        estimate = record.get("estimate") or {}
        events.append({
            "ticker": symbol,
            "date": iso,
            "days_until": days_until,
            "label": _label(days_until),
            "eps_estimate": estimate.get("eps_estimate"),
            "beats": estimate.get("beats"),
            "quarters": estimate.get("quarters"),
        })

    events.sort(key=lambda event: (event["days_until"], event["ticker"]))
    return events

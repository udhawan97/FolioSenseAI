"""
Fundamentals over time — revenue, profit, and EPS from the numbers a company
actually filed, via SEC XBRL company facts (keyless, public domain).

Two traps the raw feed sets, both handled here:
  * A 10-K reports the current year AND prior-year comparatives under one
    ``fy``, so ``fy`` is the *report* year, not the period. The ``frame``
    (``CY2024``) is the real period key; quarterly frames (``CY2024Q3``) look
    annual but aren't.
  * Revenue migrated tags — the legacy ``Revenues`` gave way to
    ``RevenueFromContractWithCustomerExcludingAssessedTax`` around 2018. Reading
    one tag alone silently truncates the history, so both are merged.

Only operating companies file financials. Funds and ETFs have no CIK and no
facts — callers get an honest empty, never a fabricated series.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from app.services.edgar_service import fetch_company_facts, get_cik
from app.services.ttl_cache import ttl_cache

logger = logging.getLogger(__name__)

_FUNDAMENTALS_TTL = 24 * 3600  # facts change quarterly at most
_DEFAULT_YEARS = 6

# Legacy tag first only for backfill; the modern tag always wins a shared year.
_REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
)
_NET_INCOME_TAG = "NetIncomeLoss"
_EPS_TAG = "EarningsPerShareDiluted"

_ANNUAL_FRAME = re.compile(r"^CY(\d{4})$")  # rejects the CY2024Q3 quarterlies


def _annual_series(rows: list[dict]) -> dict[int, float]:
    """Full-year values keyed by period year, most-recent filing winning.

    Rows arrive oldest-filing-first, so iterating in order and letting later
    rows overwrite gives the latest restatement of any given year.
    """
    series: dict[int, tuple[int, float]] = {}
    for row in rows or []:
        if row.get("form") != "10-K" or row.get("fp") != "FY":
            continue
        match = _ANNUAL_FRAME.match(str(row.get("frame", "")))
        if not match:
            continue
        try:
            value = float(row["val"])
        except (KeyError, TypeError, ValueError):
            continue
        year = int(match.group(1))
        report_fy = int(row.get("fy") or 0)
        # Keep the value from the most recent report of this period.
        if year not in series or report_fy >= series[year][0]:
            series[year] = (report_fy, value)
    return {year: value for year, (_fy, value) in series.items()}


def _concept_series(gaap: dict, tag: str) -> dict[int, float]:
    units = (gaap.get(tag) or {}).get("units") or {}
    for rows in units.values():  # a concept has one unit (USD, USD/shares)
        return _annual_series(rows)
    return {}


def _revenue_series(gaap: dict) -> dict[int, float]:
    """Merge the revenue tags: the modern tag wins, the legacy one backfills."""
    merged: dict[int, float] = {}
    for tag in reversed(_REVENUE_TAGS):  # legacy first, modern overwrites
        merged.update(_concept_series(gaap, tag))
    return merged


def _build_periods(gaap: dict, *, years: int = _DEFAULT_YEARS) -> list[dict]:
    revenue = _revenue_series(gaap)
    net_income = _concept_series(gaap, _NET_INCOME_TAG)
    eps = _concept_series(gaap, _EPS_TAG)

    all_years = sorted(set(revenue) | set(net_income) | set(eps))[-years:]
    periods = []
    for year in all_years:
        rev = revenue.get(year)
        net = net_income.get(year)
        margin = (
            round(net / rev * 100, 1)
            if rev not in (None, 0) and net is not None
            else None
        )
        periods.append(
            {
                "year": year,
                "revenue": rev,
                "net_income": net,
                "eps_diluted": eps.get(year),
                "net_margin": margin,
            }
        )
    return periods


def _empty(ticker: str, quality: str) -> dict:
    return {
        "ticker": ticker,
        "periods": [],
        "data_quality": quality,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@ttl_cache(
    ttl=_FUNDAMENTALS_TTL,
    # ``years`` only trims a series we already hold, so it stays out of the key
    # — the same company answers every window from one stored fetch.
    key=lambda ticker, years: (ticker or "").strip().upper(),
    # Only a real series is worth a day. Every empty answer here — not a filer,
    # EDGAR down, unreadable facts — stays retryable.
    cache_when=lambda result: bool(result["periods"]),
    copy=dict,
)
def get_fundamentals(
    ticker: str, *, years: int = _DEFAULT_YEARS, force_refresh: bool = False
) -> dict:
    """Annual revenue, net income, and diluted EPS for a company over time."""
    symbol = (ticker or "").strip().upper()
    if not symbol:
        return _empty(symbol, "live")

    cik = get_cik(symbol, force_refresh=force_refresh)
    if not cik:
        # Not an SEC filer (fund/ETF/foreign) — nothing to show, but not broken.
        return _empty(symbol, "live")

    raw = fetch_company_facts(cik)
    if not raw:
        return _empty(symbol, "unavailable")
    try:
        gaap = json.loads(raw)["facts"]["us-gaap"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return _empty(symbol, "unavailable")

    return {
        "ticker": symbol,
        "periods": _build_periods(gaap, years=years),
        "data_quality": "live",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

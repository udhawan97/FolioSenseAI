"""
Insider activity — SEC Form 4, straight from the filer's own hand.

Every officer and director must report trades in their company's stock within
two business days, so this is the rare dataset that is complete, keyless, and
legally can't be late. The nuance is in the transaction codes: most Form 4s are
compensation plumbing (option exercises, tax withholding), not conviction.
Only open-market buys (P) and sales (S) are counted as a signal here; the rest
are listed with honest labels and kept out of the totals.

Funds and crypto have no insiders to report — callers get an empty, live
result, the same "nothing to show" honesty as the filings timeline.
"""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

from app.services.edgar_service import fetch_filing_document, get_recent_filings

logger = logging.getLogger(__name__)

_WINDOW_DAYS = 90
_MAX_FILINGS = 10  # one throttled fetch each; enough to cover a busy quarter
_ACTIVITY_TTL = 6 * 3600
_ACTIVITY_CACHE: dict[str, tuple[float, dict]] = {}

# SEC transaction codes. P and S are real money changing hands on the open
# market; everything else is plumbing or transfers.
_CODE_LABELS = {
    "P": ("buy", "Open-market buy"),
    "S": ("sell", "Open-market sale"),
    "M": ("other", "Option exercise"),
    "F": ("other", "Tax withholding"),
    "A": ("other", "Grant or award"),
    "G": ("other", "Gift"),
    "D": ("other", "Disposition to issuer"),
    "C": ("other", "Conversion"),
    "J": ("other", "Other acquisition/disposition"),
}


def _classify(code: str) -> tuple[str, str]:
    return _CODE_LABELS.get(code, ("other", f"Code {code}"))


def _raw_doc_url(viewer_url: str) -> str:
    """The submissions feed points at the XSL-rendered viewer; the raw XML
    lives one directory up (…/xslF345X06/form4.xml → …/form4.xml)."""
    parts = str(viewer_url).rsplit("/", 2)
    if len(parts) == 3 and parts[1].startswith("xsl"):
        return f"{parts[0]}/{parts[2]}"
    return viewer_url


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    value = el.find("value")
    node = value if value is not None else el
    return (node.text or "").strip()


def _number(el: ET.Element | None) -> float | None:
    raw = _text(el)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _flag(rel: ET.Element, tag: str) -> bool:
    # SEC schema booleans arrive as "true" or "1" depending on the filer's tool.
    return _text(rel.find(tag)) in ("true", "1")


def _owner_and_role(root: ET.Element) -> tuple[str, str]:
    owner = root.find("./reportingOwner/reportingOwnerId/rptOwnerName")
    rel = root.find("./reportingOwner/reportingOwnerRelationship")
    role = ""
    if rel is not None:
        role = _text(rel.find("officerTitle"))
        if not role and _flag(rel, "isDirector"):
            role = "Director"
        if not role and _flag(rel, "isTenPercentOwner"):
            role = "10% owner"
    return _text(owner) if owner is not None else "", role


def _parse_form4(xml_text: str) -> list[dict]:
    """Common-stock transactions from one Form 4, or [] if unreadable.

    Refuses documents declaring a DTD or entities — same guard as the Treasury
    feed; a legitimate Form 4 never carries either.
    """
    text = xml_text or ""
    # Whole-document scan: a comment can legally pad the prolog, so a
    # fixed-size head check would be bypassable.
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    owner, role = _owner_and_role(root)
    rows = []
    for tx in root.iter("nonDerivativeTransaction"):
        code = _text(tx.find("./transactionCoding/transactionCode"))
        tx_date = _text(tx.find("transactionDate"))
        shares = _number(tx.find("./transactionAmounts/transactionShares"))
        if not code or not tx_date or shares is None:
            continue
        rows.append(
            {
                "date": tx_date,
                "owner": owner,
                "role": role,
                "code": code,
                "shares": shares,
                "price": _number(
                    tx.find("./transactionAmounts/transactionPricePerShare")
                ),
            }
        )
    return rows


def _summarize(transactions: list[dict], *, window_days: int = _WINDOW_DAYS) -> dict:
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    recent = sorted(
        (tx for tx in transactions if tx.get("date", "") >= cutoff),
        key=lambda tx: tx["date"],
        reverse=True,
    )

    buys = sells = 0
    bought_value = sold_value = 0.0
    enriched = []
    for tx in recent:
        action, label = _classify(tx["code"])
        value = (
            round(tx["shares"] * tx["price"], 2)
            if tx.get("price") is not None
            else None
        )
        if action == "buy":
            buys += 1
            bought_value += value or 0.0
        elif action == "sell":
            sells += 1
            sold_value += value or 0.0
        enriched.append({**tx, "action": action, "code_label": label, "value": value})

    return {
        "window_days": window_days,
        "buys": buys,
        "sells": sells,
        "bought_value": round(bought_value, 2),
        "sold_value": round(sold_value, 2),
        "transactions": enriched,
    }


def get_insider_activity(ticker: str, *, force_refresh: bool = False) -> dict:
    """Open-market insider trades for a ticker over the last 90 days."""
    symbol = (ticker or "").strip().upper()
    empty = _summarize([])

    cached = _ACTIVITY_CACHE.get(symbol)
    if not force_refresh and cached and cached[0] > time.monotonic():
        return dict(cached[1])

    try:
        filings = get_recent_filings(symbol, forms=("4",), limit=_MAX_FILINGS)
        transactions = []
        for filing in filings:
            doc = fetch_filing_document(_raw_doc_url(filing.get("url", "")))
            if not doc:
                continue
            for tx in _parse_form4(doc):
                transactions.append({**tx, "url": filing.get("url", "")})
        activity = {
            "ticker": symbol,
            **_summarize(transactions),
            "data_quality": "live",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug(
            "Insider activity failed; ticker=%s exception_type=%s",
            symbol,
            type(exc).__name__,
        )
        return {
            "ticker": symbol,
            **empty,
            "data_quality": "unavailable",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    _ACTIVITY_CACHE[symbol] = (time.monotonic() + _ACTIVITY_TTL, activity)
    return dict(activity)

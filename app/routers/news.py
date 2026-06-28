"""
app/routers/news.py

News zone endpoints.

GET /api/news/feed   — Always available (local-safe). Returns grouped news
                       for all active holdings + watchlist, ordered by sector
                       then ticker.  Empty/no-news holdings are still listed so
                       the UI can show a meaningful empty state per holding.

GET /api/news/themes — Claude mode only. Heartbeat-gated; cached by headline
                       signature so re-opening the zone costs 0 extra tokens;
                       returns HTTP 503 when Claude is unreachable or fails.
"""
import hashlib
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Holding
from app.services.ai_service import generate_news_themes, get_cached_claude_heartbeat
from app.services.news_service import (
    build_themes_snapshot,
    fetch_portfolio_news,
)
from app.services.stock_service import get_ticker_info, normalize_ticker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/news", tags=["news"])

# ── In-memory themes cache ─────────────────────────────────────────────────────
# Keyed by SHA-1 of the headline set — identical feeds cost 0 Claude tokens.
_THEMES_CACHE: dict[str, tuple[float, dict]] = {}
_THEMES_TTL = 30 * 60  # 30 min


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _get_active_holdings(db: Session, portfolio_id: int = 1) -> list[Holding]:
    """Return all active holdings for a portfolio."""
    return (
        db.query(Holding)
        .filter(Holding.portfolio_id == portfolio_id, Holding.is_active.is_(True))
        .all()
    )


def _holding_info_brief(ticker: str) -> dict:
    """
    Fetch a minimal subset of yfinance .info for display purposes.
    Returns {company_name, sector} — fails gracefully to empty strings.
    """
    try:
        info = get_ticker_info(ticker)
        return {
            "company_name": (
                info.get("longName") or info.get("shortName") or ticker
            ),
            "sector": info.get("sector") or info.get("quoteType") or "",
        }
    except Exception:  # pylint: disable=broad-except
        return {"company_name": ticker, "sector": ""}


def _headlines_signature(news_by_ticker: dict[str, list[dict]]) -> str:
    """SHA-1 over the sorted headline set — themes cache key."""
    titles = sorted(
        item["title"]
        for items in news_by_ticker.values()
        for item in items
    )
    return hashlib.sha1(  # noqa: S324 — non-security digest
        "\n".join(titles).encode(), usedforsecurity=False
    ).hexdigest()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/feed")
async def get_news_feed(portfolio_id: int = 1, db: Session = Depends(get_db)):
    """
    Grouped news feed for all active holdings + watchlist.
    Always available — no AI required, no heartbeat gate.
    Holdings are ordered by sector then watchlist flag then ticker so related
    companies cluster together in the UI.
    """
    holdings  = _get_active_holdings(db, portfolio_id)
    tickers   = [normalize_ticker(h.ticker) for h in holdings]

    news_by_ticker = fetch_portfolio_news(tickers) if tickers else {}

    enriched: list[dict] = []
    for h in holdings:
        ticker = normalize_ticker(h.ticker)
        brief  = _holding_info_brief(ticker)
        enriched.append({
            "ticker":       ticker,
            "company_name": brief["company_name"],
            "sector":       brief["sector"],
            "is_watchlist": bool(h.is_watchlist),
            "items":        news_by_ticker.get(ticker, []),
        })

    # Sector → watchlist flag → ticker (empty sector sorts last)
    enriched.sort(key=lambda h: (
        h["sector"] or "~",
        int(h["is_watchlist"]),
        h["ticker"],
    ))

    return {
        "holdings":     enriched,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/themes")
async def get_news_themes(portfolio_id: int = 1, db: Session = Depends(get_db)):
    """
    Claude-mode news themes: portfolio briefing + cross-holding clusters.
    Heartbeat-gated — returns 503 when Claude is unreachable.
    Cached by headline signature so re-opening the zone costs 0 extra tokens.
    """
    heartbeat = get_cached_claude_heartbeat()
    if not heartbeat.get("live"):
        raise HTTPException(
            status_code=503,
            detail="Claude AI is not reachable; news themes unavailable.",
        )

    holdings = _get_active_holdings(db, portfolio_id)
    tickers  = [normalize_ticker(h.ticker) for h in holdings]

    news_by_ticker = fetch_portfolio_news(tickers) if tickers else {}

    holding_meta: dict[str, dict] = {
        normalize_ticker(h.ticker): {
            "is_watchlist": bool(h.is_watchlist),
            "shares":       float(h.shares or 0),
            "avg_cost":     float(h.avg_cost or 0),
        }
        for h in holdings
    }

    sig   = _headlines_signature(news_by_ticker)
    now   = time.monotonic()
    cached = _THEMES_CACHE.get(sig)
    if cached and cached[0] > now:
        result = dict(cached[1])
        result["from_cache"] = True
        return result

    snapshot = build_themes_snapshot(holding_meta, news_by_ticker)

    try:
        themes_data = generate_news_themes(snapshot)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "news_themes: Claude call failed; exception_type=%s", type(exc).__name__
        )
        raise HTTPException(
            status_code=503,
            detail="News themes generation failed; Claude returned an error.",
        ) from exc

    result = {
        "briefing":     themes_data["briefing"],
        "themes":       themes_data["themes"],
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    _THEMES_CACHE[sig] = (now + _THEMES_TTL, result)
    return result

"""
app/routers/ai.py
AI-powered summary endpoints using Claude.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AISummary
from app.services.ai_service import MODEL, generate_stock_summary
from app.services.stock_service import DEFAULT_HOLDINGS, get_all_quotes, get_stock_data

router = APIRouter(prefix="/api/ai", tags=["ai"])

CACHE_TTL = timedelta(hours=24)
PRICE_DRIFT_THRESHOLD = 0.05  # expire cache when price moves >5% from when it was generated


def _cache_is_fresh(cached: AISummary, current_price: float | None = None) -> bool:
    # getattr gives pyright concrete Python types instead of SQLAlchemy ColumnElement
    generated_at: datetime = getattr(cached, "generated_at")
    cached_price: float | None = getattr(cached, "price_when_generated")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if now - generated_at > CACHE_TTL:
        return False
    if current_price is not None and cached_price is not None and cached_price > 0:
        drift = abs(current_price - cached_price) / cached_price
        if drift > PRICE_DRIFT_THRESHOLD:
            return False
    return True


@router.get("/summary/{ticker}")
async def get_stock_summary(
    ticker: str,
    force_refresh: bool = False,
    db: Session = Depends(get_db),
):
    """
    Get AI summary for a single ticker.
    Checks the database cache first — only calls Claude if needed.
    Cache expires after 24 hours. Use force_refresh=true to bypass.
    """
    ticker = ticker.upper()

    if not force_refresh:
        cached = (
            db.query(AISummary)
            .filter(AISummary.ticker == ticker, AISummary.summary_type == "stock")
            .order_by(AISummary.generated_at.desc())
            .first()
        )
        if cached and _cache_is_fresh(cached):
            return {
                "ticker": ticker,
                "summary": cached.summary_text,
                "generated_at": cached.generated_at.isoformat(),
                "from_cache": True,
                "price_when_generated": cached.price_when_generated,
            }

    stock_data = get_stock_data(ticker)
    if stock_data.get("error"):
        raise HTTPException(status_code=404, detail=f"Cannot fetch data for {ticker}")

    summary_text = generate_stock_summary(stock_data)

    summary = AISummary(
        ticker=ticker,
        summary_type="stock",
        summary_text=summary_text,
        price_when_generated=stock_data["current_price"],
        model_used=MODEL,
    )
    db.add(summary)
    db.commit()

    return {
        "ticker": ticker,
        "summary": summary_text,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "from_cache": False,
        "price_when_generated": stock_data["current_price"],
    }


@router.get("/summaries/all")
async def get_all_summaries(db: Session = Depends(get_db)):
    """
    Get or generate summaries for all default holdings.
    Returns cached summaries immediately, generates new ones for missing or stale tickers.
    This endpoint may take 30-60 seconds if generating all summaries fresh.
    """
    results = {}

    quotes = {q["ticker"]: q for q in get_all_quotes()}

    for ticker in DEFAULT_HOLDINGS:
        current_price = quotes.get(ticker, {}).get("current_price")

        cached = (
            db.query(AISummary)
            .filter(AISummary.ticker == ticker, AISummary.summary_type == "stock")
            .order_by(AISummary.generated_at.desc())
            .first()
        )

        if cached and _cache_is_fresh(cached, current_price=current_price):
            results[ticker] = {"summary": cached.summary_text, "from_cache": True}
            continue

        stock_data = quotes.get(ticker, {})
        if stock_data and not stock_data.get("error"):
            summary_text = generate_stock_summary(stock_data)
            new_summary = AISummary(
                ticker=ticker,
                summary_type="stock",
                summary_text=summary_text,
                price_when_generated=stock_data.get("current_price"),
                model_used=MODEL,
            )
            db.add(new_summary)
            db.commit()
            results[ticker] = {"summary": summary_text, "from_cache": False}

    return {"summaries": results, "count": len(results)}

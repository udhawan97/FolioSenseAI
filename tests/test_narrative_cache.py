"""Interface tests for Portfolio narrative caching."""

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import AISummary, Base
from app.services.narrative_cache import NarrativeCache, portfolio_scope


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_portfolio_json_cache_is_isolated_validated_and_corruption_safe():
    db = make_db()
    cache = NarrativeCache(db, ttl=timedelta(hours=24))

    assert cache.store_json(portfolio_scope(1), "briefing", {"health": "one"}, "test")
    assert cache.store_json(portfolio_scope(2), "briefing", {"health": "two"}, "test")
    assert cache.get_json(portfolio_scope(1), "briefing") == {"health": "one"}
    assert cache.get_json(portfolio_scope(2), "briefing") == {"health": "two"}
    assert cache.get_json(
        portfolio_scope(1),
        "briefing",
        validator=lambda payload: payload.get("health") == "two",
    ) is None

    row = db.query(AISummary).filter_by(ticker="BOOK:1", summary_type="briefing").one()
    row.summary_text = "{not-json"
    row.generated_at = datetime.now().replace(microsecond=0) - timedelta(hours=25)
    db.commit()
    assert cache.get_json(portfolio_scope(1), "briefing") is None


def test_verdict_serialization_provenance_and_portfolio_cleanup_stay_inside_cache():
    db = make_db()
    cache = NarrativeCache(db)
    assert cache.store_verdict(
        portfolio_scope(7),
        "verdict:hold",
        "Stay patient.",
        None,
        "fallback",
    )

    cached = cache.get_verdict(portfolio_scope(7), "verdict:hold")
    assert cached == {"quip": "Stay patient.", "ai": None, "model_used": "fallback"}

    assert cache.delete_portfolio(7) == 1
    assert cache.get_verdict(portfolio_scope(7), "verdict:hold") is None


def test_fresh_many_batches_ticker_narratives_and_applies_price_drift():
    db = make_db()
    cache = NarrativeCache(db)
    cache.store_text("AAPL", "stock", "Apple", "test", price_when_generated=100)
    cache.store_text("MSFT", "stock", "Microsoft", "test", price_when_generated=100)

    fresh = cache.fresh_many(
        ["AAPL", "MSFT"],
        "stock",
        current_prices={"AAPL": 101, "MSFT": 120},
    )

    assert list(fresh) == ["AAPL"]
    assert fresh["AAPL"].summary_text == "Apple"

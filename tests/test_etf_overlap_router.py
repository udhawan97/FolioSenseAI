"""HTTP-level tests for GET /api/portfolio/etf-overlap.

Same shape as tests/test_fund_costs_router.py: only the portfolio router on a
bare FastAPI app with an in-memory SQLite DB. The overlap math is covered by
tests/test_etf_overlap.py; this file is about the router — ETF selection from
the merged quote metadata, the payload's caveat reaching HTTP, and 404s.
"""
# pylint: disable=redefined-outer-name,unused-argument
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.models import Base, Holding, Portfolio
from app.routers import portfolio as portfolio_router
from app.services import portfolio_valuation

_TOP_HOLDINGS = {
    "VOO": [{"symbol": "AAPL", "weight": 7.0}, {"symbol": "XOM", "weight": 2.0}],
    "QQQ": [{"symbol": "AAPL", "weight": 9.0}],
}

_FULL_QUOTES = {
    "VOO": {"quote_type": "ETF"},
    "QQQ": {"quote_type": "ETF"},
    "AAPL": {"quote_type": "EQUITY", "exchange": "NMS"},
}


def _make_db(tickers=("VOO", "QQQ", "AAPL")):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)  # pylint: disable=invalid-name
    db = Session()
    db.add(Portfolio(id=1, name="Test"))
    for ticker in tickers:
        db.add(Holding(portfolio_id=1, ticker=ticker, shares=10, avg_cost=50,
                       is_active=True, is_watchlist=False))
    db.commit()
    return db


def _fast_quotes(tickers):
    return [
        {"ticker": t, "name": t, "current_price": 100.0,
         "day_change": 0.0, "day_change_pct": 0.0}
        for t in tickers
    ]


@pytest.fixture
def make_client(monkeypatch):
    def _build(tickers=("VOO", "QQQ", "AAPL")):
        monkeypatch.setattr(portfolio_valuation, "get_portfolio_quotes", _fast_quotes)
        monkeypatch.setattr(
            portfolio_router,
            "get_all_quotes",
            lambda tickers: [{"ticker": t, **_FULL_QUOTES.get(t, {})} for t in tickers],
        )
        monkeypatch.setattr(
            "app.services.etf_overlap._fetch_top_holdings",
            lambda ticker: list(_TOP_HOLDINGS.get(ticker.upper(), [])),
        )
        db = _make_db(tickers)
        app = FastAPI()
        app.include_router(portfolio_router.router)
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    return _build


def test_etf_overlap_pairs_the_held_etfs_and_ignores_stocks(make_client):
    body = make_client().get("/api/portfolio/etf-overlap").json()

    assert body["has_data"] is True
    assert body["etf_count"] == 2
    assert len(body["pairs"]) == 1
    pair = body["pairs"][0]
    assert (pair["a"], pair["b"]) == ("QQQ", "VOO")
    assert pair["overlap_pct"] == 7.0
    assert pair["shared_holdings"][0]["symbol"] == "AAPL"


def test_etf_overlap_states_its_basis_over_http(make_client):
    body = make_client().get("/api/portfolio/etf-overlap").json()

    assert body["basis"] == "top_10_holdings"
    assert "top 10" in body["caveat"].lower()
    assert body["data_quality"] == "complete"


def test_etf_overlap_with_a_single_etf_is_empty_not_an_error(make_client):
    response = make_client(tickers=("VOO", "AAPL")).get("/api/portfolio/etf-overlap")

    assert response.status_code == 200
    body = response.json()
    assert body["has_data"] is False
    assert not body["pairs"]
    assert body["etf_count"] == 1


def test_etf_overlap_unknown_portfolio_404s(make_client):
    response = make_client().get("/api/portfolio/etf-overlap?portfolio_id=999")

    assert response.status_code == 404

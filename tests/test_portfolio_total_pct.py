# pylint: disable=protected-access

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Holding, Portfolio, RealizedTrade
from app.routers import portfolio as portfolio_router
from app.schemas import HoldingCreate


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(Portfolio(id=1, name="Test Portfolio"))
    session.commit()
    return session


def make_empty_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def add_holding(db, ticker, shares, avg_cost, is_active=True):
    db.add(
        Holding(
            portfolio_id=1,
            ticker=ticker,
            shares=shares,
            avg_cost=avg_cost,
            is_active=is_active,
        )
    )
    db.commit()


def add_trade(db, ticker, shares_sold, sale_price, avg_cost):
    db.add(
        RealizedTrade(
            portfolio_id=1,
            ticker=ticker,
            shares_sold=shares_sold,
            sale_price=sale_price,
            avg_cost=avg_cost,
            realized_gain=(sale_price - avg_cost) * shares_sold,
        )
    )
    db.commit()


def quote(ticker, price, day_change=0.0, day_change_pct=0.0):
    return {
        "ticker": ticker,
        "name": f"{ticker} Inc.",
        "current_price": price,
        "day_change": day_change,
        "day_change_pct": day_change_pct,
    }


def row_by_ticker(rows, ticker):
    return next(row for row in rows if row["ticker"] == ticker)


def test_open_holding_total_pct_uses_current_price(monkeypatch):
    db = make_db()
    add_holding(db, "OPEN", shares=10, avg_cost=100)
    monkeypatch.setattr(portfolio_router, "get_all_quotes", lambda _tickers: [quote("OPEN", 115)])

    rows, *_ = portfolio_router._compute_portfolio(1, db)

    assert row_by_ticker(rows, "OPEN")["total_return_pct"] == 15.0


def test_holding_daily_value_change_uses_share_count_times_quote_move(monkeypatch):
    db = make_db()
    add_holding(db, "VOO", shares=8.5, avg_cost=400)
    monkeypatch.setattr(
        portfolio_router,
        "get_all_quotes",
        lambda _tickers: [quote("VOO", 456.70, day_change=-1.32, day_change_pct=-0.29)],
    )

    rows, total_value, total_daily_change, _ = portfolio_router._compute_portfolio(1, db)
    row = row_by_ticker(rows, "VOO")

    assert total_value == 3881.95
    assert row["day_change"] == -1.32
    assert row["daily_value_change"] == -11.22
    assert total_daily_change == -11.22


def test_partial_sale_total_pct_combines_realized_and_unrealized(monkeypatch):
    db = make_db()
    add_holding(db, "MIX", shares=5, avg_cost=100)
    add_trade(db, "MIX", shares_sold=2, sale_price=130, avg_cost=100)
    add_trade(db, "MIX", shares_sold=3, sale_price=90, avg_cost=100)
    monkeypatch.setattr(portfolio_router, "get_all_quotes", lambda _tickers: [quote("MIX", 120)])

    rows, *_ = portfolio_router._compute_portfolio(1, db)

    # Realized: +30 over $500 sold basis. Unrealized: +100 over $500 remaining basis.
    assert row_by_ticker(rows, "MIX")["total_return_pct"] == 13.0


def test_realized_stats_weight_multiple_sells_by_quantity():
    db = make_db()
    add_trade(db, "SOLD", shares_sold=1, sale_price=150, avg_cost=100)
    add_trade(db, "SOLD", shares_sold=3, sale_price=110, avg_cost=100)

    stats = portfolio_router._realized_stats_by_ticker(1, db)["SOLD"]

    assert stats["shares_sold"] == 4
    assert stats["avg_sell_price"] == 120
    assert stats["avg_cost"] == 100
    assert stats["total_return_pct"] == 20


def test_missing_or_zero_basis_returns_none(monkeypatch):
    db = make_db()
    add_holding(db, "FREE", shares=10, avg_cost=0)
    add_trade(db, "ZERO", shares_sold=2, sale_price=50, avg_cost=0)
    monkeypatch.setattr(portfolio_router, "get_all_quotes", lambda _tickers: [quote("FREE", 20)])

    rows, *_ = portfolio_router._compute_portfolio(1, db)
    stats = portfolio_router._realized_stats_by_ticker(1, db)["ZERO"]

    assert row_by_ticker(rows, "FREE")["total_return_pct"] is None
    assert stats["total_return_pct"] is None


def test_default_portfolio_is_created_on_first_use(monkeypatch):
    db = make_empty_db()
    monkeypatch.setattr(portfolio_router.settings, "DEFAULT_HOLDINGS", ["VOO", "QQQ"])

    portfolio = portfolio_router._ensure_default_portfolio(db)

    holdings = db.query(Holding).order_by(Holding.ticker).all()
    assert portfolio.id == 1
    assert portfolio.name == "My Portfolio"
    assert [h.ticker for h in holdings] == ["QQQ", "VOO"]
    assert all(h.shares == 0 for h in holdings)


def test_holding_create_rejects_unsafe_ticker_characters():
    try:
        HoldingCreate(ticker="');x//", shares=1)
    except ValueError as exc:
        assert "Ticker may contain only" in str(exc)
    else:
        raise AssertionError("Unsafe ticker was accepted")


def test_holding_create_allows_common_yfinance_ticker_characters():
    assert HoldingCreate(ticker="brk.b", shares=1).ticker == "BRK.B"
    assert HoldingCreate(ticker="btc-usd", shares=1).ticker == "BTC-USD"

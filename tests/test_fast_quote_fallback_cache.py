"""
Regression test: get_fast_quote must cache its full-quote fallback under the fast key.

When the cheap snapshot carries no usable price, get_fast_quote falls back to
get_stock_data. Previously the fallback result was never stored under the fast key, so
every dashboard valuation refresh re-ran the snapshot network call for that ticker. The
fallback must now be cached so a second call is a pure cache hit.

No real network calls — the snapshot comes from the market-data seam's fake adapter.
"""
from app.services import stock_service


def test_fast_quote_fallback_is_cached(monkeypatch, fake_market_data):
    # A snapshot with no usable price is what forces the fallback path.
    fake = fake_market_data(fast_info={"XYZ": {"last_price": 0.0, "previous_close": 0.0}})

    stock_calls = {"n": 0}

    def _fake_get_stock_data(ticker):
        stock_calls["n"] += 1
        return {"ticker": ticker, "current_price": 42.0, "error": None}

    monkeypatch.setattr(stock_service, "get_stock_data", _fake_get_stock_data)

    first = stock_service.get_fast_quote("XYZ")
    second = stock_service.get_fast_quote("XYZ")

    assert first["current_price"] == 42.0
    assert second == first
    # Fallback fetch happened once; the second call was served from the fast cache.
    assert stock_calls["n"] == 1
    assert fake.calls.count(("get_fast_info", "XYZ")) == 1

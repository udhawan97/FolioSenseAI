"""Fixtures every test in this suite gets, whether it asks for them or not.

Two properties belong to the *suite*, not to any one test, and were being
arranged (or forgotten) file by file across ninety-odd of them:

  * **Nothing reaches Yahoo.** Tests used to pin the vendor wherever the module
    under test happened to import it — ``app.services.news_service.yf.Ticker``,
    ``yfinance.Ticker``, ``stock_service.yf`` — so the same intent was spelled
    three ways and a module that moved its import broke tests that never
    mentioned it. One adapter installed once replaces all of that.
  * **No test inherits another's cached answers.** The fetchers behind
    ``ttl_cache`` are module-level, so a quote remembered by one test is still
    remembered by the next one. That is how a suite acquires order-dependent
    tests, and it is why several files grew their own ``cache_clear()``
    boilerplate.
"""
from __future__ import annotations

import pytest

from app.services import market_data
from app.services.market_data import FakeMarketData
from app.services.ttl_cache import clear_all


@pytest.fixture(scope="session", autouse=True)
def _offline_market_data():
    """Point the market-data seam at an empty fake for the whole session.

    Nothing preloaded means every read comes back unavailable — the empty value
    of its return type — which is exactly what a test that never mentions market
    data should see: deterministic, instant, and socket-free. Tests that need
    Yahoo to say something ask for `fake_market_data`; tests that exercise the
    vendor adapter itself build their own and hand it a stub vendor.
    """
    previous = market_data.set_adapter(FakeMarketData())
    yield
    market_data.set_adapter(previous)


@pytest.fixture(name="fake_market_data")
def _fake_market_data():
    """Install a preloaded adapter for one test and hand it back::

        fake = fake_market_data(info={"AAPL": {"currentPrice": 189.0}})
        ...
        assert ("get_info", "AAPL") in fake.calls

    Tables are keyed by symbol and named after the accessor they answer: `info`,
    `fast_info`, `history`, `news`, `earnings_estimates`, `earnings_calendar`,
    `fund_holdings`, `search`. Anything not preloaded still reads as unavailable.
    Call it more than once to change what Yahoo says mid-test; the session-wide
    empty fake is restored either way.
    """
    previous = market_data.get_adapter()

    def install(**tables) -> FakeMarketData:
        fake = FakeMarketData(**tables)
        market_data.set_adapter(fake)
        return fake

    yield install
    market_data.set_adapter(previous)


@pytest.fixture(autouse=True)
def _empty_ttl_caches():
    """Start and finish every test with no memoised answers anywhere.

    Cleared on the way out as well as in, so a test that warms a cache leaves
    the process as it found it — including for code that runs outside a test,
    like a fixture in the next file.
    """
    clear_all()
    yield
    clear_all()

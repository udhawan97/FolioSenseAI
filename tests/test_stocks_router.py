"""HTTP-level tests for the stocks router's period validation.

Mounts only the stocks router on a bare FastAPI app (the pattern in
tests/test_earnings_radar_router.py) so no network or app lifespan runs. The
point is the query-parameter contract: an out-of-range ``period`` must be
rejected with 422 on BOTH history endpoints, not silently forwarded to yfinance
where it would fail and return empty data.
"""
# pylint: disable=redefined-outer-name
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import stocks as stocks_router


@pytest.fixture
def client(monkeypatch):
    # Stub the data layer so an accepted period never hits the network.
    monkeypatch.setattr(stocks_router, "_fetch_ticker_history",
                        lambda ticker, period: (ticker, []))
    monkeypatch.setattr(stocks_router, "get_historical_prices",
                        lambda ticker, period: [])
    app = FastAPI()
    app.include_router(stocks_router.router)
    return TestClient(app)


def test_batch_history_rejects_invalid_period(client):
    assert client.get("/api/stocks/history/batch?period=9y").status_code == 422
    assert client.get("/api/stocks/history/batch?period=bogus").status_code == 422


def test_batch_history_accepts_valid_period(client):
    res = client.get("/api/stocks/history/batch?tickers=VOO&period=6mo")
    assert res.status_code == 200
    assert res.json()["period"] == "6mo"


def test_single_history_rejects_invalid_period(client):
    assert client.get("/api/stocks/history/VOO?period=9y").status_code == 422

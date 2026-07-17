"""HTTP-level tests for the SEC filings timeline in the news zone.

Mounts only the news router on a bare FastAPI app (the pattern in
tests/test_stocks_router.py) so no network or app lifespan runs. The contract
under test is coverage honesty: only SEC filers can have filings, and the
holdings that can't (funds, crypto) must be reported as such rather than
silently rendered as companies that filed nothing.
"""
# pylint: disable=redefined-outer-name
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.routers import news as news_router


class _Holding:
    def __init__(self, ticker, is_watchlist=False):
        self.ticker = ticker
        self.is_watchlist = is_watchlist
        self.is_active = True


_FILINGS = {
    "AAPL": [
        {
            "form": "8-K",
            "label": "Material event (8-K)",
            "filed_at": "2026-06-10",
            "items": "2.02,9.01",
            "url": "https://www.sec.gov/Archives/edgar/data/320193/x/a.htm",
        }
    ],
    "MSFT": [],  # an SEC filer that simply hasn't filed lately
}


@pytest.fixture
def client(monkeypatch):
    holdings = [_Holding("AAPL"), _Holding("MSFT"), _Holding("VOO")]
    monkeypatch.setattr(news_router, "_get_active_holdings", lambda db, pid=1: holdings)
    monkeypatch.setattr(
        news_router, "_holding_info_brief", lambda t: {"company_name": t, "sector": "Tech"}
    )
    # VOO is a fund: no CIK, so EDGAR has nothing to offer.
    monkeypatch.setattr(
        news_router, "get_cik", lambda t, **k: None if t == "VOO" else "0000320193"
    )
    monkeypatch.setattr(
        news_router, "get_recent_filings", lambda t, **k: _FILINGS.get(t, [])
    )
    app = FastAPI()
    app.include_router(news_router.router)
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def test_filings_endpoint_returns_filings_per_holding(client):
    res = client.get("/api/news/filings")
    assert res.status_code == 200
    body = res.json()
    aapl = [h for h in body["holdings"] if h["ticker"] == "AAPL"][0]
    assert aapl["filings"][0]["form"] == "8-K"
    assert aapl["filings"][0]["url"].startswith("https://www.sec.gov/")


def test_a_filer_with_no_recent_filings_is_still_listed(client):
    body = client.get("/api/news/filings").json()
    msft = [h for h in body["holdings"] if h["ticker"] == "MSFT"][0]
    assert msft["filings"] == []
    assert msft["is_filer"] is True


def test_non_filers_are_reported_not_faked(client):
    # A fund with zero filings must not read as "this company filed nothing".
    body = client.get("/api/news/filings").json()
    voo = [h for h in body["holdings"] if h["ticker"] == "VOO"][0]
    assert voo["is_filer"] is False
    assert voo["filings"] == []
    assert "VOO" in body["not_filers"]


def test_response_reports_when_it_was_generated(client):
    assert "generated_at" in client.get("/api/news/filings").json()


def test_edgar_failure_degrades_to_an_empty_timeline(client, monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("EDGAR unreachable")

    monkeypatch.setattr(news_router, "get_recent_filings", _boom)
    res = client.get("/api/news/filings")
    assert res.status_code == 200
    body = res.json()
    assert all(h["filings"] == [] for h in body["holdings"])
    assert body["degraded"] is True


def test_healthy_response_is_not_flagged_degraded(client):
    assert client.get("/api/news/filings").json()["degraded"] is False

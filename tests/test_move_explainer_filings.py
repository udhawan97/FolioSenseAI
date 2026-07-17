"""Tests for filings as move catalysts."""
from datetime import date, timedelta

from app.services import move_explainer
from app.services.move_explainer import (
    FilingCatalyst,
    _recent_filing_catalysts,
    explain_move,
)


def _edgar_row(filed_at: str, form: str = "8-K") -> dict:
    return {
        "form": form,
        "label": f"Material event ({form})",
        "filed_at": filed_at,
        "items": "2.02,9.01",
        "url": f"https://www.sec.gov/Archives/edgar/data/320193/x/{filed_at}.htm",
    }


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def test_a_fresh_filing_becomes_a_catalyst(monkeypatch):
    monkeypatch.setattr(
        move_explainer, "get_recent_filings", lambda *a, **k: [_edgar_row(_days_ago(1))]
    )
    catalysts = _recent_filing_catalysts("AAPL")
    assert len(catalysts) == 1
    assert isinstance(catalysts[0], FilingCatalyst)
    assert catalysts[0].filing_type == "8-K"
    assert catalysts[0].title == "Material event (8-K)"
    assert catalysts[0].filed_at == _days_ago(1)
    assert catalysts[0].url.startswith("https://www.sec.gov/")


def test_a_stale_filing_cannot_explain_todays_move(monkeypatch):
    monkeypatch.setattr(
        move_explainer, "get_recent_filings", lambda *a, **k: [_edgar_row(_days_ago(90))]
    )
    assert _recent_filing_catalysts("AAPL") == []


def test_lookback_window_is_inclusive_of_its_edge(monkeypatch):
    monkeypatch.setattr(
        move_explainer,
        "get_recent_filings",
        lambda *a, **k: [_edgar_row(_days_ago(5)), _edgar_row(_days_ago(6))],
    )
    assert [c.filed_at for c in _recent_filing_catalysts("AAPL", lookback_days=5)] == [
        _days_ago(5)
    ]


def test_no_filings_means_no_catalysts(monkeypatch):
    monkeypatch.setattr(move_explainer, "get_recent_filings", lambda *a, **k: [])
    assert _recent_filing_catalysts("AAPL") == []


def test_edgar_trouble_never_breaks_a_move_explanation(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("EDGAR down")

    monkeypatch.setattr(move_explainer, "get_recent_filings", _boom)
    assert _recent_filing_catalysts("AAPL") == []


def test_rows_missing_a_date_are_skipped(monkeypatch):
    bad = {"form": "8-K", "label": "x", "url": "https://sec.gov/x", "filed_at": ""}
    monkeypatch.setattr(move_explainer, "get_recent_filings", lambda *a, **k: [bad])
    assert _recent_filing_catalysts("AAPL") == []


# --- explain_move only pays for filings when asked ---
#
# /move-explanations/all walks every holding in a serial loop, so an EDGAR round
# trip per holding would add seconds to a dashboard load. Filings are opt-in.


def _offline_move(monkeypatch):
    """Pin explain_move's network edges so these tests stay offline."""
    monkeypatch.setattr(
        move_explainer, "_primary_benchmark_chg", lambda *_a, **_k: (None, None, None)
    )
    monkeypatch.setattr(move_explainer, "_sector_etf_change", lambda *_a: (None, None))
    monkeypatch.setattr(move_explainer, "_earnings_near", lambda *_a: (False, None))


_STOCK_DATA = {
    "ticker": "AAPL",
    "day_change_pct": -3.4,
    "day_change": -6.1,
    "sector": "Technology",
    "volume": 1000,
    "average_volume": 1000,
}
_BENCHMARKS = {"SPY": 0.2, "QQQ": 0.3}


def test_explain_move_skips_filings_by_default(monkeypatch):
    _offline_move(monkeypatch)
    called: list[str] = []
    monkeypatch.setattr(
        move_explainer,
        "_recent_filing_catalysts",
        lambda *a, **k: called.append("hit") or [],
    )
    summary = explain_move(_STOCK_DATA, shared_benchmarks=dict(_BENCHMARKS))
    assert summary.filings == []
    assert called == []  # no EDGAR round trip on the batch path


def test_explain_move_attaches_filings_when_asked(monkeypatch):
    _offline_move(monkeypatch)
    catalyst = FilingCatalyst(
        filing_type="8-K",
        title="Material event (8-K)",
        url="https://www.sec.gov/x",
        filed_at=_days_ago(1),
    )
    monkeypatch.setattr(
        move_explainer, "_recent_filing_catalysts", lambda *a, **k: [catalyst]
    )
    summary = explain_move(
        _STOCK_DATA, shared_benchmarks=dict(_BENCHMARKS), include_filings=True
    )
    assert summary.filings == [catalyst]


def test_explain_move_never_looks_up_filings_for_an_etf(monkeypatch):
    # Funds have no CIK; asking EDGAR would burn a request to learn nothing.
    _offline_move(monkeypatch)
    called: list[str] = []
    monkeypatch.setattr(
        move_explainer,
        "_recent_filing_catalysts",
        lambda *a, **k: called.append("hit") or [],
    )
    etf_data = {**_STOCK_DATA, "ticker": "VOO", "quote_type": "ETF"}
    summary = explain_move(
        etf_data, shared_benchmarks=dict(_BENCHMARKS), include_filings=True
    )
    assert summary.filings == []
    assert called == []

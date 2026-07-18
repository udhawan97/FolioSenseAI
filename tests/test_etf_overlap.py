"""Tests for top-10 ETF overlap."""
# pylint: disable=protected-access
import pytest

from app.services import etf_overlap
from app.services.etf_overlap import (
    compute_etf_overlap,
    normalize_top_holdings,
    overlap_between,
)


def _etf(ticker, **extra):
    return {"ticker": ticker, "quote_type": "ETF", "is_watchlist": False, **extra}


def _stock(ticker, **extra):
    return {
        "ticker": ticker,
        "quote_type": "EQUITY",
        "exchange": "NMS",
        "is_watchlist": False,
        **extra,
    }


@pytest.fixture(name="stub_holdings")
def _stub_holdings(monkeypatch):
    """Pin the only network edge of the module, like market_regime._fetch_closes."""

    def _install(by_ticker: dict[str, list[dict]]):
        monkeypatch.setattr(
            "app.services.etf_overlap._fetch_top_holdings",
            lambda ticker: list(by_ticker.get(ticker.upper(), [])),
        )

    return _install


def test_overlap_score_is_the_shared_weight_both_funds_agree_on():
    a = {"AAPL": 7.0, "MSFT": 6.0, "XOM": 2.0}
    b = {"AAPL": 9.0, "MSFT": 4.0, "JPM": 3.0}

    result = overlap_between(a, b)

    # min(7,9) + min(6,4) = 7 + 4 = 11
    assert result["overlap_pct"] == 11.0
    assert result["shared_count"] == 2
    assert [h["symbol"] for h in result["shared_holdings"]] == ["AAPL", "MSFT"]
    assert result["shared_holdings"][0] == {
        "symbol": "AAPL",
        "weight_a": 7.0,
        "weight_b": 9.0,
        "shared_weight": 7.0,
    }


def test_no_shared_names_means_zero_overlap():
    result = overlap_between({"AAPL": 7.0}, {"JPM": 5.0})

    assert result["overlap_pct"] == 0.0
    assert result["shared_count"] == 0
    assert not result["shared_holdings"]


def test_identical_top_tens_overlap_by_their_full_weight():
    same = {"AAPL": 7.0, "MSFT": 6.0}

    result = overlap_between(same, dict(same))

    assert result["overlap_pct"] == 13.0


def test_normalize_upper_cases_and_strips_holding_symbols():
    rows = [{"symbol": " aapl ", "weight": 7.0}, {"symbol": "msft", "weight": 6.0}]

    assert normalize_top_holdings(rows) == {"AAPL": 7.0, "MSFT": 6.0}


def test_normalize_merges_duplicate_symbols_that_differ_only_by_case():
    rows = [{"symbol": "AAPL", "weight": 4.0}, {"symbol": "aapl", "weight": 3.0}]

    assert normalize_top_holdings(rows) == {"AAPL": 7.0}


def test_normalize_keeps_only_the_ten_heaviest_names():
    rows = [{"symbol": f"T{i}", "weight": float(i)} for i in range(1, 15)]

    normalized = normalize_top_holdings(rows)

    assert len(normalized) == 10
    assert "T14" in normalized
    assert "T4" not in normalized


def test_normalize_drops_unusable_rows():
    rows = [
        {"symbol": "AAPL", "weight": 7.0},
        {"symbol": "", "weight": 5.0},
        {"symbol": "MSFT", "weight": 0.0},
        {"symbol": "GOOG", "weight": None},
        {"symbol": "META", "weight": "bad"},
    ]

    assert normalize_top_holdings(rows) == {"AAPL": 7.0}


def test_normalize_drops_a_non_finite_weight():
    """A pandas NaN weight is missing data — it must not become a holding, and it
    must not slip through the `weight <= 0` guard (NaN comparisons are False)."""
    rows = [{"symbol": "AAPL", "weight": 7.0}, {"symbol": "MSFT", "weight": float("nan")}]

    assert normalize_top_holdings(rows) == {"AAPL": 7.0}


# ── Portfolio-level pairing ───────────────────────────────────────────────────


def test_pairs_every_held_etf_once_and_never_with_itself(stub_holdings):
    stub_holdings({
        "VOO": [{"symbol": "AAPL", "weight": 7.0}],
        "QQQ": [{"symbol": "AAPL", "weight": 9.0}],
        "SCHD": [{"symbol": "AAPL", "weight": 4.0}],
    })

    result = compute_etf_overlap([_etf("VOO"), _etf("QQQ"), _etf("SCHD")])

    assert result["has_data"] is True
    assert {(p["a"], p["b"]) for p in result["pairs"]} == {
        ("QQQ", "VOO"), ("SCHD", "VOO"), ("QQQ", "SCHD"),
    }
    assert all(p["a"] != p["b"] for p in result["pairs"])


def test_the_same_etf_listed_twice_makes_no_pair(stub_holdings):
    stub_holdings({"VOO": [{"symbol": "AAPL", "weight": 7.0}]})

    result = compute_etf_overlap([_etf("VOO"), _etf(" voo ")])

    assert not result["pairs"]
    assert result["etf_count"] == 1


def test_pairs_are_ranked_by_overlap(stub_holdings):
    stub_holdings({
        "VOO": [{"symbol": "AAPL", "weight": 7.0}, {"symbol": "XOM", "weight": 2.0}],
        "QQQ": [{"symbol": "AAPL", "weight": 9.0}],
        "VYM": [{"symbol": "XOM", "weight": 3.0}],
    })

    result = compute_etf_overlap([_etf("VOO"), _etf("QQQ"), _etf("VYM")])

    scores = [p["overlap_pct"] for p in result["pairs"]]
    assert scores == sorted(scores, reverse=True)
    assert result["pairs"][0]["overlap_pct"] == 7.0


def test_holding_symbol_case_and_whitespace_do_not_hide_overlap(stub_holdings):
    stub_holdings({
        "VOO": [{"symbol": " aapl ", "weight": 7.0}],
        "QQQ": [{"symbol": "AAPL", "weight": 9.0}],
    })

    result = compute_etf_overlap([_etf("VOO"), _etf("QQQ")])

    assert result["pairs"][0]["overlap_pct"] == 7.0
    assert result["pairs"][0]["shared_holdings"][0]["symbol"] == "AAPL"


def test_payload_names_its_basis_so_the_ui_cannot_overclaim(stub_holdings):
    stub_holdings({
        "VOO": [{"symbol": "AAPL", "weight": 7.0}],
        "QQQ": [{"symbol": "AAPL", "weight": 9.0}],
    })

    result = compute_etf_overlap([_etf("VOO"), _etf("QQQ")])

    assert result["basis"] == "top_10_holdings"
    assert result["score_method"] == "sum_of_min_shared_weight"
    assert "top 10" in result["caveat"].lower()


# ── Honest degradation ────────────────────────────────────────────────────────


def test_fewer_than_two_etfs_is_an_empty_result_not_an_error(stub_holdings):
    stub_holdings({"VOO": [{"symbol": "AAPL", "weight": 7.0}]})

    result = compute_etf_overlap([_etf("VOO"), _stock("AAPL")])

    assert result["has_data"] is False
    assert not result["pairs"]
    assert result["etf_count"] == 1


def test_empty_portfolio_is_an_empty_result(stub_holdings):
    stub_holdings({})

    result = compute_etf_overlap([])

    assert result["has_data"] is False
    assert not result["pairs"]
    assert result["etf_count"] == 0


def test_etf_without_holdings_data_is_excluded_and_reported(stub_holdings):
    stub_holdings({
        "VOO": [{"symbol": "AAPL", "weight": 7.0}],
        "QQQ": [{"symbol": "AAPL", "weight": 9.0}],
        "MYSTERY": [],
    })

    result = compute_etf_overlap([_etf("VOO"), _etf("QQQ"), _etf("MYSTERY")])

    assert result["uncovered_tickers"] == ["MYSTERY"]
    assert sorted(result["covered_tickers"]) == ["QQQ", "VOO"]
    assert all("MYSTERY" not in (p["a"], p["b"]) for p in result["pairs"])
    assert result["data_quality"] == "partial"


def test_offline_with_no_holdings_data_at_all_degrades_honestly(stub_holdings):
    stub_holdings({})

    result = compute_etf_overlap([_etf("VOO"), _etf("QQQ")])

    assert result["has_data"] is False
    assert not result["pairs"]
    assert sorted(result["uncovered_tickers"]) == ["QQQ", "VOO"]
    assert result["data_quality"] == "unavailable"


def test_full_coverage_reports_complete(stub_holdings):
    stub_holdings({
        "VOO": [{"symbol": "AAPL", "weight": 7.0}],
        "QQQ": [{"symbol": "AAPL", "weight": 9.0}],
    })

    result = compute_etf_overlap([_etf("VOO"), _etf("QQQ")])

    assert result["data_quality"] == "complete"
    assert not result["uncovered_tickers"]


def test_fetch_seam_returns_nothing_when_the_fund_is_unknown(fake_market_data):
    """Offline, the network edge must hand back 'no data' — never raise into the
    endpoint. Everything above it then reports the fund as uncovered."""
    fake_market_data(fund_holdings={"QQQ": [{"symbol": "AAPL", "weight": 9.0}]})

    assert not etf_overlap._fetch_top_holdings("VOO")


def test_fetch_seam_passes_the_funds_own_rows_through(fake_market_data):
    """The seam already answers in {symbol, name, weight}; caching is all this adds."""
    rows = [{"symbol": "AAPL", "name": "Apple Inc", "weight": 7.2}]
    fake = fake_market_data(fund_holdings={"VOO": rows})

    assert etf_overlap._fetch_top_holdings("voo ") == rows
    assert etf_overlap._fetch_top_holdings("VOO") == rows
    # Second read came off the cache, not the seam.
    assert fake.calls.count(("get_fund_holdings", "VOO")) == 1


def test_watchlist_etfs_are_not_part_of_the_book(stub_holdings):
    stub_holdings({
        "VOO": [{"symbol": "AAPL", "weight": 7.0}],
        "QQQ": [{"symbol": "AAPL", "weight": 9.0}],
    })

    result = compute_etf_overlap([_etf("VOO"), _etf("QQQ", is_watchlist=True)])

    assert result["etf_count"] == 1
    assert not result["pairs"]

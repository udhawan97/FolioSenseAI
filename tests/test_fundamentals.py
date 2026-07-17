"""Tests for fundamentals-over-time (SEC XBRL company facts)."""
import json

from app.services import fundamentals
from app.services.fundamentals import (
    _annual_series,
    _build_periods,
    _revenue_series,
    get_fundamentals,
)


def _rows(*triples):
    """(frame, val, fy) -> XBRL unit rows, all 10-K/FY like the real feed."""
    return [
        {"end": f"{frame[2:6]}-12-31", "val": val, "fy": fy, "fp": "FY",
         "form": "10-K", "frame": frame}
        for frame, val, fy in triples
    ]


# --- annual series: the frame is the period key, not the report year ---


def test_annual_series_keys_by_the_frame_period_not_the_report_year():
    # A 10-K reports the current year AND prior-year comparatives under the same
    # fy; the frame (CY2024 vs CY2025) is what actually distinguishes them.
    rows = _rows(("CY2024", 391_000, 2025), ("CY2025", 416_000, 2025))
    series = _annual_series(rows)
    assert series == {2024: 391_000.0, 2025: 416_000.0}


def test_annual_series_drops_quarterly_frames():
    # CY2018Q3 is a quarter masquerading in the annual rows — must not count.
    rows = _rows(("CY2018", 265_000, 2018), ("CY2018Q3", 62_900, 2018))
    assert _annual_series(rows) == {2018: 265_000.0}


def test_annual_series_last_filing_wins_on_a_restated_year():
    # Same period restated across filings; the later (higher fy) value wins.
    rows = _rows(("CY2023", 100, 2023), ("CY2023", 105, 2024))
    assert _annual_series(rows)[2023] == 105.0


def test_annual_series_ignores_non_annual_forms():
    rows = _rows(("CY2024", 391_000, 2025))
    rows.append({"end": "2024-06-30", "val": 90_000, "fy": 2024, "fp": "Q2",
                 "form": "10-Q", "frame": "CY2024Q2"})
    assert _annual_series(rows) == {2024: 391_000.0}


def test_annual_series_of_nothing():
    assert _annual_series([]) == {}


# --- revenue tag drift: two GAAP concepts, one story ---


_GAAP = {
    "RevenueFromContractWithCustomerExcludingAssessedTax": {
        "units": {"USD": _rows(("CY2022", 394_000, 2022), ("CY2023", 383_000, 2023))}
    },
    "Revenues": {
        "units": {"USD": _rows(("CY2020", 274_000, 2020), ("CY2021", 365_000, 2021),
                               ("CY2022", 999_999, 2022))}
    },
    "NetIncomeLoss": {"units": {"USD": _rows(("CY2022", 99_000, 2022), ("CY2023", 97_000, 2023))}},
    "EarningsPerShareDiluted": {
        "units": {"USD/shares": _rows(("CY2022", 6.11, 2022), ("CY2023", 6.13, 2023))}
    },
}


def test_revenue_prefers_the_modern_tag_and_backfills_the_legacy_one():
    series = _revenue_series(_GAAP)
    # 2020/2021 only exist under the legacy Revenues tag...
    assert series[2020] == 274_000.0
    assert series[2021] == 365_000.0
    # ...2022 exists under both; the modern tag wins over the stale legacy value.
    assert series[2022] == 394_000.0
    assert series[2023] == 383_000.0


def test_revenue_series_empty_without_either_tag():
    assert not _revenue_series({"NetIncomeLoss": {"units": {"USD": []}}})


# --- periods: assembled, aligned, margin computed ---


def test_build_periods_aligns_metrics_and_computes_margin():
    periods = _build_periods(_GAAP, years=6)
    assert [p["year"] for p in periods] == [2020, 2021, 2022, 2023]
    latest = periods[-1]
    assert latest["revenue"] == 383_000.0
    assert latest["net_income"] == 97_000.0
    assert latest["eps_diluted"] == 6.13
    # margin = 97000/383000 ≈ 25.3%
    assert 25.0 <= latest["net_margin"] <= 25.6


def test_build_periods_leaves_gaps_as_none_never_zero():
    # A year with revenue but no EPS must report None, not a fabricated 0.
    gaap = {
        "Revenues": {"units": {"USD": _rows(("CY2021", 365_000, 2021))}},
    }
    periods = _build_periods(gaap, years=6)
    assert periods[0]["revenue"] == 365_000.0
    assert periods[0]["net_income"] is None
    assert periods[0]["eps_diluted"] is None
    assert periods[0]["net_margin"] is None


def test_build_periods_caps_to_the_requested_window():
    gaap = {"Revenues": {"units": {"USD": _rows(
        *[(f"CY{y}", y * 10, y) for y in range(2016, 2026)])}}}
    periods = _build_periods(gaap, years=4)
    assert [p["year"] for p in periods] == [2022, 2023, 2024, 2025]


# --- the public interface ---


def _wire(monkeypatch, *, cik, facts):
    monkeypatch.setattr(fundamentals, "_FUNDAMENTALS_CACHE", {})
    monkeypatch.setattr(fundamentals, "get_cik", lambda t, **_k: cik)
    monkeypatch.setattr(fundamentals, "fetch_company_facts", lambda c: facts)


def test_get_fundamentals_live(monkeypatch):
    _wire(monkeypatch, cik="0000320193",
          facts=json.dumps({"facts": {"us-gaap": _GAAP}}))
    result = get_fundamentals("AAPL", force_refresh=True)
    assert result["data_quality"] == "live"
    assert result["periods"][-1]["year"] == 2023
    assert result["periods"][-1]["revenue"] == 383_000.0


def test_get_fundamentals_for_a_non_filer_is_empty_but_live(monkeypatch):
    # ETFs have no CIK and no financials — honest empty, not an error.
    _wire(monkeypatch, cik=None, facts=None)
    result = get_fundamentals("VOO", force_refresh=True)
    assert result["data_quality"] == "live"
    assert result["periods"] == []


def test_get_fundamentals_when_edgar_is_unreachable(monkeypatch):
    _wire(monkeypatch, cik="0000320193", facts=None)
    result = get_fundamentals("AAPL", force_refresh=True)
    assert result["data_quality"] == "unavailable"
    assert result["periods"] == []


def test_get_fundamentals_survives_garbage_json(monkeypatch):
    _wire(monkeypatch, cik="0000320193", facts="not json")
    result = get_fundamentals("AAPL", force_refresh=True)
    assert result["data_quality"] == "unavailable"


def test_get_fundamentals_is_cached(monkeypatch):
    calls = []

    def _facts(cik):
        calls.append(cik)
        return json.dumps({"facts": {"us-gaap": _GAAP}})

    monkeypatch.setattr(fundamentals, "_FUNDAMENTALS_CACHE", {})
    monkeypatch.setattr(fundamentals, "get_cik", lambda t, **_k: "0000320193")
    monkeypatch.setattr(fundamentals, "fetch_company_facts", _facts)
    get_fundamentals("AAPL", force_refresh=True)
    get_fundamentals("AAPL")
    assert len(calls) == 1

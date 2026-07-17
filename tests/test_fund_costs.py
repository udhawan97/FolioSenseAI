"""Tests for fund fee-drag analysis."""
import pytest

from app.services import fund_costs
from app.services.fund_costs import compute_fee_drag


def _fund(ticker, value, expense_ratio=None, **extra):
    row = {
        "ticker": ticker,
        "current_value": value,
        "quote_type": "ETF",
        "is_watchlist": False,
    }
    if expense_ratio is not None:
        row["expense_ratio"] = expense_ratio
    row.update(extra)
    return row


def _stock(ticker, value, **extra):
    row = {
        "ticker": ticker,
        "current_value": value,
        "quote_type": "EQUITY",
        "exchange": "NMS",
        "is_watchlist": False,
    }
    row.update(extra)
    return row


def test_annual_fee_is_position_value_times_expense_ratio():
    result = compute_fee_drag([_fund("VOO", 10_000.0, 0.0003)])

    assert result["has_data"] is True
    assert result["annual_fee_cost"] == 3.0
    assert result["holdings"][0]["ticker"] == "VOO"
    assert result["holdings"][0]["annual_fee"] == 3.0


def test_blended_expense_ratio_is_value_weighted_across_covered_funds():
    result = compute_fee_drag([
        _fund("VOO", 30_000.0, 0.0010),
        _fund("QTUM", 10_000.0, 0.0050),
    ])

    # (30k × 10bps + 10k × 50bps) / 40k = 20bps
    assert result["blended_expense_ratio_bps"] == 20
    assert result["annual_fee_cost"] == 80.0
    assert result["covered_value"] == 40_000.0


# ── Coverage honesty ──────────────────────────────────────────────────────────


def test_stocks_are_excluded_from_fee_coverage_rather_than_counted_unknown():
    result = compute_fee_drag([
        _fund("VOO", 10_000.0, 0.0003),
        _stock("AAPL", 5_000.0),
    ])

    assert result["coverage"]["fund_count"] == 1
    assert result["coverage"]["uncovered_count"] == 0
    assert result["coverage"]["uncovered_tickers"] == []
    assert result["coverage"]["stock_count"] == 1
    assert [h["ticker"] for h in result["holdings"]] == ["VOO"]
    assert result["data_quality"] == "complete"


def test_fund_without_an_expense_ratio_is_reported_uncovered_not_free():
    result = compute_fee_drag([
        _fund("VOO", 10_000.0, 0.0003),
        _fund("MYSTERY", 5_000.0),
    ])

    assert result["coverage"]["uncovered_tickers"] == ["MYSTERY"]
    assert result["coverage"]["uncovered_count"] == 1
    assert result["coverage"]["uncovered_value"] == 5_000.0
    assert result["annual_fee_cost"] == 3.0  # the unknown fund adds no fake $0 fee
    assert result["covered_value"] == 10_000.0
    assert result["data_quality"] == "partial"


def test_a_fund_with_no_expense_ratio_at_all_is_unknown():
    # Superseded the old "zero means unknown" rule: that was only true while the
    # quote layer's `or` chain silently turned a real 0.0 into None. The
    # chokepoint now preserves zero, so absence is the only unknown.
    result = compute_fee_drag([_fund("ZERO", 10_000.0)])

    assert result["coverage"]["uncovered_tickers"] == ["ZERO"]
    assert result["has_data"] is False
    assert result["data_quality"] == "unavailable"


def test_absurd_expense_ratio_is_rejected_as_bad_data():
    result = compute_fee_drag([
        _fund("VOO", 10_000.0, 0.0003),
        _fund("BOGUS", 10_000.0, 0.35),  # 35% — not a real expense ratio
    ])

    assert result["coverage"]["uncovered_tickers"] == ["BOGUS"]
    assert result["annual_fee_cost"] == 3.0
    assert any("BOGUS" in flag for flag in result["flags"])


def test_non_finite_expense_ratio_is_rejected_as_bad_data():
    """A NaN ratio slips past both `not x` and range checks (NaN comparisons are
    always False) and would poison the fee totals — and the JSON response."""
    result = compute_fee_drag([_fund("NANFUND", 10_000.0, float("nan"))])

    assert result["coverage"]["uncovered_tickers"] == ["NANFUND"]
    assert result["annual_fee_cost"] == 0.0
    assert result["has_data"] is False


def test_negative_expense_ratio_is_rejected_as_bad_data():
    result = compute_fee_drag([_fund("BAD", 10_000.0, -0.002)])

    assert result["coverage"]["uncovered_tickers"] == ["BAD"]
    assert result["annual_fee_cost"] == 0.0


def test_all_stock_portfolio_has_no_fee_view():
    result = compute_fee_drag([_stock("AAPL", 5_000.0), _stock("MSFT", 4_000.0)])

    assert result["has_data"] is False
    assert result["coverage"]["fund_count"] == 0
    assert result["coverage"]["stock_count"] == 2
    assert result["annual_fee_cost"] == 0.0
    assert result["blended_expense_ratio"] is None
    assert result["data_quality"] == "complete"  # nothing to cover, nothing missing


def test_empty_portfolio_has_no_fee_view():
    result = compute_fee_drag([])

    assert result["has_data"] is False
    assert not result["holdings"]
    assert result["coverage"]["fund_count"] == 0
    assert result["annual_fee_cost"] == 0.0


def test_watchlist_rows_are_not_charged_fees():
    result = compute_fee_drag([
        _fund("VOO", 10_000.0, 0.0003),
        _fund("QQQ", 50_000.0, 0.0020, is_watchlist=True),
    ])

    assert [h["ticker"] for h in result["holdings"]] == ["VOO"]
    assert result["annual_fee_cost"] == 3.0


# ── Long-horizon drag ─────────────────────────────────────────────────────────


def test_one_year_horizon_fee_equals_one_annual_fee():
    result = compute_fee_drag([_fund("VOO", 10_000.0, 0.0030)], horizon_years=1)

    assert result["horizon_fee_cost"] == 30.0


def test_zero_horizon_costs_nothing_but_still_reports_the_annual_fee():
    result = compute_fee_drag([_fund("VOO", 10_000.0, 0.0030)], horizon_years=0)

    assert result["horizon_fee_cost"] == 0.0
    assert result["annual_fee_cost"] == 30.0


def test_horizon_fee_compounds_against_a_growing_balance():
    """The fee is charged on the balance as it grows, so ten years of drag costs
    much more than ten flat years of today's fee."""
    result = compute_fee_drag([_fund("QTUM", 10_000.0, 0.0050)], horizon_years=10)

    naive = 10_000.0 * 0.0050 * 10
    assert result["horizon_fee_cost"] > naive * 1.5
    assert result["holdings"][0]["horizon_fee"] == result["horizon_fee_cost"]


def test_horizon_fee_is_gross_growth_minus_net_of_fee_growth():
    value, expense_ratio, years = 10_000.0, 0.0050, 10
    growth = fund_costs.DEFAULT_GROWTH_RATE
    expected = value * ((1 + growth) ** years - (1 + growth - expense_ratio) ** years)

    result = compute_fee_drag([_fund("QTUM", value, expense_ratio)], horizon_years=years)

    assert result["horizon_fee_cost"] == pytest.approx(expected, abs=0.01)


def test_assumptions_are_stated_in_the_payload():
    result = compute_fee_drag([_fund("VOO", 10_000.0, 0.0003)])

    assumptions = result["assumptions"]
    assert assumptions["annual_growth_rate"] == fund_costs.DEFAULT_GROWTH_RATE
    assert assumptions["method"] == "gross_minus_net_compounding"
    assert assumptions["note"]


def test_growth_assumption_is_overridable_and_moves_the_drag():
    flat = compute_fee_drag(
        [_fund("VOO", 10_000.0, 0.0050)], horizon_years=10, growth_rate=0.0
    )
    grown = compute_fee_drag(
        [_fund("VOO", 10_000.0, 0.0050)], horizon_years=10, growth_rate=0.07
    )

    assert grown["horizon_fee_cost"] > flat["horizon_fee_cost"]
    assert flat["assumptions"]["annual_growth_rate"] == 0.0


def test_negative_horizon_is_clamped_to_zero():
    result = compute_fee_drag([_fund("VOO", 10_000.0, 0.0030)], horizon_years=-5)

    assert result["horizon_years"] == 0
    assert result["horizon_fee_cost"] == 0.0


def test_no_covered_funds_means_no_horizon_cost():
    result = compute_fee_drag([_stock("AAPL", 10_000.0)], horizon_years=10)

    assert result["horizon_fee_cost"] == 0.0


def test_a_genuinely_free_fund_is_free_not_unknown():
    """A 0% fee is a fact about the fund, not a gap in the data.

    stock_service._normalized_expense_ratio preserves a real 0.0 (only a
    missing/unusable value becomes None), so 0.0 arriving here means free.
    """
    result = compute_fee_drag([_fund("FREE", 10_000.0, 0.0)])

    assert result["has_data"] is True
    assert result["annual_fee_cost"] == 0.0
    assert result["horizon_fee_cost"] == 0.0
    assert result["coverage"]["uncovered_tickers"] == []
    assert result["coverage"]["covered_count"] == 1
    assert result["flags"] == []


def test_a_free_fund_does_not_drag_the_blended_ratio_off():
    result = compute_fee_drag([
        _fund("FREE", 10_000.0, 0.0),
        _fund("PRICEY", 10_000.0, 0.0020),
    ])
    # (10k × 0 + 10k × 20bps) / 20k = 10bps
    assert result["blended_expense_ratio_bps"] == 10


def test_a_missing_expense_ratio_is_still_unknown():
    result = compute_fee_drag([_fund("NOFEEDATA", 10_000.0)])
    assert result["coverage"]["uncovered_tickers"] == ["NOFEEDATA"]
    assert result["has_data"] is False

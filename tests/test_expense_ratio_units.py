"""The expense ratio leaving the chokepoint is always a fraction.

yfinance is inconsistent about units and the two keys are exactly 100x apart
(verified live: VFIAX reports annualReportExpenseRatio 0.0086 AND
netExpenseRatio 0.86 for the same 0.86% fund). Everything downstream —
etf_quality's cost tiers, the fee view, the UI's percent formatting — reads a
fraction, so the conversion belongs here, once, rather than in each consumer.
"""
import math

from app.services.etf_quality import _cost_label
from app.services.stock_service import _normalized_expense_ratio


def test_net_expense_ratio_is_a_percent_and_gets_converted():
    # VOO: yfinance says 0.03, meaning 0.03%.
    assert _normalized_expense_ratio({"netExpenseRatio": 0.03}) == 0.0003


def test_annual_report_expense_ratio_is_already_a_fraction():
    # VFIAX: yfinance says 0.0086, meaning 0.86%.
    assert _normalized_expense_ratio({"annualReportExpenseRatio": 0.0086}) == 0.0086


def test_the_fraction_key_wins_when_both_are_present():
    ratio = _normalized_expense_ratio(
        {"annualReportExpenseRatio": 0.0086, "netExpenseRatio": 0.86}
    )
    assert ratio == 0.0086


def test_absent_expense_ratio():
    assert _normalized_expense_ratio({}) is None


def test_none_values_are_not_ratios():
    assert _normalized_expense_ratio({"annualReportExpenseRatio": None}) is None


def test_nan_is_not_a_ratio():
    assert _normalized_expense_ratio({"netExpenseRatio": float("nan")}) is None


def test_non_numeric_is_not_a_ratio():
    assert _normalized_expense_ratio({"netExpenseRatio": "cheap"}) is None


def test_a_zero_fee_fund_is_free_not_unknown():
    # Zero-fee funds exist (FZROX). Zero must survive as 0.0, not collapse to None.
    assert _normalized_expense_ratio({"netExpenseRatio": 0.0}) == 0.0


def test_negative_ratios_are_rejected():
    assert _normalized_expense_ratio({"netExpenseRatio": -1.0}) is None


def test_the_cheapest_etf_on_earth_reads_as_cheap_end_to_end():
    # The bug this guards: VOO's 0.03% fee arrived as 0.03 and was scored in the
    # most expensive tier — the opposite of the truth.
    voo = _normalized_expense_ratio({"netExpenseRatio": 0.03})
    assert _cost_label(voo) == "Ultra-Low"


def test_an_expensive_fund_still_reads_as_expensive():
    ark = _normalized_expense_ratio({"netExpenseRatio": 0.75})  # 0.75%
    assert math.isclose(ark, 0.0075)
    assert _cost_label(ark) == "High"

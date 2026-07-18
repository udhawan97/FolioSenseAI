"""Behavior tests for the dividend payment calendar service.

Pure projection over injected ex-date history — no network, no yfinance.
The core promises: cadence is read from real trailing ex-dates, amounts come
from the forward annual income the income card already shows, and a payer
whose cadence can't be read is listed as unscheduled — never spread across
months we invented.
"""
from datetime import date

from app.services.dividend_calendar import build_income_calendar, payment_months

TODAY = date(2026, 7, 18)


def _payer(ticker: str, annual: float) -> dict:
    return {"ticker": ticker, "annual_income": annual}


def _quarterly_dates() -> list[date]:
    # Ex-dates in Feb / May / Aug / Nov, the classic large-cap pattern.
    return [date(2025, 8, 8), date(2025, 11, 7), date(2026, 2, 6), date(2026, 5, 8)]


# ── payment_months: cadence inference ────────────────────────────────────────

def test_four_trailing_ex_dates_read_as_quarterly():
    cadence = payment_months(_quarterly_dates(), TODAY)
    assert cadence["per_year"] == 4
    assert cadence["months"] == {2, 5, 8, 11}

def test_twelve_trailing_ex_dates_read_as_monthly():
    dates = [date(2025, m, 15) for m in range(8, 13)] + [date(2026, m, 15) for m in range(1, 8)]
    cadence = payment_months(dates, TODAY)
    assert cadence["per_year"] == 12
    assert cadence["months"] == set(range(1, 13))

def test_two_trailing_ex_dates_read_as_semiannual():
    cadence = payment_months([date(2025, 12, 10), date(2026, 6, 10)], TODAY)
    assert cadence["per_year"] == 2
    assert cadence["months"] == {6, 12}

def test_one_trailing_ex_date_reads_as_annual():
    cadence = payment_months([date(2026, 3, 20)], TODAY)
    assert cadence["per_year"] == 1
    assert cadence["months"] == {3}

def test_no_recent_history_reads_as_unknown():
    assert payment_months([], TODAY) is None
    # Ancient history only — a payer that stopped paying is unknown, not annual.
    assert payment_months([date(2020, 3, 20)], TODAY) is None

def test_future_ex_dates_are_ignored():
    # A declared-but-not-yet-passed ex-date must not count as history.
    assert payment_months([date(2026, 8, 30)], TODAY) is None


# ── build_income_calendar: projection ────────────────────────────────────────

def test_quarterly_payer_lands_in_its_four_months_at_a_quarter_each():
    result = build_income_calendar(
        [_payer("VZ", 100.0)], {"VZ": _quarterly_dates()}, TODAY)
    assert result["has_data"] is True
    paying = {m["month"]: m["total"] for m in result["months"] if m["total"] > 0}
    # 12 slots from 2026-07 → 2027-06; Feb/May/Aug/Nov each pay once.
    assert paying == {"2026-08": 25.0, "2026-11": 25.0, "2027-02": 25.0, "2027-05": 25.0}
    assert result["total_next_12m"] == 100.0

def test_calendar_starts_with_the_current_month_and_spans_twelve():
    result = build_income_calendar(
        [_payer("VZ", 100.0)], {"VZ": _quarterly_dates()}, TODAY)
    months = [m["month"] for m in result["months"]]
    assert len(months) == 12
    assert months[0] == "2026-07"
    assert months[-1] == "2027-06"

def test_unknown_cadence_is_unscheduled_never_smeared_across_months():
    result = build_income_calendar([_payer("NEW", 60.0)], {}, TODAY)
    assert result["has_data"] is False
    assert all(m["total"] == 0.0 for m in result["months"])
    assert result["unscheduled"] == [{"ticker": "NEW", "annual_income": 60.0}]

def test_mixed_payers_stack_within_a_shared_month():
    monthly = [date(2025, m, 1) for m in range(8, 13)] + [date(2026, m, 1) for m in range(1, 8)]
    result = build_income_calendar(
        [_payer("VZ", 100.0), _payer("O", 120.0)],
        {"VZ": _quarterly_dates(), "O": monthly}, TODAY)
    by_month = {m["month"]: m for m in result["months"]}
    # August: VZ quarter (25) + O month (10)
    assert by_month["2026-08"]["total"] == 35.0
    tickers = {p["ticker"] for p in by_month["2026-08"]["payers"]}
    assert tickers == {"VZ", "O"}
    # July: O only
    assert by_month["2026-07"]["total"] == 10.0

def test_amounts_come_from_forward_income_not_history_sums():
    # History only supplies the WHEN. A raised dividend (forward income 120
    # vs whatever history paid) must project 30/quarter.
    result = build_income_calendar(
        [_payer("VZ", 120.0)], {"VZ": _quarterly_dates()}, TODAY)
    assert max(m["total"] for m in result["months"]) == 30.0

def test_calendar_is_labelled_as_ex_date_based():
    # The months are ex-dividend months, not pay months — the payload must say
    # so, so the UI can't quietly promise cash-in-hand dates.
    result = build_income_calendar([], {}, TODAY)
    assert result["basis"] == "ex_date"

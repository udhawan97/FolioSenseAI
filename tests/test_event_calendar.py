"""Tests for earnings event calendar."""
from datetime import date, timedelta
from unittest.mock import patch

from app.services.event_calendar import (
    build_event_context,
    apply_earnings_cap,
    _EARNINGS_WINDOW_DAYS,
)


def test_build_event_context_within_window():
    soon = date.today() + timedelta(days=7)
    ctx = build_event_context("NOW", security_type="STOCK", earnings_date=soon)
    assert ctx is not None
    assert ctx["event_type"] == "earnings"
    assert ctx["days_until"] == 7
    assert "Earnings" in ctx["label"]


def test_build_event_context_outside_window():
    far = date.today() + timedelta(days=30)
    ctx = build_event_context("NOW", security_type="STOCK", earnings_date=far)
    assert ctx is None


def test_build_event_context_etf_skipped():
    soon = date.today() + timedelta(days=5)
    ctx = build_event_context("VOO", security_type="ETF", earnings_date=soon)
    assert ctx is None


def test_apply_earnings_cap_add():
    event = {"confidence_cap": 55, "risk_note": "Earnings soon"}
    conf, risks = apply_earnings_cap(72, "add", event)
    assert conf == 55
    assert risks

"""Tests for macro regime detection."""
from app.services.market_regime import (
    _classify_risk,
    _classify_rates,
    _classify_usd,
    _component_adjustments,
    _trend_from_closes,
    apply_regime_to_weights,
)


def test_trend_rising():
    closes = [100.0] * 10 + [110.0] * 15
    assert _trend_from_closes(closes) == "rising"


def test_trend_falling():
    closes = [110.0] * 10 + [100.0] * 15
    assert _trend_from_closes(closes) == "falling"


def test_risk_on_classification():
    assert _classify_risk("rising") == "risk_on"
    assert _classify_risk("falling") == "risk_off"


def test_rates_classification():
    assert _classify_rates("falling") == "rates_rising"
    assert _classify_rates("rising") == "rates_falling"


def test_usd_classification():
    assert _classify_usd("rising") == "usd_strong"


def test_risk_off_adjustments():
    adj = _component_adjustments("risk_off", "rates_flat", "usd_neutral", "normal")
    assert adj["momentum"] < 0
    assert adj["quality"] > 0


def test_apply_regime_weights_sum_100():
    base = {"analyst": 32, "valuation": 26, "momentum": 24, "quality": 18}
    adj = {"analyst": 0, "valuation": 2, "momentum": -4, "quality": 4}
    result = apply_regime_to_weights(base, adj)
    assert sum(result.values()) == 100

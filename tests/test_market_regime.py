"""Tests for macro regime detection."""
# The _fetch_closes stub must keep the real `period` keyword in its signature —
# the caller passes it by name — even though the fake ignores it.
# pylint: disable=unused-argument
from app.services.market_regime import (
    _classify_risk,
    _classify_rates,
    _classify_usd,
    _component_adjustments,
    _regime_label,
    _trend_from_closes,
    _vix_percentile,
    apply_regime_to_weights,
    get_market_regime,
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


# --- VIX percentile: where today's fear sits against its own recent history ---


def test_vix_percentile_at_the_top_of_its_range():
    closes = [float(v) for v in range(10, 310)]  # today is the highest of 300
    assert _vix_percentile(closes) == 100.0


def test_vix_percentile_at_the_bottom_of_its_range():
    closes = [float(v) for v in range(300, 10, -1)]  # today is the lowest
    assert _vix_percentile(closes) == 0.0


def test_vix_percentile_in_the_middle():
    closes = [float(v) for v in range(1, 301)] + [150.0]
    assert 49.0 <= _vix_percentile(closes) <= 51.0


def test_vix_percentile_needs_a_year_of_history():
    assert _vix_percentile([20.0] * 100) is None


def test_vix_percentile_without_history():
    assert _vix_percentile([]) is None


# --- Yield curve feeds the regime ---


def test_inverted_curve_favors_quality_over_momentum():
    adj = _component_adjustments(
        "neutral", "rates_flat", "usd_neutral", "normal", curve_state="inverted"
    )
    assert adj["quality"] > 0
    assert adj["momentum"] < 0


def test_normal_curve_is_not_a_signal():
    adj = _component_adjustments(
        "neutral", "rates_flat", "usd_neutral", "normal", curve_state="normal"
    )
    assert adj == {"analyst": 0, "valuation": 0, "momentum": 0, "quality": 0}


def test_unknown_curve_is_not_a_signal():
    adj = _component_adjustments(
        "neutral", "rates_flat", "usd_neutral", "normal", curve_state="unknown"
    )
    assert adj == {"analyst": 0, "valuation": 0, "momentum": 0, "quality": 0}


def _stub_regime_inputs(monkeypatch, *, curve, vix_closes=None):
    """Pin every network edge of the regime so tests stay offline."""
    rising = [100.0] * 10 + [110.0] * 15

    def _fake_closes(ticker, period="3mo"):
        if ticker == "^VIX":
            return vix_closes if vix_closes is not None else [18.0] * 30
        return rising

    monkeypatch.setattr("app.services.market_regime._fetch_closes", _fake_closes)
    monkeypatch.setattr(
        "app.services.market_regime.get_yield_curve", lambda **_kw: curve
    )


_LIVE_CURVE = {
    "curve_state": "inverted",
    "spread_2s10s": -36.0,
    "spread_3m10y": -12.0,
    "inverted": True,
    "label": "Inverted curve · 2s10s −36bp",
    "as_of": "2026-07-16",
    "data_quality": "live",
}

_DEAD_CURVE = {
    "curve_state": "unknown",
    "spread_2s10s": None,
    "spread_3m10y": None,
    "inverted": None,
    "label": "Curve unavailable",
    "as_of": None,
    "data_quality": "unavailable",
}


def test_label_surfaces_an_inverted_curve():
    label = _regime_label("risk_on", "rates_flat", "usd_neutral", "inverted")
    assert "Curve inverted" in label


def test_label_ignores_an_ordinary_curve():
    label = _regime_label("risk_on", "rates_flat", "usd_neutral", "normal")
    assert "Curve" not in label
    assert label == "Risk-on"


def test_regime_carries_the_yield_curve(monkeypatch):
    _stub_regime_inputs(monkeypatch, curve=_LIVE_CURVE)
    regime = get_market_regime(force_refresh=True)
    assert regime["yield_curve"]["curve_state"] == "inverted"
    assert regime["yield_curve"]["spread_2s10s"] == -36.0
    assert "2s10s" in regime["source_fields"]


def test_inverted_curve_reaches_the_verdict_weights(monkeypatch):
    _stub_regime_inputs(monkeypatch, curve=_LIVE_CURVE)
    regime = get_market_regime(force_refresh=True)
    assert regime["component_adjustments"]["quality"] > 0


def test_regime_survives_an_unavailable_curve(monkeypatch):
    _stub_regime_inputs(monkeypatch, curve=_DEAD_CURVE)
    regime = get_market_regime(force_refresh=True)
    # SPY still priced, so the regime itself is live — only the curve is missing.
    assert regime["data_quality"] == "live"
    assert regime["yield_curve"]["curve_state"] == "unknown"
    assert regime["component_adjustments"]["quality"] == 0


def test_regime_reports_vix_percentile(monkeypatch):
    _stub_regime_inputs(
        monkeypatch, curve=_DEAD_CURVE, vix_closes=[float(v) for v in range(10, 310)]
    )
    regime = get_market_regime(force_refresh=True)
    assert regime["vix_percentile"] == 100.0


def test_regime_omits_vix_percentile_without_enough_history(monkeypatch):
    _stub_regime_inputs(monkeypatch, curve=_DEAD_CURVE, vix_closes=[18.0] * 30)
    regime = get_market_regime(force_refresh=True)
    assert regime["vix_percentile"] is None
    assert regime["vix_band"] == "normal"

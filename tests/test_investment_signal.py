"""
Tests for app/services/investment_signal.py and related verdict infrastructure.
No real network calls — AnalystRec objects are constructed directly.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.analyst_recommendation import AnalystRec
from app.services.investment_signal import (
    InvestmentSignal,
    _needs_data,
    build_investment_signal,
    signal_to_dict,
)
from app.services.ai_service import fallback_quip, generate_verdict_quips


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _stock_rec(action="buy", count=15, mean=1.8, upside=12.0, fcf=None):
    return AnalystRec(
        ticker="NOW",
        action=action,
        label={"buy": "Buy", "hold": "Hold", "sell": "Sell"}.get(action, "Unavailable"),
        analyst_count=count,
        recommendation_mean=mean,
        target_price=120.0,
        target_upside_pct=upside,
        fcf_yield=fcf,
        subtext="test",
        source="yfinance",
        security_type="STOCK",
        rating_type="analyst",
    )


def _unavailable_rec(fcf=None, ticker="XYZ"):
    return AnalystRec(
        ticker=ticker,
        action="unavailable",
        label="Unavailable",
        analyst_count=None,
        recommendation_mean=None,
        target_price=None,
        target_upside_pct=None,
        fcf_yield=fcf,
        subtext="Analyst rating unavailable",
        source="yfinance",
        security_type="STOCK",
        rating_type="analyst",
    )


def _etf_rec(zone="Fair", quality_score=75, category_risk="Low", quality_label="Strong"):
    price_signal = {
        "priceZoneLabel": zone,
        "percentile": {"Bargain": 5.0, "Fair": 50.0, "Elevated": 65.0, "Rich": 95.0}.get(zone, 50.0),
        "dataWarnings": [],
    }
    etf_quality = {
        "score": quality_score,
        "qualityLabel": quality_label,
        "costLabel": "Low",
        "liquidityLabel": "High",
        "diversificationLabel": "Broad",
        "categoryRiskLabel": category_risk,
    }
    return AnalystRec(
        ticker="VOO",
        action="etf-quality",
        label=f"ETF Quality: {quality_label}",
        analyst_count=None,
        recommendation_mean=None,
        target_price=None,
        target_upside_pct=None,
        fcf_yield=None,
        subtext="Low cost · High liquidity",
        source="etf-quality",
        security_type="ETF",
        rating_type="etf_quality",
        etf_quality=etf_quality,
        price_signal=price_signal,
    )


# ── Stock buy/hold/sell → add/hold/trim mapping ────────────────────────────────

class TestStockActionMapping:
    def test_buy_maps_to_add(self):
        sig = build_investment_signal(_stock_rec("buy"))
        assert sig.action == "add"
        assert sig.label == "Add"

    def test_hold_maps_to_hold(self):
        sig = build_investment_signal(_stock_rec("hold", mean=3.0, upside=1.0))
        assert sig.action == "hold"
        assert sig.label == "Hold"

    def test_sell_maps_to_trim(self):
        sig = build_investment_signal(_stock_rec("sell", mean=4.5, upside=-8.0))
        assert sig.action == "trim"
        assert sig.label == "Trim"


# ── Confidence bounds ──────────────────────────────────────────────────────────

class TestConfidenceBounds:
    def test_confidence_is_0_to_100(self):
        for action in ("buy", "hold", "sell"):
            sig = build_investment_signal(_stock_rec(action))
            assert 0 <= sig.confidence <= 100, f"confidence out of range for {action}"

    def test_unavailable_no_fcf_is_needs_data_with_0_confidence(self):
        sig = build_investment_signal(_unavailable_rec(fcf=None))
        assert sig.action == "needs-data"
        assert sig.confidence == 0

    def test_needs_data_sentinel_confidence(self):
        sig = _needs_data("ABC")
        assert sig.confidence == 0
        assert sig.action == "needs-data"

    def test_no_analyst_fcf_high_confidence_capped_at_45(self):
        sig = build_investment_signal(_unavailable_rec(fcf=8.0))
        assert sig.confidence <= 45

    def test_strong_buy_conviction_boosts_confidence(self):
        sig_strong = build_investment_signal(_stock_rec("buy", count=25, mean=1.0, upside=25.0))
        sig_weak   = build_investment_signal(_stock_rec("buy", count=2,  mean=2.8, upside=2.0))
        assert sig_strong.confidence > sig_weak.confidence


# ── ETF price-zone → action mapping ───────────────────────────────────────────

class TestEtfActionMapping:
    def test_bargain_zone_gives_add(self):
        sig = build_investment_signal(_etf_rec("Bargain"))
        assert sig.action == "add"

    def test_fair_zone_gives_hold(self):
        sig = build_investment_signal(_etf_rec("Fair"))
        assert sig.action == "hold"

    def test_elevated_zone_gives_hold(self):
        sig = build_investment_signal(_etf_rec("Elevated"))
        assert sig.action == "hold"

    def test_rich_zone_gives_trim(self):
        sig = build_investment_signal(_etf_rec("Rich"))
        assert sig.action == "trim"

    def test_unavailable_zone_gives_needs_data(self):
        sig = build_investment_signal(_etf_rec("Unavailable"))
        assert sig.action == "needs-data"
        assert sig.confidence == 0


# ── Speculative gate ───────────────────────────────────────────────────────────

class TestSpeculativeGate:
    def test_speculative_bargain_capped_at_hold(self):
        sig = build_investment_signal(_etf_rec("Bargain", category_risk="Speculative"))
        assert sig.action == "hold", "Speculative ETF in Bargain zone must not output 'add'"

    def test_speculative_risk_bullet_present(self):
        sig = build_investment_signal(_etf_rec("Bargain", category_risk="Speculative"))
        risk_text = " ".join(sig.risks)
        assert "speculative" in risk_text.lower() or "Speculative" in risk_text

    def test_non_speculative_bargain_is_add(self):
        sig = build_investment_signal(_etf_rec("Bargain", category_risk="Low"))
        assert sig.action == "add"


# ── Allocation risk modifier ───────────────────────────────────────────────────

class TestAllocationRisk:
    def test_high_allocation_adds_risk_bullet(self):
        sig = build_investment_signal(_stock_rec("buy"), allocation_pct=15.0)
        risk_text = " ".join(sig.risks)
        assert "concentration" in risk_text.lower()

    def test_high_allocation_add_softens_confidence(self):
        sig_no_alloc = build_investment_signal(_stock_rec("buy"))
        sig_high_alloc = build_investment_signal(_stock_rec("buy"), allocation_pct=15.0)
        assert sig_high_alloc.confidence <= sig_no_alloc.confidence

    def test_watchlist_skips_concentration_penalty(self):
        sig_watchlist = build_investment_signal(_stock_rec("buy"), allocation_pct=15.0, is_watchlist=True)
        sig_no_watch  = build_investment_signal(_stock_rec("buy"), allocation_pct=15.0)
        # watchlist should not have concentration risk bullet
        risk_text = " ".join(sig_watchlist.risks)
        assert "concentration" not in risk_text.lower()

    def test_low_allocation_no_risk_bullet(self):
        sig = build_investment_signal(_stock_rec("buy"), allocation_pct=2.0)
        risk_text = " ".join(sig.risks)
        assert "concentration" not in risk_text.lower()


# ── needs-data path ────────────────────────────────────────────────────────────

class TestNeedsData:
    def test_needs_data_has_no_reasons(self):
        sig = _needs_data("ABC")
        assert sig.reasons == []

    def test_needs_data_has_generic_risk(self):
        sig = _needs_data("ABC")
        assert len(sig.risks) >= 1

    def test_unavailable_no_fcf_needs_data(self):
        sig = build_investment_signal(_unavailable_rec())
        assert sig.action == "needs-data"

    def test_exception_in_build_returns_needs_data(self):
        bad_rec = MagicMock(spec=AnalystRec)
        bad_rec.ticker = "ERR"
        bad_rec.security_type = "STOCK"
        bad_rec.action = "buy"
        bad_rec.analyst_count = None
        bad_rec.recommendation_mean = None
        bad_rec.target_upside_pct = None
        bad_rec.fcf_yield = None
        # Make something blow up inside the scorer
        type(bad_rec).action = property(lambda s: (_ for _ in ()).throw(RuntimeError("oops")))
        sig = build_investment_signal(bad_rec)
        assert sig.action == "needs-data"


# ── source_fields populated ────────────────────────────────────────────────────

class TestSourceFields:
    def test_stock_buy_has_source_fields(self):
        sig = build_investment_signal(_stock_rec("buy"))
        assert len(sig.source_fields) >= 1
        assert "action" in sig.source_fields

    def test_etf_has_price_signal_source(self):
        sig = build_investment_signal(_etf_rec("Bargain"))
        assert any("price_signal" in s for s in sig.source_fields)

    def test_allocation_adds_source_field(self):
        sig = build_investment_signal(_stock_rec("buy"), allocation_pct=15.0)
        assert "allocation_pct" in sig.source_fields


# ── signal_to_dict ─────────────────────────────────────────────────────────────

class TestSignalToDict:
    def test_returns_json_serializable_dict(self):
        sig = build_investment_signal(_stock_rec("buy"))
        d = signal_to_dict(sig)
        json.dumps(d)  # must not raise

    def test_dict_has_all_required_keys(self):
        sig = build_investment_signal(_stock_rec("buy"))
        d = signal_to_dict(sig)
        for key in ("ticker", "action", "label", "confidence", "reasons",
                    "risks", "data_quality", "source_fields", "generated_at"):
            assert key in d, f"signal_to_dict missing key: {key}"


# ── fallback_quip ──────────────────────────────────────────────────────────────

class TestFallbackQuip:
    @pytest.mark.parametrize("action", ["add", "hold", "trim", "needs-data"])
    def test_returns_non_empty_sentence(self, action):
        q = fallback_quip(action)
        assert isinstance(q, str)
        assert len(q) > 0

    def test_unknown_action_returns_string(self):
        q = fallback_quip("unknown-action")
        assert isinstance(q, str)
        assert len(q) > 0

    def test_rotates_across_calls(self):
        results = {fallback_quip("add") for _ in range(4)}
        assert len(results) > 1, "fallback_quip should rotate through templates"


# ── generate_verdict_quips ─────────────────────────────────────────────────────

class TestGenerateVerdictQuips:
    def test_returns_empty_dict_on_api_error(self):
        with patch("app.services.ai_service.client") as mock_client:
            mock_client.messages.create.side_effect = Exception("network error")
            result = generate_verdict_quips([
                {"ticker": "NOW", "action": "add", "confidence": 72, "reason": "Analysts bullish"}
            ])
        assert result == {}

    def test_returns_empty_dict_on_empty_signals(self):
        result = generate_verdict_quips([])
        assert result == {}

    def test_parses_valid_json_response(self):
        mock_msg = MagicMock()
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = '{"NOW": "Quietly stacking gains like nobody is watching."}'
        mock_msg.content = [mock_block]
        with patch("app.services.ai_service.client") as mock_client:
            mock_client.messages.create.return_value = mock_msg
            result = generate_verdict_quips([
                {"ticker": "NOW", "action": "add", "confidence": 72, "reason": "Analysts bullish"}
            ])
        assert "NOW" in result
        assert isinstance(result["NOW"], str)
        assert len(result["NOW"]) > 0

    def test_parses_json_with_code_fence(self):
        mock_msg = MagicMock()
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = '```json\n{"VOO": "The index never blinked."}\n```'
        mock_msg.content = [mock_block]
        with patch("app.services.ai_service.client") as mock_client:
            mock_client.messages.create.return_value = mock_msg
            result = generate_verdict_quips([
                {"ticker": "VOO", "action": "hold", "confidence": 55, "reason": "Fair value zone"}
            ])
        assert "VOO" in result

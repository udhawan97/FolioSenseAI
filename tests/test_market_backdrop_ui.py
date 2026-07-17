"""Tests for the market backdrop strip — yield curve card + VIX percentile."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _backdrop_block() -> str:
    js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")
    assert "function _buildMarketBackdropBlock" in js
    return js.split("function _buildMarketBackdropBlock")[1][:8000]


def test_backdrop_reads_the_yield_curve_off_the_regime():
    block = _backdrop_block()
    assert "yield_curve" in block
    assert "curve_state" in block


def test_curve_card_is_gated_on_a_known_enum_like_every_other_card():
    # The strip only renders values the backend explicitly supports.
    block = _backdrop_block()
    assert "KNOWN_CURVE" in block
    for state in ("inverted", "flat", "normal", "steep"):
        assert f'"{state}"' in block


def test_curve_card_names_the_spread_it_is_reporting():
    block = _backdrop_block()
    assert "Yield curve" in block
    assert "2s10s" in block
    assert "spread_2s10s" in block


def test_inverted_curve_reads_as_negative():
    block = _backdrop_block()
    inverted = block.split('curveState === "inverted"')[1][:300]
    assert "Inverted" in inverted
    assert "negative" in inverted


def test_backdrop_reports_where_vix_sits_in_its_own_range():
    block = _backdrop_block()
    assert "vix_percentile" in block
    assert "5 years" in block

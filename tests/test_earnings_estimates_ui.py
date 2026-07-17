"""The earnings radar surfaces consensus estimates, not just dates."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js() -> str:
    return (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")


def test_estimate_helper_exists():
    assert "function _earningsEstimateText" in _js()


def test_estimate_text_reads_the_backend_fields():
    helper = _js().split("function _earningsEstimateText")[1][:900]
    assert "eps_estimate" in helper
    assert "beats" in helper
    assert "quarters" in helper


def test_estimate_text_is_empty_without_an_estimate():
    # No estimate is common (fresh listings, thin coverage) and must stay quiet.
    helper = _js().split("function _earningsEstimateText")[1][:900]
    assert "isFinite" in helper


def test_radar_chips_carry_the_estimate():
    strip = _js().split("function renderEarningsStrip")[1][:1600]
    assert "_earningsEstimateText" in strip


def test_holding_badge_carries_the_estimate():
    badge = _js().split("function earningsBadgeHtml")[1][:900]
    assert "_earningsEstimateText" in badge

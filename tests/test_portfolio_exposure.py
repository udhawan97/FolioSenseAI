"""Tests for portfolio look-through exposure."""
from app.services.portfolio_exposure import (
    build_portfolio_exposure,
    exposure_context_for_ticker,
    _concentration_hhi,
)


def test_concentration_hhi_single_sector():
    sectors = [{"name": "Tech", "weight_pct": 100.0}]
    assert _concentration_hhi(sectors) == 1.0


def test_build_portfolio_exposure_empty():
    result = build_portfolio_exposure([])
    assert result["holding_count"] == 0
    assert result["sector_exposure"] == []


def test_build_portfolio_exposure_voo_only():
    holdings = [{"ticker": "VOO", "allocation_pct": 50.0, "is_watchlist": False}]
    result = build_portfolio_exposure(holdings)
    assert result["holding_count"] == 1
    assert len(result["sector_exposure"]) >= 1
    tech = next((s for s in result["sector_exposure"] if "tech" in s["name"].lower()), None)
    assert tech is not None
    assert tech["weight_pct"] > 10


def test_exposure_context_crowded_theme():
    exposure = {
        "theme_overlap": [{"theme": "US tech exposure", "weight_pct": 38, "label": "~38% US tech"}],
        "sector_exposure": [{"name": "Technology", "weight_pct": 38}],
    }
    ctx = exposure_context_for_ticker(exposure, "QQQ")
    assert ctx is not None
    assert ctx.get("crowded_themes")

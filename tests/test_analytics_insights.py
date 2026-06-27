"""
Tests for analytics insights service and GET /api/ai/analytics-insights.
"""
import asyncio
import json
from unittest.mock import MagicMock, patch

from app.services.analytics_insights import (
    MODULE_DIGEST,
    build_analytics_snapshot,
    build_local_analytics_insights,
)


_FAKE_SNAPSHOT = {
    "as_of": "2026-06-27",
    "performance": {
        "has_holdings": True,
        "total_return_pct": 12.5,
        "today_pnl_pct": 0.8,
        "history_days": 30,
        "max_drawdown_pct": -5.2,
    },
    "risk": {
        "has_data": True,
        "concentration_hhi": 0.35,
        "portfolio_vol_pct": 18.0,
        "max_drawdown_pct": -5.2,
        "top_sector": "Technology",
    },
    "exposure": {
        "has_data": True,
        "top_sectors": [{"name": "Technology", "weight_pct": 42.0}],
        "top_countries": [{"name": "United States", "weight_pct": 65.0}],
    },
    "signals": {
        "has_data": True,
        "dominant_action": "hold",
        "hold_weight_pct": 70.0,
        "add_weight_pct": 20.0,
        "trim_weight_pct": 10.0,
        "avg_confidence": 72,
    },
    "markets": {
        "has_data": True,
        "best_match_name": "S&P 500",
        "best_correlation": 0.82,
        "us_exposure_pct": 65.0,
        "summary": "Moves with US equities.",
    },
}

_AI_INSIGHTS = {
    "performance": "Your portfolio is up 12.5% overall with a steady 0.8% gain today.",
    "risk": "Technology concentration keeps volatility near 18% annually.",
    "exposure": "Technology dominates your look-through book at 42%.",
    "signals": "Most of the book sits on hold with solid confidence.",
    "markets": "Your holdings track the S&P 500 more closely than other regions.",
}

_AI_WIDGET_INSIGHTS = {
    "benchmark-tracker": "You are beating the S&P 500 over the past year.",
    "beta-dial": "Beta near 1.0 means your book moves with the market.",
}


def test_local_insights_include_digest_and_one_liners():
    payload = build_local_analytics_insights(_FAKE_SNAPSHOT)
    assert payload["mode"] == "local"
    assert payload["digest"] == MODULE_DIGEST
    assert "performance" in payload["insights"]
    assert "risk" in payload["insights"]
    assert "+12.5%" in payload["insights"]["performance"]
    assert payload["insights"]["exposure"].startswith("Largest look-through")
    assert "widget_insights" in payload
    assert "benchmark-tracker" in payload["widget_insights"] or "total-return" in payload["widget_insights"]


def test_analytics_insights_local_endpoint():
    from app.routers.ai import get_analytics_insights

    db = MagicMock()
    with patch("app.services.analytics_insights.build_analytics_snapshot", return_value=_FAKE_SNAPSHOT):
        result = asyncio.run(get_analytics_insights(mode="local", force_refresh=False, db=db))
    assert result["mode"] == "local"
    assert result["digest"]["risk"] == MODULE_DIGEST["risk"]
    assert "insights" in result


def test_analytics_insights_ai_endpoint_uses_claude():
    from app.routers.ai import get_analytics_insights

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

    with patch("app.services.analytics_insights.build_analytics_snapshot", return_value=_FAKE_SNAPSHOT), patch(
        "app.routers.ai.generate_analytics_insights",
        return_value={"insights": _AI_INSIGHTS, "widget_insights": _AI_WIDGET_INSIGHTS},
    ):
        result = asyncio.run(get_analytics_insights(mode="ai", force_refresh=True, db=db))

    assert result["mode"] == "ai"
    assert result["source"] == "claude"
    assert result["insights"]["markets"] == _AI_INSIGHTS["markets"]
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_analytics_insights_ai_serves_cache():
    from datetime import datetime, timezone

    from app.models import AISummary
    from app.routers.ai import get_analytics_insights

    cached_payload = {
        "mode": "ai",
        "source": "claude",
        "insights": _AI_INSIGHTS,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    cached = AISummary(
        ticker="BOOK",
        summary_type="analytics_insights",
        summary_text=json.dumps(cached_payload),
        generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = cached

    with patch("app.services.analytics_insights.build_analytics_snapshot") as snap_mock, patch(
        "app.routers.ai.generate_analytics_insights"
    ) as gen_mock:
        result = asyncio.run(get_analytics_insights(mode="ai", force_refresh=False, db=db))

    assert result["from_cache"] is True
    assert result["insights"]["risk"] == _AI_INSIGHTS["risk"]
    snap_mock.assert_not_called()
    gen_mock.assert_not_called()

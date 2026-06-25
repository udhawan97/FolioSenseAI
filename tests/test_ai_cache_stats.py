"""
Tests for AI cache accounting.
"""
import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.models import AISummary, Base
from app.routers.ai import get_ai_cache_stats


def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_ai_cache_stats_excludes_local_fallback_rows_from_token_cost(monkeypatch):
    db = _make_db()
    db.add_all([
        AISummary(
            ticker="NOW",
            summary_type="verdict",
            summary_text="Local fallback note.",
            model_used="fallback",
        ),
        AISummary(
            ticker="VOO",
            summary_type="scan",
            summary_text="Deterministic scan note.",
            model_used="deterministic",
        ),
        AISummary(
            ticker="AAPL",
            summary_type="stock",
            summary_text="Claude-backed cached summary.",
            model_used="claude-haiku-4-5-20251001",
        ),
    ])
    db.commit()
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")

    stats = asyncio.run(get_ai_cache_stats(db))

    assert stats["cached_summaries"] == 3
    assert stats["claude_cached_summaries"] == 1
    assert stats["local_cached_summaries"] == 2
    assert stats["estimated_input_tokens"] > 0
    assert stats["estimated_output_tokens"] > 0
    assert stats["estimated_total_tokens"] == (
        stats["estimated_input_tokens"] + stats["estimated_output_tokens"]
    )


def test_ai_cache_stats_marks_billing_paused_without_api_key(monkeypatch):
    db = _make_db()
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")

    stats = asyncio.run(get_ai_cache_stats(db))

    assert stats["claude_configured"] is False
    assert stats["billing_active"] is False
    assert "paused" in stats["note"]

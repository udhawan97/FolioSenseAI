"""Tests for verdict calibration snapshots."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.services.verdict_calibration import (
    log_verdict_snapshot,
    calibration_summary,
    _predicted_band,
)


def _db():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_predicted_band():
    assert _predicted_band(75) == "70+"
    assert _predicted_band(60) == "55-69"
    assert _predicted_band(45) == "40-54"


def test_log_and_summary():
    db = _db()
    log_verdict_snapshot(
        db,
        ticker="VOO",
        action="hold",
        confidence=62,
        local_score=62,
        ai_score=None,
        price_at_scan=450.0,
    )
    db.commit()
    summary = calibration_summary(db)
    assert summary["total_snapshots"] == 1
    assert len(summary["buckets"]) >= 1

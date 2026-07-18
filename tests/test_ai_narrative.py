"""Interface tests for the cached-Claude-narrative flow.

Exercised directly with fake closures — no router, no endpoint, no Claude.  What
is pinned here is the policy the four narrative endpoints used to each own a copy
of: when the snapshot gets built, when Claude gets called, what happens to the
result, and which failures the caller is allowed to see.
"""

import json
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import AISummary, Base
from app.services import ai_narrative


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


_COMPLETE = {"valuation": {"data_quality": "complete", "missing_tickers": []}}
_PARTIAL = {"valuation": {"data_quality": "partial", "missing_tickers": ["MSFT"]}}


class _Calls:
    """Records which closures ran, so 'was Claude paid for?' is assertable."""

    def __init__(self, snapshot=None, payload=None, generate_error=None,
                 snapshot_error=None):
        self.snapshot_value = _COMPLETE if snapshot is None else snapshot
        self.payload = payload if payload is not None else {"text": "generated"}
        self.generate_error = generate_error
        self.snapshot_error = snapshot_error
        self.snapshots = 0
        self.generates = 0
        self.fallbacks: list = []

    def build_snapshot(self) -> dict:
        self.snapshots += 1
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return dict(self.snapshot_value)

    def generate(self, _snapshot: dict) -> dict:
        self.generates += 1
        if self.generate_error is not None:
            raise self.generate_error
        return dict(self.payload)

    def fallback(self, snapshot: dict | None) -> dict:
        self.fallbacks.append(snapshot)
        return {"source": "local-fallback"}


def run(db, calls, **kwargs):
    return ai_narrative.narrative(
        db,
        "BOOK:1",
        "unit_test",
        build_snapshot=calls.build_snapshot,
        generate=calls.generate,
        fallback=calls.fallback,
        model="test-model",
        label="Unit narrative",
        **kwargs,
    )


def stored_rows(db):
    return db.query(AISummary).filter(AISummary.summary_type == "unit_test").all()


# ── Generation, caching and refresh ───────────────────────────────────────────

def test_first_call_generates_and_stores_and_second_call_serves_the_cache():
    db = make_db()
    calls = _Calls()

    first = run(db, calls)
    assert first == {"text": "generated"}
    assert "from_cache" not in first
    rows = stored_rows(db)
    assert len(rows) == 1
    assert json.loads(rows[0].summary_text) == {"text": "generated"}
    assert rows[0].model_used == "test-model"

    second = run(db, calls)
    assert second["from_cache"] is True
    assert second["text"] == "generated"
    # A served cache entry costs neither market data nor a Claude call.
    assert (calls.snapshots, calls.generates) == (1, 1)


def test_force_refresh_skips_the_read_but_still_writes():
    db = make_db()
    calls = _Calls()

    run(db, calls)
    refreshed = run(db, calls, force_refresh=True)

    assert "from_cache" not in refreshed
    assert calls.generates == 2
    assert len(stored_rows(db)) == 2


def test_validator_rejects_an_outgrown_cache_entry_and_forces_regeneration():
    db = make_db()
    calls = _Calls(payload={"text": "v1", "version": 1})
    run(db, calls)

    calls.payload = {"text": "v2", "version": 2}
    result = run(db, calls, validator=lambda payload: payload.get("version", 1) >= 2)

    assert result == {"text": "v2", "version": 2}
    assert calls.generates == 2


def test_a_stale_entry_is_not_served():
    db = make_db()
    calls = _Calls()
    run(db, calls, ttl=timedelta(seconds=0))

    second = run(db, calls, ttl=timedelta(seconds=0))

    assert "from_cache" not in second
    assert calls.generates == 2


# ── The data-quality gate ─────────────────────────────────────────────────────

def test_incomplete_valuation_skips_claude_and_hands_the_snapshot_to_the_fallback():
    db = make_db()
    calls = _Calls(snapshot=_PARTIAL)

    result = run(db, calls)

    assert result == {"source": "local-fallback"}
    assert calls.generates == 0
    assert calls.fallbacks == [_PARTIAL]
    # Nothing deterministic is ever written to the Claude cache.
    assert stored_rows(db) == []


def test_quality_ok_is_the_seam_for_a_narrative_with_its_own_notion_of_enough_data():
    db = make_db()
    calls = _Calls(snapshot=_PARTIAL)

    result = run(db, calls, quality_ok=lambda snapshot: True)

    assert result == {"text": "generated"}
    assert calls.generates == 1
    assert not calls.fallbacks


# ── Failure absorption ────────────────────────────────────────────────────────

def test_a_claude_failure_falls_back_on_the_snapshot_it_already_built():
    db = make_db()
    calls = _Calls(generate_error=RuntimeError("Claude down"))

    result = run(db, calls)

    assert result == {"source": "local-fallback"}
    assert calls.fallbacks == [_COMPLETE]
    assert stored_rows(db) == []


def test_a_snapshot_failure_falls_back_with_no_snapshot_at_all():
    db = make_db()
    calls = _Calls(snapshot_error=ValueError("no market data"))

    result = run(db, calls)

    assert result == {"source": "local-fallback"}
    assert calls.generates == 0
    assert calls.fallbacks == [None]


def test_a_fallback_that_raises_declares_the_narrative_cannot_degrade():
    db = make_db()
    calls = _Calls(snapshot_error=ValueError("no market data"))

    class _Boom(Exception):
        pass

    def refuse(_snapshot):
        raise _Boom()

    try:
        ai_narrative.narrative(
            db,
            "BOOK:1",
            "unit_test",
            build_snapshot=calls.build_snapshot,
            generate=calls.generate,
            fallback=refuse,
            model="test-model",
            label="Unit narrative",
        )
    except _Boom:
        pass
    else:
        raise AssertionError("a raising fallback must reach the caller")


def test_a_failed_cache_write_still_serves_the_generated_payload():
    db = make_db()
    calls = _Calls()

    def explode(*_args, **_kwargs):
        raise RuntimeError("disk full")

    db.add = explode  # every store path goes through Session.add

    result = run(db, calls)

    assert result == {"text": "generated"}


# ── The gate's default ────────────────────────────────────────────────────────

def test_valuation_is_complete_only_accepts_a_fully_priced_book():
    assert ai_narrative.valuation_is_complete(_COMPLETE) is True
    assert ai_narrative.valuation_is_complete(_PARTIAL) is False
    assert ai_narrative.valuation_is_complete({"valuation": None}) is False
    assert ai_narrative.valuation_is_complete({}) is False

"""Coherent persistence interface for cached AI narratives.

Portfolio narratives use ``BOOK:<portfolio_id>`` scopes because the historical
``ai_summaries`` table has no portfolio column.  This module owns that encoding,
freshness and price-drift rules, JSON corruption handling, and writes.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.models import AISummary
from app.services.verdict_ai_enhancement import (
    decode_verdict_cache,
    encode_verdict_cache,
)

DEFAULT_TTL = timedelta(hours=24)
DEFAULT_PRICE_DRIFT_THRESHOLD = 0.08


def portfolio_scope(portfolio_id: int = 1) -> str:
    """Return the persisted scope for one Portfolio's narratives."""
    return f"BOOK:{portfolio_id}"


def is_fresh(
    cached: AISummary,
    *,
    ttl: timedelta = DEFAULT_TTL,
    current_price: float | None = None,
    price_drift_threshold: float = DEFAULT_PRICE_DRIFT_THRESHOLD,
    now: datetime | None = None,
) -> bool:
    """Check age and optional market-price drift for a cached narrative."""
    generated_at: datetime = getattr(cached, "generated_at")
    if generated_at.tzinfo is not None:
        generated_at = generated_at.astimezone(timezone.utc).replace(tzinfo=None)
    reference = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if reference.tzinfo is not None:
        reference = reference.astimezone(timezone.utc).replace(tzinfo=None)
    if reference - generated_at > ttl:
        return False
    cached_price = getattr(cached, "price_when_generated", None)
    if current_price is not None and cached_price is not None and cached_price > 0:
        drift = abs(current_price - cached_price) / cached_price
        if drift > price_drift_threshold:
            return False
    return True


class NarrativeCache:
    """Read and write fresh text or structured narratives through one seam."""

    def __init__(
        self,
        db: Session,
        *,
        ttl: timedelta = DEFAULT_TTL,
        price_drift_threshold: float = DEFAULT_PRICE_DRIFT_THRESHOLD,
    ):
        self.db = db
        self.ttl = ttl
        self.price_drift_threshold = price_drift_threshold

    def latest(self, scope: str, narrative_type: str) -> AISummary | None:
        """Return the latest row regardless of freshness."""
        return (
            self.db.query(AISummary)
            .filter(
                AISummary.ticker == scope,
                AISummary.summary_type == narrative_type,
            )
            .order_by(AISummary.generated_at.desc())
            .first()
        )

    def fresh(
        self,
        scope: str,
        narrative_type: str,
        *,
        current_price: float | None = None,
    ) -> AISummary | None:
        """Return the latest fresh row for callers that need cache metadata."""
        cached = self.latest(scope, narrative_type)
        if cached is None or not is_fresh(
            cached,
            ttl=self.ttl,
            current_price=current_price,
            price_drift_threshold=self.price_drift_threshold,
        ):
            return None
        return cached

    def fresh_many(
        self,
        scopes: list[str],
        narrative_type: str,
        *,
        current_prices: dict[str, float | None] | None = None,
    ) -> dict[str, AISummary]:
        """Batch-load the latest fresh narrative for each requested scope."""
        if not scopes:
            return {}
        latest_by_scope: dict[str, AISummary] = {}
        for row in (
            self.db.query(AISummary)
            .filter(
                AISummary.ticker.in_(scopes),
                AISummary.summary_type == narrative_type,
            )
            .order_by(AISummary.generated_at.desc())
            .all()
        ):
            latest_by_scope.setdefault(str(row.ticker), row)

        prices = current_prices or {}
        return {
            scope: row
            for scope in scopes
            if (row := latest_by_scope.get(scope)) is not None
            and is_fresh(
                row,
                ttl=self.ttl,
                current_price=prices.get(scope),
                price_drift_threshold=self.price_drift_threshold,
            )
        }

    def get_text(
        self,
        scope: str,
        narrative_type: str,
        *,
        current_price: float | None = None,
    ) -> str | None:
        """Return a fresh narrative string, or ``None`` when absent/stale."""
        cached = self.fresh(
            scope,
            narrative_type,
            current_price=current_price,
        )
        if cached is None:
            return None
        return str(getattr(cached, "summary_text", ""))

    def get_verdict(
        self,
        scope: str,
        narrative_type: str,
        *,
        current_price: float | None = None,
    ) -> dict | None:
        """Return a fresh decoded verdict bundle with its model provenance."""
        cached = self.fresh(
            scope,
            narrative_type,
            current_price=current_price,
        )
        if cached is None:
            return None
        decoded = decode_verdict_cache(getattr(cached, "summary_text", ""))
        return {
            "quip": decoded.get("quip") or "",
            "ai": decoded.get("ai"),
            "model_used": str(getattr(cached, "model_used", "") or ""),
        }

    def latest_verdict(self, scope: str) -> dict | None:
        """Return the latest fresh verdict variant for analytics readers."""
        cached = (
            self.db.query(AISummary)
            .filter(
                AISummary.ticker == scope,
                AISummary.summary_type.like("v:%"),
            )
            .order_by(AISummary.generated_at.desc())
            .first()
        )
        if cached is None or not is_fresh(cached, ttl=self.ttl):
            return None
        decoded = decode_verdict_cache(getattr(cached, "summary_text", ""))
        return {
            "quip": decoded.get("quip") or "",
            "ai": decoded.get("ai"),
            "model_used": str(getattr(cached, "model_used", "") or ""),
            "narrative_type": str(getattr(cached, "summary_type", "") or ""),
        }

    def get_json(
        self,
        scope: str,
        narrative_type: str,
        *,
        validator: Callable[[dict], bool] | None = None,
    ) -> dict | None:
        """Return a fresh decoded object; reject corruption or obsolete shapes."""
        text = self.get_text(scope, narrative_type)
        if text is None:
            return None
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        if validator is not None:
            try:
                if not validator(payload):
                    return None
            except (AttributeError, KeyError, TypeError, ValueError):
                return None
        return payload

    def store_text(
        self,
        scope: str,
        narrative_type: str,
        text: str,
        model_used: str,
        *,
        price_when_generated: float | None = None,
        commit: bool = True,
    ) -> bool:
        """Stage or commit a narrative row; rollback a failed owned commit."""
        self.db.add(
            AISummary(
                ticker=scope,
                summary_type=narrative_type,
                summary_text=text,
                price_when_generated=price_when_generated,
                model_used=model_used,
            )
        )
        if not commit:
            return True
        try:
            self.db.commit()
        except Exception:  # persistence failure is non-fatal to generated output
            self.db.rollback()
            return False
        return True

    def store_json(
        self,
        scope: str,
        narrative_type: str,
        payload: dict,
        model_used: str,
        *,
        commit: bool = True,
    ) -> bool:
        """Serialize and store one structured narrative."""
        return self.store_text(
            scope,
            narrative_type,
            json.dumps(payload),
            model_used,
            commit=commit,
        )

    def store_verdict(
        self,
        scope: str,
        narrative_type: str,
        quip: str,
        ai: dict | None,
        model_used: str,
        *,
        price_when_generated: float | None = None,
        commit: bool = True,
    ) -> bool:
        """Encode and store one ticker or Portfolio verdict narrative."""
        return self.store_text(
            scope,
            narrative_type,
            encode_verdict_cache(quip, ai),
            model_used,
            price_when_generated=price_when_generated,
            commit=commit,
        )

    def delete_portfolio(self, portfolio_id: int, *, commit: bool = True) -> int:
        """Remove every narrative owned by one Portfolio scope."""
        removed = (
            self.db.query(AISummary)
            .filter(AISummary.ticker == portfolio_scope(portfolio_id))
            .delete(synchronize_session=False)
        )
        if commit:
            self.db.commit()
        return int(removed)

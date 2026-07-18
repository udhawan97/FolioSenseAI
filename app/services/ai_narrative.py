"""One flow for every cached, Claude-written narrative.

``narrative_cache`` owns *where* a narrative is stored.  This module owns *when*
one is written, which is a separate fact and was copied into four endpoints:
serve a fresh cached copy, refuse to narrate a book whose valuation is
incomplete, call Claude once, keep what came back, and answer deterministically
the moment any of that fails.  Each copy carried its own log level, its own
``from_cache`` stamp and its own cache-write guard, and none of it could be
exercised without an HTTP handler.

The interface is one function.  A caller names the cache slot and hands over the
three closures that genuinely differ between narratives — build the snapshot, ask
Claude, answer without Claude — and inherits the rest.  ``quality_ok`` is the
seam a narrative with its own notion of "enough data" plugs into without editing
here.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Callable

from sqlalchemy.orm import Session

from app.config import settings
from app.services import narrative_cache

logger = logging.getLogger(__name__)


def valuation_is_complete(snapshot: dict) -> bool:
    """Default quality gate: every expected position carried a live price.

    A narrative built on a partly-priced book states Portfolio-level totals it
    cannot stand behind, so the deterministic answer is the honest one.
    """
    return (snapshot.get("valuation") or {}).get("data_quality") == "complete"


def _log_claude_call_result(label: str, exc: Exception) -> None:
    """Warn on a genuine Claude-call failure; debug-log the common no-key case.

    An unconfigured API key surfaces as a client-side TypeError from the
    Anthropic SDK before any request is made — the default, key-optional
    state, not a failure. Warning about it on every load would cry wolf.
    """
    if settings.ANTHROPIC_API_KEY.strip():
        logger.warning("%s failed; exception_type=%s", label, type(exc).__name__)
    else:
        logger.debug("%s skipped; no Claude API key configured", label)


def narrative(
    db: Session,
    scope: str,
    narrative_type: str,
    *,
    build_snapshot: Callable[[], dict],
    generate: Callable[[dict], dict],
    fallback: Callable[[dict | None], dict],
    model: str,
    label: str,
    force_refresh: bool = False,
    validator: Callable[[dict], bool] | None = None,
    quality_ok: Callable[[dict], bool] = valuation_is_complete,
    ttl: timedelta = narrative_cache.DEFAULT_TTL,
) -> dict:
    """Serve one cached Claude narrative, generating it only when it must.

    ``build_snapshot`` runs only on a cache miss, so a served cache entry costs
    no market data.  ``generate`` turns that snapshot into the payload to serve
    and store — it is the only step allowed to reach Claude.  ``fallback``
    answers without Claude and receives the snapshot it should describe, or
    ``None`` when even the snapshot could not be built; a ``fallback`` that
    raises is declaring that this narrative cannot degrade, and its exception
    becomes the answer.

    ``validator`` rejects a cached payload whose shape has since been outgrown,
    and ``quality_ok`` decides whether a snapshot is worth narrating at all.
    Every other failure — a cache write, a Claude timeout, a missing API key —
    is absorbed here and never reaches the caller.
    """
    cache = narrative_cache.NarrativeCache(db, ttl=ttl)

    if not force_refresh:
        stored = cache.get_json(scope, narrative_type, validator=validator)
        if stored is not None:
            stored["from_cache"] = True
            return stored

    try:
        snapshot = build_snapshot()
    except Exception as exc:
        logger.error("%s snapshot failed; exception_type=%s", label, type(exc).__name__)
        return fallback(None)

    if not quality_ok(snapshot):
        return fallback(snapshot)

    try:
        payload = generate(snapshot)
    except Exception as exc:
        _log_claude_call_result(label, exc)
        return fallback(snapshot)

    try:
        cache.store_json(scope, narrative_type, payload, model)
    except Exception as exc:
        logger.debug("Failed to cache %s; exception_type=%s", label, type(exc).__name__)
    return payload

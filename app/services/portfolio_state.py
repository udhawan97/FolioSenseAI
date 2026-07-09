"""Portfolio-level cache keys derived from signal mix and concentration."""
from __future__ import annotations

_ACTION_CACHE_CODE = {"add": "a", "hold": "h", "trim": "t", "needs-data": "n"}


def portfolio_state_signature(signals: dict[str, dict], alloc_map: dict[str, float]) -> dict:
    """Coarse portfolio-state cache key: dominant + secondary action mix + concentration band.

    Both the dominant AND second-most-common action are baked into the key. Dominant
    alone collides two meaningfully different books onto one cache entry — e.g. "2 hold,
    1 add" and "2 hold, 1 trim" both have dominant_action="hold", yet one book leans add
    and the other leans trim, which should read as a different action-plan thesis. The
    secondary action breaks that tie while staying coarse enough to still get cache hits
    across genuinely similar books.
    """
    counts = {"add": 0, "hold": 0, "trim": 0, "needs-data": 0}
    for sig in signals.values():
        action = sig.get("action", "needs-data")
        counts[action if action in counts else "needs-data"] += 1

    priority = {"hold": 3, "add": 2, "trim": 1, "needs-data": 0}
    ranked = sorted(counts, key=lambda action: (counts[action], priority[action]), reverse=True)
    dominant_action = ranked[0]
    secondary_action = ranked[1] if counts[ranked[1]] > 0 else "none"

    max_alloc = max(alloc_map.values(), default=0)
    if max_alloc >= 25:
        concentration_band = "high"
    elif max_alloc >= 12:
        concentration_band = "medium"
    else:
        concentration_band = "low"

    secondary_code = (
        _ACTION_CACHE_CODE.get(secondary_action, "x") if secondary_action != "none" else "x"
    )
    dominant_code = _ACTION_CACHE_CODE.get(dominant_action, "n")
    return {
        "dominant_action": dominant_action,
        "secondary_action": secondary_action,
        "concentration_band": concentration_band,
        "summary_type": f"vp:{dominant_code}{secondary_code}:{concentration_band}",
        "reason": (
            f"Action mix add={counts['add']}, hold={counts['hold']}, "
            f"trim={counts['trim']}; concentration {concentration_band}"
        ),
    }

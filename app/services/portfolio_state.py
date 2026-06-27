"""Portfolio-level cache keys derived from signal mix and concentration."""
from __future__ import annotations

_ACTION_CACHE_CODE = {"add": "a", "hold": "h", "trim": "t", "needs-data": "n"}


def portfolio_state_signature(signals: dict[str, dict], alloc_map: dict[str, float]) -> dict:
    """Coarse portfolio-state cache key: dominant action mix + concentration band."""
    counts = {"add": 0, "hold": 0, "trim": 0, "needs-data": 0}
    for sig in signals.values():
        action = sig.get("action", "needs-data")
        counts[action if action in counts else "needs-data"] += 1

    dominant_action = max(
        counts,
        key=lambda action: (
            counts[action],
            {"hold": 3, "add": 2, "trim": 1, "needs-data": 0}[action],
        ),
    )
    max_alloc = max(alloc_map.values(), default=0)
    if max_alloc >= 25:
        concentration_band = "high"
    elif max_alloc >= 12:
        concentration_band = "medium"
    else:
        concentration_band = "low"

    return {
        "dominant_action": dominant_action,
        "concentration_band": concentration_band,
        "summary_type": (
            f"vp:{_ACTION_CACHE_CODE.get(dominant_action, 'n')}:{concentration_band}"
        ),
        "reason": (
            f"Action mix add={counts['add']}, hold={counts['hold']}, "
            f"trim={counts['trim']}; concentration {concentration_band}"
        ),
    }

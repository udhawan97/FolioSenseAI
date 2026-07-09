"""Tests for app/services/portfolio_state.py — the action-plan cache key."""

from app.services.portfolio_state import portfolio_state_signature


def _signals(*actions):
    return {f"T{i}": {"action": action} for i, action in enumerate(actions)}


def test_dominant_action_alone_used_to_collide_secondary_disambiguates():
    """Two hold + one add, and two hold + one trim, both have dominant_action
    'hold' — the secondary action must differ so the two don't share a cache key."""
    two_hold_one_add = portfolio_state_signature(_signals("hold", "hold", "add"), {})
    two_hold_one_trim = portfolio_state_signature(_signals("hold", "hold", "trim"), {})

    assert two_hold_one_add["dominant_action"] == "hold"
    assert two_hold_one_trim["dominant_action"] == "hold"
    assert two_hold_one_add["summary_type"] != two_hold_one_trim["summary_type"]


def test_identical_action_mix_still_shares_a_cache_key():
    """Coarseness is the point — two portfolios with the same action mix and
    concentration band should still hit the same cache entry."""
    a = portfolio_state_signature(_signals("hold", "hold", "add"), {"X": 5})
    b = portfolio_state_signature(_signals("hold", "hold", "add"), {"Y": 6})
    assert a["summary_type"] == b["summary_type"]


def test_no_secondary_action_falls_back_cleanly():
    sig = portfolio_state_signature(_signals("hold"), {})
    assert sig["secondary_action"] == "none"
    assert sig["summary_type"]


def test_concentration_band_still_folded_into_key():
    low = portfolio_state_signature(_signals("hold", "add"), {"X": 5})
    high = portfolio_state_signature(_signals("hold", "add"), {"X": 30})
    assert low["summary_type"] != high["summary_type"]

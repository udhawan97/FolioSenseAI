"""Tests for peer-relative valuation."""
from unittest.mock import patch

from app.services.peer_relative import (
    compute_peer_relative,
    peer_valuation_nudge,
    _percentile_in_range,
)


def test_percentile_in_range():
    closes = list(range(100, 200))
    pct = _percentile_in_range(closes)
    assert pct is not None
    assert 95 <= pct <= 100


def test_peer_valuation_nudge_cheaper_add():
    peer = {"peer_comparison": "cheaper_than_peers"}
    assert peer_valuation_nudge(peer, "add") == 6


def test_peer_valuation_nudge_richer_trim():
    peer = {"peer_comparison": "richer_than_peers"}
    assert peer_valuation_nudge(peer, "trim") == 6


@patch("app.services.peer_relative.get_cached_history_closes", return_value=[])
def test_compute_peer_relative_own_range(_mock):
    result = compute_peer_relative(
        "VOO",
        own_percentile=25.0,
        zone="Bargain",
    )
    assert result["vs_own_range"] == 25.0
    assert "Cheap" in result["vs_own_label"]

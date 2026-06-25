"""
app/services/investment_signal.py

Deterministic investment signal builder — no network calls of its own.
Consumes an AnalystRec plus holding context to produce a structured verdict.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.services.analyst_recommendation import AnalystRec

logger = logging.getLogger(__name__)

# Allocation threshold for concentration-risk warnings
_HIGH_ALLOC_PCT = 10.0

# FCF yield threshold for a "clearly high" cash generator
_HIGH_FCF_YIELD = 4.0

# Confidence adjustment when position is already large
_CONCENTRATION_CONF_PENALTY = 10


@dataclass
class InvestmentSignal:  # pylint: disable=too-many-instance-attributes
    ticker: str
    action: str                 # add | hold | trim | needs-data
    label: str                  # Add | Hold | Trim | Needs Data
    confidence: int             # 0-100
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    data_quality: str = "low"   # high | medium | low
    source_fields: list[str] = field(default_factory=list)
    generated_at: str = ""


def signal_to_dict(sig: InvestmentSignal) -> dict:
    return {
        "ticker": sig.ticker,
        "action": sig.action,
        "label": sig.label,
        "confidence": sig.confidence,
        "reasons": sig.reasons,
        "risks": sig.risks,
        "data_quality": sig.data_quality,
        "source_fields": sig.source_fields,
        "generated_at": sig.generated_at,
    }


def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


def _action_label(action: str) -> str:
    return {"add": "Add", "hold": "Hold", "trim": "Trim", "needs-data": "Needs Data"}[action]


def _needs_data(ticker: str) -> InvestmentSignal:
    return InvestmentSignal(
        ticker=ticker,
        action="needs-data",
        label="Needs Data",
        confidence=0,
        reasons=[],
        risks=["Insufficient data to form a view"],
        data_quality="low",
        source_fields=[],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def _apply_allocation_modifier(
    sig: InvestmentSignal,
    allocation_pct: Optional[float],
    is_watchlist: bool,
) -> None:
    """Mutate sig in-place: add concentration risk when position is large."""
    if allocation_pct is None or is_watchlist:
        return
    if allocation_pct >= _HIGH_ALLOC_PCT:
        sig.risks.append(
            f"Already a large position ({allocation_pct:.0f}% of portfolio)"
            " — concentration risk"
        )
        sig.source_fields.append("allocation_pct")
        if sig.action == "add":
            sig.confidence = _clamp(sig.confidence - _CONCENTRATION_CONF_PENALTY)


def _build_stock_signal(
    rec: AnalystRec,
    allocation_pct: Optional[float],
    is_watchlist: bool,
) -> InvestmentSignal:
    """Signal for a stock with analyst coverage (buy/hold/sell)."""
    analyst_action = rec.action  # buy | hold | sell
    action_map = {"buy": "add", "hold": "hold", "sell": "trim"}
    action = action_map.get(analyst_action, "needs-data")
    if action == "needs-data":
        return _needs_data(rec.ticker)

    # Base confidence
    conf = 45
    source = ["action"]

    count = rec.analyst_count or 0
    conf += min(count, 25)
    if count:
        source.append("analyst_count")

    mean = rec.recommendation_mean
    if mean is not None:
        conf += round(abs(3.0 - mean) * 12)
        source.append("recommendation_mean")

    # Upside/downside agreement bonus
    upside = rec.target_upside_pct
    if upside is not None:
        source.append("target_upside_pct")
        if action == "add" and upside > 10:
            conf += 8
        elif action == "trim" and upside < -10:
            conf += 8

    conf = _clamp(conf)

    # Reasons
    reasons: list[str] = []
    if count:
        _map = {"buy": "Buy", "hold": "Hold", "sell": "Sell"}
        _rating = _map.get(analyst_action, analyst_action.capitalize())
        reasons.append(
            f"{count} analyst{'s' if count != 1 else ''} rate this a {_rating}"
        )
    if upside is not None and rec.target_price is not None:
        sign = "+" if upside >= 0 else ""
        reasons.append(f"Analyst price target implies {sign}{upside:.0f}% from here")
    fcf = rec.fcf_yield
    if fcf is not None and fcf >= _HIGH_FCF_YIELD:
        reasons.append(f"Strong FCF yield of {fcf:.1f}%")
        source.append("fcf_yield")

    reasons = reasons[:3]

    # Risks
    risks: list[str] = []
    if action == "add" and upside is not None and upside < 5:
        risks.append("Limited analyst upside despite buy rating — monitor conviction")
    if action == "trim" and (count or 0) < 3:
        risks.append("Thin analyst coverage — sell signal carries low conviction")
    if not risks:
        risks.append("Analyst consensus can lag rapidly changing fundamentals")

    quality = "high" if count >= 5 and mean is not None else "medium" if count >= 1 else "low"

    sig = InvestmentSignal(
        ticker=rec.ticker,
        action=action,
        label=_action_label(action),
        confidence=conf,
        reasons=reasons,
        risks=risks[:2],
        data_quality=quality,
        source_fields=source,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    _apply_allocation_modifier(sig, allocation_pct, is_watchlist)
    return sig


def _build_stock_no_analyst_signal(
    rec: AnalystRec,
    allocation_pct: Optional[float],
    is_watchlist: bool,
) -> InvestmentSignal:
    """Signal for a stock without analyst coverage but possibly with FCF yield."""
    fcf = rec.fcf_yield
    if fcf is None:
        return _needs_data(rec.ticker)

    source = ["fcf_yield"]
    if fcf >= _HIGH_FCF_YIELD:
        action = "add"
        conf = _clamp(30 + round(fcf))
        reasons = [f"Solid FCF yield of {fcf:.1f}% with no analyst coverage — self-funded business"]
    else:
        action = "hold"
        conf = _clamp(20 + round(fcf))
        reasons = [f"FCF yield of {fcf:.1f}% — adequate but not standout without analyst coverage"]

    conf = min(conf, 45)  # never confident without analyst data
    risks = ["No analyst coverage — limited independent validation of this signal"]

    sig = InvestmentSignal(
        ticker=rec.ticker,
        action=action,
        label=_action_label(action),
        confidence=conf,
        reasons=reasons,
        risks=risks,
        data_quality="low",
        source_fields=source,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    _apply_allocation_modifier(sig, allocation_pct, is_watchlist)
    return sig


def _build_etf_signal(
    rec: AnalystRec,
    allocation_pct: Optional[float],
    is_watchlist: bool,
) -> InvestmentSignal:
    """Signal for an ETF using price_signal + etf_quality."""
    price_signal = rec.price_signal or {}
    quality = rec.etf_quality or {}

    zone = (price_signal.get("priceZoneLabel") or "Unavailable").strip()
    percentile = price_signal.get("percentile")

    zone_to_action = {
        "Bargain": "add",
        "Fair": "hold",
        "Elevated": "hold",
        "Rich": "trim",
        "Unavailable": "needs-data",
    }
    action = zone_to_action.get(zone, "needs-data")
    if action == "needs-data":
        return _needs_data(rec.ticker)

    # Speculative gate: never output "add" for speculative ETFs
    category_risk = (quality.get("categoryRiskLabel") or "").strip()
    if category_risk == "Speculative" and action == "add":
        action = "hold"

    source = ["price_signal.priceZoneLabel"]

    # Confidence: blend quality score + percentile decisiveness
    quality_score = quality.get("score") or 50
    decisiveness = 0
    if percentile is not None:
        decisiveness = round(abs(50 - percentile) * 0.6)
    conf = _clamp(round(quality_score * 0.55) + decisiveness)

    # Reasons
    reasons: list[str] = []
    cost_label = quality.get("costLabel", "")
    liquidity_label = quality.get("liquidityLabel", "")
    div_label = quality.get("diversificationLabel", "")
    if cost_label and cost_label != "Unknown":
        reasons.append(f"{cost_label} cost ETF — affects net returns over time")
    if liquidity_label and liquidity_label != "Unknown":
        reasons.append(f"{liquidity_label} liquidity for easy entry/exit")
    if div_label and div_label != "Unknown":
        reasons.append(f"{div_label} diversification profile")
    if zone in ("Bargain", "Rich") and percentile is not None:
        reasons.append(
            f"Price at {percentile:.0f}th percentile of its range — {zone.lower()} zone"
        )

    reasons = reasons[:3]
    source.append("etf_quality.score")

    # Risks
    risks: list[str] = []
    if category_risk and category_risk != "Unknown":
        risks.append(f"{category_risk} category risk — sector-specific volatility applies")
        source.append("etf_quality.categoryRiskLabel")
    data_warnings = price_signal.get("dataWarnings") or []
    if isinstance(data_warnings, list) and data_warnings:
        risks.append(data_warnings[0])
    if not risks:
        risks.append("ETF price signals can lag during market dislocations")

    quality_str = "medium"
    ql = (quality.get("qualityLabel") or "").lower()
    if ql in ("excellent", "strong"):
        quality_str = "high"
    elif ql in ("poor", "insufficient data"):
        quality_str = "low"

    sig = InvestmentSignal(
        ticker=rec.ticker,
        action=action,
        label=_action_label(action),
        confidence=conf,
        reasons=reasons[:3],
        risks=risks[:2],
        data_quality=quality_str,
        source_fields=source,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    _apply_allocation_modifier(sig, allocation_pct, is_watchlist)
    return sig


def build_investment_signal(
    rec: AnalystRec,
    *,
    allocation_pct: Optional[float] = None,
    is_watchlist: bool = False,
) -> InvestmentSignal:
    """
    Build a deterministic InvestmentSignal from an AnalystRec + holding context.
    Never makes network calls; never invents data.
    """
    try:
        if rec.security_type == "ETF" and rec.action == "etf-quality":
            return _build_etf_signal(rec, allocation_pct, is_watchlist)

        if rec.action in ("buy", "hold", "sell"):
            return _build_stock_signal(rec, allocation_pct, is_watchlist)

        # Stock with no analyst coverage — try FCF yield fallback
        if rec.action in ("unavailable",):
            return _build_stock_no_analyst_signal(rec, allocation_pct, is_watchlist)

        return _needs_data(rec.ticker)

    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "Signal build failed for %s; exception_type=%s",
            rec.ticker, type(exc).__name__,
        )
        return _needs_data(rec.ticker)

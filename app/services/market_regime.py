"""
Macro regime detection — risk-on/off, rates, USD trends.
Cached daily; adjusts verdict component weights.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_REGIME_CACHE: dict = {"date": None, "regime": None}

# Proxy tickers: SPY (risk), TLT (rates), ^VIX (vol), UUP (USD)
_REGIME_TICKERS = {
    "risk": "SPY",
    "rates": "TLT",
    "vix": "^VIX",
    "usd": "UUP",
}


def _trend_from_closes(closes: list[float], lookback: int = 20) -> str:
    """Classify short trend: rising | falling | flat."""
    if len(closes) < lookback + 1:
        return "flat"
    recent = closes[-1]
    prior = closes[-lookback]
    if prior <= 0:
        return "flat"
    change_pct = (recent - prior) / prior * 100
    if change_pct >= 2.0:
        return "rising"
    if change_pct <= -2.0:
        return "falling"
    return "flat"


def _fetch_closes(ticker: str, period: str = "3mo") -> list[float]:
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period=period, interval="1d")
        if hist is None or hist.empty:
            return []
        return [float(c) for c in hist["Close"].tolist() if c == c]
    except Exception as exc:
        logger.debug("Regime fetch failed for %s: %s", ticker, type(exc).__name__)
        return []


def _classify_risk(trend: str) -> str:
    if trend == "rising":
        return "risk_on"
    if trend == "falling":
        return "risk_off"
    return "neutral"


def _classify_rates(tlt_trend: str) -> str:
    # TLT rising = rates falling (bond prices up)
    if tlt_trend == "rising":
        return "rates_falling"
    if tlt_trend == "falling":
        return "rates_rising"
    return "rates_flat"


def _classify_usd(uup_trend: str) -> str:
    if uup_trend == "rising":
        return "usd_strong"
    if uup_trend == "falling":
        return "usd_weak"
    return "usd_neutral"


def _vix_band(closes: list[float]) -> str:
    if not closes:
        return "unknown"
    vix = closes[-1]
    if vix >= 25:
        return "elevated"
    if vix <= 15:
        return "low"
    return "normal"


def _component_adjustments(risk: str, rates: str, usd: str, vix_band: str) -> dict[str, int]:
    """Return pct-point shifts for component weights (analyst, valuation, momentum, quality)."""
    adj = {"analyst": 0, "valuation": 0, "momentum": 0, "quality": 0}
    if risk == "risk_off":
        adj["momentum"] -= 4
        adj["quality"] += 4
        adj["valuation"] += 2
    elif risk == "risk_on":
        adj["momentum"] += 3
        adj["quality"] -= 2
    if rates == "rates_rising":
        adj["valuation"] += 3
        adj["momentum"] -= 2
    elif rates == "rates_falling":
        adj["momentum"] += 2
    if usd == "usd_strong":
        adj["quality"] += 2
    elif usd == "usd_weak":
        adj["momentum"] += 2
    if vix_band == "elevated":
        adj["momentum"] -= 3
        adj["quality"] += 3
    return adj


def _regime_label(risk: str, rates: str, usd: str) -> str:
    parts = []
    labels = {
        "risk_on": "Risk-on",
        "risk_off": "Risk-off",
        "neutral": "Mixed risk",
        "rates_rising": "Rates rising",
        "rates_falling": "Rates easing",
        "rates_flat": "Rates steady",
        "usd_strong": "Strong USD",
        "usd_weak": "Weak USD",
        "usd_neutral": "USD neutral",
    }
    parts.append(labels.get(risk, risk))
    if rates != "rates_flat":
        parts.append(labels.get(rates, rates))
    if usd != "usd_neutral":
        parts.append(labels.get(usd, usd))
    return " · ".join(parts[:2])


def get_market_regime(*, force_refresh: bool = False) -> dict:
    """Return cached daily regime + component weight adjustments."""
    today = date.today().isoformat()
    if (
        not force_refresh
        and _REGIME_CACHE.get("date") == today
        and _REGIME_CACHE.get("regime")
    ):
        return dict(_REGIME_CACHE["regime"])

    spy = _fetch_closes(_REGIME_TICKERS["risk"])
    tlt = _fetch_closes(_REGIME_TICKERS["rates"])
    vix = _fetch_closes(_REGIME_TICKERS["vix"])
    uup = _fetch_closes(_REGIME_TICKERS["usd"])

    spy_trend = _trend_from_closes(spy)
    tlt_trend = _trend_from_closes(tlt)
    uup_trend = _trend_from_closes(uup)

    risk = _classify_risk(spy_trend)
    rates = _classify_rates(tlt_trend)
    usd = _classify_usd(uup_trend)
    vix_band = _vix_band(vix)

    adjustments = _component_adjustments(risk, rates, usd, vix_band)
    regime = {
        "risk_regime": risk,
        "rates_regime": rates,
        "usd_regime": usd,
        "vix_band": vix_band,
        "label": _regime_label(risk, rates, usd),
        "component_adjustments": adjustments,
        "tip_title": "Market backdrop",
        "tip_body": (
            "Reads SPY (risk appetite), TLT (rate direction), VIX (fear gauge), "
            "and UUP (dollar strength) over the last ~20 sessions. Shifts how much "
            "each verdict input counts — e.g. risk-off favors quality over momentum."
        ),
        "source_fields": ["SPY", "TLT", "VIX", "UUP"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_quality": "live" if spy else "partial",
    }
    _REGIME_CACHE["date"] = today
    _REGIME_CACHE["regime"] = regime
    return regime


def apply_regime_to_weights(
    base_weights: dict[str, int],
    adjustments: dict[str, int],
) -> dict[str, int]:
    """Rebalance component weights after regime shifts; keep sum at 100."""
    shifted = {
        k: max(4, base_weights.get(k, 0) + adjustments.get(k, 0))
        for k in ("analyst", "valuation", "momentum", "quality")
    }
    total = sum(shifted.values())
    if total <= 0:
        return base_weights
    return {k: max(4, round(v / total * 100)) for k, v in shifted.items()}

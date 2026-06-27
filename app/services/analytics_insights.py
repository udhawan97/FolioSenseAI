"""
Analytics tab insights — compact snapshot + local one-liners per sub-tab.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

MODULE_DIGEST: dict[str, str] = {
    "performance": (
        "Your return story — total P&L, performance history, growth scenarios, "
        "and realized trades from positions you've closed."
    ),
    "risk": (
        "How bumpy and concentrated your book is: reward vs volatility, whether "
        "holdings move together, drawdowns, and diversification."
    ),
    "exposure": (
        "What you truly own after looking inside ETFs — sector and country weights, "
        "plus your allocation table."
    ),
    "signals": (
        "FolioSense verdicts on each holding, who moved today's P&L, and your "
        "overall book tone weighted by position size."
    ),
    "markets": (
        "Live world indices and how closely each one moves with your portfolio — "
        "higher correlation means more ripple when that market swings."
    ),
}


def _concentration_word(hhi: float) -> str:
    if hhi < 0.25:
        return "well spread"
    if hhi < 0.5:
        return "moderately concentrated"
    if hhi < 0.75:
        return "concentrated"
    return "very concentrated"


def build_local_analytics_insights(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Deterministic one-liner per analytics sub-tab + static digests."""
    perf = snapshot.get("performance") or {}
    risk = snapshot.get("risk") or {}
    exposure = snapshot.get("exposure") or {}
    signals = snapshot.get("signals") or {}
    markets = snapshot.get("markets") or {}

    insights: dict[str, str] = {}

    if perf.get("has_holdings"):
        insights["performance"] = (
            f"You're {perf.get('total_return_pct', 0):+.1f}% all-in"
            f"{' with ' + str(perf.get('history_days', 0)) + ' days of history tracked' if perf.get('history_days') else ''}"
            f"; today is {perf.get('today_pnl_pct', 0):+.1f}%."
        )
    else:
        insights["performance"] = (
            "Set share counts to start tracking total return and building your performance chart."
        )

    if risk.get("has_data"):
        top = risk.get("top_sector")
        vol = risk.get("portfolio_vol_pct")
        vol_bit = f" ~{vol:.0f}% annual volatility." if vol else ""
        sector_bit = f" Top sector: {top}." if top else ""
        insights["risk"] = (
            f"Concentration looks {_concentration_word(float(risk.get('concentration_hhi') or 0))}."
            f"{vol_bit}{sector_bit}"
        ).strip()
    else:
        insights["risk"] = "Add holdings to see volatility, correlation, and drawdown readings."

    if exposure.get("has_data"):
        sectors = exposure.get("top_sectors") or []
        countries = exposure.get("top_countries") or []
        s0 = sectors[0]["name"] if sectors else "mixed sectors"
        c0 = countries[0]["name"] if countries else "multiple regions"
        if sectors:
            insights["exposure"] = (
                f"Largest look-through slice is {s0} ({sectors[0]['weight_pct']:.0f}%); "
                f"geography leans {c0}."
            )
        else:
            insights["exposure"] = f"Largest look-through slice is {s0}; geography leans {c0}."
    else:
        insights["exposure"] = "Exposure maps appear once holdings have look-through data."

    if signals.get("has_data"):
        dom = (signals.get("dominant_action") or "hold").upper()
        insights["signals"] = (
            f"Overall tone is {dom} with ~{signals.get('hold_weight_pct', 0):.0f}% of the book on hold"
            f" and average confidence {signals.get('avg_confidence', 0):.0f}%."
        )
    else:
        insights["signals"] = "Signals summarize FolioSense's read once holdings are set up."

    if markets.get("has_data"):
        name = markets.get("best_match_name") or "global equities"
        corr = float(markets.get("best_correlation") or 0)
        insights["markets"] = (
            f"Most in sync with {name} ({corr * 100:.0f}% correlated)"
            + (
                f"; ~{markets.get('us_exposure_pct', 0):.0f}% US look-through exposure."
                if markets.get("us_exposure_pct", 0) >= 30
                else "."
            )
        )
    else:
        insights["markets"] = "Markets context links global indices to your book once holdings exist."

    return {
        "mode": "local",
        "source": "local",
        "insights": insights,
        "digest": dict(MODULE_DIGEST),
    }


def build_analytics_fallback(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Use local lines when Claude is unavailable."""
    payload = build_local_analytics_insights(snapshot)
    payload["source"] = "local-fallback"
    return payload


def fetch_world_markets_sync() -> list[dict]:
    """Sync world-index quotes (same sources as stocks router)."""
    import yfinance as yf
    from app.routers.stocks import _WORLD_MARKETS

    results: list[dict] = []
    for market in _WORLD_MARKETS:
        try:
            fi = yf.Ticker(market["ticker"]).fast_info
            price = float(getattr(fi, "last_price", None) or 0)
            prev = float(getattr(fi, "previous_close", None) or 0)
            if price > 0 and prev > 0:
                chg = price - prev
                chg_pct = chg / prev * 100
            else:
                chg = chg_pct = 0.0
            results.append({
                **market,
                "price": round(price, 2),
                "day_change": round(chg, 2),
                "day_change_pct": round(chg_pct, 2),
            })
        except Exception:
            results.append({**market, "price": 0, "day_change": 0, "day_change_pct": 0})
    return results


def _signals_snapshot(db, non_watchlist: list[dict]) -> dict[str, Any]:
    from app.models import AISummary
    from app.routers.ai import _portfolio_state_signature
    from app.services.verdict_ai_enhancement import decode_verdict_cache

    signals_dict: dict[str, dict] = {}
    for h in non_watchlist:
        ticker = h["ticker"]
        cached = (
            db.query(AISummary)
            .filter(
                AISummary.ticker == ticker,
                AISummary.summary_type.like("verdict%"),
            )
            .order_by(AISummary.generated_at.desc())
            .first()
        )
        if cached:
            try:
                v = decode_verdict_cache(getattr(cached, "summary_text", ""))
                signals_dict[ticker] = {
                    "action": v.get("action", "hold"),
                    "confidence": v.get("confidence", 50),
                }
            except Exception:
                signals_dict[ticker] = {"action": "hold", "confidence": 50}
        else:
            signals_dict[ticker] = {"action": "needs-data", "confidence": 50}

    alloc_map = {h["ticker"]: float(h.get("allocation_pct") or 0) for h in non_watchlist}
    state = _portfolio_state_signature(signals_dict, alloc_map)

    buckets = {"add": 0.0, "hold": 0.0, "trim": 0.0}
    conf_weighted = 0.0
    weight_total = 0.0
    for ticker, sig in signals_dict.items():
        w = alloc_map.get(ticker, 0)
        if w <= 0:
            continue
        action = str(sig.get("action") or "hold").lower()
        if action in ("buy", "add"):
            bucket = "add"
        elif action in ("sell", "trim"):
            bucket = "trim"
        else:
            bucket = "hold"
        buckets[bucket] += w
        conf_weighted += float(sig.get("confidence") or 50) * w
        weight_total += w

    return {
        "has_data": weight_total > 0,
        "dominant_action": state.get("dominant_action", "hold"),
        "hold_weight_pct": round(buckets["hold"], 1),
        "add_weight_pct": round(buckets["add"], 1),
        "trim_weight_pct": round(buckets["trim"], 1),
        "avg_confidence": round(conf_weighted / weight_total) if weight_total else 0,
    }


def build_analytics_snapshot(db) -> dict[str, Any]:
    """Compact cross-tab snapshot for analytics insights."""
    from app.models import PortfolioSnapshot
    from app.routers.portfolio import _compute_portfolio, _cumulative_realized
    from app.services.portfolio_analytics import (
        compute_drawdown,
        compute_market_context,
        compute_risk_metrics,
    )
    from app.services.portfolio_exposure import build_portfolio_exposure
    from app.services.stock_service import get_all_quotes

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    holdings_rows, total_value, total_daily_change, total_cost_basis = _compute_portfolio(1, db)
    non_watchlist = [h for h in holdings_rows if not h.get("is_watchlist")]

    total_unrealized = sum(float(h.get("unrealized_gain") or 0) for h in non_watchlist)
    realized = _cumulative_realized(1, db)
    total_return_dollar = round(total_unrealized + realized, 2)
    total_return_pct = (
        round(total_return_dollar / total_cost_basis * 100, 2) if total_cost_basis > 0 else 0.0
    )
    prev_value = total_value - total_daily_change
    today_pnl_pct = (
        round(total_daily_change / prev_value * 100, 2) if abs(prev_value) > 0 else 0.0
    )

    snapshots = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.portfolio_id == 1)
        .order_by(PortfolioSnapshot.snapshot_date.asc())
        .all()
    )
    drawdown = compute_drawdown([
        {"date": s.snapshot_date, "total_value": s.total_value}
        for s in snapshots
    ])
    risk = compute_risk_metrics(holdings_rows, total_value)
    quotes = get_all_quotes([h["ticker"] for h in non_watchlist])
    exposure = build_portfolio_exposure(
        [
            {
                "ticker": h["ticker"],
                "allocation_pct": h.get("allocation_pct"),
                "is_watchlist": h.get("is_watchlist"),
            }
            for h in non_watchlist
        ],
        quotes={q["ticker"]: q for q in quotes},
    )
    world = fetch_world_markets_sync()
    market_ctx = compute_market_context(holdings_rows, world)
    signals = _signals_snapshot(db, non_watchlist)

    sectors = exposure.get("sector_exposure") or []
    countries = exposure.get("country_exposure") or []
    best = market_ctx.get("best_match") or {}

    return {
        "as_of": today,
        "performance": {
            "has_holdings": bool(non_watchlist) and total_value > 0,
            "total_return_pct": total_return_pct,
            "today_pnl_pct": today_pnl_pct,
            "history_days": len(snapshots),
            "max_drawdown_pct": drawdown.get("max_drawdown_pct"),
        },
        "risk": {
            "has_data": risk.get("has_data"),
            "concentration_hhi": exposure.get("concentration_hhi"),
            "portfolio_vol_pct": (risk.get("portfolio") or {}).get("annual_vol_pct"),
            "max_drawdown_pct": drawdown.get("max_drawdown_pct"),
            "top_sector": sectors[0]["name"] if sectors else None,
        },
        "exposure": {
            "has_data": bool(sectors or countries),
            "top_sectors": sectors[:3],
            "top_countries": countries[:3],
        },
        "signals": signals,
        "markets": {
            "has_data": market_ctx.get("has_data"),
            "best_match_name": best.get("name"),
            "best_correlation": best.get("correlation"),
            "us_exposure_pct": market_ctx.get("us_exposure_pct"),
            "summary": market_ctx.get("summary"),
        },
    }

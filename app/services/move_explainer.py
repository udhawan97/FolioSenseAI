"""
app/services/move_explainer.py
Explains why a holding moved today using market data, volume, and recent news.
Every explanation is grounded in retrieved data — no invented reasons.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)

SECTOR_ETF_MAP: dict[str, str] = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Health Care": "XLV",
    "Financials": "XLF",
    "Financial Services": "XLF",
    "Energy": "XLE",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
    "Telecommunications": "XLC",
}

DRIVER_ICONS: dict[str, str] = {
    "market": "bi-globe2",
    "sector": "bi-diagram-3",
    "earnings": "bi-calendar-event-fill",
    "news": "bi-newspaper",
    "volume": "bi-bar-chart-fill",
    "filing": "bi-file-earmark-text-fill",
    "etf-index": "bi-stack",
    "macro": "bi-graph-up-arrow",
    "unclear": "bi-question-circle",
}


@dataclass
class MoveDriver:
    driver_type: str
    description: str
    magnitude: str  # strong | moderate | weak
    icon: str
    evidence_url: Optional[str] = None


@dataclass
class NewsCatalyst:
    title: str
    source: str
    url: str
    published_at: str


@dataclass
class FilingCatalyst:
    filing_type: str
    title: str
    url: str
    filed_at: str


@dataclass
class MacroContext:
    spy_change_pct: float
    qqq_change_pct: float
    sector_etf: Optional[str]
    sector_etf_change_pct: Optional[float]


@dataclass
class HoldingMoveSummary:
    ticker: str
    day_change_pct: float
    day_change_dollar: float
    attribution_type: str  # market-driven|sector-driven|company-specific|earnings-driven|mixed|unclear|etf-index
    drivers: list = field(default_factory=list)
    confidence: str = "Low"   # Low | Medium | High
    news: list = field(default_factory=list)
    filings: list = field(default_factory=list)
    macro_context: Optional[MacroContext] = None
    explanation_text: str = ""
    is_etf: bool = False
    volume_vs_avg: Optional[float] = None


def _day_change_pct(ticker: str) -> float:
    try:
        info = yf.Ticker(ticker).info
        current = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("navPrice")
            or 0
        )
        prev = info.get("previousClose") or info.get("regularMarketPreviousClose") or 0
        if prev > 0 and current > 0:
            return round((current - prev) / prev * 100, 2)
    except Exception:
        pass
    return 0.0


def get_benchmark_data() -> dict[str, float]:
    """Fetch SPY and QQQ day change pct. Call once per batch to share across holdings."""
    return {
        "SPY": _day_change_pct("SPY"),
        "QQQ": _day_change_pct("QQQ"),
    }


def _sector_etf_change(sector: str) -> tuple[Optional[str], Optional[float]]:
    etf = SECTOR_ETF_MAP.get(sector)
    if not etf:
        return None, None
    return etf, _day_change_pct(etf)


def _extract_news(stock: yf.Ticker) -> list[NewsCatalyst]:
    results: list[NewsCatalyst] = []
    try:
        for item in (stock.news or [])[:5]:
            try:
                content = item.get("content", {}) or {}
                if content:
                    title = content.get("title", "")
                    source = (content.get("provider") or {}).get("displayName", "")
                    url = (content.get("canonicalUrl") or {}).get("url", "")
                    pub = str(content.get("pubDate", ""))
                else:
                    title = item.get("title", "")
                    source = item.get("publisher", "")
                    url = item.get("link", "")
                    pub = str(item.get("providerPublishTime", ""))
                if title:
                    results.append(NewsCatalyst(
                        title=title, source=source, url=url, published_at=pub
                    ))
            except Exception:
                continue
    except Exception:
        pass
    return results


def _earnings_near(stock: yf.Ticker) -> tuple[bool, Optional[str]]:
    try:
        cal = stock.calendar
        if cal is None:
            return False, None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        dates = []

        if hasattr(cal, "loc"):  # pandas DataFrame (older yfinance)
            try:
                val = cal.loc["Earnings Date"]
                dates = list(val) if hasattr(val, "__iter__") else [val]
            except (KeyError, Exception):
                return False, None
        elif isinstance(cal, dict):
            raw = cal.get("Earnings Date", [])
            dates = raw if isinstance(raw, list) else [raw]

        for d in dates:
            try:
                if hasattr(d, "to_pydatetime"):
                    d = d.to_pydatetime().replace(tzinfo=None)
                elif not hasattr(d, "year"):
                    continue
                if abs((d - now).days) <= 3:
                    return True, d.strftime("%b %d")
            except Exception:
                continue
    except Exception:
        pass
    return False, None


def _attribute(
    ticker_chg: float,
    spy_chg: float,
    sector_chg: Optional[float],
    has_news: bool,
    high_vol: bool,
    near_earnings: bool,
) -> tuple[str, str]:
    """Algorithmic attribution. Returns (attribution_type, confidence)."""
    alpha_spy = ticker_chg - spy_chg
    alpha_sector = (ticker_chg - sector_chg) if sector_chg is not None else None

    company_specific = abs(alpha_spy) > 1.5
    market_explains = abs(alpha_spy) <= 0.5
    sector_explains = alpha_sector is not None and abs(alpha_sector) <= 0.5

    if near_earnings:
        return "earnings-driven", "High" if (high_vol or has_news) else "Medium"

    if company_specific:
        if has_news and high_vol:
            return "company-specific", "High"
        if has_news or high_vol:
            return "company-specific", "Medium"
        return "company-specific", "Low"

    if sector_explains:
        return "sector-driven", "Medium" if abs(sector_chg or 0) > 0.3 else "Low"

    if market_explains:
        return "market-driven", "Medium" if abs(spy_chg) > 0.3 else "Low"

    return "mixed", "Low"


def explain_move(
    stock_data: dict, shared_benchmarks: Optional[dict] = None
) -> HoldingMoveSummary:
    """
    Explain why this holding moved today.
    Pass shared_benchmarks={SPY: pct, QQQ: pct} from get_benchmark_data() when
    processing multiple holdings to avoid redundant API calls.
    """
    ticker = str(stock_data.get("ticker", "UNKNOWN")).upper()
    day_chg_pct = float(stock_data.get("day_change_pct") or 0)
    day_chg_dollar = float(stock_data.get("day_change") or 0)
    sector = str(stock_data.get("sector") or "N/A")
    qt = str(stock_data.get("quote_type") or "EQUITY").upper()
    is_etf = qt in ("ETF", "MUTUALFUND")

    bm = shared_benchmarks if shared_benchmarks else get_benchmark_data()
    spy_chg = float(bm.get("SPY", 0))
    qqq_chg = float(bm.get("QQQ", 0))

    sector_etf, sector_chg = (None, None) if is_etf else _sector_etf_change(sector)

    macro = MacroContext(
        spy_change_pct=spy_chg,
        qqq_change_pct=qqq_chg,
        sector_etf=sector_etf,
        sector_etf_change_pct=sector_chg,
    )

    # Volume ratio comes from pre-fetched stock_data — no extra API call needed
    vol = float(stock_data.get("volume") or 0)
    avg_vol = float(stock_data.get("average_volume") or 0)
    vol_ratio = round(vol / avg_vol, 2) if vol > 0 and avg_vol > 0 else None
    high_vol = (vol_ratio or 0) >= 1.5

    news: list[NewsCatalyst] = []
    near_earnings = False
    earnings_date_str: Optional[str] = None

    if not is_etf:
        try:
            yf_stock = yf.Ticker(ticker)
            news = _extract_news(yf_stock)
            near_earnings, earnings_date_str = _earnings_near(yf_stock)
        except Exception as e:
            logger.debug("Extra data fetch failed for %s: %s", ticker, e)

    has_news = len(news) > 0
    drivers: list[MoveDriver] = []

    market_mag = "strong" if abs(spy_chg) > 1.0 else "moderate" if abs(spy_chg) > 0.3 else "weak"
    drivers.append(MoveDriver(
        driver_type="market",
        description=f"Broad market (S&P 500) moved {spy_chg:+.2f}% today",
        magnitude=market_mag,
        icon=DRIVER_ICONS["market"],
    ))

    if is_etf:
        alpha = day_chg_pct - spy_chg
        if abs(alpha) < 0.5:
            attribution_type, confidence = "market-driven", "Medium"
            drivers.append(MoveDriver(
                driver_type="etf-index",
                description="Closely tracking the broad market — this ETF's holdings moved with the overall market",
                magnitude="moderate",
                icon=DRIVER_ICONS["etf-index"],
            ))
        else:
            attribution_type, confidence = "sector-driven", "Medium"
            word = "more" if alpha > 0 else "less"
            drivers.append(MoveDriver(
                driver_type="etf-index",
                description=f"Moved {alpha:+.2f}% {word} than the S&P 500 — driven by its specific sector or index holdings",
                magnitude="moderate",
                icon=DRIVER_ICONS["etf-index"],
            ))

        if abs(qqq_chg) > 0.1:
            qqq_mag = "moderate" if abs(qqq_chg) > 0.5 else "weak"
            direction = "rising" if qqq_chg > 0 else "falling"
            drivers.append(MoveDriver(
                driver_type="macro",
                description=f"NASDAQ also moved {qqq_chg:+.2f}% — tech and growth stocks broadly {direction} today",
                magnitude=qqq_mag,
                icon=DRIVER_ICONS["macro"],
            ))

        if high_vol:
            drivers.append(MoveDriver(
                driver_type="volume",
                description=f"Volume is {vol_ratio:.1f}× the average — elevated activity, possibly from index rebalancing or sector flows",
                magnitude="strong",
                icon=DRIVER_ICONS["volume"],
            ))

        alpha = day_chg_pct - spy_chg
        if abs(alpha) < 0.3:
            explanation = (
                f"{ticker} moved {day_chg_pct:+.2f}% today, closely tracking the broad market "
                f"({spy_chg:+.2f}%). As an ETF, its price reflects the collective movement of its underlying holdings."
            )
        else:
            d = "outperformed" if alpha > 0 else "underperformed"
            explanation = (
                f"{ticker} {d} the broad market by {abs(alpha):.1f}% today (total: {day_chg_pct:+.2f}%). "
                "This is driven by the specific sector or securities this ETF holds, not any single company event."
            )
    else:
        attribution_type, confidence = _attribute(
            day_chg_pct, spy_chg, sector_chg, has_news, high_vol, near_earnings
        )

        if sector_chg is not None:
            sect_mag = "strong" if abs(sector_chg) > 1.0 else "moderate" if abs(sector_chg) > 0.3 else "weak"
            drivers.append(MoveDriver(
                driver_type="sector",
                description=f"Its sector ETF ({sector_etf}) moved {sector_chg:+.2f}% today",
                magnitude=sect_mag,
                icon=DRIVER_ICONS["sector"],
            ))

        if high_vol:
            drivers.append(MoveDriver(
                driver_type="volume",
                description=f"Volume is {vol_ratio:.1f}× the 30-day average — unusually high trading activity today",
                magnitude="strong",
                icon=DRIVER_ICONS["volume"],
            ))

        if near_earnings:
            date_label = f" (around {earnings_date_str})" if earnings_date_str else ""
            drivers.append(MoveDriver(
                driver_type="earnings",
                description=f"Earnings report{date_label} — stock prices often swing before and after earnings announcements",
                magnitude="strong",
                icon=DRIVER_ICONS["earnings"],
            ))

        if has_news:
            drivers.append(MoveDriver(
                driver_type="news",
                description=f"{len(news)} recent news article{'s' if len(news) > 1 else ''} found — see sources below",
                magnitude="moderate",
                icon=DRIVER_ICONS["news"],
            ))

        alpha = day_chg_pct - spy_chg
        if attribution_type == "market-driven":
            explanation = (
                f"{ticker} moved {day_chg_pct:+.2f}% today, closely tracking the broad market "
                f"(S&P 500: {spy_chg:+.2f}%). No clear company-specific catalyst — this looks like normal market movement."
            )
        elif attribution_type == "sector-driven":
            direction = "rising" if (sector_chg or 0) > 0 else "falling"
            explanation = (
                f"{ticker} moved {day_chg_pct:+.2f}% today alongside its sector ({sector_etf}: {sector_chg:+.2f}%). "
                f"The whole sector is {direction} today, not just this stock."
            )
        elif attribution_type == "earnings-driven":
            date_label = f" around {earnings_date_str}" if earnings_date_str else ""
            explanation = (
                f"{ticker} moved {day_chg_pct:+.2f}% with earnings{date_label}. "
                "Stock prices often swing significantly before and after companies report quarterly results."
            )
        elif attribution_type == "company-specific":
            word = "more" if alpha > 0 else "less"
            if has_news:
                explanation = (
                    f"{ticker} moved {day_chg_pct:+.2f}% today — {abs(alpha):.1f}% {word} than the broad market. "
                    "Recent news may explain the move — see the sources below."
                )
            else:
                explanation = (
                    f"{ticker} moved {day_chg_pct:+.2f}% today — {abs(alpha):.1f}% {word} than the S&P 500. "
                    "No obvious news catalyst found. This could be institutional trading or a delayed reaction to earlier news."
                )
        else:
            explanation = (
                f"{ticker} moved {day_chg_pct:+.2f}% today. Multiple factors may be at play — "
                f"market conditions ({spy_chg:+.2f}%)"
                + (f", sector trends ({sector_chg:+.2f}%)" if sector_chg is not None else "")
                + ", and possibly company-specific activity."
            )

        if not has_news and not high_vol and not near_earnings and attribution_type not in (
            "market-driven", "sector-driven"
        ):
            explanation += (
                " No obvious company-specific catalyst found. "
                "The move appears mostly market or sector-driven, or within normal daily volatility."
            )

    return HoldingMoveSummary(
        ticker=ticker,
        day_change_pct=day_chg_pct,
        day_change_dollar=day_chg_dollar,
        attribution_type=attribution_type,
        drivers=drivers[:5],
        confidence=confidence,
        news=news[:3],
        filings=[],
        macro_context=macro,
        explanation_text=explanation,
        is_etf=is_etf,
        volume_vs_avg=vol_ratio,
    )

# FolioSenseAI v3.1 Release Notes

**Release date:** June 27, 2026

---

## ✦ Instant On, Zero Redundant Scrapes

> *v3.1 is the release where the dashboard stopped making Yahoo Finance explain itself three times per load. One shared cache, one warm-up thread, one instant paint from localStorage — the data was already there; we just stopped throwing it away.*

The holdings table now appears immediately from the last saved snapshot while fresh prices reload in the background. Behind the scenes every service that previously made its own `.info` network call now draws from a single shared cache with market-hours-aware TTLs. On startup a background thread pre-warms all caches so the first real fetch hits warm data. The Analytics Signals pane got an O(n) → O(1) rewrite in two hot paths. And a polish pass tightened up the verdict mix bar, signal board tiles, and confidence spectrum.

---

## What's New

### Performance

- **Shared `.info` cache** (`stock_service.get_ticker_info`) — quotes, analyst recs, holding intelligence, earnings calendar, move explainer, and ETF price-zone signal all draw from one cached blob per ticker instead of each triggering their own Yahoo scrape. TTL is 5 min while the market is open, 1 hr while closed.
- **Background startup warmup** — on server start a daemon thread pre-fetches quotes, 1-year history closes, and world market data for all active holdings so the first dashboard load sees warm caches.
- **Stale-while-revalidate portfolio cache** — `localStorage` snapshot of the last good `/api/portfolio/value` response; the holdings table and summary cards paint instantly on page load while fresh prices fetch in the background. The cache key is `foliosense-portfolio-value-v1`.
- **Analytics Signals O(1) lookups** — watchlist filtering and allocation-weight accumulation now use a pre-built `Set` and `Map` respectively instead of `Array.find` inside hot loops.

### UI Polish

- **Verdict mix bar** — taller (12 → 18 px), segment gaps with individually rounded end-caps, inset shadow for depth.
- **Signal board tiles** — wider minimum (88 → 104 px), taller (min-height 72 px), bigger ticker label (0.72 → 0.95 rem), smoother lift-on-hover with `will-change: transform`.
- **Confidence spectrum** — band rows separated by hairlines, dot enlarged with a glow ring via `color-mix`, ticker pills now show a hover state, average confidence value enlarged (0.82 → 1.15 rem), `+N more` badge simplified.

### Code Quality

- Removed misleading `_normalize_expense_ratio` helper in `analyst_recommendation.py`; expense-ratio normalization is now inline with an explanatory comment.
- Simplified `_compute_fcf_yield` — single exit point, no redundant `return None` inside the except block.
- Fixed `data_quality` field in `holding_intelligence.py` — previously stayed `"static"` when only live country weights or top holdings were fetched (no live sectors). Now correctly set to `"live"` whenever any live data is returned.
- Moved buried local imports in `holding_intelligence.py` to module top; neither creates a circular dependency.
- `etf_price_signal.py`: `yfinance` import promoted to module level; added clarifying comment on the intentional `range_position` / `percentile` equality when the 52W-range fallback is active.
- Removed dead `holdingAllocPct()` function in `analytics-charts.js` — superseded by the `allocByTicker` Map.
- `stock_service.py` restructured: module docstring added, constants and helpers now appear before the functions that reference them, `_parallel_fetch()` extracted to deduplicate `get_all_quotes` / `get_portfolio_quotes`, `_r()` closure promoted to module-level `_round_or_none()`.

---

## Developer Notes

- FastAPI metadata version **`3.1.0`**
- Static cache keys: `style.css?v=97`, `dashboard.js?v=90`, `analytics-charts.js?v=13`
- No database schema changes — no migration required.
- No `.env` changes required.
- **`297 tests passing`**

---

## Install & Upgrade

### Fresh install

**Mac / Linux**

```bash
curl -L -o FolioSenseAI-v3.1.zip https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v3.1.zip
unzip FolioSenseAI-v3.1.zip
cd FolioSenseAI-release-v3.1
./scripts/setup.sh
```

**Windows PowerShell**

```powershell
Invoke-WebRequest -Uri "https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v3.1.zip" -OutFile "FolioSenseAI-v3.1.zip"
Expand-Archive -Path "FolioSenseAI-v3.1.zip" -DestinationPath .
cd FolioSenseAI-release-v3.1
.\scripts\setup.ps1
```

### Upgrade from v3.0

1. Stop the app (`Ctrl+C`).
2. Back up `database/` and `.env`.
3. Download v3.1 into a **new folder** — do not overwrite in place.
4. Copy `database/` and `.env` into the new tree.
5. Run setup once, then `start.sh` / `start.ps1` going forward.

No database migration or `.env` change required.

---

## Final Word

v3.1 is still not financial advice. It is just faster at telling you things you probably already suspected.

---

# FolioSenseAI v3.0 Release Notes

**Release date:** June 27, 2026

---

## ✦ The Portfolio Stopped Pretending It Was Diversified

> *FolioSenseAI v3.0 is the release where your book gets treated like a system — overlap, mood, timelines, and three futures with probability bars — instead of a decorative pile of tickers wearing a diversification costume.*

Your portfolio finally has **look-through exposure**, a **market-regime chip**, **peer context**, **earnings risk flags**, **Base/Bull/Bear scenarios**, and an entire **Analytics** tab with five sub-zones and per-chart insight lines. Claude and Local Intelligence now share one engine across briefing, analytics, and verdicts. The navbar got an overflow menu. The pet only wiggles on hover. Very composed. Still judging you.

---

## What's New

### Dashboard &amp; UX

- **Three zones** — Overview, Holdings, and Analytics with persistent tab state
- **Portfolio briefing card** — Claude narrative or deterministic local digest
- **Navbar overflow menu** — theme, text size, pet mode, AI-cost controls in one sheet
- **Semantic color tokens** — green means money up, not "design liked it"
- **Local Intelligence guide** — dismissible banner when Claude is available but Local mode is active
- **Holdings command deck** — action tray, agent status pill (idle / scanning / ready)

### Intelligence &amp; Verdicts

- **Look-through exposure** — sector, country, theme overlap, duplicate detection, HHI concentration
- **Market regime context** — SPY/TLT/VIX/UUP backdrop with cached daily weight shifts
- **Peer-relative positioning** — own-range percentile vs peer median
- **Earnings event awareness** — names inside 14 days get capped confidence and a risk note
- **Time horizons** — `auto` / `trade` / `core` / `anchor` with cycle pill on verdict card
- **Confidence ranges** — `range_low` / `range_high` beside headline score
- **Base / Bull / Bear scenarios** — local paths plus Claude probability splits when AI is connected
- **Claude tension gating** — nudges only when inputs conflict; agreement skips the drama
- **Verdict calibration snapshots** — logged to SQLite for future hit-rate accountability
- **Deep intelligence on expand** — richer context loads async when you open a row

### Analytics *(new zone)*

- **Five sub-tabs** — Performance, Risk, Exposure, Signals, Markets
- Lazy Chart.js visualizations with per-tab insight bar and per-widget tip cards
- Growth projection, correlation matrix, drawdown, beta, rolling vol, sector tilt, conviction gaps, macro alignment, and more

---

## Developer Notes

- FastAPI metadata version **`3.0.0`**
- New services: `portfolio_exposure.py`, `market_regime.py`, `peer_relative.py`, `event_calendar.py`, `verdict_calibration.py`, `verdict_ai_enhancement.py`, `portfolio_analytics.py`, `portfolio_projection.py`, `analytics_insights.py`
- Extended `investment_signal.py` — horizon weights, confidence ranges, scenario builders, modifier hooks
- Extended Claude prompts in `ai_service.py` — disagreement, scenario-probability, briefing, analytics-narrator
- `VerdictSnapshot` model + startup migration for `verdict_snapshots`
- Extended `hold_class` schema — `trade` and `core` alongside `auto` and `anchor`
- New API routes under `/api/portfolio/*`, `/api/ai/portfolio-summary`, `/api/ai/analytics-insights`, `/api/ai/portfolio-exposure`, `/api/ai/verdict-calibration`, `/api/ai/intelligence/{ticker}/deep`, `/api/stocks/world-markets`, `/api/stocks/history/batch`
- Static cache keys: `style.css?v=93`, `dashboard.js?v=88`, `analytics-charts.js?v=9`
- Analytics insights cache version **`widget_insights_version: 2`**
- **`297 tests passing`** — analytics, briefing, projection, intelligence engine UI, calibration, scenarios

---

## Install &amp; Upgrade

### Fresh install

**Mac / Linux**

```bash
curl -L -o FolioSenseAI-v3.zip https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v3.zip
unzip FolioSenseAI-v3.zip
cd FolioSenseAI-release-v3
./scripts/setup.sh
```

**Windows PowerShell**

```powershell
Invoke-WebRequest -Uri "https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v3.zip" -OutFile "FolioSenseAI-v3.zip"
Expand-Archive -Path "FolioSenseAI-v3.zip" -DestinationPath .
cd FolioSenseAI-release-v3
.\scripts\setup.ps1
```

Open [http://localhost:8000](http://localhost:8000). Anthropic API key is optional.

### Upgrade from v2.x

1. Stop the app (`Ctrl+C`).
2. Back up `database/` and `.env`.
3. Download v3 into a **new folder** — do not overwrite in place.
4. Copy `database/` and `.env` into the new tree.
5. Run setup once, then `start.sh` / `start.ps1` going forward.

The `verdict_snapshots` table is created automatically on startup. No `.env` changes required. `force_local=true` still skips Claude; all local intelligence works offline.

---

## Final Word

v3.0 still is not financial advice. It is a more honest briefing layer — overlap, mood, timelines, and futures with probability bars — for portfolios that stopped pretending five tech ETFs count as diversification.

---

# FolioSenseAI v2.4 Release Notes

**Release date:** June 25, 2026

## Headline

FolioSenseAI v2.4 is the mode-control release: Claude when you want the charm, Local Intelligence when you want deterministic quiet, and fresher-feeling market data without extra drama.

## What's New

- **Claude AI / Local Intel toggle** — switch verdict quips without removing your API key
- **`force_local=true`** on `/api/ai/investment-signals/all` — deterministic local quips on demand
- **Persistent mode preference** in browser storage
- **60-second quote cache** — snappier repeated dashboard loads
- **Last-sync resilience** — keeps last good timestamp on failed refresh
- **Sync-state race fix** — HUD commits before render; in-flight guard on portfolio value load
- **Toggle polish** — placement, labels, pet copy

## Upgrade Notes

No database migration or `.env` change required.

```bash
curl -L -o FolioSenseAI-v2.4.zip https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v2.4.zip
unzip FolioSenseAI-v2.4.zip
cd FolioSenseAI-release-v2.4
./scripts/setup.sh
```

---

# FolioSenseAI v2.3 Release Notes

**Release date:** June 2026

## Headline

FolioSenseAI v2.3 is the graceful-offline release: clearer no-key behavior, sharper local labels, and one less thing for CodeQL to side-eye.

## What's New

- Claude offline setup guidance in the brand callout
- **Local Intelligence Verdict** labels when Claude is disconnected
- Dynamic verdict kicker updates on reconnect
- Day-change rendering polish and timing-signal log sanitization

## Final Word

v2.3 still is not financial advice. It just stopped pretending Claude was whispering when he wasn't in the room.

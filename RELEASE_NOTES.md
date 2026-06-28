# FolioSenseAI v4.0 Release Notes

**Release date:** June 27, 2026

---

## ✦ The Portfolio Finally Has Opinions

> *v4.0 is the release where the dashboard stopped watching your book and started reading it. Now it tells you what to do with it — and what the market is saying about it while you decide.*

Your portfolio now has an **Action Plan**. Claude reads the full book — signals, regime, concentration, earnings risk — and comes back with a prioritized Hold / Add / Trim / Exit breakdown, a thesis for each bucket, and the macro mood ring right there on the card. No Claude key? The local fallback runs the same bucket logic deterministically and generates plain-language headlines and per-bucket priority moves, no API call, no wait. Either way, the plan is cached for 24 hours and invalidates itself when your portfolio's dominant action or concentration meaningfully shifts — so rebalancing clears the stale take without you having to ask.

Your portfolio also has a **News tab** now — a fourth zone alongside Overview, Holdings, and Analytics. It pulls live yfinance headlines for every active holding, dedupes, caches, and groups them by ticker. In Claude mode it adds a portfolio-wide briefing and a set of cross-holding theme clusters so you can see which macro story is quietly working three of your positions at once. Holdings with no news still appear; the feed never silently drops a position.

The cockpit got a deeper pass too. The dark canvas is noticeably darker, panels lift off it cleanly, the gain/loss bar is taller, the P&L glow is more dramatic, the sector strip is glassier, and two cascading specificity bugs that were leaving icon pills cramped in the holdings table were finally rooted out and killed.

v4.0 is the release where "what does this mean?" gets a partner: "what should I actually do about it?"

---

## What's New

### Action Plan

- **`/api/ai/action-plan`** — Claude reads the full portfolio signal snapshot and returns a prioritized bucket plan: Hold / Add / Trim / Exit. Each bucket carries a thesis, top moves, and supporting context. Cached 24 h in `AISummary` (ticker=`BOOK`, type=`action_plan`). Falls back deterministically when Claude is unavailable or `force_local=True`.
- **Drift invalidation** — the cache key includes the portfolio's dominant-action distribution and concentration signature. Rebalancing or a meaningful shift in signals automatically invalidates the cached plan so a stale take never lingers after you act.
- **Regime-aware context** — the plan surfaces the current market regime (risk-on / risk-off / neutral) alongside the thesis so bucket decisions have macro backdrop, not just holding-level math.
- **Local fallback with real language** — when Claude is not in the loop, the fallback now builds a plain-language headline from the dominant signal ("3 positions flagged for trim/exit — 4 anchors steady") and generates per-bucket priority moves with specific tickers and actionable copy.
- **Action Plan UI** — four bucketed cards with colour-accented top borders, regime chip, Claude vs Local mode badge, per-bucket thesis, and a refresh button. Skeleton loading state holds layout during the fetch so the card does not pop.

### News

- **`/api/news/feed`** — always available (no Claude key needed). Fetches and caches yfinance headlines for all active holdings and watchlist tickers concurrently. Normalized, deduped, and sorted by recency. Holdings with no news are still included so the feed never silently omits a position.
- **`/api/news/themes`** — Claude mode only, gated on heartbeat. One Haiku call per unique headline signature: a second-person portfolio briefing ("here is what today's news means for your book") plus cross-holding theme clusters grouping the macro narrative that is hitting multiple positions at once.
- **`news_service.py`** — new service covering fetch, in-memory TTL caching (5 min during market hours, 1 h when closed), normalization, dedup, and concurrent multi-ticker fetching.

### UI Polish

- **Darker canvas** — `--bg-base` deepened (`#0a0a0f` → `#050508`), surface opacities pulled back, nav surface opacity raised (`0.62` → `0.88`). Every panel now has more room to lift off the background.
- **Snapshot panel shell** — panels carry their own opaque dark surface, a stronger top-edge inset highlight, and a real drop shadow.
- **Sector strip** — taller (4.5 rem → 6 rem), border-radius bumped, segment sheen dialed back (0.28 → 0.18) for a glassier feel.
- **Gain/loss bar** — taller (0.7 rem → 1 rem); mover tracks taller (0.48 rem → 0.65 rem) with a higher-contrast track background.
- **P&L glow** — text-shadow radius widened (22 px → 32 px) for a more dramatic green/red bleed on positive and negative days.
- **Briefing card** — ambient periwinkle crown stronger (9% → 14%), header padding bumped, separator upgraded from `--hairline` to `--hairline-hover`.
- **Holdings mode box icon fix** — a specificity collision between the GROUP rule (0,2,0) and the per-element rule (0,2,0) left `min-height` losing unpredictably, clipping icons at the top of manage-modal pill buttons. Parent-scoped selectors at (0,3,0) now definitively own `min-height`, `justify-content`, and `overflow` for both modal segments and table-row strips.

### Bug Fixes

- **Mode persistence** — `initDashboardPet()` was hardcoding `_forcedLocalMode = true` on every page load, silently overwriting the preference saved by `enableClaudeAiAndReload()`. The fix reads the `PET_MODE_KEY` value from `localStorage` and only defaults to local (`"1"`) when no preference is stored. Switching to Claude AI now sticks across reloads.
- Two new tests in `tests/test_intelligence_engine_ui.py`: one asserting the init function reads localStorage and `enableClaudeAiAndReload()` writes `"0"`, one asserting the nav Engine toggle and the banner "Enable Claude AI" button both exist with correct `aria-pressed` and JS wiring.

---

## Developer Notes

- FastAPI metadata version **`4.0.0`**
- New router: `app/routers/news.py` — mounted at `/api/news`
- New service: `app/services/news_service.py`
- New AI service function: `generate_news_themes()` in `ai_service.py`
- `_collect_portfolio_signals_core()` extracted and shared between `/investment-signals/all` and `/action-plan` to avoid computing the signal pipeline twice
- Static cache keys: `style.css?v=97`, `dashboard.js?v=90`, `analytics-charts.js?v=13`
- No database schema changes — no migration required.
- No `.env` changes required.
- **356 tests passing**

---

## Install & Upgrade

### Fresh install

**Mac / Linux**

```bash
curl -L -o FolioSenseAI-v4.0.zip https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v4.0.zip
unzip FolioSenseAI-v4.0.zip
cd FolioSenseAI-release-v4.0
./scripts/setup.sh
```

**Windows PowerShell**

```powershell
Invoke-WebRequest -Uri "https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v4.0.zip" -OutFile "FolioSenseAI-v4.0.zip"
Expand-Archive -Path "FolioSenseAI-v4.0.zip" -DestinationPath .
cd FolioSenseAI-release-v4.0
.\scripts\setup.ps1
```

### Upgrade from v3.x

1. Stop the app (`Ctrl+C`).
2. Back up `database/` and `.env`.
3. Download v4.0 into a **new folder** — do not overwrite in place.
4. Copy `database/` and `.env` into the new tree.
5. Run setup once, then use `start.sh` / `start.ps1` going forward.

No schema migration or `.env` change required. All v3.x tables carry over as-is.

---

## Final Word

v4.0 is still not financial advice. It is just the first version that will tell you, with a thesis and a regime chip, what it thinks you should probably do about it.

---

# FolioSenseAI v3.1 Release Notes

**Release date:** June 27, 2026

---

## ✦ Warm on Arrival

> *v3.1 is the release where the dashboard stopped treating every page load like the first time it had ever heard of your portfolio. The data was already there — it just needed somewhere to live between refreshes.*

Your holdings table now paints from the last saved snapshot the moment the page opens, before a single network request has left the building. Behind the scenes, every service that once scraped Yahoo Finance independently — quotes, analyst recommendations, holding intelligence, earnings dates, move explanations, ETF price signals — now shares a single cached response per ticker, with TTLs that stretch to an hour when the market is closed. A background thread warms those caches on startup so the first real fetch is never cold. Two O(n) hot paths in the Analytics Signals pane became O(1). And a quiet design pass made the verdict mix bar, signal board tiles, and confidence spectrum feel more considered.

v3.1 is a tightening, not a reinvention. The same cockpit, now ready before you sit down.

---

## What's New

### Performance

- **Shared `.info` cache** — six previously independent callers (quotes, analyst recs, holding intelligence, earnings calendar, move explainer, ETF price-zone signal) now draw from one cached Yahoo Finance scrape per ticker via `get_ticker_info()`. TTL is 5 minutes during market hours, 1 hour when closed. Redundant round-trips on a typical dashboard load: gone.
- **Stale-while-revalidate portfolio cache** — on every successful `/api/portfolio/value` response the full payload is written to `localStorage`. On the next page open the holdings table and summary cards render instantly from that snapshot; live prices replace them in place as they arrive.
- **Background startup warmup** — a daemon thread fires immediately on server start, pre-fetching quotes, 1-year history closes, and world market data for all active holdings. The first real dashboard request hits a warm cache rather than a cold scrape.
- **Analytics Signals O(1) lookups** — watchlist filtering and allocation-weight accumulation rebuilt with a `Set` and `Map` respectively, replacing `Array.find` calls inside hot iteration loops.

### UI Polish

- **Verdict mix bar** — taller at 18 px (up from 12), segment gaps with individual rounded end-caps, inset shadow for depth.
- **Signal board tiles** — wider minimum footprint (104 px), taller minimum height (72 px), larger ticker label (0.95 rem), smoother `will-change` lift on hover with border and shadow transition.
- **Confidence spectrum** — band rows separated by hairlines, indicator dot enlarged with a `color-mix` glow ring, ticker pills show a hover state, average confidence value enlarged and set in tabular numerals, `+N more` badge simplified.

### Code Quality

- **Bug fix** — `data_quality` in `holding_intelligence.py` was stuck at `"static"` whenever live country weights or top holdings arrived but live sectors did not. It now correctly reflects `"live"` whenever any live data is present.
- Removed `_normalize_expense_ratio` — the function only cast to `float` and did not perform the normalization its name and docstring claimed; logic is now inline with an accurate comment.
- `stock_service.py` restructured end-to-end: module docstring added, constants and helpers appear before the functions that reference them, `_parallel_fetch()` extracted to deduplicate `get_all_quotes` / `get_portfolio_quotes`, closure `_r()` promoted to module-level `_round_or_none()`.
- Dead function `holdingAllocPct()` in `analytics-charts.js` removed — fully superseded by the `allocByTicker` Map.
- Buried local imports in `holding_intelligence.py` moved to module top (no circular dependency); lazy `import yfinance` inside `etf_price_signal.fetch_etf_price_signal` promoted to module level.
- `event_calendar.py` and `move_explainer.py` migrated to `get_ticker_info()` — they now benefit from the shared cache automatically.

---

## Developer Notes

- FastAPI metadata version **`3.1.0`**
- Static cache keys: `style.css?v=97`, `dashboard.js?v=90`, `analytics-charts.js?v=13`
- No database schema changes — no migration required.
- No `.env` changes required.
- **297 tests passing**

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
5. Run setup once, then use `start.sh` / `start.ps1` going forward.

No schema migration or `.env` change required. Your `verdict_snapshots` table carries over as-is.

---

## Final Word

v3.1 is still not financial advice. It is just ready before you finish opening the tab.

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

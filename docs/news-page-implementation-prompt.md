# Implementation Prompt — Portfolio News Zone ("The Wire")

You are implementing a new **News** zone in FolioOrb, a Flask + vanilla-JS portfolio
dashboard. Read this whole spec before writing code, then follow the existing house
patterns exactly (cited by file:line below). Do not introduce new dependencies, new API
keys, or a frontend framework.

## Goal

Add a 4th dashboard zone (alongside Overview / Holdings / Analytics) that shows the
**latest news for the user's holdings + watchlist**. It must work in two engine modes,
reusing the app's existing engine plumbing:

- **Local mode (no AI, no tokens):** real news pulled from `yfinance`, grouped by holding
  (ordered by sector). This is the always-present substrate and must be fully useful on its own.
- **Claude mode (AI):** ON TOP of the same feed, lead with two AI-generated elements —
  a short **portfolio news briefing** and **theme clusters** (cross-holding narratives).
  Per-article AI commentary and AI sentiment are explicitly OUT of scope.

Decisions already locked: data source = **yfinance only**; Claude layer = **portfolio
briefing + theme clustering only**; layout = **themes-first in Claude mode, grouped-by-holding
in local mode**; scope = **active holdings + watchlist**.

## Architecture you must reuse (do not reinvent)

**Engine modes** (`static/js/dashboard.js`):
- `isLocalIntelligenceMode()` / `getIntelligenceEngineMode()` — line ~602.
- `setEngineScopedVisibility()` (line ~619) auto-toggles any element tagged
  `data-engine-claude-only` (hidden in local / when Claude offline) or
  `data-engine-local-only`. **Use these attributes** so the briefing + themes section
  auto-hide in local mode — do not hand-roll visibility.
- `onIntelligenceModeChanged(local, ...)` (line ~7354) is THE central hook fired when the
  user flips the engine. Add your news re-render here (fetch/show themes when switching to
  Claude, drop them in local), mirroring how it calls `loadPortfolioBriefing(...)` and
  `AnalyticsCharts?.onIntelligenceModeChanged?.()`.

**Zone tabs** (`templates/index.html` lines 214-235; `static/js/dashboard.js`):
- `DASHBOARD_ZONES = ["overview","holdings","analytics"]` at line 2605 — add `"news"`.
- `setDashboardZone(zone)` at line 2620 — add an `if (zone === "news") { ... }` branch that
  lazy-loads the feed on first entry (mirror the `if (zone === "analytics")` branch which
  calls `ensureProjectionLoaded()`). Loading must NOT happen on page load.
- Tab buttons are `.dzt-tab` with `data-zone`, `role="tab"`, `onclick="setDashboardZone(...)"`.
  Panes are `<section class="dashboard-zone-pane" data-zone-pane="...">`.

**Claude calls** (`app/services/ai_service.py`): copy `generate_portfolio_briefing()`
(line 374) exactly — `client.messages.create(model=MODEL, max_tokens=..., system=_cached_system(SYSTEM), messages=[{"role":"user","content":_compact_json(snapshot)}])`,
strip ```` ``` ```` fences, `json.loads`, validate keys, `logger.info("... %s+%s tokens", usage.input_tokens, usage.output_tokens)`, and **raise on any failure so the caller can fall back**. `MODEL` is Haiku 4.5. Heartbeat gate: `get_cached_claude_heartbeat()`.

**yfinance + caching** (`app/services/stock_service.py`): match the in-memory TTL cache
style (lines 49-59): `dict[key] = (expiry_monotonic, payload)`, longer TTL while market
closed. Validate tickers with `ticker_shape_is_safe()` (line 71) / `normalize_ticker()`.
For multi-ticker fetches use the `ThreadPoolExecutor` + `as_completed(timeout=...)` pattern
from `app/services/move_explainer.py` (line 174) so 10+ tickers fetch concurrently without
hanging. Per-ticker `try/except` — one bad ticker must not break the feed.

**Holdings + watchlist source**: `Holding` filtered by `portfolio_id` and
`is_active.is_(True)`; `is_watchlist` flag (`app/routers/portfolio.py` line 302-326,
and `_holding_meta()` in `app/routers/ai.py` line 758 for sector/weight context).

## yfinance news shape (verified)

`yf.Ticker(t).news` → list of ~10 dicts. Each item's payload is under `item["content"]`
with keys: `title`, `description`, `summary`, `pubDate` (ISO8601 e.g.
`2026-06-27T12:00:00Z`), `thumbnail` (dict with resolution URLs), `provider`
(`{"displayName": ...}`), `canonicalUrl`/`clickThroughUrl` (dict with `url`), `id`.
Normalize each to a flat dict and DEDUPE across tickers by `id` (or URL):
`{ticker, title, summary, url, source, published_at (parsed datetime → epoch or ISO),
thumbnail_url}`. Guard every field with `.get(...)`; some items lack thumbnails/urls.

## Backend to build

1. **`app/services/news_service.py`** (new):
   - `fetch_ticker_news(ticker) -> list[dict]` — one ticker, normalized + cached
     (TTL ~15 min open / ~60 min closed). Validate ticker shape first.
   - `fetch_portfolio_news(tickers) -> dict` — concurrent fan-out over tickers
     (ThreadPoolExecutor), returns `{ticker: [items...]}`, deduped, each ticker's items
     sorted newest-first.
   - `build_themes_snapshot(holding_meta, news_by_ticker) -> dict` — compact snapshot for
     Claude: per owned holding `{ticker, weight_pct, headlines: [≤3 titles]}` plus watchlist
     titles flagged. Keep it small (compact_json-friendly).

2. **`app/services/ai_service.py`**: add `generate_news_themes(snapshot) -> dict` following
   `generate_portfolio_briefing`. System prompt (concise, JSON-only, no financial advice):
   produce `{"briefing": "1-2 sentence second-person read of what in today's news matters to
   THIS book", "themes": [{"title": ≤6w, "summary": ≤28w, "tickers": [...]}]}` — 2 to 4
   themes max, each tying a shared narrative to the holdings it touches. Validate, raise on
   failure.

3. **`app/routers/news.py`** (new, `APIRouter(prefix="/api/news", tags=["news"])`, register
   it in `app/main.py` next to the other routers):
   - `GET /api/news/feed` (always available, local-safe): returns
     `{"holdings": [{ticker, company_name, sector, is_watchlist, items: [...]}],
       "generated_at": ...}`. Cover active holdings + watchlist. Order holdings by sector
     then ticker. Empty/no-news holdings still listed (so the UI can show an empty state).
   - `GET /api/news/themes` (Claude mode): heartbeat-gate; build snapshot from the feed +
     `_holding_meta`, call `generate_news_themes`, cache by a content signature of the
     headline set (so repeated views cost 0 tokens). Returns `{"briefing", "themes",
     "generated_at"}`. On Claude failure/offline return HTTP 503 (frontend hides the
     section anyway via `data-engine-claude-only`).

## Frontend to build

`templates/index.html` — add tab + pane:
- Tab button after Analytics (line 233): `data-zone="news"`, icon `bi bi-newspaper`,
  label "News", `onclick="setDashboardZone('news')"`, proper `role="tab"`/`aria-selected`.
- `<section class="dashboard-zone-pane" data-zone-pane="news" role="tabpanel" aria-label="News">`
  containing, in order:
  1. **AI section** wrapped with `data-engine-claude-only`: a "Briefing" card + a
     theme-clusters row (each cluster = title, summary, the ticker chips it spans).
     Auto-hidden in local mode / when Claude offline.
  2. **Grouped feed** (always visible): one group per holding — header chip with ticker,
     company name, a watchlist badge when applicable, and P/L-colored accent reusing the
     existing holding color helpers; then a list of article cards. Each card: thumbnail
     (lazy, graceful fallback), headline linking to the article (`target="_blank"
     rel="noopener noreferrer"`), `source · time-ago`, and a clamped description.
  3. Loading skeleton + empty states ("No recent news for your holdings.").

`static/js/dashboard.js`:
- Add `"news"` to `DASHBOARD_ZONES`; add the `news` branch in `setDashboardZone` that calls
  a new `ensureNewsLoaded()` (lazy, runs once; guard with a module flag like the analytics
  pattern).
- `loadNewsZone()`: always `GET /api/news/feed` and render the grouped feed. If
  `!isLocalIntelligenceMode()`, also `GET /api/news/themes` and render the AI section;
  on 503 just leave the (already hidden) AI section empty.
- Add a `timeAgo(date)` helper (none exists today) for "3h ago"-style stamps.
- In `onIntelligenceModeChanged` (line ~7354): if the news zone has loaded, re-fetch/show
  themes when entering Claude and clear them when entering local. Rely on
  `setEngineScopedVisibility()` for the show/hide.
- Reuse existing scan/loading copy style; sanitize all news text before inserting (use
  `textContent` / your existing escaping helper, never raw `innerHTML` with provider text).

`static/css/style.css`: add styles using existing CSS variables and card aesthetics
(match `.dashboard-zone-pane`, summary cards, chips). New classes for news groups, article
cards, thumbnails, and theme clusters. Keep it visually consistent with the dark theme.

## Constraints & acceptance criteria

- No new pip/npm dependencies, no new env vars, no new API keys.
- Local mode renders a real, useful, grouped news feed with **zero** Claude calls.
- Claude mode adds briefing + 2-4 theme clusters above the feed; themes are cached so
  re-opening the zone spends no tokens; token usage is `logger.info`-logged like peers.
- Switching engine via the existing toggle updates the News zone correctly with no reload.
- News loads only on first entry to the zone, never on initial page load.
- Empty portfolio, watchlist-only holdings, tickers with no news, and yfinance/Claude
  failures all degrade gracefully (no crashes, sensible empty/hidden states).
- Accessibility: tab has proper `role`/`aria-selected`; links open safely; images have alt.
- Follow existing naming, comment density, and formatting. Run the app via `run.py` and
  verify the four zones switch cleanly; add tests under `tests/` mirroring existing test
  style for `news_service` normalization/dedup and the `/api/news/feed` route.

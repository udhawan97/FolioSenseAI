# Earnings Radar — Implementation Plan

**Status:** approved, ready to implement
**Effort:** Small (~half a day)
**Confidence:** High — the hard part (earnings-date fetching/parsing) already exists in
`app/services/event_calendar.py`; this feature surfaces it.

## Goal

Give users a heads-up when a holding (or watchlist ticker) is about to report earnings,
so an earnings-day move never catches them flat-footed.

Two user-visible pieces:

1. **Row badge** — a small calendar badge next to the ticker in the holdings table when
   earnings are ≤ 14 days away (e.g. `📅 3d`, tooltip "Earnings ~Feb 12 — in 3 days").
2. **Radar strip** — a compact chip row above the holdings table listing everything
   reporting in the next 30 days, soonest first (e.g. `MSFT · in 3d`, `NVDA · in 9d`).
   Hidden entirely when there's nothing upcoming.

## Non-goals (do not build)

- OS/push notifications — in-dashboard only.
- Past earnings ("reported 2 days ago") — possible stretch later, not now.
- Overview-zone placement — Holdings pane only for v1.
- Dividends/splits/other events — earnings only.
- No new DB tables. No schema changes. In-memory cache only.

## What already exists (reuse, don't rebuild)

| Piece | Where | Notes |
| --- | --- | --- |
| Earnings-date fetch + parse | `app/services/event_calendar.py` → `fetch_next_earnings(ticker)` | Returns `Optional[date]`. Handles list/timestamp/str shapes. Its `mostRecentQuarter` fallback can return a *past* date — the window filter below excludes those naturally. |
| Ticker info w/ TTL cache | `app/services/stock_service.py` → `get_ticker_info` (`_INFO_CACHE`, 5 min open / 1 h closed) | `fetch_next_earnings` calls this internally, so info is fetched once per ticker per TTL. |
| Security classification | `app/services/security_type.py` → `classify_security(ticker, metadata)` | ETFs/funds don't report earnings — skip them like `build_event_context` does. |
| Fan-out pattern | `app/services/news_service.py` | `ThreadPoolExecutor`, `_MAX_WORKERS = 8`, module-level `dict` TTL cache, market-open-aware TTLs. Mirror this style. |
| Log hygiene | `app/services/log_safety.py` → `sanitize_for_log` | Use for any ticker in log lines (repo convention). |
| Row badge pattern | `static/js/dashboard.js` → `holdingBadgeHtml(h)` (~line 3793) | Watchlist "Research" badge; earnings badge sits beside it in the ticker cell built in `updateHoldingRow`. |
| Banner-above-table pattern | `renderHoldings()` → `research-filter-banner` (~line 2902) | Shows how a strip is inserted above the holdings table wrap. |
| Idle boot hook | `dashboard.js` `scheduleWhenIdle(...)` after `await criticalData` (~line 9849) | Radar load goes here — never block critical data. |

Note: verdict signals (`/api/ai/investment-signal*`) already embed an `events` context,
but it only covers scanned stocks within 14 days and loads late/heavy. The radar needs a
cheap, early, 30-day, watchlist-inclusive view → dedicated endpoint. Do **not** couple it
to the signals pipeline.

## Backend

### 1. New service — `app/services/earnings_radar.py`

```python
def get_earnings_events(tickers: list[str], window_days: int = 30) -> list[dict]
```

Behavior:

- Fan out over tickers with `ThreadPoolExecutor(max_workers=8)`; overall wait ≤ 15 s,
  return partial results on timeout (log a debug line, never raise).
- Per ticker: `info = get_ticker_info(t)`; skip unless
  `classify_security(t, info) == "STOCK"` (match how the verdict path treats ETFs);
  then `fetch_next_earnings(t)` (pass the already-fetched date via
  `_parse_earnings_date(info)` directly to avoid a second info lookup — either is fine,
  info is cached).
- Module-level per-ticker cache `_RADAR_CACHE: dict[str, tuple[float, str | None]]`
  storing the **ISO date string (or None)**, TTL 6 h (`21600`). Cache the date, not
  `days_until` — recompute days at read time so an entry cached yesterday stays correct.
- Filter: keep `0 <= days_until <= window_days` (past dates from the
  `mostRecentQuarter` fallback fall out here).
- Sort by `(days_until, ticker)`.
- Each event dict:

```python
{
    "ticker": "MSFT",
    "date": "2026-02-12",        # ISO
    "days_until": 3,
    "label": "In 3 days",        # "Today" / "Tomorrow" / "In N days"
}
```

- Failures (no info, parse fail, network) → ticker silently excluded;
  `logger.debug` with `sanitize_for_log(ticker)`.

### 2. New endpoint — `GET /api/portfolio/earnings` in `app/routers/portfolio.py`

- Params: `portfolio_id: int = 1`, `window: int = Query(30, ge=1, le=60)`.
- `_get_portfolio_or_404`, query active holdings (**including** watchlist rows — a
  watched ticker's earnings matter too), call the service, then stamp
  `is_watchlist: bool` onto each event from the holdings map.
- Response:

```json
{
  "portfolio_id": 1,
  "window_days": 30,
  "events": [
    {"ticker": "MSFT", "date": "2026-02-12", "days_until": 3, "label": "In 3 days", "is_watchlist": false}
  ],
  "count": 1
}
```

- Keep the router thin — all logic in the service (repo convention; routers are
  wiring, tests target services).

## Frontend (`static/js/dashboard.js`, `templates/index.html`, `static/css/style.css`)

### 3. Data load

- `let cachedEarnings = {};` (ticker → event) near `cachedRecommendations` (~line 769).
- `async function loadEarningsRadar()` — fetch `/api/portfolio/earnings`, rebuild
  `cachedEarnings`, then `renderEarningsStrip()` and `renderHoldings()` (to refresh
  badges). Wrap in try/catch → on failure leave `cachedEarnings = {}` and hide the
  strip. No user-facing error; this is garnish, not dinner.
- Call it inside the existing `scheduleWhenIdle(() => { ... })` block after
  `await criticalData` (~line 9849). Also call after a holding is added/removed
  (same places the holdings list reloads). **No polling** — earnings dates change
  quarterly; once per app load + on portfolio change is plenty.

### 4. Row badge

- `earningsBadgeHtml(h)` next to `holdingBadgeHtml` (~line 3793):
  - Look up `cachedEarnings[h.ticker]`; render only when `days_until <= 14`
    (strip covers the 15–30 day tail — the badge is for "soon", the strip for "ahead").
  - Markup: `<span class="badge earnings-badge ms-1" title="Earnings ~Feb 12 — in 3 days"><i class="bi bi-calendar-event me-1"></i>3d</span>`
    with `Today`/`1d`/`Nd` text. Escape via `escapeHtml` like neighbors.
- Append in `updateHoldingRow`'s `tickerHtml` right after `${holdingBadgeHtml(h)}`.

### 5. Radar strip

- Static container in `templates/index.html`, Holdings pane
  (`data-zone-pane="holdings"`, ~line 1783), directly above the table wrap:
  `<div id="earnings-radar-strip" class="earnings-radar-strip" hidden></div>`.
- `renderEarningsStrip()` fills it: a label (`<i class="bi bi-broadcast"></i> Earnings radar`)
  plus one chip per event (max ~8, `+N more` overflow), `MSFT · in 3d`, watchlist
  chips get the flask icon. Empty events → set `hidden`, done.
- CSS in `static/css/style.css`: mirror `.research-filter-banner` / chip styles already
  there; muted panel background, amber accent for ≤ 3 days. **No animation** — static
  chips, zero layout thrash (snappiness rule). Nothing needed for
  `prefers-reduced-motion` if nothing moves.

## Edge cases (handle explicitly)

1. **No earnings date** (common for foreign/small tickers) → excluded server-side;
   UI shows nothing for that ticker. Never render "unknown".
2. **ETFs/funds** (`VOO`, `SCHD`) → classified out server-side; never show a badge.
3. **yfinance returns a range** (`earningsDate` as 2-item list) → parser already takes
   the first; label copy says "~" (approximate) in tooltips for honesty.
4. **Cold cache on big portfolio** → endpoint may take seconds; it loads idle so the
   dashboard never waits on it. Warm calls are near-instant (`_RADAR_CACHE`).
5. **Offline / API down** → fetch fails, strip stays hidden, badges absent, zero errors
   in console beyond the caught fetch.
6. **`days_until == 0`** → "Today" (badge text `Today`, not `0d`).

## Tests (offline, mocked — repo convention: no TestClient, test services + wiring)

New `tests/test_earnings_radar.py`:

1. Window filter: dates at −1, 0, 14, 30, 31 days → only 0/14/30 kept; labels
   `Today` / `In 14 days` / `In 30 days`.
2. ETF skipped: monkeypatch `classify_security` → `"ETF"` for `VOO`; not in results.
3. Unknown date (`fetch_next_earnings` → `None`) → excluded, no raise.
4. Sorting: mixed days → ascending `(days_until, ticker)`.
5. Cache: two calls with a monkeypatched clock inside TTL hit the cache (fetch called
   once per ticker); expired TTL refetches. Recomputed `days_until` reflects "today".
6. Fetch raises for one ticker → others still returned.

Wiring test (style of `tests/test_analytics_dashboard.py`) — assert strings exist:
`"/api/portfolio/earnings"` in `dashboard.js`; `earnings-radar-strip` in
`templates/index.html`; `.earnings-badge` and `.earnings-radar-strip` in
`static/css/style.css`; `loadEarningsRadar` and `earningsBadgeHtml` in `dashboard.js`.

## Implementation order

1. `app/services/earnings_radar.py` + unit tests → green.
2. Router endpoint (thin) → curl it with the demo portfolio.
3. JS: load + badge + strip; HTML container; CSS.
4. Wiring test; full quality gate:
   `python -m compileall -q app run.py tests && python -m pytest -q && python -m pylint $(git ls-files '*.py')`
5. Manual check: `python run.py`, seed demo (`POST /api/portfolio/seed`), verify
   `/api/portfolio/earnings` JSON, badge + strip render, and an offline-ish failure
   path (block the endpoint → strip hidden, no console spam).

## Ship

Per standing workflow: verify green, commit to `main`, push (rebase-first). Suggested
message: `feat: earnings radar — upcoming-earnings badges and strip on holdings`.
After shipping, update the roadmap teasers (README table, docs roadmap page, website
card): move "Earnings radar" from "Quietly brewing" to shipped/remove it, and delete
its row from the `folio-future-upgrades` memory per that file's instructions.

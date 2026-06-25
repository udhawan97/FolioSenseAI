# FolioSenseAI v2.4 Release Notes

Release date: June 25, 2026

## Headline

FolioSenseAI v2.4 is the mode-control release: a polished Claude AI / Local Intel toggle, deterministic verdict quips on demand, faster repeated quote reads, and a last-sync HUD that stays graceful when refreshes fail. Claude gets the charm. Local Intelligence gets the quiet competence. You get to choose. Flirty? Only in the most professionally documented way.

## What's New

- **Claude AI / Local Intel toggle**: switch verdict quips into deterministic local mode for the session without removing your Anthropic API key.
- **Forced-local verdict path**: `/api/ai/investment-signals/all?force_local=true` skips Claude quip generation and uses fallback/local quips for holdings and portfolio health.
- **Persistent mode preference**: the dashboard remembers your local-mode choice in browser storage and updates verdict labels/kickers in place.
- **Smarter offline state**: the mode toggle disables cleanly when Claude is offline and opens the setup guidance instead of pretending a network problem is a personality trait.
- **Quote caching**: live quote reads are cached for 60 seconds in `stock_service`, cutting repeated Yahoo Finance calls during tight dashboard refresh loops.
- **Last-sync resilience**: the HUD keeps the last good sync timestamp when a refresh fails, marks the state clearly, and avoids replacing usable data with panic confetti.
- **Sync state before render**: HUD timestamp and loaded-state are committed as soon as data arrives from the API, so a Chart.js or rendering error cannot flip the sync indicator back to "failed."
- **In-flight guard**: a `_portfolioValueInFlight` flag prevents overlapping `loadPortfolioValue` calls from racing to create duplicate chart canvases and triggering false refresh failures.
- **% column polish**: the percentage column in the target-trend list is wider and `white-space: nowrap`; `formatSignalPct` drops the decimal when the value hits triple digits so the string stays compact for any holding.
- **Toggle polish**: placement, labels, title text, and dashboard pet copy now make the Claude/local relationship clearer and a little more charming.

## Developer Notes

- Bumped FastAPI metadata version to `2.4.0`.
- Updated the dashboard intro badge to `v2.4`.
- Added `force_local: bool = False` to `get_all_investment_signals()`.
- Updated dashboard signal fetches to append `?force_local=true` when Local Intel mode is active.
- Added `_QUOTE_CACHE` and `_QUOTE_TTL = 60` to `app/services/stock_service.py`.
- Added HUD sync failure handling so stale-but-valid data remains visible after a failed refresh.
- Moved HUD DOM update (timestamp, `_hasLoadedOnce`) to run immediately after API response, before any rendering — rendering errors can no longer affect sync display.
- Added `_portfolioValueInFlight` guard to `loadPortfolioValue` to prevent concurrent calls from racing on the chart canvas.
- Wrapped all rendering code in an inner `try/catch`; a render error now warns to the console instead of surfacing "Refresh failed" to the user.
- Widened `.target-trend-list` percentage column (`2.7rem → 3rem`), added `white-space: nowrap` to `.target-trend-line strong`, and updated `formatSignalPct` to drop the decimal at ≥100.
- Added `.pet-mode-toggle` CSS and related state styling.
- Bumped the dashboard script cache key to load the new frontend behavior.

## Upgrade Notes

No database migration or `.env` change is required. Existing installs continue to run as before.

The new Local Intel mode is client-side selectable. With Claude configured, users can switch between Claude-backed quips and deterministic local quips. Without Claude configured, the app continues in offline/local mode and shows setup guidance.

If you use GitHub release archives, install v2.4 with:

```bash
curl -L -o FolioSenseAI-v2.4.zip https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v2.4.zip
unzip FolioSenseAI-v2.4.zip
cd FolioSenseAI-release-v2.4
./scripts/setup.sh
```

Windows PowerShell:

```powershell
Invoke-WebRequest -Uri "https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v2.4.zip" -OutFile "FolioSenseAI-v2.4.zip"
Expand-Archive -Path "FolioSenseAI-v2.4.zip" -DestinationPath .
cd FolioSenseAI-release-v2.4
.\scripts\setup.ps1
```

## Final Word

v2.4 still is not financial advice. It is a more controllable, more resilient dashboard that lets Claude bring the sparkle when invited and lets Local Intelligence keep working when you prefer the numbers without the perfume.

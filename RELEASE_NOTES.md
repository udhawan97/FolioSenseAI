# FolioSenseAI v2.2 Release Notes

Release date: June 25, 2026

## Headline

FolioSenseAI v2.2 is the polish-and-trust release: safer ticker entry, cleaner portfolio math, honest AI billing visibility, and a live Claude status heartbeat in the dashboard. Same local-first portfolio intelligence. Sharper suit. Better manners. Still flirts with your unrealized losses.

## What's New

- **Claude heartbeat in the HUD**: the dashboard now reports whether the Claude API is reachable, missing a key, or temporarily unavailable.
- **AI cost clarity**: `/api/ai/cache/stats` now separates Claude-backed cached summaries from local fallback/deterministic rows, and clearly marks billing as paused when no Anthropic API key is configured.
- **Force-refresh control**: the live feed popover now includes a refresh-all action for prices, signals, and dashboard state.
- **Ticker validation before save**: new holdings are checked for safe ticker shape and live quote resolution before entering the portfolio.
- **Ticker suggestions**: invalid or misspelled ticker attempts can return Yahoo Finance suggestions so users can recover without doing the sad browser-tab shuffle.
- **Research-mode holdings**: watchlist/research entries can be added without share counts, keeping ideas separate from funded positions.
- **Cleaner realized P&L history**: realized sale rows now include IDs and can be deleted through `DELETE /api/portfolio/trades/{trade_id}`, with today's snapshot recalculated afterward.
- **Better total return math**: open positions, partial sales, realized gains, and zero-basis edge cases now behave more consistently.
- **Dashboard polish**: tighter holding intelligence cards, improved table sizing, mobile-friendly holding inputs, better Claude copy, and a cleaner live-feed presentation.

## Developer Notes

- Bumped FastAPI metadata version to `2.2.0`.
- Added `claude_api_heartbeat()` in `app/services/ai_service.py`.
- Added `GET /api/ai/heartbeat`.
- Added richer `claude_live`, cache, billing, and fallback accounting for AI endpoints.
- Added ticker normalization, safe-shape checks, quote resolution, and Yahoo Finance search suggestions in `app/services/stock_service.py`.
- Added support for zero-share research holdings while preserving positive-share validation for real positions.
- Added realized-trade deletion and P&L snapshot refresh behavior.
- Expanded tests for AI cache accounting, Claude heartbeat, ticker validation, research holdings, realized-trade deletion, and portfolio return percentage calculations.

## Upgrade Notes

No manual migration is required for a normal local install. Existing portfolios continue to work, startup migrations remain idempotent, and `.env` settings are unchanged.

If you use GitHub release archives, install v2.2 with:

```bash
curl -L -o FolioSenseAI-v2.2.zip https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v2.2.zip
unzip FolioSenseAI-v2.2.zip
cd FolioSenseAI-release-v2.2
./scripts/setup.sh
```

Windows PowerShell:

```powershell
Invoke-WebRequest -Uri "https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v2.2.zip" -OutFile "FolioSenseAI-v2.2.zip"
Expand-Archive -Path "FolioSenseAI-v2.2.zip" -DestinationPath .
cd FolioSenseAI-release-v2.2
.\scripts\setup.ps1
```

## Final Word

v2.2 is not a trading strategy, a crystal ball, or a licensed financial advisor. It is a cleaner, sharper portfolio dashboard that explains the chaos with live data, Claude-assisted context, and just enough charm to make red numbers feel personally attacked.

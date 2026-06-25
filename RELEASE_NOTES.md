# FolioSenseAI v2.3 Release Notes

Release date: June 25, 2026

## Headline

FolioSenseAI v2.3 is the graceful-offline release: clearer behavior when Claude is not connected, more honest Local Intelligence labels, cleaner day-change UI polish, and a security hardening pass for timing-signal logs. It is less dramatic, more reliable, and still very good at making your portfolio feel seen.

## What's New

- **Claude offline guidance**: the brand callout now gives direct setup steps when no Anthropic API key is configured, including where to get a key, what to add to `.env`, and how to restart the app.
- **Local Intelligence labeling**: verdict headers and kickers now switch to local-language when Claude is offline, then restore Folio Sense × Claude labeling when the API is live again.
- **Cleaner offline UX**: the dashboard explains that AI features are paused while local market data, deterministic signals, and cached/fallback notes continue to work.
- **Day-change polish**: the daily percentage move now uses a reusable styled cell for cleaner caret alignment and less inline styling.
- **Security hardening**: timing-signal logging now strips line breaks from ticker values before logging, closing a log-injection scan finding.

## Developer Notes

- Bumped FastAPI metadata version to `2.3.0`.
- Updated the dashboard intro badge to `v2.3`.
- Added `_safe_log_value()` in `app/services/timing_signal.py` and applied it to untrusted ticker logging.
- Added `.day-chg-cell` CSS and moved day-change icon styling out of inline HTML.
- Wrapped verdict kicker text in `.verdict-kicker-label` so online/offline Claude state can update rendered verdicts in place.
- Expanded offline callout markup and styles for API-key setup guidance.

## Upgrade Notes

No database migration or `.env` change is required. Existing installs continue to run as before.

If you want Claude-backed explanations, make sure `.env` contains:

```env
ANTHROPIC_API_KEY=sk-ant-your-real-key-goes-here
```

Then restart the app:

```bash
./scripts/start.sh
```

Windows:

```powershell
.\scripts\start.ps1
```

If you use GitHub release archives, install v2.3 with:

```bash
curl -L -o FolioSenseAI-v2.3.zip https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v2.3.zip
unzip FolioSenseAI-v2.3.zip
cd FolioSenseAI-release-v2.3
./scripts/setup.sh
```

Windows PowerShell:

```powershell
Invoke-WebRequest -Uri "https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v2.3.zip" -OutFile "FolioSenseAI-v2.3.zip"
Expand-Archive -Path "FolioSenseAI-v2.3.zip" -DestinationPath .
cd FolioSenseAI-release-v2.3
.\scripts\setup.ps1
```

## Final Word

v2.3 does not make investment decisions for you. It simply keeps the dashboard honest about whether Claude is in the room, keeps local intelligence useful when Claude is not, and closes a security wrinkle with the quiet confidence of someone who read the log file before flirting with production.

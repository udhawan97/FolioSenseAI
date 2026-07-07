# FolioSenseAI — Desktop Product & Download Experience Plan

**Status:** Planning document. Nothing here is implemented yet.
**Author:** Fable (planning pass), for Opus (execution pass).
**Date:** 2026-07-07
**Repo:** `udhawan97/FolioSenseAI` · current version `4.2.0` · latest tag `release-v4.2`

---

## 1. Repo audit summary

### What the app actually is

FolioSenseAI is **not Electron and not Tauri**. It is a **Python 3.11+ FastAPI + Uvicorn web app** that runs locally and opens the dashboard in the user's default browser at `http://localhost:8000`.

| Fact | Evidence |
| --- | --- |
| Entry point | `run.py` — starts uvicorn with `reload=True`, host `0.0.0.0`, port 8000, opens browser after 2 s |
| App version | Hardcoded `version="4.2.0"` in `app/main.py:64` (only source of truth) |
| Frontend | Server-rendered single HTML shell (`templates/index.html`) + `static/` (vanilla JS, Chart.js, Bootstrap) — no build step |
| Data | SQLite at `sqlite:///./database/portfolio.db` (cwd-relative), `.env` loaded via `load_dotenv()` (cwd-relative) — `app/config.py` |
| Relative-path hazards | `app/main.py:80` mounts `StaticFiles(directory="static")`; `app/main.py:82` opens `templates/index.html` — both cwd-relative; breaks the moment the app is frozen/installed |
| Key deps | fastapi 0.138.2, uvicorn 0.48.0, SQLAlchemy 2.0.51, anthropic 0.105.2, **yfinance 1.5.1 + curl_cffi 0.15.0** (packaging-sensitive), `platformdirs` already pinned (4.10.0) |
| Tests | ~363 test functions across 31 files, offline-focused, run in CI on Python 3.11 + 3.12 |
| CI today | `ci.yml` (tests + pip-audit), `pylint.yml`, `codeql.yml`, `dependency-review.yml`, `security-hygiene.yml`, `docs.yml` |
| GitHub Pages | **Already deployed via GitHub Actions** (`docs.yml` → `actions/deploy-pages@v4`). Astro 7 + Starlight 0.41 site in `docs-site/`, published at `https://udhawan97.github.io/FolioSenseAI/` |
| Docs homepage | Starlight `template: splash` page at `docs-site/src/content/docs/index.mdx` — nice but doc-flavored, not a product landing page; no download CTAs |
| Releases | One GitHub release: `FolioSenseAI v4.2` on tag `release-v4.2` — **source-only, no binary assets** |
| Install scripts | `scripts/install-mac.sh`, `scripts/install-win.ps1` — curl/irm one-liners that download the source zip **hardcoded to tag `release-v4.2`**, create a venv, pip install, write a desktop shortcut. They require Python 3.11+ on the user's machine |
| Launchers | `FolioSenseAI.command` (macOS), `FolioSenseAI.bat` (Windows) — double-click venv bootstrap + `python run.py` |
| Brand assets | `static/img/brand/`: `folio-orbit-icon-1024.png` (icon source ✔), `folio-orbit-icon.svg`, animated + static light/dark wordmarks. Docs site reuses them |
| Stale content found | README badge says FastAPI `0.136.3` (actual 0.138.2); arch table says SQLAlchemy `2.0.50` (actual 2.0.51) and yfinance `1.4.1` (actual 1.5.1); static `release-v4.2` badge; docs-site index claims "361 tests" (already drifted); install scripts pinned to `release-v4.2` forever |

### What this means for the plan

- **electron-builder and tauri-action are the wrong tools here.** The correct path for a Python server app is **PyInstaller** (freeze Python + deps into a self-contained app) plus native installer tooling: **`create-dmg` on macOS, Inno Setup on Windows**.
- The **hard product gap** is that today's "install" requires the user to have Python. A real DMG/EXE removes that requirement entirely — that's the headline win.
- Pages infrastructure, branding, docs, and CI hygiene are already good. This plan **adds** a landing page, a release pipeline, and packaging — it does not rebuild what exists.

---

## 2. Recommended packaging approach

### Decision: PyInstaller (onedir) + pywebview desktop shell

| Option | Verdict |
| --- | --- |
| **A. PyInstaller + pywebview window (recommended)** | Freeze the FastAPI app; a new `desktop/main.py` starts uvicorn in-process on `127.0.0.1:<free port>` and opens a native window (WKWebView on macOS, WebView2 on Windows) pointed at it. Closing the window shuts the server down. Feels like a real desktop app; solves the "how do I quit this thing" problem that a headless browser-launcher has. One small extra dependency. |
| B. PyInstaller + default browser + tray/status window | Fallback if pywebview verification fails (see Risks). Same pipeline, same installers; only `desktop/main.py` differs. Keep this in back pocket — do not build both. |
| C. Tauri wrapper + Python sidecar | Rejected: adds a Rust toolchain and a second app layer for zero user benefit. |
| D. Electron wrapper bundling Python | Rejected: two runtimes, 150 MB+ artifacts, heavy maintenance. |
| E. Briefcase (BeeWare) | Rejected: template-driven repo restructuring; PyInstaller is more surgical for an existing app. |

**Onedir, not onefile.** `--onedir` starts faster, avoids self-extraction to temp, and triggers fewer antivirus false positives. The DMG/installer wraps the folder, so users never see it.

### Required app changes (small, surgical)

1. **`app/version.py`** — single source of truth: `__version__ = "4.3.0"`. Consumed by `app/main.py`, the PyInstaller spec, the Inno script (via `/D` define), and CI.
2. **`app/paths.py`** — two helpers:
   - `resource_dir()`: returns `sys._MEIPASS`-based path when `getattr(sys, "frozen", False)`, else the repo root. Used for `static/` and `templates/`.
   - `data_dir()`: when frozen, `platformdirs.user_data_dir("FolioSenseAI", "FolioSenseAI")` (create on first run); else repo root. Holds `portfolio.db` and `.env`. **Installed apps must never write inside the install location** (`/Applications/...app` or `Program Files`).
3. **`app/config.py`** — `load_dotenv(data_dir() / ".env")`; default `DATABASE_URL` points into `data_dir()/database/` when frozen; `DEBUG` defaults to `False` in frozen builds.
4. **`app/main.py`** — replace the two cwd-relative paths (`:80`, `:82`) with `resource_dir()`-based absolute paths; import version from `app/version.py`.
5. **`desktop/main.py`** — desktop entry point:
   - Pick port: try 8000, else `socket` a free one. Set `CORS_ALLOWED_ORIGINS` env for the chosen origin **before** importing `app.main`.
   - Run uvicorn in a thread with `reload=False` (PyInstaller cannot survive uvicorn's reload subprocess model), host `127.0.0.1` only (never `0.0.0.0` in the shipped app).
   - Wait for `/health`, then open the pywebview window (title, icon, sensible min size, "Open in Browser" menu item).
   - `--smoke` flag: start server, poll `/health`, print version, exit 0 — used by CI on both platforms to prove the frozen binary actually boots.
   - Clean shutdown on window close.
6. **`requirements-desktop.txt`** — `pywebview` + `pyinstaller`, kept out of `requirements.txt` so the web/dev/CI path and pip-audit scope stay untouched (add a second pip-audit line for it in CI if desired).

### macOS packaging

- **Apple Silicon first**: build on `macos-latest` (arm64). PyInstaller **ad-hoc signs by default**, which is mandatory for arm64 binaries to run at all.
- **Intel**: GitHub's `macos-15-intel` label exists **until August 2027**. Ship arm64 in v1; add an Intel job later only if users ask (it's a copy-paste matrix entry). **Do not attempt universal2** — it requires universal wheels for every dep (curl_cffi won't cooperate) for marginal benefit.
- **DMG**: `brew install create-dmg`, then `create-dmg` with app icon, volume name `FolioSenseAI`, drag-to-Applications layout, optional background PNG (brand-colored, subtle — reuse orbit mark).
- **Icon**: generate `packaging/icons/FolioSenseAI.icns` from `static/img/brand/folio-orbit-icon-1024.png` (`sips` + `iconutil`). Commit the generated `.icns`/`.ico` so CI never needs cross-platform icon tooling; keep `scripts/make-icons.sh` in repo for regeneration.

### Windows packaging

- Build on `windows-latest` (Server 2025). **Inno Setup is NOT preinstalled there** — install with `choco install innosetup -y` in the workflow (fast, cached by chocolatey CDN).
- `packaging/windows/installer.iss`:
  - `PrivilegesRequired=lowest` → per-user install under `{localappdata}\Programs\FolioSenseAI` — no UAC prompt, cleaner SmartScreen story, clean uninstall.
  - AppName, AppVersion (passed via `/DMyAppVersion=` from CI), publisher `Umang Dhawan / FolioSenseAI`, MIT license page, icon, Start-menu + optional desktop shortcut, uninstaller registered in Apps & Features.
  - **WebView2 runtime check**: pywebview on Windows needs the WebView2 runtime (preinstalled on Win 11 and updated Win 10). Add the standard Inno snippet: detect via registry, download/run the Evergreen Bootstrapper (~2 MB, MS-hosted) only if missing.
- Windows x64 only (matches every realistic user).

### Artifact naming (exact)

```
FolioSenseAI-macOS-arm64-v4.3.0.dmg
FolioSenseAI-Windows-x64-v4.3.0-Setup.exe
SHA256SUMS.txt          # one file covering all assets, uploaded to the same release
```
Latest-main prereleases use the same names with `v4.3.0` replaced by `main-<shortsha>`.

---

## 3. GitHub Actions workflow plan

**Keep it to exactly one new workflow.** Existing `ci.yml`, `codeql.yml`, `pylint.yml`, `dependency-review.yml`, `security-hygiene.yml`, `docs.yml` stay as-is (one small edit to `docs.yml` noted in §7).

### New: `.github/workflows/release.yml`

```
Triggers:
  push:  tags: ["v*"]          → stable release
  push:  branches: [main]      → rolling "latest-main" prerelease
  workflow_dispatch:           → manual rebuild

Jobs (DAG):
  test ──┬── build-macos  ──┬── publish
         └── build-windows ─┘
```

- **`test`** — single quick gate (Python 3.12, `pip install -r requirements.txt pytest`, `python -m pytest -q`). The full matrix still runs in `ci.yml`; this job exists so a red main can never ship binaries.
- **`build-macos`** (`macos-latest`, needs: test)
  1. `actions/setup-python@v5` (3.12, `cache: pip`)
  2. `pip install -r requirements.txt -r requirements-desktop.txt`
  3. `pyinstaller packaging/pyinstaller/FolioSenseAI.spec` — spec includes `--collect-all curl_cffi`, `--hidden-import _cffi_backend`, `collect_submodules("uvicorn")`, and datas for `static/`, `templates/`, `.env.example`
  4. Smoke test: `dist/FolioSenseAI.app/Contents/MacOS/FolioSenseAI --smoke`
  5. `brew install create-dmg` → build DMG
  6. `shasum -a 256` → sidecar `.sha256`; upload artifact
- **`build-windows`** (`windows-latest`, needs: test) — same shape; `choco install innosetup -y`; smoke test the frozen exe; `iscc /DMyAppVersion=... installer.iss`; `Get-FileHash`.
- **`publish`** (`ubuntu-latest`, needs: both builds) — the **only** job with `permissions: contents: write`:
  - Download both artifacts, assemble `SHA256SUMS.txt`.
  - **Tag build (`v*`)** → `softprops/action-gh-release@v2`: create release from tag, attach DMG + EXE + SHA256SUMS, auto-generated notes + curated section pasted from `RELEASE_NOTES.md`.
  - **Main push** → maintain one rolling prerelease with fixed tag `latest-main`: `gh release upload latest-main <assets> --clobber`, then update the release body with commit SHA, date, and a "built from main, may be unstable" banner. Marked `prerelease: true` so it never becomes `releases/latest`.
- **Safety / rollback semantics**
  - Publishing happens only after **both** platform builds and smoke tests pass — no partial releases.
  - If anything fails, the previous stable release and previous `latest-main` assets remain untouched. Rollback = the failure case does nothing (this is the correct behavior; no delete-then-upload sequencing).
  - `concurrency: group: release-${{ github.ref }}` with `cancel-in-progress: false` so two quick merges can't interleave asset uploads.
- **Permissions**: workflow default `permissions: contents: read`; only `publish` elevates to `contents: write`. No other scopes. No secrets needed until code signing (Phase 2+).
- **Caching**: pip cache via setup-python (both platforms). That's it — don't cache brew/choco; installs are <30 s and cache complexity isn't worth it.

### Website metadata strategy — no `latest.json` commit-backs

The landing page fetches release metadata **client-side at page load** from the public GitHub API (CORS-enabled, no auth):

- `GET https://api.github.com/repos/udhawan97/FolioSenseAI/releases/latest` → stable version, date, assets, download URLs
- `GET .../releases/tags/latest-main` → dev build info (behind a dropdown)

Cache the response in `sessionStorage` (rate limit is 60/hr/IP — one fetch per session is nothing). **Graceful fallback**: if the fetch fails, buttons degrade to the static permalink `https://github.com/udhawan97/FolioSenseAI/releases/latest` — which always works.

Why this beats committing `latest.json`: zero bot commits, zero Pages rebuilds on release, buttons are *always* current, and the release pipeline and website deploy stay fully decoupled. (If an in-app auto-update check is ever wanted, a `latest.json` **release asset** can be added then — noted in Risks, not built now.)

---

## 4. Release & versioning strategy

- **Move to plain semver tags: `v4.3.0`** (the pipeline triggers on `v*`). The old `release-v4.2` tag stays as history; nothing depends on it after the install scripts are updated.
- **`app/version.py` is the single version source.** A tag-time CI guard in `publish` verifies tag == `__version__` (fail loudly on mismatch).
- **Two channels, explicitly:**
  - **Stable** — cut by pushing a tag. This is what the website, README, and docs point to by default.
  - **latest-main** — rolling prerelease auto-refreshed on every green main merge. Surfaced only behind a "Development builds" dropdown with an explicit stability warning. This satisfies "always downloadable from the latest main commit" without ever making an untested build the default.
- **Release cadence/policy** (documented in docs §7): tags are cut manually when meaningful; `RELEASE_NOTES.md` remains the curated changelog; GitHub auto-notes supplement it.
- **First shipped version: `v4.3.0`** — "FolioSenseAI goes desktop."

### Code signing — honest staged plan

| Phase | What | Cost | Website/doc language |
| --- | --- | --- | --- |
| **1 (now)** | Unsigned (macOS ad-hoc signature only). Ship with clear, honest warnings + bypass instructions + checksums | $0 | "Early builds aren't code-signed yet. macOS and Windows will warn you. Here's exactly what you'll see and how to proceed — and how to verify your download came from GitHub Releases." |
| 2 | Apple Developer ID signing in CI (cert + key in Actions secrets) | $99/yr | Remove Gatekeeper bypass steps for new versions |
| 3 | Notarization (`notarytool` step, ~2 min in CI, same Apple account) | included | "No warnings on macOS" |
| 4 | Windows signing — evaluate **Azure Trusted Signing** (~$10/mo) vs **SignPath free OSS tier** | ~$0–120/yr | SmartScreen warnings fade (reputation still takes time) |

Phase 1 ships now. Phases 2–4 are documented as a roadmap section in the docs — **never** implied to exist before they do. Important accuracy note for docs: on **macOS 15 Sequoia, right-click → Open no longer bypasses Gatekeeper**; the flow is *attempt open → System Settings → Privacy & Security → "Open Anyway"*. Docs must show the Sequoia flow.

---

## 5. Website / download page plan

### Placement & architecture

- Stay in the existing Astro project. Add **`docs-site/src/pages/index.astro`** — a custom Astro page that takes over `/` (specific routes beat Starlight's catch-all). Delete the current splash `index.mdx`; docs remain at their existing slugs; "View Docs" lands on `get-started/introduction/`. One repo, one deploy workflow, consistent branding.
- Zero frameworks, zero animation libraries. Hand-written Astro + scoped CSS + ~2 small vanilla JS modules (release fetcher, clipboard). Budget: **< 50 KB JS, LCP < 1.5 s, CLS 0**.
- Reuse the existing brand system: orbit mark (animated SVG already exists), Starlight accent palette, dark-first with light support.

### Iteration 1 — Functional, clean, trustworthy

Single-column, generous whitespace, Apple-store clarity. Order:

1. **Hero** — animated orbit mark, "FolioSenseAI", tagline *"Your folio, finally making sense."*, one-sentence plain-English description, two equal buttons: **Download for macOS** / **Download for Windows**, quiet links: View Docs · GitHub · Release Notes.
2. **Release strip** — `v4.3.0 · Jul 7, 2026 · abc1234 · macOS arm64 / Windows x64`, populated from the API; SHA links to the commit.
3. **Screenshot** — existing `docs/dashboard.png` in a simple frame.
4. **Install accordions** (native `<details>`) — macOS (Apple Silicon), macOS (Intel — "not shipped yet, build from source"), Windows, Build from source, One-line script install (power users). Every command block has a copy button.
5. **Troubleshooting** — Gatekeeper (Sequoia flow), SmartScreen ("More info → Run anyway"), checksum verification (`shasum -a 256 -c` / `Get-FileHash`), "why the warnings" honesty box.
6. **Footer** — GitHub, docs, releases, MIT, "not financial advice" one-liner.

Strength: total download confidence. Weakness: reads like documentation, not a product launch.

### Iteration 2 — Premium, futuristic, professional

Same skeleton, elevated presentation (Linear/Cursor/Anthropic as quality bar):

- **Platform-aware CTA**: detect OS (`navigator.userAgentData?.platform ?? navigator.platform`), promote the matching button to primary with version + file size inline (`Download for macOS · v4.3.0 · 84 MB`), demote the other; both always visible. Small "Development builds ▾" dropdown under the CTAs exposing latest-main artifacts with a warning chip.
- **Backdrop**: fixed CSS-only radial gradient field in brand colors + slow drifting orbit lines (pure CSS transforms, `prefers-reduced-motion` disables everything, no canvas, no particles library).
- **Platform cards**: two glass cards (subtle `backdrop-filter`, 1 px borders, soft glow on hover only) with OS glyphs, arch chips (`arm64` / `x64`), size, SHA256 popover.
- **Screenshot**: framed in a window chrome mock with soft ambient glow; slight fade+rise on scroll (IntersectionObserver toggling a CSS class — one pattern reused for all reveals).
- **Feature grid**: six compact cards (Local-first · Claude optional · Live market context · Risk analytics · News themes · Meet Senpai) with existing icon language.
- **Trust section**: "Built in the open" — links every download to its Release, its commit, its checksum, and its Actions run. This is the open-source flex proprietary apps can't do.
- **Microinteractions**: copy buttons flip to ✓, buttons have 150 ms ease transforms, Senpai orb in the footer cycles a quip on click (asset + behavior already exist in-app).
- **Release notes preview**: latest release name + first lines from the API, "All releases →".

### Final recommendation (build this)

**Iteration 1's structure with Iteration 2's finish, minus anything that risks the perf budget.** Concretely: platform-aware hero CTAs + dev-builds dropdown, glass platform cards, CSS-only gradient backdrop (skip drifting orbit lines if they read gimmicky in review), one reusable scroll-reveal, copy-to-clipboard everywhere, trust section, feature grid, framed screenshot, footer Senpai egg. Hard rules: no JS animation libs, `prefers-reduced-motion` respected, works fully with JS disabled (static fallback links), Lighthouse ≥ 95 on all four scores.

---

## 6. README refresh plan

Target: **~40% shorter**, scannable in 30 seconds, credible for all three audiences (casual user, recruiter, developer). Keep the voice — Senpai stays.

**New structure:**

1. Brand mark + tagline + one-line description (keep)
2. **Badges (pruned to meaningful+live):** dynamic release badge (`img.shields.io/github/v/release/...`), CI status, downloads count (`img.shields.io/github/downloads/...`), Python 3.11+, MIT. **Drop**: static `release-v4.2`, FastAPI-version, SQLite, "Claude optional", "setup scripts" badges (stale or noise). Pylint/CodeQL move to a dev-section line.
3. **⬇️ Download** (new, near top): macOS DMG button-link, Windows EXE button-link (both to `releases/latest/download/...`-style or releases/latest), "all releases", website, docs. One honest sentence about unsigned-build warnings linking to the troubleshooting accordion.
4. **What it does** — trimmed "line went up" intro (2 short paragraphs max) + the existing Do-this/Get-this table (kept, it's good).
5. Screenshot (keep; re-shoot only if v4.3 visibly changes chrome).
6. **Meet Senpai** — trimmed to ~half.
7. **Install** — desktop installers first (one line + link to docs), then `<details>` for: script install, manual/git install, Claude setup.
8. **For developers** — `<details>` blocks: dev setup, quality checks, project layout, architecture diagrams (move both mermaid diagrams + table here), packaging (`how to build the DMG/EXE locally`).
9. **Release workflow** — short section: tags → Actions → DMG/EXE/checksums on Releases; latest-main prereleases; link to release.yml and docs page.
10. **Troubleshooting install** — `<details>` with the table (add Gatekeeper/SmartScreen rows).
11. Privacy (trim to table), Contributing, License (keep).

**Corrections while in there:** fix FastAPI 0.136.3→0.138.2, SQLAlchemy 2.0.50→2.0.51, yfinance 1.4.1→1.5.1 (or better: drop patch-level claims entirely so they can't rot), remove the hardcoded test count on the docs homepage ("361 tests"), update install one-liners to latest-release form (§8).

---

## 7. Docs update plan (`docs-site/`)

**New sidebar group "Download & Install"** (placed first, above Get Started):

| Page | Content |
| --- | --- |
| `download.mdx` | The download story: stable vs latest-main channels, what each artifact is, checksums how-to, link matrix |
| `install-macos.mdx` | DMG flow with Sequoia Gatekeeper walkthrough (screenshots of the actual dialogs), where data lives (`~/Library/Application Support/FolioSenseAI`), uninstall |
| `install-windows.mdx` | Installer flow, SmartScreen walkthrough, WebView2 note, data location (`%APPDATA%`), uninstall via Apps & Features |
| `updating.mdx` | Update by installing the new version over the old; data/DB preserved (lives in user-data dir); script/git update paths |
| `build-from-source.mdx` | Dev run + `pyinstaller` build instructions per platform (absorbs/links existing installation.mdx content) |
| `releases-and-versioning.mdx` | Channel policy, semver tags, **pipeline diagram** (static SVG matching `architecture.svg` style): `main merge → tests → build macOS/Windows → smoke test → GitHub Release → website buttons`; second small diagram: stable vs latest-main; signing roadmap phases 1–4, stated honestly |

**Edits to existing pages:** `get-started/installation.mdx` becomes "Install from source / scripts" and cross-links the new pages; troubleshooting page gains the Gatekeeper/SmartScreen/checksum entries; release-notes page links the Releases feed. Update stale "361 tests" phrasing to something durable ("hundreds of offline tests"). Advanced detail goes into Starlight's built-in accordion/tab components. No mermaid plugin — hand-made SVGs only (Starlight doesn't render mermaid without extra tooling; keep the toolchain lean).

**`docs.yml` edit:** none required (landing page lives in `docs-site/`, already in its path filter). Optionally rename workflow display name "Docs" → "Website".

---

## 8. Install script plan

Scripts stay as the **power-user secondary path** (they're genuinely good); DMG/EXE become primary everywhere.

- **`scripts/install-mac.sh` / `install-win.ps1`**: replace the hardcoded `release-v4.2` URLs with latest-release resolution — query `https://api.github.com/repos/udhawan97/FolioSenseAI/releases/latest` for the tag, then download `.../archive/refs/tags/<tag>.zip`. Add `FOLIO_REF` env override (`FOLIO_REF=latest-main` or any tag) for channel choice. Keep every existing safety property: no sudo, `set -euo pipefail`, temp-dir + trap cleanup, `.env`/database preservation, transparent readable code with section comments.
- Optional integrity step: after download, print the zip's SHA256 so users can eyeball it (source zips aren't in SHA256SUMS; the checksums file covers installers — say so honestly rather than fake-verifying).
- Website/docs present scripts inside the "One-line install (advanced)" accordion with copy buttons and a "read the script first" link to the file on GitHub — never piped-to-shell as the headline flow.
- Validation: run both scripts in CI-ish conditions (macOS runner bash, Windows runner PowerShell) as a manual pre-release check; full clean-machine validation is in §11.

---

## 9. File-by-file implementation checklist for Opus

**Phase A — App changes for packaging**
- [ ] `app/version.py` — new; `__version__ = "4.3.0"`
- [ ] `app/paths.py` — new; `resource_dir()`, `data_dir()` (platformdirs when frozen)
- [ ] `app/config.py` — load `.env` from `data_dir()`; frozen-aware `DATABASE_URL` default; `DEBUG` default False when frozen
- [ ] `app/main.py` — absolute paths for static mount (`:80`) and template read (`:82`); version from `app/version.py`
- [ ] `desktop/main.py` — new desktop entry (port pick → CORS env → uvicorn thread `127.0.0.1`, no reload → `/health` wait → pywebview window; `--smoke` mode; clean shutdown)
- [ ] `requirements-desktop.txt` — new (`pywebview`, `pyinstaller`, pinned)
- [ ] Tests: unit tests for `paths.py` dev-mode behavior; existing suite must stay green untouched

**Phase B — Packaging assets**
- [ ] `scripts/make-icons.sh` — new; 1024 PNG → `.icns` (sips/iconutil) + `.ico` (Pillow)
- [ ] `packaging/icons/FolioSenseAI.icns`, `FolioSenseAI.ico` — generated, committed
- [ ] `packaging/pyinstaller/FolioSenseAI.spec` — onedir; datas: `static/`, `templates/`; `collect_all("curl_cffi")`, `hiddenimports=["_cffi_backend"]`, `collect_submodules("uvicorn")`; windowed; icons; macOS bundle identifier `com.foliosenseai.app`, version from `app/version.py`
- [ ] `packaging/windows/installer.iss` — per-user, metadata, license, shortcuts, uninstaller, WebView2 bootstrap check
- [ ] (optional) `packaging/macos/dmg-background.png`
- [ ] Local build verify on this Mac: `pyinstaller ... && ./dist/.../FolioSenseAI --smoke` before touching CI

**Phase C — Pipeline**
- [ ] `.github/workflows/release.yml` — per §3 (triggers, 4 jobs, minimal perms, concurrency, smoke tests, SHA256SUMS, tag-vs-version guard, stable + latest-main publishing)
- [ ] Create rolling prerelease once: tag `latest-main` + `gh release create latest-main --prerelease`
- [ ] Ship `v4.3.0`: bump version file, update `RELEASE_NOTES.md`, tag, verify end-to-end

**Phase D — Website**
- [ ] `docs-site/src/pages/index.astro` + `src/components/landing/*` (Hero, PlatformCards, ReleaseStrip, InstallAccordion, TrustSection, FeatureGrid, Footer) + `src/styles/landing.css`
- [ ] `src/scripts/releases.js` (API fetch + sessionStorage + fallback), `clipboard.js`
- [ ] Delete `docs-site/src/content/docs/index.mdx` (content redistributed to landing + intro docs)
- [ ] Verify Starlight nav still resolves; all internal links respect the `/FolioSenseAI` base path (this bit the repo before — commit `1c3b972`)

**Phase E — Docs**
- [ ] Six new/updated pages per §7 + sidebar config in `astro.config.mjs`
- [ ] Pipeline SVG + channels SVG in `docs-site/src/assets/`
- [ ] Real dialog screenshots for Gatekeeper/SmartScreen pages (capture during §11 validation)

**Phase F — README & scripts**
- [ ] `README.md` restructure per §6 (download section, pruned badges, `<details>` blocks, stale-fact fixes)
- [ ] `scripts/install-mac.sh`, `scripts/install-win.ps1` — latest-release resolution + `FOLIO_REF`
- [ ] `FolioSenseAI.command` / `.bat` — unchanged (still the from-source path); README repositions them

---

## 10. Validation checklist (two-pass loop for Opus)

### Pass 1 — Build & packaging

- [ ] `pytest` green locally and in CI after Phase A (no regressions from path changes)
- [ ] Local macOS: PyInstaller build succeeds; `--smoke` passes; app launches; window shows dashboard; quotes load; DB + `.env` created under `~/Library/Application Support/FolioSenseAI`; **install dir stays pristine**; icon correct in Dock/Finder; version correct in About/health; quit actually kills the server (check with `lsof -i`)
- [ ] DMG: mounts, drag-to-Applications works, app runs from `/Applications`, Gatekeeper flow matches what docs will say
- [ ] CI Windows artifact on a real Windows machine/VM: installer runs without admin, shortcuts work, app launches (WebView2 path verified on a machine *without* the runtime if possible), data in `%APPDATA%`, uninstall removes program + shortcuts and leaves user data
- [ ] Upgrade-in-place: install v-old → add a holding → install v-new → holding survives
- [ ] `release.yml`: tag run produces release with exactly 3+1 assets, names match §2 spec, SHA256SUMS verifies against downloads; main-merge run refreshes `latest-main` only; **kill one build job intentionally → confirm nothing publishes and prior assets survive**; tag/version mismatch fails loudly
- [ ] Workflow permissions audit: only `publish` has `contents: write`

### Pass 2 — Website, docs, README, UX

- [ ] Landing page: correct version/date/SHA from API; both buttons download the actual artifacts; OS detection promotes the right card (test macOS + Windows + Linux UA); dev-builds dropdown gated + warned; JS-disabled fallback links work; base-path correctness on every link; Lighthouse ≥ 95 ×4; `prefers-reduced-motion` honored; mobile layout sane
- [ ] Checksum instructions actually verify a fresh download on both OSes (run them, don't assume)
- [ ] Every README link resolves (download links, docs links, badge targets render live values)
- [ ] Docs: all new pages render, sidebar order right, screenshots match current OS dialogs, diagrams legible in dark + light
- [ ] Install scripts: fresh macOS user account + fresh Windows VM, both channels (`latest`, `FOLIO_REF=latest-main`), re-run preserves data
- [ ] Read-through: no claim anywhere implies signing/notarization exists (Phase 1 honesty check); no stale versions/counts anywhere
- [ ] Loop rule: any Pass-1 fix that touches packaging → rerun affected Pass-1 items before re-entering Pass 2

---

## 11. Risks & trade-offs

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| **PyInstaller misses dynamic imports** (curl_cffi/yfinance/uvicorn) → frozen app dies at runtime | Medium | Known flags baked into spec (`collect-all curl_cffi`, `_cffi_backend`, uvicorn submodules); `--smoke` in CI catches boot failures on every build; iterate locally in Phase B before CI |
| **pywebview friction** (WebView2 missing on old Win 10; WKWebView quirks with Chart.js) | Low–Medium | Inno WebView2 bootstrap; fallback plan B (browser + status window) swaps only `desktop/main.py`, pipeline unchanged |
| Unsigned-app warnings scare users away | High (certainty) | Honest UX: warnings explained with screenshots before download; checksums + provenance section; Phase 2–4 signing roadmap |
| macOS Sequoia Gatekeeper flow changes again | Low | Docs point at Settings-based flow; screenshots versioned |
| Artifact size (~80–120 MB) surprises users vs. the 5 MB script install | Medium | Show size on buttons; keep script path documented for minimalists |
| GitHub API rate limit on landing page | Low | sessionStorage cache + static fallback links |
| `latest-main` races on rapid merges | Low | `concurrency` group, no cancel-in-progress |
| Intel Mac users | Low | Build-from-source + scripts still work on Intel; add `macos-15-intel` job later if demand (available until Aug 2027) |
| Version drift between tag and `app/version.py` | Medium | CI guard fails the release on mismatch |
| Auto-update expectations | — | Out of scope, deliberately; "Updating" docs page sets expectations; `latest.json` asset can be added later without redesign |
| relative-path regressions in dev mode from `paths.py` refactor | Low | dev-mode behavior identical (repo root); tests + local run verify |

**Trade-offs accepted:** no universal2 binary (two-DMG path later instead); no Linux packaging (script/git path covers it); no auto-updater; checksums cover installers only (source zips are GitHub-generated); one extra rolling prerelease visible in the Releases list (labeled clearly).

---

## 12. Copy-ready execution prompt for Opus

> You are executing a pre-approved plan: **`docs/plans/desktop-product-plan.md`** in `udhawan97/FolioSenseAI`. Read the whole plan first; it contains the repo audit, all decisions, and exact file lists. Do not re-litigate stack choice (PyInstaller onedir + pywebview; create-dmg; Inno Setup; one new `release.yml`; landing page at `docs-site/src/pages/index.astro`).
>
> Execute phases in order, committing per phase with clear messages, on a feature branch:
> **A** app changes (`app/version.py`, `app/paths.py`, config/main path fixes, `desktop/main.py` with `--smoke`, `requirements-desktop.txt`) — full test suite must stay green.
> **B** packaging (`scripts/make-icons.sh`, committed `.icns`/`.ico`, PyInstaller spec with the curl_cffi/uvicorn collection flags, `installer.iss` per-user with WebView2 bootstrap) — build and smoke-test locally on macOS before CI.
> **C** `.github/workflows/release.yml` exactly per plan §3: tag `v*` → stable release, main push → rolling `latest-main` prerelease, publish job only after both platform builds + smoke tests pass, minimal permissions (`contents: write` on publish only), SHA256SUMS.txt, tag==version guard. Create the `latest-main` prerelease shell.
> **D** landing page per plan §5 final recommendation: platform-aware CTAs, client-side release metadata from the GitHub API with static fallback, glass platform cards, install/troubleshooting accordions with copy buttons, trust section, CSS-only backdrop, `prefers-reduced-motion`, <50 KB JS, base-path-safe links.
> **E** docs per plan §7 (six pages + two SVG diagrams + sidebar), **F** README per plan §6 (Download section top, pruned live badges, `<details>` depth, fix the stale version/test-count facts listed in §1) and install scripts switched to latest-release resolution with `FOLIO_REF` override.
> Then run the **two-pass validation loop in plan §10** and fix what it finds. Honesty constraints: builds are unsigned in Phase 1 — never imply otherwise; every user-facing claim must be true of the artifacts you actually produced. Finish by tagging `v4.3.0` only after Pass 1 is fully green.

---

*End of plan.*

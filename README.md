<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="static/img/brand/folio-orbit-mark-light.svg">
    <source media="(prefers-color-scheme: light)" srcset="static/img/brand/folio-orbit-mark-dark.svg">
    <img src="static/img/brand/folio-orbit-mark-dark.svg" alt="FolioSenseAI" width="300"/>
  </picture>
</p>

<h2 align="center">FolioSenseAI</h2>
<p align="center"><em>Your portfolio's therapist. Explains the red. Won't fix it.</em></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/FastAPI-0.136-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Claude_AI-Anthropic-D4A853?style=flat-square&logo=anthropic&logoColor=white" alt="Claude AI"/>
  <img src="https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite"/>
  <img src="https://img.shields.io/badge/Bootstrap-5-7952B3?style=flat-square&logo=bootstrap&logoColor=white" alt="Bootstrap 5"/>
  <img src="https://img.shields.io/badge/Chart.js-FF6384?style=flat-square&logo=chartdotjs&logoColor=white" alt="Chart.js"/>
  <img src="https://img.shields.io/badge/release-v1-brightgreen?style=flat-square" alt="Release v1"/>
</p>

<p align="center">
  <a href="https://github.com/udhawan97/FolioSenseAI/actions/workflows/ci.yml"><img src="https://github.com/udhawan97/FolioSenseAI/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="https://github.com/udhawan97/FolioSenseAI/actions/workflows/pylint.yml"><img src="https://github.com/udhawan97/FolioSenseAI/actions/workflows/pylint.yml/badge.svg" alt="Pylint"/></a>
  <a href="https://github.com/udhawan97/FolioSenseAI/actions/workflows/codeql.yml"><img src="https://github.com/udhawan97/FolioSenseAI/actions/workflows/codeql.yml/badge.svg" alt="CodeQL"/></a>
</p>

---

> **Because "I don't know why my portfolio is down" is only acceptable once.**
>
> FolioSenseAI tracks your holdings, pulls live prices from Yahoo Finance, and asks Claude AI to explain what on earth is happening — market context, sector moves, macro events, analyst takes. All the excuses reasons you need, in one dashboard.

---

## 📸 Marketing

<p align="center">
  <img src="docs/dashboard.png" alt="FolioSenseAI Dashboard" width="850"/>
  <br/>
  <sub><em>Numbers are fake to protect the traumatized investor.</em></sub>
</p>


---

## ✨ Features

### 📊 Live Dashboard
- Real-time prices and daily gain/loss for all holdings
- Total portfolio value and daily P&L *(color-coded — green good, red bad, you know the drill)*
- Allocation, return, and performance-history views
- Market open/closed indicator with auto-refresh countdown — so you can watch it drop in real time

### 🧠 Portfolio Intelligence *(the whole point)*
- **Movement explanations** — macro, sector, news, and company context for each holding
- **Portfolio-level AI analysis** — diversification themes, concentration risks, notable movers
- **Holding coverage** — ETF sectors, regions, themes, and benchmark context
- **Analyst recommendations** and ETF quality labels *(take with an appropriate grain of salt)*

### ⚙️ Portfolio Management
- Add and remove holdings from the UI
- Update share counts and average cost basis
- Soft-delete holdings while preserving historical trade data *(because your mistakes deserve to be remembered)*

---

## 🏗️ Tech Stack

*No blockchain. No NFTs. No regrets.*

| Layer | Technology | Why |
|-------|------------|-----|
| 🐍 **Backend** | Python 3.11+ · FastAPI · Uvicorn | Fast, async, and doesn't make you cry |
| 🗄️ **Database** | SQLite · SQLAlchemy 2.0 · Pydantic v2 | ACID-compliant, unlike your trading decisions |
| 🤖 **AI** | Anthropic Claude | Smarter than CNBC. Low bar. Cleared it. |
| 📈 **Market Data** | yfinance · Yahoo Finance | Free real-time data — the only free thing in investing |
| 🎨 **Frontend** | Bootstrap 5 · Chart.js · Vanilla JS | Zero frontend frameworks harmed in the making |
| 🔐 **Config** | python-dotenv | Secrets stay secret. Your ticker picks do not. |

---

## 🚀 Local Setup

### Prerequisites

You'll need these before anything else:

| Requirement | Where to get it |
|------------|----------------|
| **Python 3.11+** | [python.org](https://www.python.org/downloads/) |
| **Git** *(optional)* | [git-scm.com](https://git-scm.com/) — only needed for Git Bash or source development |
| **Anthropic API key** | [console.anthropic.com](https://console.anthropic.com/) |

> 💡 The Anthropic API key costs a little money per AI query — roughly pennies. The AI explanations are cached, so you won't rack up charges just by refreshing.

---

### 🍎 Mac Setup

macOS tends to just work here. Suspiciously well.

**1. Download the v1 release**

```bash
curl -L -o FolioSenseAI-v1.zip https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v1.zip
unzip FolioSenseAI-v1.zip
cd FolioSenseAI-release-v1
```

> 💡 This installs the GitHub release [v1](https://github.com/udhawan97/FolioSenseAI/releases/tag/release-v1). If you're developing the app instead, clone the repo from `main`.

**2. Create a virtual environment and install dependencies**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> 💡 If `python3` isn't found, install via [Homebrew](https://brew.sh/): `brew install python`
>
> 💡 You'll know the venv is active when your terminal prompt shows `(venv)`. Don't skip this step — global Python installs are a mess.

**3. Configure environment**

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
SECRET_KEY=some_long_random_string_here
DEBUG=True
DATABASE_URL=sqlite:///./database/portfolio.db
CORS_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
DEFAULT_HOLDINGS=
```

> 💡 Generate a proper secret key in one line:
> ```bash
> python3 -c "import secrets; print(secrets.token_hex(32))"
> ```

**4. Run**

```bash
python run.py
```

Open [http://localhost:8000](http://localhost:8000) — your dashboard awaits.

**5. Create your local portfolio** *(first run only)*

```bash
curl -X POST http://localhost:8000/api/portfolio/seed
```

This creates an empty local portfolio by default. To seed starter tickers without committing personal holdings, set `DEFAULT_HOLDINGS=VOO,QQQ,BND` in your own `.env`, then run the seed command.

---

### 🪟 Windows Setup

Windows is supported. We have feelings about it, but we support it.

**Step 0: Install Python properly**

Download Python from [python.org](https://www.python.org/downloads/). During install, **check "Add Python to PATH"** — this is not optional. If you miss it, uninstall and reinstall. Trust us.

**Option A: Command Prompt or PowerShell**

```powershell
Invoke-WebRequest -Uri "https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v1.zip" -OutFile "FolioSenseAI-v1.zip"
Expand-Archive -Path "FolioSenseAI-v1.zip" -DestinationPath .
cd FolioSenseAI-release-v1

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
```

> 💡 If PowerShell blocks script execution, run this first:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

**Option B: Git Bash** *(recommended — Unix-like and sane)*

If you installed Git for Windows, Git Bash lets you use the same commands as Mac:

```bash
curl -L -o FolioSenseAI-v1.zip https://github.com/udhawan97/FolioSenseAI/archive/refs/tags/release-v1.zip
unzip FolioSenseAI-v1.zip
cd FolioSenseAI-release-v1

python -m venv venv
source venv/Scripts/activate   # Note: "Scripts" not "bin" on Windows

pip install -r requirements.txt
```

> 💡 Both Windows options install the GitHub release [v1](https://github.com/udhawan97/FolioSenseAI/releases/tag/release-v1). Clone the repo only if you want to work from the latest source instead of the release.

**Configure environment:**

```cmd
copy .env.example .env
```

Open `.env` in Notepad, VS Code, or anything that isn't WordPad:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
SECRET_KEY=some_long_random_string_here
DEBUG=True
DATABASE_URL=sqlite:///./database/portfolio.db
CORS_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
DEFAULT_HOLDINGS=
```

> 💡 Generate a secret key in PowerShell:
> ```powershell
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

**Run:**

```cmd
python run.py
```

Open [http://localhost:8000](http://localhost:8000).

> ⚠️ **SSL errors?** If yfinance complains about certificates, run: `pip install --upgrade certifi`

---

### 🔗 Useful URLs *(once running)*

| URL | What's there |
|-----|-------------|
| `http://localhost:8000` | The dashboard |
| `http://localhost:8000/docs` | Swagger API docs (surprisingly pretty) |
| `http://localhost:8000/health` | Health check endpoint |

---

## 🔐 Clean-Slate Fork Safety

This repo is designed so forks start without personal portfolio data:

- `.env` stays local and is ignored by Git.
- SQLite databases and database backups are ignored.
- `POST /api/portfolio/seed` creates an empty portfolio unless you set `DEFAULT_HOLDINGS` in your own `.env`.
- `CORS_ALLOWED_ORIGINS` defaults to local app origins instead of `*`.

If you previously committed a real database backup, delete it from the current tree and purge it from Git history before treating the public repo as clean.

---

## 📡 API Reference

Full interactive docs at `/docs` when running locally. Here's the cheat sheet:

<details>
<summary>📈 Market Data</summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/stocks/prices` | Live prices for all holdings |
| `GET` | `/api/stocks/price/{ticker}` | Single ticker price |
| `GET` | `/api/stocks/history/{ticker}?period=1mo` | Historical OHLCV data |
| `GET` | `/api/stocks/market-status` | Is the market open (and punishing you)? |

</details>

<details>
<summary>💼 Portfolio</summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/portfolio/holdings` | All active holdings |
| `POST` | `/api/portfolio/holdings` | Add a holding |
| `PUT` | `/api/portfolio/holdings/{id}` | Update shares/cost |
| `DELETE` | `/api/portfolio/holdings/{id}` | Remove a holding (touch grass) |
| `GET` | `/api/portfolio/value` | Portfolio value, allocation, daily P&L |
| `GET` | `/api/portfolio/pnl` | Historical returns and realized P&L |
| `POST` | `/api/portfolio/seed` | Create the local portfolio and optional configured starter holdings |

</details>

<details>
<summary>🤖 AI Intelligence</summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/ai/summary/{ticker}` | AI summary for one holding |
| `GET` | `/api/ai/summaries/all` | AI summaries for all holdings |
| `GET` | `/api/ai/portfolio-insight` | Portfolio-level AI analysis |
| `GET` | `/api/ai/explain-move/{ticker}` | Why is this thing moving? |
| `GET` | `/api/ai/explain-moves/all` | Why is everything moving? |
| `GET` | `/api/ai/holding-intelligence/all` | Coverage and benchmark context |
| `GET` | `/api/ai/analyst-recommendations/all` | Analyst takes and ETF quality labels |
| `GET` | `/api/ai/cache/stats` | Cache stats and estimated API cost |
| `DELETE` | `/api/ai/cache/clear` | Clear cached summaries |

</details>

---

## 🧪 Tests

```bash
python -m pytest tests/ -v
```

External services are mocked. *(Real integration tests would cost money. Claude is cheap but not free.)*

---

## 🛡️ GitHub Checks

The repo now has a tiny robot compliance department. It does not wear a tie, but it will absolutely block nonsense.

| Check | What it does | Vibe |
|-------|--------------|------|
| **CI** | Installs dependencies, compiles Python, imports the FastAPI app, and runs the test suite on Python 3.11 and 3.12 | Makes sure the app still has a pulse |
| **Pylint** | Runs static analysis on pull requests and pushes to `main` | Complains professionally |
| **Dependency Audit** | Uses `pip-audit` against `requirements.txt` | Checks whether a package has entered its villain era |
| **Dependency Review** | Reviews dependency changes in pull requests and fails on moderate-or-worse known vulnerabilities | Stops suspicious packages at the door |
| **CodeQL** | Runs GitHub code scanning for Python security and quality issues | Reads the code like it has trust issues |
| **Security Hygiene** | Blocks local secrets, databases, backups, and OS confetti from being tracked | Protects you from committing your digital laundry |
| **Dependabot** | Checks Python packages and GitHub Actions monthly | Gently nags the dependencies into the present |

These checks run on GitHub Actions, so pull requests get the useful red/green lights before anything lands on `main`. If a check fails, read the log before blaming the market. The market is innocent this time. Probably.

---

## 💰 Cost Breakdown

| Service | Cost |
|---------|------|
| yfinance market data | 🆓 Free |
| SQLite database | 🆓 Free |
| Self-hosted app | 🆓 Free |
| Anthropic Claude | 💸 ~Pennies per AI query, cached aggressively |
| Your time reading this README | 💸 Sunk cost |

---

## 🗺️ Roadmap

*No promises. No timeline. It's a side project.*

- [ ] Real-time WebSocket price updates
- [ ] Transaction history views
- [ ] Price alerts
- [ ] PostgreSQL support for cloud deployments
- [ ] AI-powered rebalancing suggestions
- [ ] Export portfolio to CSV
- [ ] Cope with market volatility *(stretch goal)*

---

## 📄 License

Personal project. **Not financial advice.** If you make or lose money based on a dashboard you found on GitHub, that's entirely on you. No warranties, express or implied, for your portfolio or your life choices.

---

<p align="center">
  Built with 🤖 AI, ☕ caffeine, and a concerning interest in watching numbers move.<br/>
  ⭐ Star this repo if it helped you feel better about your losses.
</p>

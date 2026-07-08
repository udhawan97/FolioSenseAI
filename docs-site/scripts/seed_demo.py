"""Seed a throwaway SQLite database with a safe demo portfolio for screenshots.

Run against a TEMP database only (set DATABASE_URL to a temp path before calling).
The data here is deliberately fictional — public tickers with invented share counts
and cost bases — so nothing personal is ever captured in a landing-page screenshot.

Usage:
    DATABASE_URL="sqlite:///./_shots/demo.db" python docs-site/scripts/seed_demo.py
"""

import os
import sys

# Make the repo root importable when run from anywhere.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# A fresh, demo-only portfolio: one core ETF, one mega-cap stock, one watchlist item.
DEMO_HOLDINGS = [
    # ticker, shares, avg_cost, is_watchlist, hold_class
    ("VOO", 18.0, 452.10, False, "anchor"),   # core S&P 500 ETF
    ("MSFT", 22.0, 396.40, False, "auto"),     # mega-cap stock
    ("SCHD", 60.0, 27.85, False, "auto"),      # dividend ETF, adds allocation variety
    ("NVDA", 0.0, 0.0, True, "auto"),          # watchlist only (no position)
]


def main() -> int:
    # Import after sys.path is set so the app package resolves.
    from app.database import SessionLocal, engine
    from app import models

    models.Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        # Wipe any prior rows so the seed is deterministic and repeatable.
        db.query(models.Holding).delete()
        db.query(models.Portfolio).delete()
        db.flush()

        portfolio = models.Portfolio(
            id=1, name="Demo Portfolio", description="Demo data only — not a real portfolio"
        )
        db.add(portfolio)
        db.flush()

        for ticker, shares, avg_cost, is_watchlist, hold_class in DEMO_HOLDINGS:
            db.add(
                models.Holding(
                    portfolio_id=portfolio.id,
                    ticker=ticker,
                    shares=shares,
                    avg_cost=avg_cost,
                    is_watchlist=is_watchlist,
                    hold_class=hold_class,
                    is_active=True,
                )
            )
        db.commit()

    print(f"Seeded demo portfolio with {len(DEMO_HOLDINGS)} holdings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

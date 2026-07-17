---
title: Analytics & Risk
description: Performance, risk, exposure, and signal analytics across five sub-tabs.
---

The Analytics tab covers the questions Overview doesn't have room for:

| Sub-tab | What it shows |
| --- | --- |
| Performance | Historical portfolio value, benchmark comparison, drawdown |
| Risk | Volatility, beta, and risk decomposition across holdings |
| Exposure | Sector tilt, concentration, and how "diversified" your portfolio actually is |
| Signals | Aggregated verdict and confidence spectrum across all holdings |
| Market Context | Regime classification and how it's shaping the rest of the analytics |

Charts are rendered with Chart.js and loaded lazily, so the Analytics tab doesn't cost
anything until you actually open it.

## Reading the confidence spectrum

Verdicts aren't binary. A "Hold" with high confidence and a "Hold" with low confidence
mean different things — the confidence spectrum view is where that distinction actually
becomes visible instead of getting flattened into one label.

## Reading exposure

Exposure analytics exist specifically to answer the "is this actually diversified"
question. A portfolio can look balanced by position count and still be one sector-wide
bet — this is the view that will tell you if that's what's happening.

## What your funds cost you

Every fund charges a fee whether or not you ever notice it. The fee view turns each fund's
expense ratio into the number that actually matters: dollars per year, at your position
size, plus what that compounds to over a longer horizon — including the growth those fees
never got to earn.

Two honesty rules apply:

- The long-horizon figure is a **projection under a stated growth assumption**, not a
  forecast. The assumption is printed next to the number.
- A fund whose expense ratio can't be read is listed as **fee unknown**, never charged $0.
  Individual stocks don't carry an expense ratio at all, so they're left out of the fee
  math rather than counted as free.

## Do your ETFs own the same thing?

Holding three funds isn't diversification if they hold the same companies. The overlap view
compares each pair of your ETFs and shows what they share.

It compares each fund's **top 10 published holdings** — that's what's freely available, and
the view says so rather than implying it has seen the full book. Two S&P-heavy funds will
show a high overlap; that reading is real, but it's a floor, not the whole picture.

## What your holdings pay you

The income view is the other side of holding: not what your positions are worth, but what
they pay *you*. It turns each holding's forward dividend rate into annual cash at your
position size, totals it, and shows the blended yield across the holdings that actually pay.

Holdings that pay nothing are named, never counted as $0 income padding the coverage. Each
payer shows its yield on today's price, and an **ex-dividend heads-up** appears when a
payment's cutoff date is near — the date by which you need to own the shares to collect the
next one. A per-share dividend larger than the share price is rejected as bad data rather
than trusted.

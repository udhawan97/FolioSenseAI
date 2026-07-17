---
title: News & Market Context
description: Headlines for your holdings and a live view of what the broader market is doing.
---

## News

The News tab fetches grouped headlines for every ticker you hold or watch, deduplicated
and cached so refreshing the page doesn't mean re-fetching everything. With Claude
connected, the tab can also generate portfolio-level **news themes** — a synthesized read
across headlines rather than a flat list.

## Straight from the filings

Under the headlines sits the same news with the commentary removed: what your companies
actually told the SEC. FolioOrb reads EDGAR directly — material events (8-K), quarterly and
annual reports (10-Q, 10-K), and proxy statements — and links each one to the source
document on `sec.gov`. No key, no account, no middleman: filings are public record.

Only operating companies file with the SEC. Funds, crypto, and most foreign listings have
no filing record at all, so they're named as non-filers rather than displayed as companies
that happened to file nothing. When a recent filing lands within a few days of a price move,
it also shows up as a possible catalyst in that holding's move explanation.

Filings need no Claude key — the timeline works the same on Local Intelligence.

## Market context

Alongside your holdings, FolioOrb pulls:

- Live quotes and historical prices
- US market open/closed status
- Major world market indices
- The **US Treasury yield curve** — the 2s10s and 3m10y spreads, straight from Treasury's
  daily par-yield file
- **Where the VIX sits in its own five-year range**, which says more than the number alone

This is the context that feeds the market regime classification shown on Overview and
used throughout Analytics and the verdict engine.

An **inverted curve** — 10-year yields below 2-year — is the bond market pricing cuts ahead,
and it earns its own line in the backdrop. It's also one of the few signals allowed to shift
the verdict engine's weights toward quality and away from momentum. A flat, normal, or steep
curve is reported and left at that: the evidence doesn't support reading more into it.

If the curve can't be reached, it says so and the rest of the backdrop carries on.

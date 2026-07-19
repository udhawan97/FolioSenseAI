"""Tests for the portfolio switcher's stale-while-revalidate cache.

Static-assertion style, like tests/test_dividend_calendar_ui.py.

Switching portfolios reloads the page — deliberately, because a reload is what
guarantees no in-memory cache leaks one portfolio's data into another. The list
of portfolios lived only in memory, so every switch threw it away and the
trigger fell back to the word "Portfolio" until a fresh fetch landed. That beat
is what makes rapid switching feel broken, and it is what this cache removes.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js() -> str:
    return (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")


def _switcher() -> str:
    js = _js()
    assert "async function loadPortfolios" in js
    return js.split("// ── Portfolio switcher")[1][:6000]


def test_the_list_is_persisted_under_its_own_key():
    # Not keyed per portfolio the way the value cache is — this *is* the list of
    # them, so one global entry is correct.
    js = _js()
    assert 'PORTFOLIO_LIST_KEY = "folioorb-portfolios-v1"' in js
    assert "folioorb-" in js  # shares the app-wide localStorage prefix


def test_the_triad_mirrors_the_portfolio_value_cache():
    js = _js()
    for name in (
        "function persistPortfolioList",
        "function readPortfolioList",
        "function hydratePortfolioSwitcherFromCache",
    ):
        assert name in js, f"missing {name}"


def test_the_switcher_paints_from_cache_before_the_fetch():
    # Order matters: hydrate first so the correct name is on screen in the first
    # frame after a reload, then let the network reconcile.
    init = _js().split("function initPortfolioSwitcher")[1][:1200]
    hydrate = init.index("hydratePortfolioSwitcherFromCache();")
    fetch = init.index("loadPortfolios();")
    assert hydrate < fetch, "the cache must paint before the fetch is issued"


def test_a_successful_fetch_refreshes_the_cache():
    body = _switcher().split("async function loadPortfolios")[1][:800]
    assert "persistPortfolioList(_portfolios)" in body


def test_a_malformed_entry_is_rejected_rather_than_rendered():
    # A half-written or older-format entry must not reach the renderer, which
    # would paint "undefined" into the trigger.
    body = _switcher().split("function readPortfolioList")[1][:700]
    assert "Array.isArray(parsed)" in body
    assert "Number.isFinite(p.id)" in body
    assert 'typeof p.name === "string"' in body


def test_creating_a_portfolio_seeds_the_cache_before_reloading():
    # The new portfolio is the one name the switcher could not paint on the
    # first frame, because the cached list predates it.
    body = _js().split("async function createNewPortfolio")[1][:1200]
    seed = body.index("persistPortfolioList(")
    switch = body.index("switchPortfolio(data.id)")
    assert seed < switch, "seed the cache before the reload, not after"


def test_the_deleted_portfolio_fallback_still_runs():
    # A cached entry for a portfolio deleted in another session is safe only
    # because picking it reloads and this path re-scopes to a live one. It must
    # survive the caching change.
    body = _switcher().split("async function loadPortfolios")[1][:900]
    assert "p.id === activePortfolioId" in body
    assert "location.reload()" in body


def test_the_dashboard_script_was_cache_busted():
    # Editing dashboard.js without bumping its ?v= serves users the stale file.
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    assert "dashboard.js?v=99" not in html
    assert "dashboard.js?v=100" in html

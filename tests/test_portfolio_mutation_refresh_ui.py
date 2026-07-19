"""Portfolio mutations must not leave stale holdings in dashboard analytics."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _function_body(js: str, name: str, next_name: str) -> str:
    start = js.index(f"function {name}(")
    end = js.index(f"function {next_name}(", start)
    return js[start:end]


def test_holding_delete_forces_a_post_mutation_portfolio_fetch():
    js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")

    refresh = _function_body(js, "refreshDashboardData", "refreshData")
    mutation_refresh = _function_body(
        js, "refreshPortfolioMutationInBackground", "forceRefreshEverything"
    )
    remove = _function_body(js, "removeHolding", "removeTrade")

    assert "forcePortfolioValue" in refresh
    assert "loadPortfolioValueAfterMutation()" in refresh
    assert "forcePortfolioValue: true" in mutation_refresh
    assert "latestHoldings = latestHoldings.filter" in remove
    assert "renderHoldings()" in remove
    assert "refreshPortfolioMutationInBackground()" in remove


def test_post_mutation_loader_waits_out_any_pre_delete_request():
    js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")

    helper = _function_body(
        js, "loadPortfolioValueAfterMutation", "refreshDashboardData"
    )
    assert "_portfolioValuePromise" in helper
    assert "await inFlight" in helper
    assert "return loadPortfolioValue()" in helper

"""Tests for insider activity (SEC Form 4)."""
from datetime import date, timedelta

import pytest

from app.services import insider_activity
from app.services.insider_activity import (
    _classify,
    _parse_form4,
    _raw_doc_url,
    _summarize,
    get_insider_activity,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test starts and ends with an empty per-ticker activity cache."""
    insider_activity.get_insider_activity.cache_clear()
    yield
    insider_activity.get_insider_activity.cache_clear()


def _form4_xml(
    *,
    code: str = "P",
    shares: str = "1000",
    price: str = "150.00",
    acquired: str = "A",
    owner: str = "Doe Jane",
    officer: bool = True,
    title: str = "Chief Financial Officer",
    tx_date: str = "2026-07-01",
) -> str:
    """Shaped like the live filing (verified 2026-07-17): values nest in <value>."""
    relationship = (
        f"<isOfficer>true</isOfficer><officerTitle>{title}</officerTitle>"
        if officer
        else "<isDirector>true</isDirector>"
    )
    price_el = (
        f"<transactionPricePerShare><value>{price}</value></transactionPricePerShare>"
        if price
        else '<transactionPricePerShare><footnoteId id="F1"/></transactionPricePerShare>'
    )
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <schemaVersion>X0609</schemaVersion>
  <documentType>4</documentType>
  <periodOfReport>{tx_date}</periodOfReport>
  <issuer><issuerCik>0000320193</issuerCik><issuerTradingSymbol>AAPL</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>{owner}</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>{relationship}</reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>{tx_date}</value></transactionDate>
      <transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>{shares}</value></transactionShares>
        {price_el}
        <transactionAcquiredDisposedCode><value>{acquired}</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


# --- parsing one filing ---


def test_parse_reads_an_open_market_buy():
    rows = _parse_form4(_form4_xml(code="P"))
    assert len(rows) == 1
    tx = rows[0]
    assert tx["owner"] == "Doe Jane"
    assert tx["role"] == "Chief Financial Officer"
    assert tx["code"] == "P"
    assert tx["date"] == "2026-07-01"
    assert tx["shares"] == 1000.0
    assert tx["price"] == 150.0


def test_parse_reads_a_director_without_a_title():
    rows = _parse_form4(_form4_xml(officer=False))
    assert rows[0]["role"] == "Director"


def test_parse_accepts_numeric_booleans_for_roles():
    # SEC schema allows both "true" and "1" — NVIDIA's live filings use "1"
    # (caught live 2026-07-17: directors rendered with no role).
    xml = _form4_xml(officer=False).replace(
        "<isDirector>true</isDirector>", "<isDirector>1</isDirector>"
    )
    assert _parse_form4(xml)[0]["role"] == "Director"


def test_parse_survives_a_missing_price():
    # Option exercises often carry only a footnote where the price would be.
    rows = _parse_form4(_form4_xml(code="M", price=""))
    assert rows[0]["price"] is None
    assert rows[0]["shares"] == 1000.0


def test_parse_returns_nothing_for_garbage():
    assert not _parse_form4("not xml")
    assert not _parse_form4("")


def test_parse_refuses_documents_carrying_entity_declarations():
    hostile = _form4_xml().replace(
        '<?xml version="1.0"?>',
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY boom "aaaa">]>',
    )
    assert not _parse_form4(hostile)


def test_parse_refuses_a_doctype_hidden_past_any_fixed_head_window():
    # A comment can legally pad the prolog, pushing the DOCTYPE arbitrarily
    # deep — the guard must scan the whole document, not a prefix.
    hostile = _form4_xml().replace(
        '<?xml version="1.0"?>',
        '<?xml version="1.0"?><!-- ' + "x" * 4096 + " -->"
        '<!DOCTYPE x [<!ENTITY boom "aaaa">]>',
    )
    assert not _parse_form4(hostile)


def test_parse_ignores_filings_with_no_common_stock_transactions():
    xml = """<?xml version="1.0"?>
<ownershipDocument><documentType>4</documentType>
  <reportingOwner><reportingOwnerId><rptOwnerName>X</rptOwnerName></reportingOwnerId>
  <reportingOwnerRelationship><isDirector>true</isDirector></reportingOwnerRelationship></reportingOwner>
</ownershipDocument>"""
    assert not _parse_form4(xml)


# --- classification: only open-market trades carry conviction ---


def test_open_market_buy_and_sale_are_the_signal():
    assert _classify("P")[0] == "buy"
    assert _classify("S")[0] == "sell"


def test_compensation_plumbing_is_not_a_signal():
    # M = option exercise, F = tax withholding, G = gift, A = grant.
    for code in ("M", "F", "G", "A"):
        assert _classify(code)[0] == "other"


def test_every_code_gets_a_human_label():
    assert "buy" in _classify("P")[1].lower()
    assert _classify("ZZ")[1]  # unknown codes still label as something


# --- the viewer URL hides the machine-readable document ---


def test_raw_doc_url_strips_the_xsl_viewer_prefix():
    base = "https://www.sec.gov/Archives/edgar/data/320193/000114036126025622"
    viewer = f"{base}/xslF345X06/form4.xml"
    raw = f"{base}/form4.xml"
    assert _raw_doc_url(viewer) == raw


def test_raw_doc_url_leaves_plain_urls_alone():
    plain = "https://www.sec.gov/Archives/edgar/data/1/2/form4.xml"
    assert _raw_doc_url(plain) == plain


# --- summarizing a window ---


def _tx(code: str, days_ago: int, shares=100.0, price=10.0, owner="A B"):
    return {
        "date": (date.today() - timedelta(days=days_ago)).isoformat(),
        "owner": owner,
        "role": "Officer",
        "code": code,
        "shares": shares,
        "price": price,
        "url": "https://www.sec.gov/x",
    }


def test_summary_counts_only_window_and_only_conviction_trades():
    txs = [
        _tx("P", 5),
        _tx("S", 10),
        _tx("S", 20),
        _tx("M", 3),      # plumbing: listed but not counted
        _tx("P", 120),    # outside the 90-day window entirely
    ]
    s = _summarize(txs, window_days=90)
    assert s["buys"] == 1
    assert s["sells"] == 2
    assert len(s["transactions"]) == 4  # the stale one is dropped, plumbing kept


def test_summary_totals_dollar_values_only_when_price_is_known():
    txs = [_tx("P", 5, shares=100, price=10.0), _tx("P", 6, shares=50, price=None)]
    s = _summarize(txs, window_days=90)
    assert s["bought_value"] == 1000.0  # priceless rows never fake a $0


def test_summary_of_nothing():
    s = _summarize([], window_days=90)
    assert s["buys"] == 0
    assert s["sells"] == 0
    assert not s["transactions"]


# --- the public interface ---


def _wire(monkeypatch, *, filings, docs):
    monkeypatch.setattr(
        insider_activity, "get_recent_filings", lambda t, **_k: filings
    )
    monkeypatch.setattr(insider_activity, "fetch_filing_document", docs.get)


_FILING = {
    "form": "4",
    "label": "Insider transaction (Form 4)",
    "filed_at": "2026-07-10",
    "items": "",
    "url": (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000114036126025622/xslF345X06/form4.xml"
    ),
}
_RAW_URL = (
    "https://www.sec.gov/Archives/edgar/data/320193/000114036126025622/form4.xml"
)


def test_activity_for_a_ticker_with_a_recent_buy(monkeypatch):
    _wire(
        monkeypatch,
        filings=[_FILING],
        docs={_RAW_URL: _form4_xml(code="P", tx_date=date.today().isoformat())},
    )
    activity = get_insider_activity("AAPL", force_refresh=True)
    assert activity["data_quality"] == "live"
    assert activity["buys"] == 1
    assert activity["transactions"][0]["owner"] == "Doe Jane"
    # Every transaction links back to the human-readable filing.
    assert activity["transactions"][0]["url"].startswith("https://www.sec.gov/")


def test_activity_for_a_non_filer_is_an_honest_empty(monkeypatch):
    _wire(monkeypatch, filings=[], docs={})
    activity = get_insider_activity("VOO", force_refresh=True)
    assert activity["data_quality"] == "live"
    assert activity["buys"] == 0
    assert not activity["transactions"]


def test_activity_when_edgar_is_unreachable(monkeypatch):
    def _boom(t, **_k):
        raise RuntimeError("down")

    monkeypatch.setattr(insider_activity, "get_recent_filings", _boom)
    activity = get_insider_activity("AAPL", force_refresh=True)
    assert activity["data_quality"] == "unavailable"
    assert not activity["transactions"]


def test_activity_is_served_from_cache(monkeypatch):
    calls: list[str] = []

    def _counted(t, **_k):
        calls.append(t)
        return [_FILING]

    monkeypatch.setattr(insider_activity, "get_recent_filings", _counted)
    monkeypatch.setattr(
        insider_activity, "fetch_filing_document", lambda url: _form4_xml()
    )
    get_insider_activity("AAPL", force_refresh=True)
    get_insider_activity("AAPL")
    assert len(calls) == 1


def test_activity_skips_documents_that_fail_to_fetch(monkeypatch):
    _wire(monkeypatch, filings=[_FILING], docs={})  # doc fetch returns None
    activity = get_insider_activity("AAPL", force_refresh=True)
    assert activity["data_quality"] == "live"
    assert not activity["transactions"]

"""Tests for the US Treasury par yield curve source."""
from datetime import date

from app.services.treasury_yield_curve import (
    _classify_curve,
    _compute_spreads,
    _fetch_curve_xml,
    _parse_curve_xml,
    get_yield_curve,
)

# Trimmed from the real feed (home.treasury.gov daily_treasury_yield_curve).
# Two entries, deliberately out of date order, to prove newest-wins.
_XML = """<?xml version="1.0" encoding="utf-8" standalone="yes" ?>
<feed xml:base="https://home.treasury.gov/x" xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" xmlns="http://www.w3.org/2005/Atom">
<entry><content type="application/xml"><m:properties>
<d:Id m:type="Edm.Int32">274</d:Id>
<d:NEW_DATE m:type="Edm.DateTime">2026-07-16T00:00:00</d:NEW_DATE>
<d:BC_1MONTH m:type="Edm.Double">3.76</d:BC_1MONTH>
<d:BC_3MONTH m:type="Edm.Double">3.84</d:BC_3MONTH>
<d:BC_6MONTH m:type="Edm.Double">3.94</d:BC_6MONTH>
<d:BC_1YEAR m:type="Edm.Double">3.99</d:BC_1YEAR>
<d:BC_2YEAR m:type="Edm.Double">4.16</d:BC_2YEAR>
<d:BC_5YEAR m:type="Edm.Double">4.28</d:BC_5YEAR>
<d:BC_10YEAR m:type="Edm.Double">4.57</d:BC_10YEAR>
<d:BC_30YEAR m:type="Edm.Double">5.09</d:BC_30YEAR>
</m:properties></content></entry>
<entry><content type="application/xml"><m:properties>
<d:Id m:type="Edm.Int32">273</d:Id>
<d:NEW_DATE m:type="Edm.DateTime">2026-07-15T00:00:00</d:NEW_DATE>
<d:BC_1MONTH m:type="Edm.Double">3.70</d:BC_1MONTH>
<d:BC_3MONTH m:type="Edm.Double">3.80</d:BC_3MONTH>
<d:BC_2YEAR m:type="Edm.Double">4.10</d:BC_2YEAR>
<d:BC_10YEAR m:type="Edm.Double">4.50</d:BC_10YEAR>
</m:properties></content></entry>
</feed>"""


def test_parse_picks_newest_entry_regardless_of_document_order():
    curve = _parse_curve_xml(_XML)
    assert curve["as_of"] == "2026-07-16"
    assert curve["tenors"]["2yr"] == 4.16
    assert curve["tenors"]["10yr"] == 4.57


def test_parse_reads_full_tenor_ladder():
    curve = _parse_curve_xml(_XML)
    assert curve["tenors"]["1mo"] == 3.76
    assert curve["tenors"]["3mo"] == 3.84
    assert curve["tenors"]["30yr"] == 5.09


def test_parse_omits_tenors_absent_from_the_feed():
    xml = _XML.replace('<d:BC_2YEAR m:type="Edm.Double">4.16</d:BC_2YEAR>', "")
    curve = _parse_curve_xml(xml)
    assert "2yr" not in curve["tenors"]
    assert curve["tenors"]["10yr"] == 4.57


def test_parse_skips_entries_with_unreadable_values():
    xml = _XML.replace(">4.57<", ">n/a<")
    curve = _parse_curve_xml(xml)
    assert "10yr" not in curve["tenors"]


def test_parse_returns_none_for_garbage():
    assert _parse_curve_xml("not xml at all") is None


def test_parse_returns_none_when_feed_has_no_entries():
    assert _parse_curve_xml('<feed xmlns="http://www.w3.org/2005/Atom"></feed>') is None


def test_spreads_are_basis_points():
    spreads = _compute_spreads({"3mo": 3.84, "2yr": 4.16, "10yr": 4.57})
    assert spreads["spread_2s10s"] == 41.0
    assert spreads["spread_3m10y"] == 73.0


def test_spreads_are_none_when_a_leg_is_missing():
    spreads = _compute_spreads({"10yr": 4.57})
    assert spreads["spread_2s10s"] is None
    assert spreads["spread_3m10y"] is None


def test_classify_inverted_when_tens_below_twos():
    assert _classify_curve(-45.0) == "inverted"


def test_classify_flat_inside_the_noise_band():
    assert _classify_curve(10.0) == "flat"


def test_classify_normal():
    assert _classify_curve(41.0) == "normal"


def test_classify_steep():
    assert _classify_curve(180.0) == "steep"


def test_classify_unknown_without_a_spread():
    assert _classify_curve(None) == "unknown"


def test_parse_refuses_documents_carrying_entity_declarations():
    # stdlib ElementTree really does expand internal entities (the billion-laughs
    # class of payload). The Treasury feed never declares a DTD, so refusing one
    # outright costs nothing and removes the whole attack class. This payload is
    # otherwise a valid, parseable curve — only the DTD should disqualify it.
    hostile = _XML.replace(
        '<?xml version="1.0" encoding="utf-8" standalone="yes" ?>',
        '<?xml version="1.0" encoding="utf-8" ?>\n'
        '<!DOCTYPE feed [<!ENTITY boom "aaaaaaaaaa">]>',
    )
    assert _parse_curve_xml(hostile) is None


def test_fetch_falls_back_to_last_year_when_the_new_year_has_no_data(monkeypatch):
    # On Jan 1 the current year's feed exists but carries no business days yet.
    empty = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    requested: list[int] = []

    class _Resp:
        def __init__(self, text):
            self.status_code = 200
            self.text = text

    def _fake_get(url, **_kwargs):
        year = int(url.rsplit("=", 1)[1])
        requested.append(year)
        return _Resp(empty if year == date.today().year else _XML)

    monkeypatch.setattr("requests.get", _fake_get)
    xml_text = _fetch_curve_xml()
    assert xml_text == _XML
    assert requested == [date.today().year, date.today().year - 1]


def test_fetch_does_not_ask_for_last_year_when_this_year_has_data(monkeypatch):
    requested: list[int] = []

    class _Resp:
        status_code = 200
        text = _XML

    def _fake_get(url, **_kwargs):
        requested.append(int(url.rsplit("=", 1)[1]))
        return _Resp()

    monkeypatch.setattr("requests.get", _fake_get)
    assert _fetch_curve_xml() == _XML
    assert requested == [date.today().year]


def test_get_yield_curve_reports_live_curve(monkeypatch):
    monkeypatch.setattr(
        "app.services.treasury_yield_curve._fetch_curve_xml", lambda: _XML
    )
    curve = get_yield_curve(force_refresh=True)
    assert curve["data_quality"] == "live"
    assert curve["curve_state"] == "normal"
    assert curve["inverted"] is False
    assert curve["spread_2s10s"] == 41.0
    assert curve["as_of"] == "2026-07-16"


def test_get_yield_curve_degrades_honestly_when_offline(monkeypatch):
    monkeypatch.setattr(
        "app.services.treasury_yield_curve._fetch_curve_xml", lambda: None
    )
    curve = get_yield_curve(force_refresh=True)
    assert curve["data_quality"] == "unavailable"
    assert curve["curve_state"] == "unknown"
    assert curve["inverted"] is None
    assert curve["spread_2s10s"] is None
    assert curve["tenors"] == {}


def test_get_yield_curve_flags_inversion(monkeypatch):
    inverted = _XML.replace(">4.57<", ">3.80<")  # 10yr below 2yr
    monkeypatch.setattr(
        "app.services.treasury_yield_curve._fetch_curve_xml", lambda: inverted
    )
    curve = get_yield_curve(force_refresh=True)
    assert curve["inverted"] is True
    assert curve["curve_state"] == "inverted"
    assert curve["spread_2s10s"] == -36.0


def test_get_yield_curve_serves_cached_value_within_the_day(monkeypatch):
    monkeypatch.setattr(
        "app.services.treasury_yield_curve._fetch_curve_xml", lambda: _XML
    )
    get_yield_curve(force_refresh=True)

    def _boom():
        raise AssertionError("should not refetch within the same day")

    monkeypatch.setattr("app.services.treasury_yield_curve._fetch_curve_xml", _boom)
    curve = get_yield_curve()
    assert curve["spread_2s10s"] == 41.0

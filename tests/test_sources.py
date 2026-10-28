import pytest

from iegrid.fetch import parse_last_modified, pdf_links
from iegrid.sources import SOURCES, classify

# The links as they were on both pages on 28 Oct 2026.
CURRENT = {
    "https://cms.eirgrid.ie/sites/default/files/publications/TSO-Contracted-Wind-Report-05-08-2026.pdf":
        "eirgrid.tso_contracted_wind",
    "https://cms.eirgrid.ie/sites/default/files/publications/TSO-Contracted-Non-Wind-Report-05-08-2026.pdf":
        "eirgrid.tso_contracted_nonwind",
    "https://media.esbnetworks.ie/media/docs/default-source/publications/"
    "renewable-distribution-connected-generation_summary-report_01jul26.pdf?sfvrsn=4ba9191a_27":
        "esb.renewable_summary",
    "https://media.esbnetworks.ie/media/docs/default-source/publications/"
    "dso-contracted-renewable-generators_doc-300424-hxx_accessible_q2_2026.pdf?sfvrsn=5e5bb2f4_26":
        "esb.dso_contracted_renewable",
    "https://media.esbnetworks.ie/media/docs/default-source/publications/"
    "dso-energised-renewable-generators_doc-300424-hxv_accessible_q2_2026.pdf?sfvrsn=19be3394_29":
        "esb.dso_energised_renewable",
    "https://media.esbnetworks.ie/media/docs/default-source/publications/"
    "dso-contracted-non-renewable-generators_doc-300424-hxy_accessible_q2-2026.pdf?sfvrsn=8e1d4db4_29":
        "esb.dso_contracted_nonrenewable",
    "https://media.esbnetworks.ie/media/docs/default-source/publications/"
    "dso-energised-non-renewable-generators_doc-300424-hxw_accessible_q2_2026.pdf?sfvrsn=9d5db900_26":
        "esb.dso_energised_nonrenewable",
    "https://media.esbnetworks.ie/media/docs/default-source/publications/"
    "dso-live-connection-assessments_doc-300424-hxz_accessible_q2-2026.pdf?sfvrsn=4202a9ff_27":
        "esb.dso_live_assessments",
}


@pytest.mark.parametrize("url, source_id", CURRENT.items())
def test_current_links_classify(url, source_id):
    assert classify(url).source_id == source_id


def test_every_source_has_a_current_link():
    assert set(CURRENT.values()) == {s.source_id for s in SOURCES}


def test_older_names_still_classify():
    # 2024 ESB names had no doc number
    url = "https://esbnetworks.ie/docs/default-source/publications/dso-contracted-renewable-generators-q3-2024.pdf"
    assert classify(url).source_id == "esb.dso_contracted_renewable"


def test_unknown_pdf_is_not_classified():
    assert classify("https://cms.eirgrid.ie/x/Data-Centre-Customer-Application-Form-May-2026.pdf") is None


def test_pdf_links_absolute_and_deduped():
    html = ('<a href="/docs/a.pdf">a</a> <a href=\'https://x.ie/b.pdf?v=1&amp;q=2\'>b</a>'
            '<a href="/docs/a.pdf">again</a> <a href="/page.html">no</a>')
    assert pdf_links("https://www.esbnetworks.ie/services/x", html) == [
        "https://www.esbnetworks.ie/docs/a.pdf",
        "https://x.ie/b.pdf?v=1&q=2",
    ]


def test_last_modified():
    dt = parse_last_modified("Mon, 10 Aug 2026 14:02:52 GMT")
    assert dt.isoformat() == "2026-08-10T14:02:52+00:00"
    assert parse_last_modified(None) is None
    assert parse_last_modified("not a date") is None

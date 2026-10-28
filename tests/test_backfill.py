from datetime import UTC, date, datetime

import pytest

from iegrid import backfill
from iegrid.sources import classify_archived
from tests.conftest import make_pdf

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
LM = datetime(2022, 3, 31, 14, 53, 55, tzinfo=UTC)
CAPTURED = datetime(2022, 3, 31, 19, 40, 21, tzinfo=UTC)
E = "https://www.eirgridgroup.com/site-files/library/EirGrid/"
C = "https://cms.eirgrid.ie/sites/default/files/publications/"
ESB = "https://esbnetworks.ie/docs/default-source/publications/"


@pytest.mark.parametrize("url, source_id", [
    (E + "Connected%20Wind%20Report%2012Jan10.pdf", "eirgrid.tso_dso_connected_wind"),
    (E + "Connected%20(Other%20Types%20of%20Generators)_14092009.pdf",
     "eirgrid.tso_dso_connected_nonwind"),
    (E + "Connected%20(Non-Wind%20Generators)%20-%2031%20Dec%202011.pdf",
     "eirgrid.tso_dso_connected_nonwind"),
    (E + "Contracted%20Wind%20Farms%20-%2030%20Sep%202011.pdf", "eirgrid.tso_dso_contracted_wind"),
    (E + "Connected%20TSO%20Wind%20Farms%2016%20Nov%2012.pdf", "eirgrid.tso_connected_wind"),
    (E + "ConnectedTSO(Non-Wind)Generators-18thSept2015.pdf", "eirgrid.tso_connected_nonwind"),
    (E + "contractedtso(non%20wind)generators18july2013.pdf", "eirgrid.tso_contracted_nonwind"),
    (E + "Contracted%20(Wind)%2009042009.pdf", "eirgrid.tso_dso_contracted_wind"),
    (E + "TSO-Wind-Contracted-31.03.2022.pdf", "eirgrid.tso_contracted_wind"),
    (E + "tso_nonwind_contracted_14.12.2018.pdf", "eirgrid.tso_contracted_nonwind"),
    (C + "Revised-TSO-Wind-Contracted-23.08.2021.pdf", "eirgrid.tso_contracted_wind"),
    (C + "Contracted-TSO-Non-Wind-Generators-21-12-2023.pdf", "eirgrid.tso_contracted_nonwind"),
    (C + "TSO-Contracted-Wind-Report-17-09-2025.pdf", "eirgrid.tso_contracted_wind"),
    (E + "TSO-Connected-Renewables-01-Nov-2017.pdf", "eirgrid.tso_connected_renewable"),
    (C + "TSO-Connected-Non-Renewable-Generation(1).pdf", "eirgrid.tso_connected_nonrenewable"),
    (ESB + "dso-contracted-wind-generators-q4-2022.pdf", "esb.dso_contracted_wind"),
    (ESB + "dso-contracted-non-wind-generators-q4-2020.pdf", "esb.dso_contracted_nonwind"),
    (ESB + "dso-connected-energised-wind-generators-sept-2017.pdf", "esb.dso_energised_wind"),
    (ESB + "dso-connected-energised-non-wind-generators-q1-2023.pdf", "esb.dso_energised_nonwind"),
    (ESB + "dso-contracted-renewable-generators-q3-2024.pdf", "esb.dso_contracted_renewable"),
    (ESB + "renewable-distribution-connected-generation---summary-report_31dec23.pdf",
     "esb.renewable_summary"),
    (ESB + "dso-live-connection-assessments-q4-2023.pdf", "esb.dso_live_assessments"),
])
def test_archived_names(url, source_id):
    assert classify_archived(url) == source_id


@pytest.mark.parametrize("url", [
    E + "Appendix-B-List-of-Generators-in-ECP-2.2-Constraint-Forecast.pdf",
    C + "cp1186-agannygal-ennis-and-connected-stations-aas-determination.pdf",
    ESB + "non-firm-access-for-distribution-connected-distributed-generators-guide.pdf",
    E + "North-South-Project-Summary-Report-20-October-2015_Final.pdf",
    E + "TUoS-Agreement-Application-Form-Distribution-Connected_Oct-2015.pdf",
])
def test_not_lists(url):
    assert classify_archived(url) is None


def test_candidates_one_per_digest_earliest_capture():
    url = E + "TSO-Wind-Contracted-31.03.2022.pdf"
    rows = [["20220601000000", url, "AAA", "application/pdf"],
            ["20220331194021", url, "AAA", "application/pdf"],
            ["20220701000000", url, "BBB", "application/pdf"],   # re-issued with new bytes
            ["20220331194021", E + "page.html", "CCC", "text/html"],
            ["20220331194021", E + "Annual-Report-2021.pdf", "DDD", "application/pdf"]]
    got = backfill.candidates(rows)
    assert [(c.digest, c.capture_ts) for c in got] == [("AAA", "20220331194021"),
                                                        ("BBB", "20220701000000")]


def cap(content, lm=LM):
    return lambda c: backfill.Capture(content, lm, CAPTURED)


def cand(name="TSO-Wind-Contracted-31.03.2022.pdf", digest="AAA"):
    url = E + name
    return backfill.Candidate(classify_archived(url), url, "20220331194021", digest)


PDF = make_pdf(["Contracted TSO (Wind) Generators", "Correct as of 31/03/2022"])


def test_stored_with_archive_provenance(con, tmp_path):
    outcome, _note, pid = backfill.backfill_one(con, cand(), tmp_path, NOW, cap(PDF))
    assert outcome == "stored" and pid
    row = con.execute("select source_id, url, as_of, published_at, published_at_basis, "
                      "vintage_quality, fetched_from, first_captured_at from publication").fetchone()
    assert row == ("eirgrid.tso_contracted_wind", E + "TSO-Wind-Contracted-31.03.2022.pdf",
                   date(2022, 3, 31), LM, "last-modified", "estimated",
                   "https://web.archive.org/web/20220331194021id_/" + E
                   + "TSO-Wind-Contracted-31.03.2022.pdf", CAPTURED)


def test_same_bytes_again_is_a_duplicate(con, tmp_path):
    backfill.backfill_one(con, cand(), tmp_path, NOW, cap(PDF))
    outcome, note, pid = backfill.backfill_one(con, cand(digest="ZZZ"), tmp_path, NOW, cap(PDF))
    assert outcome == "duplicate" and pid and "publication" in note


@pytest.mark.parametrize("capture, outcome", [
    (cap(make_pdf(["a list with no date"])), "no-as-of"),
    (cap(b"<html>error</html>"), "download-failed"),
    (cap(PDF, lm=None), "no-publish-time"),
])
def test_reasons(con, tmp_path, capture, outcome):
    got, note, pid = backfill.backfill_one(con, cand(), tmp_path, NOW, capture)
    assert got == outcome and note and pid is None
    assert con.execute("select count(*) from publication").fetchone()[0] == 0


def test_download_error_is_a_reason_not_a_crash(con, tmp_path):
    def boom(c):
        raise OSError("timed out")
    assert backfill.backfill_one(con, cand(), tmp_path, NOW, boom)[0] == "download-failed"


def test_run_records_every_edition_and_reruns_skip(con, tmp_path):
    rows = [["20220331194021", E + "TSO-Wind-Contracted-31.03.2022.pdf", "AAA", "application/pdf"],
            ["20220331194021", E + "TSO-NonWind-Contracted-31.03.2022.pdf", "BBB", "application/pdf"],
            ["20220331194021", C + "cp1186-connected-stations.pdf", "CCC", "application/pdf"]]
    contents = {"AAA": PDF, "BBB": make_pdf(["no date here"])}

    def get(c):
        return backfill.Capture(contents[c.digest], LM, CAPTURED)

    s = backfill.run(con, tmp_path, rows_for=lambda p: rows if "eirgridgroup" in p else [],
                     get_capture=get, now=NOW)
    assert {k: len(v) for k, v in s.outcomes.items()} == {"stored": 1, "no-as-of": 1,
                                                          "not-a-list": 1}
    assert con.execute("select count(*) from backfill_found").fetchone()[0] == 3
    # a re-run looks at nothing new; --retry looks again at the one that wasn't final
    assert not backfill.run(con, tmp_path, rows_for=lambda p: rows, get_capture=get,
                            now=NOW).outcomes
    s = backfill.run(con, tmp_path, retry=True, rows_for=lambda p: rows, get_capture=get, now=NOW)
    assert {k: len(v) for k, v in s.outcomes.items()} == {"no-as-of": 1}


def test_index_down_is_reported(con, tmp_path):
    def down(prefix):
        raise OSError("archive index unavailable")
    s = backfill.run(con, tmp_path, rows_for=down, get_capture=cap(PDF), now=NOW)
    assert not s.ok and len(s.outcomes["download-failed"]) == 4


def test_text_date_far_from_the_name_is_refused_with_both_dates(con, tmp_path):
    c = cand("Contracted-TSO-(NonWind)-Generators-22-June-2016.pdf")
    pdf = make_pdf(["TSO Non-Wind Generators - Contracted", "it. Correct as of the 31th of May 2015"])
    outcome, note, pid = backfill.backfill_one(con, c, tmp_path, NOW, cap(pdf))
    assert outcome == "no-as-of" and pid is None
    assert "2015-05-31" in note and "2016-06-22" in note


def test_wrong_file_name_overruled_when_last_modified_agrees(con, tmp_path):
    # "contracted-tso-non-wind-generators-7-11-2024.pdf" is month-first; the text and the
    # server both say 11 July 2024
    c = cand("Contracted-TSO-Non-Wind-Generators-7-11-2024.pdf")
    pdf = make_pdf(["Correct as of 11 July 2024"])
    lm = datetime(2024, 7, 11, 9, 43, tzinfo=UTC)
    outcome, note, _ = backfill.backfill_one(con, c, tmp_path, NOW, cap(pdf, lm=lm))
    assert outcome == "stored" and "Last-Modified 2024-07-11 agrees" in note
    assert con.execute("select as_of from publication").fetchone()[0] == date(2024, 7, 11)


def test_last_modified_cannot_rescue_a_typo(con, tmp_path):
    c = cand("Contracted-TSO-(NonWind)-Generators-22-June-2016.pdf")
    pdf = make_pdf(["it. Correct as of the 31th of May 2015"])
    lm = datetime(2016, 6, 22, 9, 25, tzinfo=UTC)
    assert backfill.backfill_one(con, c, tmp_path, NOW, cap(pdf, lm=lm))[0] == "no-as-of"

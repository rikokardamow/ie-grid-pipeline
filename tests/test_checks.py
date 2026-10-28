from datetime import date

import pytest

from iegrid import ingest
from iegrid.checks import as_of_from_name, check_publications
from tests.test_ingest import NOW, fake_site
from tests.test_sources import CURRENT

# What each current file name says, read by hand on 28 Oct 2026.
EXPECTED = {
    "eirgrid.tso_contracted_wind": date(2026, 8, 5),
    "eirgrid.tso_contracted_nonwind": date(2026, 8, 5),
}


@pytest.mark.parametrize("url, source_id", CURRENT.items())
def test_current_names(url, source_id):
    assert as_of_from_name(url) == EXPECTED.get(source_id, date(2026, 7, 1))


def test_q4_rolls_to_next_year():
    assert as_of_from_name("https://x/dso-contracted-renewable-generators-q4-2024.pdf") == date(2025, 1, 1)


def test_unknown_name():
    assert as_of_from_name("https://x/TSO-NonWind-Contracted-31.03.2022.pdf") is None


def test_tampered_raw_file_fails_hash(con, tmp_path):
    ingest.run(con, tmp_path, *fake_site(), NOW)
    path = con.execute("select raw_path from publication limit 1").fetchone()[0]
    with open(path, "ab") as f:
        f.write(b"x")
    bad = [c for c in check_publications(con) if not c.hash_ok]
    assert len(bad) == 1


def test_recheck_lists_a_no_as_of_reason_that_no_longer_holds(con, tmp_path):
    from iegrid import backfill
    from iegrid.checks import recheck_no_as_of
    from tests.conftest import make_pdf

    url = ("https://esbnetworks.ie/docs/default-source/publications/"
           "dso-live-connection-assessments-q3-2024.pdf")
    c = backfill.Candidate("esb.dso_live_assessments", url, "20241101000000", "DIG1")
    backfill.record(con, c, "no-as-of", "no readable as-of phrase in the text", NOW)
    (tmp_path / "DIG1.pdf").write_bytes(make_pdf(["Information correct: 01Oct 2024 Rev. 2"]))
    assert recheck_no_as_of(con, cache=tmp_path) == [
        "dso-live-connection-assessments-q3-2024.pdf: the reader now finds 2024-10-01"]
    (tmp_path / "DIG1.pdf").write_bytes(make_pdf(["Information correct: Rev. 0"]))
    assert recheck_no_as_of(con, cache=tmp_path) == []

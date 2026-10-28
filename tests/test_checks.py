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

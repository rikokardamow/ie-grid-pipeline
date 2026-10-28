import re
from datetime import UTC, date, datetime
from pathlib import Path

from iegrid import ingest
from iegrid.fetch import Download
from iegrid.sources import EIRGRID_PAGE, ESB_PAGE, SOURCES
from tests.conftest import make_pdf
from tests.test_sources import CURRENT

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
LAST_MOD = datetime(2026, 8, 10, 14, 2, 52, tzinfo=UTC)


def fake_site(as_of="05/08/2026", last_modified=LAST_MOD, extra_links=(), drop=()):
    links = {EIRGRID_PAGE: [], ESB_PAGE: []}
    for url, sid in CURRENT.items():
        if sid in drop:
            continue
        links[EIRGRID_PAGE if sid.startswith("eirgrid") else ESB_PAGE].append(url)
    links[ESB_PAGE].extend(extra_links)
    files = {url: make_pdf([f"{sid} list", f"Correct as of {as_of}"]) for url, sid in CURRENT.items()}

    def page_links(page):
        return links[page]

    def download(url):
        return Download(url, files[url], last_modified)

    return page_links, download


def test_first_run_stores_one_row_per_source(con, tmp_path):
    pl, dl = fake_site()
    s = ingest.run(con, tmp_path, pl, dl, NOW)
    assert s.ok and len(s.stored) == len(SOURCES) and not s.unchanged
    rows = con.execute("select source_id, as_of, published_at, published_at_basis, "
                       "vintage_quality, raw_path from publication").fetchall()
    assert {r[0] for r in rows} == {src.source_id for src in SOURCES}
    for sid, as_of, published_at, basis, quality, raw_path in rows:
        assert as_of == date(2026, 8, 5)
        assert published_at == LAST_MOD and basis == "last-modified" and quality == "exact"
        assert Path(raw_path).is_file() and Path(raw_path).parent.name == sid
        assert re.fullmatch(r"2026-08-05-[0-9a-f]{12}\.pdf", Path(raw_path).name)


def test_rerun_adds_zero_rows(con, tmp_path):
    pl, dl = fake_site()
    ingest.run(con, tmp_path, pl, dl, NOW)
    s = ingest.run(con, tmp_path, pl, dl, NOW)
    assert s.ok and not s.stored and len(s.unchanged) == len(SOURCES)
    assert con.execute("select count(*) from publication").fetchone()[0] == len(SOURCES)


def test_new_edition_is_a_new_row_old_one_kept(con, tmp_path):
    ingest.run(con, tmp_path, *fake_site(as_of="17/09/2025"), NOW)
    s = ingest.run(con, tmp_path, *fake_site(as_of="05/08/2026"), NOW)
    assert len(s.stored) == len(SOURCES)
    got = con.execute("select as_of, count(*) from publication group by 1 order by 1").fetchall()
    assert got == [(date(2025, 9, 17), len(SOURCES)), (date(2026, 8, 5), len(SOURCES))]


def test_no_last_modified_is_estimated(con, tmp_path):
    ingest.run(con, tmp_path, *fake_site(last_modified=None), NOW)
    got = con.execute("select distinct published_at, published_at_basis, vintage_quality "
                      "from publication").fetchall()
    assert got == [(NOW, "ingested", "estimated")]


def test_missing_list_and_unknown_link_reported(con, tmp_path):
    extra = "https://www.esbnetworks.ie/docs/new-kind-of-list-q3-2026.pdf"
    s = ingest.run(con, tmp_path,
                   *fake_site(extra_links=[extra], drop={"esb.dso_live_assessments"}), NOW)
    assert not s.ok
    assert s.missing_sources == ["esb.dso_live_assessments"]
    assert s.unknown_links == [extra]
    assert len(s.stored) == len(SOURCES) - 1


def test_file_without_as_of_is_refused(con, tmp_path):
    pl, _ = fake_site()

    def download(url):
        return Download(url, make_pdf(["a list with no date"]), LAST_MOD)

    s = ingest.run(con, tmp_path, pl, download, NOW)
    assert not s.ok and len(s.errors) == len(SOURCES)
    assert con.execute("select count(*) from publication").fetchone()[0] == 0


def test_page_down_reports_and_carries_on(con, tmp_path):
    pl, dl = fake_site()

    def flaky(page):
        if page == EIRGRID_PAGE:
            raise OSError("timed out")
        return pl(page)

    s = ingest.run(con, tmp_path, flaky, dl, NOW)
    assert not s.ok and any("timed out" in e for e in s.errors)
    assert len(s.stored) == 6


def test_store_module_never_updates_or_deletes():
    src = Path(ingest.store.__file__).read_text().lower()
    assert not re.search(r"\b(update|delete)\s", src.split('"""', 2)[2])

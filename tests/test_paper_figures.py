"""Every chart this repository draws is a paper figure: 3.4 or 7.0 in wide, sans-serif type of
6 to 9 pt, a label with its unit on each axis, nothing about the finding on the image, a PDF
with Type 42 fonts, a 300 dpi PNG, and a LaTeX caption with the finding, units, source and
as-of date. The checks are paper_style.lint with axis labels on (docs/FIGURES.md)."""

import json
import re

import matplotlib.pyplot as plt
import pytest

from iegrid import exhibits, readme_charts, store
from iegrid import paper_style as ps

ROOT = store.ROOT
REPORTS = sorted((ROOT / "data" / "reports").glob("*.json"))
DB = ROOT / "data" / "iegrid.duckdb"
needs_report = pytest.mark.skipif(not REPORTS, reason="no weekly report in data/reports")
needs_db = pytest.mark.skipif(not DB.exists(), reason="no store in data/")


@pytest.fixture(scope="module")
def rep():
    return json.loads(REPORTS[-1].read_text())


@needs_report
@pytest.mark.parametrize("name", list(readme_charts.CHARTS))
def test_each_readme_chart_passes_the_paper_lint(rep, name):
    fig = readme_charts.CHARTS[name](rep)
    try:
        assert ps.lint(fig, axis_labels=True) == []
        assert ps.field(fig, "title") and ps.field(fig, "footer").count("Source:") == 1
        assert ps.caption(fig).count("as of ") >= 1
    finally:
        plt.close(fig)


@needs_report
def test_files_are_pdf_png_and_tex_with_type42_fonts_at_300_dpi(rep, tmp_path):
    from PIL import Image

    written = readme_charts.build_all(REPORTS[-1], tmp_path)
    assert {p.name for p in written} == {f"{n}.png" for n in readme_charts.CHARTS}
    for name in readme_charts.CHARTS:
        pdf = (tmp_path / f"{name}.pdf").read_bytes()
        assert pdf.startswith(b"%PDF") and not re.search(rb"/Subtype\s*/Type3", pdf), name
        with Image.open(tmp_path / f"{name}.png") as im:
            assert im.size[0] in (1020, 2100), (name, im.size)
        tex = (tmp_path / f"{name}.tex").read_text()
        assert tex.startswith(ps.MARK) and "\\caption{" in tex and "Source:" in tex
        assert re.search(r"as of \d{4}-\d{2}-\d{2}", tex), name
        assert not (tmp_path / f"{name}.svg").exists()


@needs_report
def test_two_runs_write_the_same_bytes(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    readme_charts.build_all(REPORTS[-1], a)
    readme_charts.build_all(REPORTS[-1], b)
    names = sorted(p.name for p in a.iterdir())
    assert names == sorted(p.name for p in b.iterdir()) and len(names) == 3 * len(
        readme_charts.CHARTS)
    for n in names:
        assert (a / n).read_bytes() == (b / n).read_bytes(), n


@needs_db
@pytest.mark.parametrize("fn", ["publication_lag", "contracted_by_technology", "queue_growth",
                                "queue_flows", "contracted_by_county", "batch_burndown"])
def test_stone_exhibits_pass_the_paper_lint(fn):
    import duckdb

    con = duckdb.connect(str(DB), read_only=True)
    try:
        fig = getattr(exhibits, fn)(con)
    finally:
        con.close()
    try:
        assert ps.lint(fig, axis_labels=True) == []
    finally:
        plt.close(fig)

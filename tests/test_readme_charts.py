"""The README's charts: every image the README embeds exists, and the generator draws
all of them from a report."""

import re
from pathlib import Path

import pytest

from iegrid import readme_charts, store

ROOT = store.ROOT


def test_every_readme_image_exists():
    readme = (ROOT / "README.md").read_text()
    paths = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", readme)
    assert paths, "the README embeds no images"
    missing = [p for p in paths if not (ROOT / p).is_file()]
    assert not missing, missing


def test_readme_charts_are_all_generated():
    names = set(readme_charts.CHARTS)
    readme = (ROOT / "README.md").read_text()
    embedded = {Path(p).stem for p in re.findall(r"!\[[^\]]*\]\((docs/img/[^)]+)\)", readme)}
    assert embedded <= names, embedded - names


def test_generator_draws_every_chart(tmp_path):
    reports = sorted((ROOT / "data" / "reports").glob("*.json"))
    if not reports:
        pytest.skip("no weekly report in data/reports")
    written = readme_charts.build_all(reports[-1], tmp_path)
    assert {p.name for p in written} == {f"{n}.png" for n in readme_charts.CHARTS}
    assert all(p.stat().st_size > 10_000 for p in written)
    # the paper format also writes the vector original and the LaTeX caption beside each PNG
    for n in readme_charts.CHARTS:
        assert (tmp_path / f"{n}.pdf").stat().st_size > 1_000
        assert (tmp_path / f"{n}.tex").read_text().startswith("% Written by paper_style.save")


def test_readme_gives_the_credit_the_images_no_longer_carry():
    """The images carry no credit text (it is in each .tex caption), so the README, which
    embeds only the PNGs, must give it and must not claim the charts do."""
    readme = (ROOT / "README.md").read_text()
    assert "credit lines stay on every chart" not in readme
    for text in ("Supported by EirGrid Group Data", "© ESB Networks", "OpenStreetMap contributors (ODbL)"):
        assert text in readme, text
    # the OSM credit sits next to the two figures that draw OSM data
    for image in ("map.png", "counties.png"):
        after = readme.split(f"docs/img/{image})", 1)[1][:400]
        assert "OpenStreetMap contributors (ODbL)" in after, image
    # every .tex caption names the publisher whose lists it draws
    for n in readme_charts.CHARTS:
        tex = (ROOT / "docs" / "img" / f"{n}.tex").read_text()
        assert "Supported by EirGrid Group Data" in tex or "ESB Networks" in tex, n

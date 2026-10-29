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

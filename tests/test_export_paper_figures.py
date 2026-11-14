"""Tests for export_paper_figures.py. Vendoring: set EXPORTER / the paper_style import if the files moved."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

HERE = Path(__file__).resolve().parent
# Where the exporter may live, relative to this test: beside it, or in a sibling folder.
EXPORTER_CANDIDATES = [
    HERE / "export_paper_figures.py",
    HERE.parent / "export_paper_figures.py",
    HERE.parent / "jobs" / "export_paper_figures.py",
    HERE.parent / "tools" / "export_paper_figures.py",
    HERE.parent / "scripts" / "export_paper_figures.py",
    HERE.parent / "ops" / "export_paper_figures.py",
]

from iegrid import paper_style as ps


# The switches are module globals shared by every test in the session. A repository shim that
# sets them (VENDORING.md, "Restoring the reference rules") may be imported first, so every
# test starts from the shipped permissive defaults; tests that need a switch set it themselves.
_DEFAULT_SWITCHES = {
    "REQUIRE": ("title",), "UNITS": None, "STRICT_DESK": False, "ASOF_ZONES": None,
    "CADENCE_PATTERN": None, "SOURCE_SHAPE": False, "LICENCE_CHECK": None, "SAVE_GUARD": None,
    "LEGACY_PREFIX": None,
}


@pytest.fixture(autouse=True)
def _permissive_defaults(monkeypatch):
    for name, value in _DEFAULT_SWITCHES.items():
        monkeypatch.setattr(ps, name, value)


def _load():
    path = next((p for p in EXPORTER_CANDIDATES if p.exists()), None)
    assert path, f"export_paper_figures.py not found in {EXPORTER_CANDIDATES}"
    spec = importlib.util.spec_from_file_location("export_paper_figures", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def job():
    return _load()


@pytest.fixture(autouse=True)
def _close():
    yield
    import matplotlib.pyplot as plt

    plt.close("all")


def _save(folder, name, title="Demand fell 3 GW in the week", formats=("pdf", "tex")):
    import matplotlib.pyplot as plt

    fig, axes = ps.figure()
    axes[0][0].plot([0, 1, 2], [3, 2, 4])
    ps.frame(fig, title=title, units="GW", source="Grid table 4 (D-1)", asof="2026-11-04",
             ylabel="Demand (GW)", xlabel="Week")
    ps.save(fig, Path(folder) / name, formats=formats)
    plt.close("all")


def test_export_collects_pdf_and_caption_with_unique_safe_names(job, tmp_path):
    a, b = tmp_path / "one", tmp_path / "two"
    _save(a, "monitor")
    _save(b, "monitor")  # the same stem in two folders must not collide
    out = tmp_path / "paper"
    assert job.export(out, [tmp_path], base=tmp_path) == 0
    names = sorted(p.name for p in (out / "figures").glob("*.pdf"))
    assert names == ["one-monitor.pdf", "two-monitor.pdf"]
    tex = (out / "figures" / "two-monitor.tex").read_text()
    assert "{two-monitor.pdf}" in tex and "\\label{fig:two-monitor}" in tex
    assert "monitor.pdf}" not in tex.replace("two-monitor.pdf}", "")
    assert "\\input{figures/one-monitor}" in (out / "figures.tex").read_text()
    assert "\\graphicspath{{figures/}}" in (out / "preamble.tex").read_text()
    assert "\\input{figures}" in (out / "example.tex").read_text()
    manifest = json.loads((out / "MANIFEST.json").read_text())
    assert [m["name"] + ".pdf" for m in manifest] == names and all(not m["problems"] for m in manifest)
    assert manifest[0]["caption"].startswith("Demand fell 3 GW in the week.")
    assert manifest[0]["source"] == "one/monitor.pdf" and manifest[0]["env"] == "figure*"


def test_tag_is_the_nested_folder_and_top_level_is_root(job, tmp_path):
    _save(tmp_path / "docs" / "img", "a")
    _save(tmp_path, "top")
    assert job.export(tmp_path / "paper", [tmp_path], base=tmp_path) == 0
    assert sorted(p.stem for p in (tmp_path / "paper" / "figures").glob("*.pdf")) == ["docs-img-a", "root-top"]


def test_identical_names_from_different_roots_get_a_suffix(job, tmp_path):
    _save(tmp_path / "x" / "y", "f")
    _save(tmp_path / "x-y", "f")  # both tag to x-y
    assert job.export(tmp_path / "paper", [tmp_path], base=tmp_path) == 0
    assert sorted(p.stem for p in (tmp_path / "paper" / "figures").glob("*.pdf")) == ["x-y-f", "x-y-f-2"]


def test_unsafe_stems_are_made_safe(job, tmp_path):
    _save(tmp_path / "d", "my figure (1)")
    assert job.export(tmp_path / "paper", [tmp_path], base=tmp_path) == 0
    (pdf,) = (tmp_path / "paper" / "figures").glob("*.pdf")
    assert job.SAFE_NAME.match(pdf.stem)
    tex = pdf.with_suffix(".tex").read_text()
    assert f"{{{pdf.stem}.pdf}}" in tex


def test_a_pdf_with_type_3_fonts_fails_the_check_and_check_writes_nothing(job, tmp_path):
    _save(tmp_path / "x", "bad")
    pdf = tmp_path / "x" / "bad.pdf"
    pdf.write_bytes(pdf.read_bytes() + b"\n% /Subtype /Type3\n")
    assert job.export(tmp_path / "paper", [tmp_path], check_only=True, base=tmp_path) == 1
    assert not (tmp_path / "paper").exists()
    assert job.export(tmp_path / "paper", [tmp_path], base=tmp_path) == 1  # written, but exit 1


def test_pdf_preflight_problems(job, tmp_path):
    _save(tmp_path, "ok")
    good = tmp_path / "ok.pdf"
    assert job.check_pdf(good) == []
    raw = good.read_bytes()
    bad = tmp_path / "t.pdf"
    bad.write_bytes(raw + b"/Subtype/Type3")
    assert any("Type 3" in p for p in job.check_pdf(bad))
    bad.write_bytes(b"%PDF-1.4\n<< /Type /Font /Subtype /TrueType >>\n")
    assert any("not embedded" in p for p in job.check_pdf(bad))
    bad.write_bytes(raw + b"/Encrypt 5 0 R")
    assert any("encrypted" in p for p in job.check_pdf(bad))
    bad.write_bytes(raw + b" " * (job.MAX_BYTES + 1))
    assert any("MB" in p for p in job.check_pdf(bad))
    bad.write_bytes(b"<html>")
    assert "not a PDF" in job.check_pdf(bad)


def test_a_pdf_without_a_paper_style_caption_is_not_a_paper_figure(job, tmp_path):
    _save(tmp_path / "x", "good")
    (tmp_path / "x" / "report.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "x" / "other.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "x" / "other.tex").write_text("\\begin{figure}\\end{figure}\n")
    assert job.export(tmp_path / "paper", [tmp_path], base=tmp_path) == 0
    assert [p.name for p in (tmp_path / "paper" / "figures").glob("*.pdf")] == ["x-good.pdf"]


def test_hidden_vendored_and_output_folders_are_skipped_unless_named(job, tmp_path):
    _save(tmp_path / "keep", "a")
    _save(tmp_path / ".local" / "private", "b")
    _save(tmp_path / ".venv" / "lib", "c")
    _save(tmp_path / "node_modules" / "pkg", "d")
    assert job.export(tmp_path / "paper", [tmp_path], base=tmp_path) == 0
    assert [p.name for p in (tmp_path / "paper" / "figures").glob("*.pdf")] == ["keep-a.pdf"]
    # a second run must not pick up its own output
    assert job.export(tmp_path / "paper", [tmp_path], base=tmp_path) == 0
    assert [p.name for p in (tmp_path / "paper" / "figures").glob("*.pdf")] == ["keep-a.pdf"]
    # naming a hidden folder as a root includes it
    assert job.export(tmp_path / "paper2", [tmp_path / ".local"], base=tmp_path) == 0
    assert [p.name for p in (tmp_path / "paper2" / "figures").glob("*.pdf")] == ["local-private-b.pdf"]


def test_overlapping_roots_export_each_figure_once(job, tmp_path):
    _save(tmp_path / "x", "a")
    assert job.export(tmp_path / "paper", [tmp_path, tmp_path / "x"], base=tmp_path) == 0
    assert len(list((tmp_path / "paper" / "figures").glob("*.pdf"))) == 1


def test_reexport_removes_figures_that_no_longer_exist_but_keeps_hand_made_files(job, tmp_path):
    src = tmp_path / "x"
    _save(src, "first")
    _save(src, "second")
    out = tmp_path / "paper"
    job.export(out, [src], base=tmp_path)
    (out / "figures" / "mine.pdf").write_bytes(b"%PDF-1.4\n")
    (src / "second.pdf").unlink()
    (src / "second.tex").unlink()
    job.export(out, [src], base=tmp_path)
    assert sorted(p.name for p in (out / "figures").glob("*.pdf")) == ["mine.pdf", "x-first.pdf"]


def test_no_figures_is_a_failure(job, tmp_path):
    assert job.export(tmp_path / "paper", [tmp_path], base=tmp_path) == 1
    assert not (tmp_path / "paper").exists()


def test_main_defaults_and_flags(job, tmp_path, capsys):
    _save(tmp_path / "d", "a")
    assert job.main(["--root", str(tmp_path), "--out", str(tmp_path / "o"), "--repo", str(tmp_path), "--check"]) == 0
    assert not (tmp_path / "o").exists() and "1 figures, 0 with problems" in capsys.readouterr().out
    assert job.main(["--root", str(tmp_path), "--out", str(tmp_path / "o"), "--repo", str(tmp_path)]) == 0
    assert (tmp_path / "o" / "MANIFEST.json").exists()


def test_repo_root_finds_git_or_pyproject(job, tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("")
    assert job.repo_root(tmp_path / "a" / "b") == tmp_path.resolve()


def test_exported_tex_is_the_one_paper_style_wrote_apart_from_the_name(job, tmp_path):
    _save(tmp_path / "x", "f")
    job.export(tmp_path / "paper", [tmp_path], base=tmp_path, quiet=True)
    orig = (tmp_path / "x" / "f.tex").read_text()
    new = (tmp_path / "paper" / "figures" / "x-f.tex").read_text()
    assert orig.replace("{f.pdf}", "{x-f.pdf}").replace("fig:f", "fig:x-f") == new
    assert new.startswith(ps.MARK)


# ------------------------------------------------------------------ fix round


def test_default_output_folder_does_not_collide_with_a_paper_folder(job):
    assert job.OUT.name == "_export" and job.OUT.parent.name == "paper"


def test_hand_written_files_are_never_overwritten(job, tmp_path, capsys):
    _save(tmp_path / "docs", "a")
    out = tmp_path / "paper"
    out.mkdir()
    (out / "preamble.tex").write_text("% MY HAND-WRITTEN PREAMBLE\n")
    (out / "figures.tex").write_text("% MY FIGURES\n")
    assert job.export(out, [tmp_path], base=tmp_path) == 2
    assert (out / "preamble.tex").read_text() == "% MY HAND-WRITTEN PREAMBLE\n"
    assert (out / "figures.tex").read_text() == "% MY FIGURES\n"
    assert not (out / "figures").exists() and not (out / "MANIFEST.json").exists()  # nothing at all
    assert "REFUSED" in capsys.readouterr().err


def test_a_hand_written_manifest_or_figure_tex_is_refused(job, tmp_path):
    _save(tmp_path / "docs", "a")
    out = tmp_path / "paper"
    out.mkdir()
    (out / "MANIFEST.json").write_text('{"mine": true}')
    assert job.export(out, [tmp_path], base=tmp_path, quiet=True) == 2
    assert (out / "MANIFEST.json").read_text() == '{"mine": true}'
    (out / "MANIFEST.json").unlink()
    (out / "figures").mkdir()
    (out / "figures" / "docs-a.tex").write_text("\\mine\n")
    assert job.export(out, [tmp_path], base=tmp_path, quiet=True) == 2
    assert (out / "figures" / "docs-a.tex").read_text() == "\\mine\n"


def test_a_hand_made_pdf_with_the_same_name_is_refused_but_other_files_stay(job, tmp_path):
    _save(tmp_path / "docs", "a")
    out = tmp_path / "paper"
    (out / "figures").mkdir(parents=True)
    (out / "figures" / "docs-a.pdf").write_bytes(b"%PDF-mine")
    (out / "figures" / "hand.pdf").write_bytes(b"%PDF-hand")
    assert job.export(out, [tmp_path], base=tmp_path, quiet=True) == 2
    assert (out / "figures" / "docs-a.pdf").read_bytes() == b"%PDF-mine"


def test_running_twice_over_its_own_output_is_fine_and_files_carry_the_mark(job, tmp_path):
    _save(tmp_path / "docs", "a")
    out = tmp_path / "paper"
    assert job.export(out, [tmp_path], base=tmp_path, quiet=True) == 0
    assert job.export(out, [tmp_path], base=tmp_path, quiet=True) == 0
    for name in ("preamble.tex", "figures.tex", "example.tex"):
        assert (out / name).read_text().startswith(job.EXPORT_MARK)
    assert job.export(out, [tmp_path], base=tmp_path, quiet=True) == 0  # copies are not re-discovered


def test_figures_saved_inside_a_paper_folder_are_found(job, tmp_path):
    _save(tmp_path / "paper", "mine")  # a figure of the paper itself
    out = tmp_path / "paper"
    assert job.export(out, [tmp_path], base=tmp_path, quiet=True) == 0
    assert [p.name for p in (out / "figures").glob("*.pdf")] == ["paper-mine.pdf"]


def test_dotted_stems_are_found_with_their_own_caption_and_stay_distinct(job, tmp_path):
    _save(tmp_path / "f", "wpsr_2026.11.04", title="Stocks fell 3 mb in the week")
    _save(tmp_path / "f", "wpsr_2026.11.11", title="Stocks rose 5 mb in the week")
    out = tmp_path / "paper"
    assert job.export(out, [tmp_path], base=tmp_path, quiet=True) == 0
    names = sorted(p.stem for p in (out / "figures").glob("*.pdf"))
    assert names == ["f-wpsr_2026_11_04", "f-wpsr_2026_11_11"]
    rows = {r["name"]: r for r in json.loads((out / "MANIFEST.json").read_text())}
    assert "fell" in rows["f-wpsr_2026_11_04"]["caption"] and "rose" in rows["f-wpsr_2026_11_11"]["caption"]
    tex = (out / "figures" / "f-wpsr_2026_11_04.tex").read_text()
    assert "{f-wpsr_2026_11_04.pdf}" in tex

"""The paper style stays intact: nothing draws a figure around paper_style.

Static checks over the repository's Python files and notebook code cells. They fail when a
script writes its own figure files, sets its own rcParams, copies the colour tokens, or
hard-codes a font size or a figure width outside the paper format: each of those is how a
second, drifting style starts.

TO ADAPT THIS TO A REPOSITORY, edit the CONFIG block below (two lines are usually enough):
  SAVEFIG_OK   files that may call .savefig( (paper_style.py itself, a report builder)
  RCPARAMS_OK  files that may set matplotlib's global style
Paths are relative to the repository root, with forward slashes; an entry also matches any
file whose path ends with "/" + entry, so "paper_style.py" works wherever it is vendored.
Put `paper-style: ok` in a comment on a line (or in a notebook line) to exempt that line.
"""

import json
import os
import re
from pathlib import Path

import pytest

# ----------------------------------------------------------------------- CONFIG

# Tests build throw-away figures to check the report page and are not plotting scripts.
SCAN = ("src", "notebooks", "ops")  # None scans the whole repository; or a tuple of folders: ("src", "notebooks", "docs")
SKIP_DIRS = {"node_modules", "__pycache__", "site-packages", "build", "dist", "paper", "htmlcov"}
# The one writer, and this style's own files; add a report builder here if it calls savefig.
# report.py writes the one-page A4 weekly status report (text and a mini chart), not a paper figure.
SAVEFIG_OK = {"paper_style.py", "src/iegrid/report.py"}
# The only places that may set matplotlib's global style.
RCPARAMS_OK = {"paper_style.py"}
# Files that are not figures and never checked: the style, its exporter, and these tests.
EXEMPT = {
    "paper_style.py",
    "export_paper_figures.py",
    "test_paper_style.py",
    "test_paper_style_guard.py",
    "test_export_paper_figures.py",
    "make_samples.py",
}
# Hex colours of paper_style.TOKENS and PALETTE: copying one into a plotting file is a second style.
# Every non-white hex of TOKENS, PALETTE and DIVERGING, including the scored-result teal 16707A
# and brick B23A2C (a hard-coded copy of those would pass as a "result" colour unnoticed).
TOKEN_HEX = re.compile(
    r"#(?:0F2A4A|1F5FBF|7D8996|DCE3EC|0B1F3A|5B6878|E69F00|56B4E9|CC79A7|F0E442"
    r"|16707A|B23A2C|5E6B7D|8A5A00|F5F7FA|8FB3E6|D9B98C)\b",
    re.IGNORECASE,
)
MIN_FONT, MAX_FONT = 6.0, 9.0
# figsize=(w, ...) with w from 8 to 19.99 in is a web-sized figure; the paper widths are 3.4 and 7.0.
WEB_FIGSIZE = re.compile(r"figsize\s*=\s*\(\s*(?:1[0-9]|[89])(?:\.[0-9]+)?\s*,")
SCAN_NOTEBOOKS = True
# Which checks run; switch one off for a repository that is not ready for it.
CHECKS = {"savefig": True, "rcparams": True, "tokens": True, "fontsize": True, "figsize": True}

# ------------------------------------------------------------------ end of CONFIG

SAVEFIG = re.compile(r"\.savefig\(")
RCPARAMS = re.compile(r"rcParams\s*(?:\.update\(|\[[^\]]+\]\s*=[^=])|rc_context|plt\.style|mplstyle|matplotlib\.rc\(")
FONT_SIZE = re.compile(r"\b(?:fontsize|labelsize)\s*=\s*([0-9]+(?:\.[0-9]+)?)")
OK_MARK = "paper-style: ok"


def find_root(start=None):
    """The repository root above this file: .git first, then pyproject/setup, else this folder.

    PAPER_STYLE_REPO_ROOT overrides it (for a test run from elsewhere).
    """
    env = os.environ.get("PAPER_STYLE_REPO_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(start or __file__).resolve().parent
    for marker in ((".git",), ("pyproject.toml", "setup.py", "setup.cfg")):
        for d in (here, *here.parents):
            if any((d / m).exists() for m in marker):
                return d
    return here


ROOT = find_root()


def _matches(rel, names):
    return any(rel == n or rel.endswith("/" + n) for n in names)


def source_files(root, scan=None, notebooks=True):
    """(path, relative posix path) of every .py (and .ipynb) file to check, in a stable order."""
    root = Path(root)
    tops = [root / s for s in scan] if scan else [root]
    for top in tops:
        if not top.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
            for name in sorted(filenames):
                if name.endswith(".py") or (notebooks and name.endswith(".ipynb")):
                    p = Path(dirpath) / name
                    rel = p.relative_to(root).as_posix()
                    if not _matches(rel, EXEMPT):
                        yield p, rel


def _strip_comment(line):
    """The code part of a line: naive about '#' inside strings, which is fine for these checks."""
    if "#" in line and "'#" not in line and '"#' not in line:
        return line.split("#")[0]
    return line


def code_lines(path):
    """(label, text) for each code line of a .py file or each line of a notebook's code cells.

    The label is 'line' for a file and 'cell N:line' for a notebook. Lines marked
    `paper-style: ok` are left out. Unreadable files give nothing.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if str(path).endswith(".ipynb"):
        try:
            nb = json.loads(text)
        except ValueError:
            return
        cells = nb.get("cells") or [c for ws in nb.get("worksheets", []) for c in ws.get("cells", [])]
        for n, cell in enumerate(cells):
            if cell.get("cell_type", "code") != "code":
                continue
            src = cell.get("source", cell.get("input", ""))
            lines = "".join(src).split("\n") if isinstance(src, list) else str(src).split("\n")
            for i, line in enumerate(lines, 1):
                if OK_MARK not in line and not line.lstrip().startswith("%"):
                    yield f"cell {n}:{i}", _strip_comment(line)
        return
    for i, line in enumerate(text.split("\n"), 1):
        if OK_MARK not in line:
            yield str(i), _strip_comment(line)


def violations(root, *, scan=None, savefig_ok=(), rcparams_ok=(), checks=None, notebooks=True):
    """Every rule break under `root` as 'check: path:where text'. The tests below assert it is empty."""
    checks = dict(CHECKS if checks is None else checks)
    out = []
    for p, rel in source_files(root, scan, notebooks):
        lines = list(code_lines(p))
        mentions = any("matplotlib" in t or "paper_style" in t or "plt." in t for _, t in lines)
        for where, line in lines:
            if checks.get("savefig") and SAVEFIG.search(line) and not _matches(rel, savefig_ok):
                out.append(f"savefig: {rel}:{where} (write figures with paper_style.save)")
            if checks.get("rcparams") and RCPARAMS.search(line) and not _matches(rel, rcparams_ok):
                out.append(f"rcparams: {rel}:{where} (set the style in paper_style.apply)")
            if checks.get("tokens") and mentions and TOKEN_HEX.search(line):
                out.append(f"tokens: {rel}:{where} (use paper_style.TOKENS / PALETTE)")
            if checks.get("fontsize"):
                for m in FONT_SIZE.finditer(line):
                    if not MIN_FONT <= float(m.group(1)) <= MAX_FONT:
                        out.append(f"fontsize: {rel}:{where} fontsize={m.group(1)} (6 to 9 pt)")
            if checks.get("figsize") and WEB_FIGSIZE.search(line):
                out.append(f"figsize: {rel}:{where} (3.4 or 7.0 in wide: paper_style.figure)")
    return out


def _check(name):
    if not CHECKS.get(name):
        pytest.skip(f"{name} check switched off in CONFIG")
    return [v for v in violations(ROOT, scan=SCAN, savefig_ok=SAVEFIG_OK, rcparams_ok=RCPARAMS_OK,
                                  checks={name: True}, notebooks=SCAN_NOTEBOOKS)]


# ----------------------------------------------------------- the repository checks


def test_only_paper_style_writes_figure_files():
    assert not _check("savefig"), "write figures with paper_style.save, not savefig"


def test_only_paper_style_sets_matplotlib_rcparams():
    assert not _check("rcparams"), "set the style in paper_style.apply, not locally"


def test_the_colour_tokens_are_not_copied_out_of_paper_style():
    assert not _check("tokens"), "use paper_style.TOKENS or PALETTE instead of a copy of the hex values"


def test_every_literal_font_size_is_on_the_paper_type_scale():
    assert not _check("fontsize"), "fonts must be 6 to 9 pt (paper_style.MIN_FONT, MAX_FONT)"


def test_no_script_builds_a_figure_at_a_web_size():
    assert not _check("figsize"), "figures are 3.4 or 7.0 in wide (paper_style.figure)"


# ------------------------------------------------- the guard itself, on scratch repos


def _nb(*cells):
    return json.dumps({
        "cells": [{"cell_type": t, "source": src.splitlines(True), "metadata": {}} for t, src in cells],
        "metadata": {}, "nbformat": 4, "nbformat_minor": 5,
    })


def _scratch(tmp_path):
    """A repo whose python files are scattered over unrelated folders, with one break of each kind."""
    (tmp_path / ".git").mkdir()
    files = {
        "pkg/sub/plots.py": "import matplotlib.pyplot as plt\nfig.savefig('x.png')\n",
        "tools/deep/er/style.py": "import matplotlib as mpl\nmpl.rcParams.update({'a': 1})\nmpl.rcParams['font.size'] = 10\n",
        "scripts/colours.py": "import matplotlib\nC = '#0F2A4A'\n",
        "a/b/c/sizes.py": "ax.text(0, 0, 's', fontsize=14)\nfig = plt.figure(figsize=(10, 4))\nax.tick_params(labelsize=5)\n",
        "x/clean.py": "import matplotlib.pyplot as plt  # savefig is fine in a comment\nax.text(0, 0, 's', fontsize=7)\nfig = plt.figure(figsize=(7.0, 4))\n",
        "x/marked.py": "fig.savefig('a.png')  # paper-style: ok\n",
        "x/rcparams_eq.py": "if mpl.rcParams['a'] == 1:\n    pass\n",
        "notebooks/n.ipynb": _nb(
            ("markdown", "fig.savefig('md.png')\n"),
            ("code", "import matplotlib.pyplot as plt\n%matplotlib inline\nplt.savefig('n.png')\n"),
            ("code", "plt.rcParams.update({'font.size': 12})\nplt.rcParams['axes.grid'] = True\n"),
            ("code", "ax.set_title('t', fontsize=20)\n"),
        ),
        "notebooks/broken.ipynb": "{not json",
        ".venv/lib/x.py": "fig.savefig('v.png')\n",
        "node_modules/p/x.py": "fig.savefig('v.png')\n",
        "paper_style.py": "import matplotlib\nplt.rcParams.update({})\nfig.savefig('ok')\n",
        "tests/test_paper_style_guard.py": "fig.savefig('self')\n",
    }
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def test_guard_finds_every_kind_of_break_in_scattered_files_and_notebooks(tmp_path):
    repo = _scratch(tmp_path)
    got = violations(repo, savefig_ok=SAVEFIG_OK, rcparams_ok=RCPARAMS_OK)
    kinds = {}
    for v in got:
        kinds.setdefault(v.split(":")[0], []).append(v)
    assert any("pkg/sub/plots.py:2" in v for v in kinds["savefig"])
    assert any("notebooks/n.ipynb:cell 1:3" in v for v in kinds["savefig"])  # notebook code cell
    assert not any("md.png" in v or "cell 0" in v for v in got)  # markdown cells are not code
    assert any("tools/deep/er/style.py:2" in v for v in kinds["rcparams"])
    assert any("tools/deep/er/style.py:3" in v for v in kinds["rcparams"])  # item assignment
    assert any("notebooks/n.ipynb:cell 2:1" in v for v in kinds["rcparams"])  # rcParams.update in a cell
    assert any("notebooks/n.ipynb:cell 2:2" in v for v in kinds["rcparams"])
    assert any("scripts/colours.py" in v for v in kinds["tokens"])
    assert {v.split()[1].split(":")[0] for v in kinds["fontsize"]} == {"a/b/c/sizes.py", "notebooks/n.ipynb"}
    assert any("fontsize=5" in v for v in kinds["fontsize"]) and any("fontsize=14" in v for v in kinds["fontsize"])
    assert any("a/b/c/sizes.py:2" in v for v in kinds["figsize"])


def test_guard_ignores_what_it_should(tmp_path):
    got = "\n".join(violations(_scratch(tmp_path), savefig_ok=SAVEFIG_OK, rcparams_ok=RCPARAMS_OK))
    for quiet in ("x/clean.py", "x/marked.py", "x/rcparams_eq.py", ".venv", "node_modules",
                  "paper_style.py", "test_paper_style_guard.py", "broken.ipynb"):
        assert quiet not in got, quiet


def test_allow_lists_match_by_path_suffix_and_exempt_one_file(tmp_path):
    repo = _scratch(tmp_path)
    got = violations(repo, savefig_ok={"pkg/sub/plots.py", "n.ipynb"}, rcparams_ok={"style.py"})
    text = "\n".join(got)
    assert "savefig: pkg/sub/plots.py" not in text and "savefig: notebooks/n.ipynb" not in text
    assert "rcparams: tools/deep/er/style.py" not in text
    assert "rcparams: notebooks/n.ipynb" in text  # "style.py" does not cover the notebook


def test_scan_folders_and_switches_and_notebook_flag(tmp_path):
    repo = _scratch(tmp_path)
    only = violations(repo, scan=("scripts",), savefig_ok=SAVEFIG_OK, rcparams_ok=RCPARAMS_OK)
    assert only and all("scripts/colours.py" in v for v in only)
    assert not [v for v in violations(repo, checks={"savefig": False}) if v.startswith("savefig")]
    assert not [v for v in violations(repo, notebooks=False) if ".ipynb" in v]
    assert violations(repo, scan=("does-not-exist",)) == []


def test_root_is_found_from_the_file_and_can_be_overridden(tmp_path, monkeypatch):
    repo = tmp_path / "r"
    (repo / ".git").mkdir(parents=True)
    (repo / "deep" / "er").mkdir(parents=True)
    monkeypatch.delenv("PAPER_STYLE_REPO_ROOT", raising=False)
    assert find_root(repo / "deep" / "er" / "t.py") == repo.resolve()
    monkeypatch.setenv("PAPER_STYLE_REPO_ROOT", str(tmp_path))
    assert find_root(repo / "deep" / "er" / "t.py") == tmp_path.resolve()
    bare = tmp_path / "bare" / "sub"
    bare.mkdir(parents=True)
    monkeypatch.delenv("PAPER_STYLE_REPO_ROOT")
    assert find_root(bare / "t.py") in (bare, *bare.parents)  # no marker: some folder above, never an error


def test_a_notebook_in_the_old_worksheet_format_is_read(tmp_path):
    nb = tmp_path / "old.ipynb"
    nb.write_text(json.dumps({"worksheets": [{"cells": [{"cell_type": "code", "input": "fig.savefig('a.png')\n"}]}]}))
    assert [t for _, t in code_lines(nb) if "savefig" in t]


def test_token_regex_covers_every_colour_of_paper_style():
    ps = pytest.importorskip("iegrid.paper_style")
    every = set(ps.TOKENS.values()) | set(ps.PALETTE) | set(ps.DIVERGING)
    missing = sorted(c for c in every if c.upper() != "#FFFFFF" and not TOKEN_HEX.fullmatch(c))
    assert not missing, f"add {missing} to TOKEN_HEX"


def test_a_hard_coded_scored_result_colour_is_found(tmp_path):
    for hexc in ("#16707A", "#B23A2C", "#b23a2c"):
        (tmp_path / "plot.py").write_text(f"import matplotlib.pyplot as plt\nBAD = '{hexc}'\n")
        out = violations(tmp_path, checks={"tokens": True})
        assert any(v.startswith("tokens:") for v in out), hexc

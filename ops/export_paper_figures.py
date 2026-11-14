"""Collect every paper figure of a repository into one folder for an arXiv source tree.

    python export_paper_figures.py                       # scans the repo, writes paper/_export/
    python export_paper_figures.py --root docs --root notebooks/figs
    python export_paper_figures.py --check               # checks only, writes nothing

Finds every `<name>.pdf` that has a `<name>.tex` beside it beginning with the line
"% Written by paper_style.save" (what `paper_style.save` writes), under each --root
(default: the repository root). Hidden folders (.git, .venv, .local, .claude), node_modules,
__pycache__ and the output folder are skipped below a root; name one explicitly with --root
to include it. Needs only the standard library, Python 3.9 or later.

Writes, under the output folder (default <repo>/paper/_export, a name no hand-written paper
folder uses; copy its contents into the paper's source tree, or compile example.tex in it):
  figures/<tag>-<name>.pdf and .tex   one vector figure and its `figure` environment each. The tag
                                      is the figure's folder relative to the repo ("docs-img",
                                      "root" for the top level), so names are unique and arXiv-safe
                                      (letters, digits, - _ .)
  preamble.tex                        the packages the captions need and \\graphicspath
  figures.tex                         \\input of every figure, for a gallery or an appendix
  example.tex                         a complete article that compiles with figures.tex
  MANIFEST.json                       source, size, caption and check result of every figure

Each PDF is checked against what arXiv and journal checkers reject: Type 3 fonts, missing
embedded fonts, encryption, and very large files. The exit code is 1 if any check fails or
if no figure was found.

Never overwrites a file it did not write: preamble.tex, figures.tex and example.tex must begin
with the line "% Written by export_paper_figures", MANIFEST.json must be a list this script
wrote, and a figure copy that already exists must be listed in that manifest or identical.
If anything else is in the way, nothing is written and the exit code is 2; choose another
--out. Only <out>/figures/ is skipped when scanning, so figures saved under paper/ are found.
"""

import argparse
import json
import re
import sys
from pathlib import Path

MARK = "% Written by paper_style.save"
EXPORT_MARK = "% Written by export_paper_figures"  # first line of every file this script writes
MAX_BYTES = 2_000_000  # a vector chart this large is usually a rasterised image or a huge scatter
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
SKIP_DIRS = {"node_modules", "__pycache__", "site-packages", "build", "dist"}


def repo_root(start=None):
    """The folder above `start` (default: this file) that holds .git or pyproject.toml, else `start`."""
    here = Path(start or __file__).resolve()
    here = here if here.is_dir() else here.parent
    for d in (here, *here.parents):
        if (d / ".git").exists() or (d / "pyproject.toml").exists():
            return d
    return here


ROOT = repo_root()
OUT = ROOT / "paper" / "_export"


def check_pdf(path):
    """Problems arXiv or a journal checker would raise, as a list of strings (empty = fine)."""
    raw = Path(path).read_bytes()
    problems = []
    if not raw.startswith(b"%PDF-"):
        problems.append("not a PDF")
    if re.search(rb"/Subtype\s*/Type3\b", raw):
        problems.append("Type 3 fonts (rejected by IEEE/ACM checkers)")
    if re.search(rb"/Type\s*/Font\b", raw) and b"/FontFile" not in raw:
        problems.append("fonts are not embedded")
    if b"/Encrypt" in raw:
        problems.append("encrypted")
    if len(raw) > MAX_BYTES:
        problems.append(f"{len(raw) / 1e6:.1f} MB, over {MAX_BYTES / 1e6:.0f} MB")
    return problems


def _skip(rel_parts):
    """True for a path below a root that sits in a hidden or vendored folder."""
    return any(p.startswith(".") or p in SKIP_DIRS for p in rel_parts[:-1])


def _tag(pdf, base):
    """The folder of `pdf` relative to the repo as an arXiv-safe tag ('docs-img'; 'root' at the top)."""
    try:
        parts = pdf.parent.resolve().relative_to(base).parts
    except ValueError:  # a root outside the repo: its own folder name
        parts = (pdf.parent.name,)
    tag = "-".join(parts) if parts else "root"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", tag).strip("-.") or "root"


def discover(roots, base, out_dir=None):
    """[(tag, pdf, tex)] for every paper_style figure under `roots`, sorted, each once."""
    found, seen = [], set()
    skip_dir = Path(out_dir).resolve() / "figures" if out_dir else None  # our own copies
    for root in roots:
        root = Path(root).resolve()
        for pdf in sorted(root.rglob("*.pdf")):
            rel = pdf.relative_to(root).parts
            if _skip(rel) or (skip_dir and skip_dir in pdf.parents):
                continue
            tex = pdf.with_name(pdf.name[:-4] + ".tex")  # not with_suffix: 'run_1.5.pdf' keeps its dot
            if pdf in seen or not tex.exists():
                continue
            if not tex.read_text(encoding="utf-8", errors="replace").startswith(MARK):
                continue  # a PDF that paper_style.save did not write
            seen.add(pdf)
            found.append((_tag(pdf, base), pdf, tex))
    return found


def rename(tex_text, stem, new):
    """Point the figure environment at the renamed PDF and give it a matching label."""
    out = tex_text.replace(f"{{{stem}.pdf}}", f"{{{new}.pdf}}")
    label = re.sub(r"[^a-z0-9]+", "-", new.lower()).strip("-")
    return re.sub(r"\\label\{fig:[^}]*\}", lambda m: f"\\label{{fig:{label}}}", out)


HEADER = EXPORT_MARK + ".py; edit the figure code and run it again, not this file.\n"

PREAMBLE = HEADER + """% Packages the figure captions need, and where the figures live.
\\usepackage{graphicx}
\\usepackage{amssymb}   % \\blacktriangle, \\blacktriangledown in captions
\\usepackage{textcomp}  % \\textdegree, \\texteuro, \\textperiodcentered in captions
\\graphicspath{{figures/}}
"""

EXAMPLE = HEADER + """% A complete article that shows every figure; compile with pdflatex or latexmk.
\\documentclass[10pt]{article}
\\usepackage[margin=1in]{geometry}
\\usepackage[T1]{fontenc}
\\usepackage{mathptmx}  % Times-compatible text and maths, like the figures
\\input{preamble}
\\begin{document}
\\section*{Figures}
\\input{figures}
\\end{document}
"""


def _unique(name, taken):
    new, n = name, 2
    while new in taken:
        new = f"{name}-{n}"
        n += 1
    taken.add(new)
    return new


def _ours_manifest(path):
    """The entries of an existing MANIFEST.json if this script wrote it, else None."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = isinstance(data, list) and all(
        isinstance(e, dict) and {"name", "source", "bytes"} <= set(e) for e in data
    )
    return data if ok else None


def _is_ours_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").startswith(EXPORT_MARK)
    except OSError:
        return False


def conflicts(out, rows):
    """Files in `out` that exist, were not written by this script, and would be overwritten."""
    out = Path(out)
    bad = []
    for name in ("preamble.tex", "figures.tex", "example.tex"):
        f = out / name
        if f.exists() and not _is_ours_text(f):
            bad.append(f)
    manifest = out / "MANIFEST.json"
    old = _ours_manifest(manifest) if manifest.exists() else None
    if manifest.exists() and old is None:
        bad.append(manifest)
    mine = {e["name"] for e in old or []}
    for r in rows:
        pdf = out / "figures" / f"{r['name']}.pdf"
        tex = out / "figures" / f"{r['name']}.tex"
        if pdf.exists() and r["name"] not in mine and pdf.read_bytes() != r["_pdf"].read_bytes():
            bad.append(pdf)
        if tex.exists() and not tex.read_text(encoding="utf-8", errors="replace").startswith(MARK):
            bad.append(tex)
    return bad


def export(out, roots=None, check_only=False, base=None, quiet=False):
    """Collect figures from `roots` into `out`.

    Returns 0; 1 if a check failed or no figure was found; 2 if `out` holds a file this
    script did not write (nothing is written then).
    """
    base = Path(base).resolve() if base else ROOT
    roots = [Path(r) for r in (roots or [base])]
    out = Path(out)
    rows, failed, taken = [], 0, set()
    for tag, pdf, tex in discover(roots, base, out):
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", pdf.stem)  # a dot in a stem becomes _
        new = _unique(f"{tag}-{stem}", taken)
        problems = check_pdf(pdf)
        if not SAFE_NAME.match(new):
            problems.append(f"name {new!r} has characters arXiv does not accept")
        failed += bool(problems)
        text = tex.read_text(encoding="utf-8")
        caption = re.search(r"\\caption\{(.*)\}\n", text)
        try:
            source = str(pdf.relative_to(base))
        except ValueError:
            source = str(pdf)
        rows.append(
            {
                "name": new,
                "source": Path(source).as_posix(),
                "bytes": pdf.stat().st_size,
                "env": "figure*" if "\\begin{figure*}" in text else "figure",
                "caption": caption.group(1) if caption else "",
                "problems": problems,
                "_pdf": pdf,
                "_tex": rename(text, pdf.stem, new),
            }
        )
    for r in rows:
        if not quiet:
            mark = "FAIL" if r["problems"] else "ok  "
            print(f"{mark} {r['name']:<48} {r['bytes'] / 1000:6.0f} kB  {'; '.join(r['problems'])}")
    if not quiet:
        print(f"{len(rows)} figures, {failed} with problems")
    if check_only or not rows:
        return 1 if failed or not rows else 0
    bad = conflicts(out, rows)
    if bad:
        if not quiet:
            print(
                "REFUSED: these files exist and were not written by export_paper_figures; "
                "nothing was written. Choose another --out, or move them:\n  "
                + "\n  ".join(str(f) for f in bad),
                file=sys.stderr,
            )
        return 2
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    old_manifest = out / "MANIFEST.json"
    old = _ours_manifest(old_manifest) if old_manifest.exists() else None
    for entry in old or []:  # a figure that was renamed or removed must not linger; hand-made files stay
        for ext in (".pdf", ".tex"):
            (fig_dir / f"{entry['name']}{ext}").unlink(missing_ok=True)
    for r in rows:
        (fig_dir / f"{r['name']}.pdf").write_bytes(r["_pdf"].read_bytes())
        (fig_dir / f"{r['name']}.tex").write_text(r["_tex"], encoding="utf-8")
    (out / "preamble.tex").write_text(PREAMBLE, encoding="utf-8")
    (out / "example.tex").write_text(EXAMPLE, encoding="utf-8")
    (out / "figures.tex").write_text(
        HEADER
        + "% \\input this file to place every figure; or \\input{figures/<name>} for one.\n"
        + "".join(f"\\input{{figures/{r['name']}}}\n" for r in rows),
        encoding="utf-8",
    )
    manifest = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    old_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", action="append", default=[], help="folder to scan (repeatable; default: the repo root)")
    ap.add_argument("--out", default=str(OUT), help="folder to write (default <repo>/paper/_export)")
    ap.add_argument("--repo", default=str(ROOT), help="repo root used for tags and source paths")
    ap.add_argument("--check", action="store_true", help="check only, write nothing")
    args = ap.parse_args(argv)
    return export(Path(args.out), args.root or None, args.check, base=args.repo)


if __name__ == "__main__":
    sys.exit(main())

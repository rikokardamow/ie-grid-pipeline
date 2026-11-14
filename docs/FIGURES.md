# Figures for a paper: the specification

This repository draws every chart through one file, `paper_style.py`. A chart made once then looks the same in a notebook, a README and an arXiv paper, and it can go into a journal without redrawing. This page says what the style is and why. The code is the authority: `paper_style.lint()` checks the rules marked P below, and `save()` refuses to write a figure that breaks one.

## Geometry

A figure is drawn at the size it prints, so 8 pt on screen is 8 pt on the page. There are two widths: 3.4 in (one column of a two-column template) and 7.0 in (the full page, or `\linewidth` in a one-column article). `ps.figure()` gives 7.0 by 4.2 in; each extra row of panels adds 1.5 in; the height never exceeds 9 in, so a figure and its caption fit on a page. `ps.figure(width=ps.COLUMN)` gives the narrow one. Margins are set in inches by `frame()` (0.6 in left, 0.2 in top, 0.5 in bottom, 14% of the width on the right, kept free for labels at the ends of lines), so they mean the same on both widths. Rule P1: the width is exactly 3.4 or 7.0 in (within 0.001 in), which is also what the 300 dpi PNG check wants: 1020 or 2100 px. Never resize a figure in LaTeX to fix a layout problem; change the code.

## Type

Serif, close to Times: STIXGeneral, then Times New Roman, then Times, then DejaVu Serif, which ships with matplotlib and has every glyph used. Axis labels are 8 pt, tick labels 7 pt, notes 7 to 7.5 pt, panel letters 8 pt bold. Every visible text must be between 6 and 9 pt (P3), and none may run off the edge of the figure (P6). Fonts are embedded as TrueType, "Type 42" (P4): matplotlib's default Type 3 is accepted by arXiv but rejected by some IEEE and ACM checkers and does not select cleanly. Maths in text is switched off (`text.parse_math` is False) so that "$2.67 against $0.79" stays text: write units with Unicode (m³, µg, CO₂, −), not with `$...$`. Matplotlib writes log-axis ticks as mathtext (`$\mathdefault{10^{0}}$`), which would print literally, so after `semilogy`, `loglog` or `set_xscale("log")` call `ps.log_axis(ax)` (plain "1, 10, 100" or "10⁵", never mathtext); lint P8 refuses a figure that still shows mathtext markup.

`save()` pins the settings that decide the printed size (`savefig.bbox`, `figure.autolayout`, constrained layout, `text.usetex`), so a repository `matplotlibrc` or a style file cannot crop or rescale a figure. `frame()` removes a constrained or tight layout engine, because it would override the margins.

## Colour, line and grid

Axis lines are muted navy at 0.6 pt, grid lines pale at 0.4 pt (horizontal only), data lines 1.0 pt. The default colour cycle is house navy `#0F2A4A`, accent blue `#1F5FBF`, grey `#7D8996`, then Okabe and Ito orange `#E69F00`, sky blue `#56B4E9` and reddish purple `#CC79A7`. Yellow `#F0E442` is slot 7 of `ps.PALETTE` but not in the cycle: it is 1.3:1 on white, so use it only as a filled mark with a dark edge (`series_style(6)` does).

Colour-blind check (Machado 2009 simulation, OKLab distance times 100, the dataviz validator and the test-suite agree): the first four colours are at least 12 apart from each other under normal, protan, deutan and tritan vision; the neighbouring pairs of all six are at least 9.6 apart for red-green colour blindness. Two non-neighbours are weak: grey with purple under protan (2.7) and sky with grey for everyone (14.5), and navy with blue is close in greyscale. So with more than four series, or if a figure may be printed in black and white, tell series apart by more than colour: `ax.plot(x, y, **ps.series_style(i))` adds a different dash to each, and `end_label()` names a line at its end, which beats a legend. The validator's lightness-band and chroma-floor FAILs are intended: navy and grey are the neutral anchors of the house style, not categorical hues.

## Captions

Nothing about the finding is drawn on the image (P2): no title, subtitle, units line or source line. They are written to `<name>.tex`, a ready `figure` environment, and LaTeX numbers it. `frame()` takes `title` (required, and it must state a finding: "Demand fell 4% in a year", not "Demand chart"), and optionally `units`, `cadence`, `source`, `asof`, `licence` and `subtitle`. Given fields are validated; `ps.REQUIRE` makes more of them mandatory (for example `("title", "source", "asof")`), and `ps.UNITS` can restrict the allowed unit spellings. Five more switches (`ASOF_ZONES`, `CADENCE_PATTERN`, `SOURCE_SHAPE`, `LICENCE_CHECK`, `SAVE_GUARD`, documented at the top of `paper_style.py`) let a repository tighten the provenance rules further. The caption reads: finding, then the subtitle (where panels are explained, "(a) ... (b) ..."), then `Units: GW; weekly.`, then `Source: Table 4 (D-1); CC BY 4.0; as of 2026-11-04 15:30 UTC.` Dates are `YYYY-MM-DD` or `YYYY-MM-DD HH:MM ZONE`; never invent a clock time you do not know. `%`, `&`, `_`, `<`, `>`, `|` and symbols are escaped for pdflatex (needs `graphicx`, `amssymb`, `textcomp`). The recommended spellings work: `CO₂` becomes `CO\textsubscript{2}`, `W m⁻²` becomes `W m\textsuperscript{$-$2}`, `µg` and Greek letters, curly quotes and dashes are mapped, and Latin letters with accents pass through (LaTeX reads UTF-8). A character with no LaTeX form (CJK, emoji) prints as a bold "?" and `save()` warns, naming the character: write it in ASCII or add it to `paper_style._TEX`. Output names keep their dots: `save(fig, "x/wpsr_2026.11.04")` writes `x/wpsr_2026.11.04.pdf`; only `.pdf .png .svg .tex` are stripped. Files are written under temporary names, size-checked (PNG pixels, PDF and SVG points), and renamed only when all pass.

## Axis labels and panels

Every data axis carries a label that names the quantity and its unit, "Demand (GW)" (`frame(xlabel=, ylabel=)`, or set on the axis; `lint(fig, axis_labels=True)` reports a missing one as P7). A string labels the first column (y) or the bottom row (x); a list labels panels in reading order. A figure with two or more panels gets bold (a), (b), ... at each top-left corner, so the text can say "Fig. 4(b)". Image, map and heat-map panels drawn with `ax.axis("off")` are panels and get letters too. An axes on top of another (`twinx`) is part of its panel: no letter, no copied label; give its scale a label of its own with `ax2.set_ylabel(...)` (`lint(axis_labels=True)` asks for it). Colour bars are not panels; mark any other helper axes with `ps.skip_panel(ax)`.

## What `lint()` checks

P0 the figure was framed and every `REQUIRE` field is present. P1 width 3.4 or 7.0 in, height at most 9 in. P2 no title, subtitle or footer on the image (also an axes title on a single-panel figure). P3 all text 6 to 9 pt. P4 serif, Type 42. P5 the PNG is width by height at 300 dpi (to within one pixel, since matplotlib rounds a size like 2.26 in its own way), and PDF, SVG, PNG and TEX are byte-identical between runs (same matplotlib version). P6 no text off the edge. P8 no mathtext markup shown literally (use `log_axis`). Not checked, so look: overlapping text inside the axes, units in every label, that two series differ by more than colour. Optional desk rules, `ps.STRICT_DESK = True`: no legend box, no twin axes, no red or green anywhere (including arrows and colour maps).

## Writing a chart in 15 lines

```python
import paper_style as ps
import numpy as np

x = np.arange(60)
fig, axes = ps.figure(width=ps.COLUMN)               # 3.4 in wide; use the default for 7.0
ax = axes[0][0]
for i, (name, slope) in enumerate([("Wind", 0.9), ("Solar", 0.6)]):
    y = 20 + slope * x
    ax.plot(x, y, **ps.series_style(i))              # colour and dash
    ps.end_label(ax, x[-1], y[-1], name, f"{y[-1]:.0f}", color=ps.PALETTE[i])
ps.frame(fig, title="Wind output outgrew solar by a third", units="TWh", cadence="monthly",
         source="Grid operator, table 3 (A-12)", asof="2026-11-04",
         xlabel="Months since January 2022", ylabel="Generation (TWh)")
print(ps.lint(fig))                                  # [] means it fits a paper
ps.save(fig, "figures/generation")                   # .pdf .png .svg .tex
```

In a notebook, call `ps.show(fig)` before `save`: the Agg backend is forced, so `plt.show()` would draw nothing. Do not call `fig.savefig`, `plt.rcParams.update` or `plt.style.use` anywhere else; `test_paper_style_guard.py` fails if you do.

## Exporting for arXiv

`python export_paper_figures.py` finds every figure that `paper_style.save` wrote (a `.pdf` with a `.tex` that starts "% Written by paper_style.save"), under `--root` folders (default: the repository), and copies them to `paper/_export/figures/` (a folder name no hand-written paper uses; change it with `--out`) under unique names (`docs-img-generation.pdf`: the folder, then the stem). It checks each PDF for Type 3 fonts, unembedded fonts, encryption and size over 2 MB, and writes `preamble.tex`, `figures.tex`, `example.tex` and `MANIFEST.json`; `--check` only checks. It never overwrites a file it did not write (its files start "% Written by export_paper_figures"): if one is in the way it writes nothing, says which, and exits 2. Copy the contents of that folder next to your main `.tex` file (or compile `example.tex` inside it). In the paper: `\input{preamble}`, then `\input{figures/docs-img-generation}` where the figure goes, and refer to it as `\ref{fig:docs-img-generation}`. Upload the PDFs and `.tex` files, not the PNG or SVG. arXiv compiles with pdfLaTeX, which includes PDF figures directly.

Panels and helper axes. Only axes whose axis is switched on are panels and get a letter. A hand-made key or inset made with `fig.add_axes(...)` and `set_axis_off()` is therefore ignored; an axes with its axis on that is not data is marked `ps.skip_panel(ax)`, and an axis-off image that should carry a letter is marked `ps.as_panel(ax)`.

# Figures for a paper: the specification

This repository draws every chart through one file, `paper_style.py`. A chart made once then looks the same in a notebook, a README and an arXiv paper, and it can go into a journal without redrawing. This page says what the style is and why. The code is the authority: `paper_style.lint()` checks the rules marked P below, and `save()` refuses to write a figure that breaks one.

## Look

The look follows the reference post on elegant scientific graphs (BBC, National Geographic, the New York Times, Nature) and takes ggplot2's `theme_minimal` as its base: the data carries the ink, everything else recedes.

- **Quiet text.** Sans-serif type at about 80% grey: labels and notes `#333333`, tick labels `#4D4D4D`, guide or muted text `#808080`, on white.
- **No box.** Left, top and right spines are off; only a light baseline (`#B3B3B3`, 0.6 pt) at the bottom, with short grey x ticks. No y tick marks: the gridlines carry the values and the labels stay.
- **Faint grid.** Horizontal major gridlines only (`#E5E5E5`, 0.5 pt, behind the data); no vertical or minor grid. A horizontal bar chart turns this round with `ps.hbar_axes(ax)` (vertical gridlines, baseline on the left).
- **Panel titles like facet strips.** `ax.set_title("Daily level")` on a multi-panel figure is left-aligned, bold, 8 pt, after the bold (a), (b) letter. A one-panel figure has no title on the image (P2): the finding lives in the caption.
- **Marks.** Data lines 1.2 pt, markers 3.5 pt; bands are light fills without edges (`ps.band(ax, x, lower, upper)`), bars have no edge.
- **Legible labels.** Direct labels and notes drawn by the helpers (`end_label`, `note`, `ref_line`, `event_rule`, `provisional`, `bar_labels`) carry a 2.5 pt white halo, so they read over lines and fills, as on BBC and NYT maps. Any other text gets one with `path_effects=ps.halo()`. `bar_labels` widens the value axis until every value label sits inside the axes (again in `frame`), so the label of a negative bar never covers its category name.
- **Few, distinct colours.** The house palette (navy, accent blue, grey) then Okabe-Ito orange, sky and purple; never red or green where a repository bans them (`STRICT_DESK`). Label lines directly rather than with a legend.

The look is set by `ps.apply()` (matplotlib) and `ps.theme_paper()` (plotnine), and nowhere else.

## Geometry

A figure is drawn at the size it prints, so 8 pt on screen is 8 pt on the page. There are two widths: 3.4 in (one column of a two-column template) and 7.0 in (the full page, or `\linewidth` in a one-column article). `ps.figure()` gives 7.0 by 4.2 in; each extra row of panels adds 1.5 in; the height never exceeds 9 in, so a figure and its caption fit on a page. `ps.figure(width=ps.COLUMN)` gives the narrow one. Margins are set in inches by `frame()` (0.6 in left, 0.2 in top, 0.5 in bottom, 18% of the width and at most 1.3 in on the right, kept free for labels at the ends of lines), so they mean the same on both widths. Rule P1: the width is exactly 3.4 or 7.0 in (within 0.001 in), which is also what the 300 dpi PNG check wants: 1020 or 2100 px. Never resize a figure in LaTeX to fix a layout problem; change the code.

## Type

Sans-serif, as in ggplot2 and Nature figures: Helvetica Neue, then Helvetica, then Arial, then DejaVu Sans, which ships with matplotlib and has every glyph used (matplotlib falls back to it glyph by glyph); maths, where it is used at all, is set in DejaVu Sans (`mathtext.fontset = "dejavusans"`). Axis labels are 8 pt, tick labels 7 pt, notes 7 to 7.5 pt, panel letters 8 pt bold. Every visible text must be between 6 and 9 pt (P3), and none may run off the edge of the figure (P6). P4 checks that every drawn text is in the house sans-serif (a text that names its own family, `family="serif"`, fails) and that fonts are embedded as TrueType, "Type 42": matplotlib's default Type 3 is accepted by arXiv but rejected by some IEEE and ACM checkers and does not select cleanly. Maths in text is switched off (`text.parse_math` is False) so that "$2.67 against $0.79" stays text: write units with Unicode (m³, µg, CO₂, −), not with `$...$`. Matplotlib writes log-axis ticks as mathtext (`$\mathdefault{10^{0}}$`), which would print literally, so after `semilogy`, `loglog` or `set_xscale("log")` call `ps.log_axis(ax)` (one notation per axis: digits "0.01, 1, 100, 10000" when every visible decade lies in 10⁻³ to 10⁴, otherwise "10⁻⁵ … 10⁷" on every tick, never a mix and never mathtext; `style="plain"` or `"power"` forces one); lint P8 refuses a figure that still shows mathtext markup.

`save()` pins the settings that decide the printed size (`savefig.bbox`, `figure.autolayout`, constrained layout, `text.usetex`), so a repository `matplotlibrc` or a style file cannot crop or rescale a figure. `frame()` removes a constrained or tight layout engine, because it would override the margins.

## Colour, line and grid

The baseline is light grey at 0.6 pt, grid lines very light grey at 0.5 pt (horizontal only), data lines 1.2 pt (see Look). The default colour cycle is house navy `#0F2A4A`, accent blue `#1F5FBF`, grey `#7D8996`, then Okabe and Ito orange `#E69F00`, sky blue `#56B4E9` and reddish purple `#CC79A7`. Yellow `#F0E442` is slot 7 of `ps.PALETTE` but not in the cycle: it is 1.3:1 on white, so use it only as a filled mark with a dark edge (`series_style(6)` does).

Colour-blind check (Machado 2009 simulation, OKLab distance times 100, the dataviz validator and the test-suite agree): the first four colours are at least 12 apart from each other under normal, protan, deutan and tritan vision; the neighbouring pairs of all six are at least 9.6 apart for red-green colour blindness. Two non-neighbours are weak: grey with purple under protan (2.7) and sky with grey for everyone (14.5), and navy with blue is close in greyscale. So with more than four series, or if a figure may be printed in black and white, tell series apart by more than colour: `ax.plot(x, y, **ps.series_style(i))` adds a different dash to each, and `end_label()` names a line at its end, which beats a legend. The validator's lightness-band and chroma-floor FAILs are intended: navy and grey are the neutral anchors of the house style, not categorical hues.

## Captions

Nothing about the finding is drawn on the image (P2): no title, subtitle, units line or source line. They are written to `<name>.tex`, a ready `figure` environment, and LaTeX numbers it. `frame()` takes `title` (required, and it must state a finding: "Demand fell 4% in a year", not "Demand chart"), and optionally `units`, `cadence`, `source`, `asof`, `licence` and `subtitle`. Given fields are validated; `ps.REQUIRE` makes more of them mandatory (for example `("title", "source", "asof")`), and `ps.UNITS` can restrict the allowed unit spellings. Five more switches (`ASOF_ZONES`, `CADENCE_PATTERN`, `SOURCE_SHAPE`, `LICENCE_CHECK`, `SAVE_GUARD`, documented at the top of `paper_style.py`) let a repository tighten the provenance rules further. The caption reads: finding, then the subtitle (where panels are explained, "(a) ... (b) ..."), then `Units: GW; weekly.`, then `Source: Table 4 (D-1); CC BY 4.0; as of 2026-11-04 15:30 UTC.` Dates are `YYYY-MM-DD` or `YYYY-MM-DD HH:MM ZONE`; never invent a clock time you do not know. `%`, `&`, `_`, `<`, `>`, `|` and symbols are escaped for pdflatex (needs `graphicx`, `amssymb`, `textcomp`). The recommended spellings work: `CO₂` becomes `CO\textsubscript{2}`, `W m⁻²` becomes `W m\textsuperscript{$-$2}`, `µg` and Greek letters, curly quotes and dashes are mapped, and Latin letters with accents pass through (LaTeX reads UTF-8). A character with no LaTeX form (CJK, emoji) prints as a bold "?" and `save()` warns, naming the character: write it in ASCII or add it to `paper_style._TEX`. Output names keep their dots: `save(fig, "x/wpsr_2026.11.04")` writes `x/wpsr_2026.11.04.pdf`; only `.pdf .png .svg .tex` are stripped. Files are written under temporary names, size-checked (PNG pixels, PDF and SVG points), and renamed only when all pass.

## Axis labels and panels

Every data axis carries a label that names the quantity and its unit, "Demand (GW)" (`frame(xlabel=, ylabel=)`, or set on the axis; `lint(fig, axis_labels=True)` reports a missing one as P7). A string labels the first column (y) or the bottom row (x); a list labels panels in reading order. A figure with two or more panels gets bold (a), (b), ... at each top-left corner, so the text can say "Fig. 4(b)". `frame()` sets the gaps between columns and rows in inches from what is drawn there (the right panel's y tick labels and axis title, the upper panel's x tick labels, the lower panel's letter and title, end labels past a panel's right edge), so a wide scale such as "240000" never prints on the panel to its left; a wider gap set with `fig.subplots_adjust(wspace=...)` before `frame()` is kept. Image, map and heat-map panels drawn with `ax.axis("off")` are panels and get letters too. An axes on top of another (`twinx`) is part of its panel: no letter, no copied label; give its scale a label of its own with `ax2.set_ylabel(...)` (`lint(axis_labels=True)` asks for it). Colour bars are not panels; mark any other helper axes with `ps.skip_panel(ax)`.

## What `lint()` checks

P0 the figure was framed and every `REQUIRE` field is present. P1 width 3.4 or 7.0 in, height at most 9 in. P2 no title, subtitle or footer on the image (also an axes title on a single-panel figure). P3 all text 6 to 9 pt. P4 the house sans-serif on every text, Type 42, DejaVu Sans maths. P5 the PNG is width by height at 300 dpi (to within one pixel, since matplotlib rounds a size like 2.26 in its own way), and PDF, SVG, PNG and TEX are byte-identical between runs (same matplotlib version). P4 also refuses a character that none of a text's fonts can draw (it would print as an empty box). P6 no text off the edge, cut at its panel edge, run into another panel (a label, a note, a panel letter, a tick label or an axis title whose box overlaps another panel's axes box; an inset's own scale inside its panel is allowed), or printed over other text (a panel letter or a facet strip over a strip or an axis title; a label in the axes, such as a bar value, over a tick label). P8 no mathtext markup shown literally (use `log_axis`). Not checked, so look: two labels inside the same axes on top of each other, text over lines, units in every label, that two series differ by more than colour. Optional desk rules, `ps.STRICT_DESK = True`: no legend box, no twin axes, no red or green anywhere (including arrows and colour maps).

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

## plotnine

A repository that writes ggplot-style code can use plotnine (install it as in VENDORING.md). `ps.theme_paper()` is `theme_minimal(base_size=8, base_family=<first installed house sans>)` with the same look: grey text, faint horizontal major grid only, grey baseline, no y ticks, bold left strip text, no plot title, subtitle or caption (they belong in the LaTeX caption), and the legend off (`theme_paper(legend=True)` puts it at the bottom without a title). `ps.from_plotnine(p, rows=1, width=ps.FULL, height=None, size=None)` draws the plot at its printed size and returns the matplotlib Figure; from there it is a matplotlib figure: `frame`, the helpers on `fig.axes`, `save`. plotnine scales line sizes by √π, so write `size=ps.gg_size(1.2)` for the 1.2 pt house line. `from_plotnine` changes two things plotnine drew: every text in one house font gets the whole fallback list (so an arrow, or the ▲ ▼ of `ps.delta`, prints instead of an empty box), and text inside a panel (`geom_text`, `annotate`) is not clipped to the panel, so an end label past the last point prints whole. Give end labels room inside the panel by widening the x scale, `p9.scale_x_continuous(expand=(0, 0, 0.2, 0))`: that works on facets too, where the next facet starts right after the panel. `theme(plot_margin_right=0.12)` (a fraction of the width) only adds room right of the last column; `frame()` keeps plotnine's layout and does not move the panels. On facets the panel letters go in front of the facet names in the strips, "(a)  Dublin"; a panel with no strip above it (the lower rows of `facet_grid("row ~ col")`) gets its letter inside its own top-left corner, with a white halo, because plotnine leaves almost no gap between rows; lint P6 reports a strip name too long for its column and a label that runs into the next facet. Never write a plotnine plot with `ggsave` or `p.save`: they bypass the size, font and caption rules, and `test_paper_style_guard.py` fails on them.

```python
import plotnine as p9
import paper_style as ps

p = (p9.ggplot(df, p9.aes("week", "gw"))
     + p9.geom_ribbon(p9.aes("week", ymin="low", ymax="high"), data=rng, inherit_aes=False,
                      fill=ps.PALETTE[2], alpha=0.22, size=0)
     + p9.geom_line(color=ps.PALETTE[0], size=ps.gg_size(1.2))
     + p9.geom_text(p9.aes(label="text"), data=last, ha="left", nudge_x=0.8, size=7.5,
                    color=ps.PALETTE[0], path_effects=ps.halo())
     + p9.scale_x_continuous(expand=(0, 0, 0.2, 0))  # room for the end label in the panel
     + p9.labs(x="Week of the year", y="Average demand (GW)")
     + ps.theme_paper())
fig = ps.from_plotnine(p)                            # 7.0 x 4.2 in; width=ps.COLUMN for 3.4 in
ps.frame(fig, title="Demand has run above its five-year range since week 32", units="GW",
         source="Grid operator, table 3 (A-12)", asof="2026-11-04")
ps.save(fig, "figures/demand")                       # .pdf .png .svg .tex, lint first
```

`samples/make_samples.py` draws the same chart in matplotlib and in plotnine (`line_band`, `line_plotnine`), plus a two-panel figure, a horizontal bar chart and four plotnine facets in one column (`facets_plotnine`: letters in the strips, end labels inside the panels, `ps.delta` triangles in the strip names).

## Notebooks and the guard

In a notebook, call `ps.show(fig)` before `save`: the Agg backend is forced, so `plt.show()` would draw nothing. Do not call `fig.savefig`, `plt.rcParams.update` or `plt.style.use` anywhere else; `test_paper_style_guard.py` fails if you do.

## Exporting for arXiv

`python export_paper_figures.py` finds every figure that `paper_style.save` wrote (a `.pdf` with a `.tex` that starts "% Written by paper_style.save"), under `--root` folders (default: the repository), and copies them to `paper/_export/figures/` (a folder name no hand-written paper uses; change it with `--out`) under unique names (`docs-img-generation.pdf`: the folder, then the stem). It checks each PDF for Type 3 fonts, unembedded fonts, encryption and size over 2 MB, and writes `preamble.tex`, `figures.tex`, `example.tex` and `MANIFEST.json`; `--check` only checks. It never overwrites a file it did not write (its files start "% Written by export_paper_figures"): if one is in the way it writes nothing, says which, and exits 2. Copy the contents of that folder next to your main `.tex` file (or compile `example.tex` inside it). In the paper: `\input{preamble}`, then `\input{figures/docs-img-generation}` where the figure goes, and refer to it as `\ref{fig:docs-img-generation}`. Upload the PDFs and `.tex` files, not the PNG or SVG. arXiv compiles with pdfLaTeX, which includes PDF figures directly.

Panels and helper axes. Only axes whose axis is switched on are panels and get a letter. A hand-made key or inset made with `fig.add_axes(...)` and `set_axis_off()` is therefore ignored; an axes with its axis on that is not data is marked `ps.skip_panel(ax)`, and an axis-off image that should carry a letter is marked `ps.as_panel(ax)`.

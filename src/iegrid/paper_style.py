"""paper_style: one file that makes a matplotlib figure fit a paper.

Standard library plus matplotlib (PIL for the PNG size check, IPython for `show` and plotnine
for `theme_paper` / `from_plotnine` are imported only when used). Python 3.9 and later. Copy
this one file into any repository.

A figure is drawn at the size it prints (3.4 in single column or 7.0 in full width), in a
sans-serif (Helvetica Neue, Helvetica, Arial, then DejaVu Sans) between 6 and 9 pt, and
leaves the finding title, units, cadence, source, licence and as-of OUT of the image: they
go into a LaTeX caption written next to the figure (`<name>.tex`). The PDF is the vector
original for arXiv or a journal (TrueType, "Type 42" fonts, never Type 3); the 300 dpi PNG
and the SVG are for a README or the web.

THE LOOK (ggplot2 `theme_minimal` as the base, as in Nature, BBC, NYT and National
Geographic figures): grey text (labels #333333, ticks #4D4D4D, notes #808080) on white; no
box (only a light #B3B3B3 baseline at the bottom); faint horizontal major gridlines behind
the data and nothing vertical; no y tick marks; bold left-aligned panel titles; 1.2 pt
lines; light bands without edges (`band`); labels drawn by the helpers carry a white halo
so they read over lines and fills. A plotnine plot gets the same look from `theme_paper()`
and becomes a paper figure through `from_plotnine(p)`, then `frame` and `save` as usual.

    import paper_style as ps

    fig, axes = ps.figure()                    # 7.0 x 4.2 in; ps.figure(width=ps.COLUMN) for 3.4 in
    axes[0][0].plot(x, y)
    ps.frame(fig, title="Demand fell 4% in a year", units="GW", source="Grid operator, table 3",
             asof="2026-11-04", ylabel="Demand (GW)", xlabel="Year")
    ps.save(fig, "figures/demand")             # demand.pdf, .png, .svg and .tex

ENFORCED by `lint()`, which `save()` runs (a figure that breaks a rule is not written):
  P0   the figure was framed, and every field named in REQUIRE is present
  P1   the figure is exactly one journal width wide (COLUMN or FULL, within 0.001 in, which is
       the same test as the PNG width in P5) and at most MAX_HEIGHT tall
  P2   no title, subtitle or footer is drawn on the image: they belong in the caption
  P3   every visible text is between MIN_FONT and MAX_FONT points
  P4   the house sans-serif on every text, no character that none of a text's fonts can
       draw (it would print as an empty box), and TrueType (Type 42) fonts in PDF and PS, so
       arXiv and journals accept the file
  P5   the PNG is exactly width x height at 300 dpi; PDF, SVG, PNG and TEX are byte-stable
  P6   no text runs off the edge of the figure, is cut at its panel edge, runs into another
       panel (a label or note, a panel letter, a tick label or an axis title whose box
       overlaps another panel's axes box), or prints over another text (a panel letter or
       strip over a strip or axis title, a label in the axes over a tick label)
  P7   (only with `lint(fig, axis_labels=True)`) every data axis has a label
  P8   no visible text carries mathtext markup (`$\\mathdefault{10^{0}}$`, `$x$`): with maths
       parsing off it would print literally. A log axis needs `log_axis(ax)`.

SWITCHES a repository may set after import (or edit in this file). The defaults are the
permissive generic ones; the energy desk's house style is the strict setting of every switch
(see VENDORING.md, "Restoring the reference rules"):
  REQUIRE        caption fields `frame` must be given. Default ("title",); for example
                 ("title", "source", "asof") makes a figure without provenance impossible.
  UNITS          None accepts any units text; a set or tuple of spellings makes `frame` refuse
                 any other, so "Mb/d" and "mb/d" cannot both appear.
  STRICT_DESK    False by default. True adds the desk rules: no legend box (label the lines at
                 their ends), no twin axes, no red or green anywhere the linter can see
                 (lines, patches, text, spines, ticks, annotation arrows, colour maps), and
                 teal and brick only on scored results (`lint(fig, scored=True)`).
  ASOF_ZONES     None accepts any zone in an as-of string; ("ET", "UTC") accepts only those.
  CADENCE_PATTERN None accepts any cadence text; a regex makes `frame` refuse a cadence that
                 does not match it.
  SOURCE_SHAPE   False by default. True demands a source of 12 or more characters that
                 contains a digit or "(", so a bare agency name is refused.
  LICENCE_CHECK  None, or a function(licence) that raises ValueError for a licence the
                 repository does not allow.
  LEGACY_PREFIX  None, or a short name such as "hs" for a repository whose own code reads
                 fig._hs_frame, fig._hs_licence and the gids "hs-panel", "hs-skip", "hs-title":
                 `frame` then also sets those two attributes, and letters and skipped axes
                 carry the "hs-" gids ("ps-" gids are always recognised as well).
  SAVE_GUARD     None, or a function(path, fields) that `save` calls before writing and that
                 raises ValueError to refuse a destination (for example "non-public licences
                 may only be written under .local/").

NOT ENFORCED, so check by eye: that two series differ by more than colour (give them dashes
or markers: `series_style(i)`), two labels inside the same axes on top of each other, text
over lines or marks, and that each axis label carries its unit.

Notes. Axes that sit exactly on top of another (twinx, twiny) are not panels: they get no
panel letter and no automatic axis label, and `lint(axis_labels=True)` asks for their label.
An axes that is not a data panel (a hand-made legend or inset on the figure) is excluded
with `skip_panel(ax)`. An axes whose axis is switched off (`set_axis_off`, an image, a hand-drawn
key) is not a panel and gets no letter, as in the energy house style; `as_panel(ax)` makes
an axis-off image panel count. `save` pins the rcParams that decide the file size, so an ambient
`savefig.bbox = "tight"` or `figure.autolayout = True` cannot change the printed size.
"""

import math
import os
import re
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from textwrap import fill

# ------------------------------------------------------------------ switches

REQUIRE = ("title", "source", "asof")
UNITS = None
STRICT_DESK = False
ASOF_ZONES = None
CADENCE_PATTERN = None
SOURCE_SHAPE = False
LICENCE_CHECK = None
SAVE_GUARD = None
LEGACY_PREFIX = None
# A title that ends in one of these words names a series; it does not state a finding.
TITLE_BAD_ENDINGS = (
    "chart",
    "plot",
    "graph",
    "figure",
    "series",
    "data",
    "prices",
    "stocks",
    "overview",
    "comparison",
)

# ------------------------------------------------------------------- tokens

TOKENS = {
    "bg": "#FFFFFF",
    "surface": "#F5F7FA",
    "border": "#DCE3EC",
    # Text at about 80% grey, as in ggplot2 and newsroom graphics: labels and annotations,
    # tick labels, then guide or muted text (#808080 is 3.9:1 on white: notes, not data).
    "text": "#333333",
    "text_ticks": "#4D4D4D",
    "text_muted": "#808080",
    "rule": "#B3B3B3",  # the baseline (bottom spine) and the x tick marks
    "grid": "#E5E5E5",  # faint horizontal gridlines
    "accent": "#1F5FBF",
    "state_hit": "#16707A",
    "state_miss": "#B23A2C",
    "state_frozen": "#5E6B7D",
    "state_stale": "#8A5A00",
    "series_1": "#0F2A4A",
    "series_2": "#1F5FBF",
    "series_3": "#7D8996",
}

# Colour-blind-safe categorical palette. The first three are the house navy, accent blue and
# grey; the rest are Okabe and Ito (2008). Checked under protan, deutan and tritan
# simulation (Machado 2009): all pairs among the first four are well separated; the
# neighbouring pairs of all six are too. Two non-neighbours stay close for some viewers
# (grey with purple under protan, sky with grey for everyone), and navy with blue is close in
# greyscale, so a figure with more than four series, or one that will be printed in black
# and white, must also use dashes, markers or direct labels: `series_style(i)`.
PALETTE = (
    "#0F2A4A",  # navy
    "#1F5FBF",  # accent blue
    "#7D8996",  # grey
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#CC79A7",  # reddish purple
    "#F0E442",  # yellow: 1.3:1 on white, so only as a filled mark with a dark edge
)
YELLOW = PALETTE[6]
CYCLE = PALETTE[:6]  # the axes colour cycle; a seventh series is a sign to use small multiples
DASHES = (
    "-",
    (0, (5, 2)),
    (0, (1, 1.5)),
    (0, (5, 1.5, 1, 1.5)),
    (0, (3, 1, 1, 1, 1, 1)),
    (0, (8, 2, 1, 2)),
    "-",
)
MARKERS = ("o", "s", "^", "D", "v", "P", "X")

# Diverging scale (cold blue to warm brown through white). No red, no green.
DIVERGING = ("#1F5FBF", "#8FB3E6", "#FFFFFF", "#D9B98C", "#8A5A00")

# ----------------------------------------------------------------- geometry

# A figure is drawn at the size it prints. COLUMN fits one column of a two-column template
# (8.6 cm), FULL spans the page (17.8 cm) and is what an arXiv `article` scales to
# \linewidth. The 0.0001 in excess keeps int() from rounding 2099.99 px down to 2099.
COLUMN = 3.4
FULL = 7.0
HEIGHT = 4.2  # default height of a one-row full-width figure (5:3)
MAX_HEIGHT = 9.0  # a figure plus its caption must fit a page
DPI = 300
MIN_FONT, MAX_FONT = 6.0, 9.0  # points, every visible text
FORMATS = ("pdf", "png", "svg", "tex")
MINUS = "\u2212"
MARK = "% Written by paper_style.save"  # first characters of every .tex the exporter accepts
_EPS = 0.0001
_WIDTH_TOL = 0.001  # inches; P1 and the PNG width check use the same tolerance (0.3 px)


def _prefixes():
    """Name prefixes of the gids this module sets and reads: "ps", and LEGACY_PREFIX if set."""
    return ("ps",) if not LEGACY_PREFIX else ("ps", str(LEGACY_PREFIX))


def _gid(kind):
    """The gid written on an artist of this kind ("panel", "page-caption"): the legacy one if set."""
    return f"{LEGACY_PREFIX or 'ps'}-{kind}"


def _gids(kind):
    return tuple(f"{p}-{kind}" for p in _prefixes())


def default_size(rows=1, width=FULL):
    """Printed size of a figure with `rows` stacked panels: 4.2 in, plus 1.5 in per extra row."""
    return (width + _EPS, min(HEIGHT + 1.5 * (rows - 1), MAX_HEIGHT) + _EPS)


SIZE = default_size()

# Sans-serif, as in ggplot2 and Nature figures: Helvetica Neue, Helvetica, Arial, then
# DejaVu Sans, which ships with matplotlib and has every glyph used here (matplotlib falls
# back to it glyph by glyph, so a minus or an arrow missing from Helvetica still prints).
_FONT_PREFERENCE = ("Helvetica Neue", "Helvetica", "Arial")
FALLBACK_FONT = "DejaVu Sans"


def _installed_fonts():
    """Preferred sans-serif fonts that exist on this machine, then DejaVu Sans."""
    from matplotlib import font_manager

    have = {f.name for f in font_manager.fontManager.ttflist}
    return [f for f in _FONT_PREFERENCE if f in have] + [FALLBACK_FONT]


def house_font():
    """The first house sans-serif installed here (what `theme_paper` names first to plotnine)."""
    return _installed_fonts()[0]


def _family_list(family):
    """A family name or list, followed by the rest of the house list, down to DejaVu Sans."""
    names = [family] if isinstance(family, str) else list(family)
    return names + [f for f in _installed_fonts() if f not in names]


# rcParams that decide the file size or the text engine. A repository matplotlibrc, a style
# file or a notebook may set any of them; `apply` resets them and `save` and `lint` re-pin
# them for the moment they run, so the printed size cannot depend on ambient configuration.
_PINNED = {
    "savefig.bbox": "standard",  # "tight" crops the page: a 7.0 in figure becomes 5.97 in
    "savefig.pad_inches": 0.1,
    "savefig.transparent": False,
    "savefig.facecolor": "auto",
    "savefig.edgecolor": "auto",
    "figure.autolayout": False,  # a layout engine ignores the margins `frame` sets
    "figure.constrained_layout.use": False,
    "text.usetex": False,  # needs a TeX install and changes every glyph
}


def apply():
    """Set rcParams once per process and force the Agg backend. Idempotent."""
    import matplotlib.pyplot as plt
    from matplotlib import cycler

    # Always the non-interactive Agg renderer: a GUI backend (macOS) rescales the DPI
    # and gives 1599-pixel files, and output must not depend on the machine.
    plt.switch_backend("Agg")
    t = TOKENS
    plt.rcParams.update(
        {
            **_PINNED,
            # A list, not one name: matplotlib falls back per glyph, so symbols such as
            # arrows come from DejaVu when the first font lacks them. Only installed fonts
            # are listed, so there are no "findfont" warnings.
            "font.family": _installed_fonts(),
            # "$2.67/bbl ... $0.79" must not turn into maths italics. Write units with
            # Unicode (m\u00b3, \u00b5g, CO\u2082), not with $...$.
            "text.parse_math": False,
            # Same input, same bytes: stable ids and no embedded date or version.
            "svg.hashsalt": "paper-style",
            # Glyph outlines, not font names: an SVG then looks the same on every machine.
            "svg.fonttype": "path",
            # TrueType (Type 42) in PDF and PS. Matplotlib's default is Type 3, which arXiv
            # accepts but IEEE/ACM checkers reject and which does not select cleanly.
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "mathtext.fontset": "dejavusans",
            "figure.facecolor": t["bg"],
            "figure.dpi": 100,
            "savefig.dpi": DPI,
            "axes.facecolor": t["bg"],
            # No box: left, top and right spines off; a light baseline at the bottom.
            "axes.edgecolor": t["rule"],
            "axes.linewidth": 0.6,
            "axes.spines.left": False,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.bottom": True,
            "axes.labelcolor": t["text"],
            "axes.labelsize": 8,
            "axes.labelpad": 4,
            # Panel titles as ggplot2 facet strips: left, bold, 8 pt (one panel: no title, P2).
            "axes.titlesize": 8,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.titlecolor": t["text"],
            "axes.titlepad": 5,
            # Faint horizontal major gridlines only, behind the data.
            "axes.grid": True,
            "axes.grid.axis": "y",
            "axes.grid.which": "major",
            "axes.axisbelow": True,  # grid lines run behind bars, not across them
            "axes.prop_cycle": cycler(color=list(CYCLE)),
            "grid.color": t["grid"],
            "grid.linewidth": 0.5,
            "grid.linestyle": "-",
            "grid.alpha": 1.0,
            # Short grey x ticks; no y tick marks (the gridlines carry the y values).
            "xtick.color": t["rule"],
            "ytick.color": t["rule"],
            "xtick.labelcolor": t["text_ticks"],
            "ytick.labelcolor": t["text_ticks"],
            "xtick.major.size": 2.5,
            "ytick.major.size": 0,
            "xtick.minor.size": 1.5,
            "ytick.minor.size": 0,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.major.pad": 2.5,
            "ytick.major.pad": 3,
            "xtick.minor.visible": False,
            "ytick.minor.visible": False,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "font.size": 8,
            "text.color": t["text"],
            # Marks: 1.2 pt lines, 3.5 pt markers, bars and fills without edges.
            "lines.linewidth": 1.2,
            "lines.markersize": 3.5,
            "patch.linewidth": 0.0,
            "legend.frameon": False,
            "legend.fontsize": 7,
            "legend.title_fontsize": 7,
            "legend.labelcolor": t["text"],
            "axes.unicode_minus": True,
        }
    )


def series_style(i, *, marker=False):
    """Keyword arguments for the i-th series: colour plus a dash (and a marker if asked).

    `ax.plot(x, y, **ps.series_style(1))`. Use it when more than three lines share a panel
    or the figure may be printed in greyscale. The yellow of slot 6 gets a dark marker edge
    and a marker, because a yellow line alone is invisible on white.
    """
    k = i % len(PALETTE)
    colour = PALETTE[k]
    style = {"color": colour, "linestyle": DASHES[k]}
    if marker or colour == YELLOW:
        style.update(
            marker=MARKERS[k],
            markersize=3.5,
            markeredgecolor=TOKENS["text"] if colour == YELLOW else colour,
            markeredgewidth=0.6,
        )
    return style


def signed(v, digits=1):
    """+1.2 / \u22121.2 with a true minus sign."""
    return f"{v:+.{digits}f}".replace("-", MINUS)


def delta(v, unit, digits=1):
    """Direction as an arrow and a sign, never colour alone: '\u25bc \u22123.2 mb'."""
    arrow = "\u25b2" if v > 0 else "\u25bc" if v < 0 else "\u25cf"
    return f"{arrow} {signed(v, digits)} {unit}"


# ------------------------------------------------------------------- figure


def figure(rows=1, cols=1, *, sharex=True, height_ratios=None, size=None, width=FULL):
    """A figure at its printed size with stacked panels on a shared x axis.

    Returns (fig, axes) with axes always a 2-D array: `axes[0][0]`. `width` is COLUMN or
    FULL (lint P1); the height follows the number of rows. Pass `size` only to break
    the format on purpose (lint P1 then reports it).
    """
    import matplotlib.pyplot as plt

    apply()
    size = size or default_size(rows, width)
    kw = {"gridspec_kw": {"height_ratios": height_ratios}} if height_ratios else {}
    fig, axes = plt.subplots(
        rows, cols, sharex=sharex, figsize=size, squeeze=False, **kw
    )
    return fig, axes


# ------------------------------------------------------------------ framing

_ASOF = re.compile(
    r"^(\d{4}-\d{2}-\d{2})"
    r"(?:(?: (\d{2}:\d{2}) (UTC(?:[+-]\d{2}:\d{2})?|[A-Z]{2,5}))| \(est\.\))?\Z",
    re.ASCII,
)
_FIELDS = ("title", "source", "asof", "units", "cadence", "licence", "subtitle", "xlabel", "ylabel")


def _clean(text):
    return " ".join(str(text).split())


def _sentence(text):
    """`text` as one sentence: trimmed, and ended with a full stop unless it already has a mark."""
    s = _clean(text)
    return s if s.endswith((".", "!", "?")) else s + "."


def parse_asof(text):
    """Validate an as-of string as a real date, or a real date and time with a zone.

    Accepted: 'YYYY-MM-DD' (release time unknown: do not invent one), 'YYYY-MM-DD HH:MM UTC',
    'YYYY-MM-DD HH:MM ET' (any 2 to 5 capital letters, or UTC+05:30), and
    'YYYY-MM-DD (est.)' for a date that is itself an estimate.
    """
    m = _ASOF.match(str(text))
    if not m:
        raise ValueError(
            f"as-of {text!r} must read 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM ZONE' (UTC, ET, UTC+01:00)"
        )
    day, clock, zone = m.groups()
    try:
        datetime.strptime(f"{day} {clock or '00:00'}", "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ValueError(f"as-of {text!r} is not a real date and time: {exc}") from exc
    if ASOF_ZONES is not None and zone and zone not in ASOF_ZONES:
        raise ValueError(f"as-of {text!r}: zone must be one of {tuple(ASOF_ZONES)} (paper_style.ASOF_ZONES)")
    return str(text)


def _to_new_york(when):
    from zoneinfo import ZoneInfo  # Python 3.9 and later

    return when.astimezone(ZoneInfo("America/New_York"))


def _asof_text(asof):
    """A string, a date or an aware datetime as a checked as-of string."""
    if isinstance(asof, datetime):
        if asof.tzinfo is None or asof.utcoffset() is None:
            raise ValueError(
                "as-of datetime has no timezone: pass an aware datetime or a string"
            )
        off = asof.utcoffset()
        if off == timedelta(0):
            zone = "UTC"
        elif ASOF_ZONES is not None:
            if "ET" not in ASOF_ZONES:
                raise ValueError(f"as-of zone must be one of {tuple(ASOF_ZONES)}: pass a UTC datetime")
            asof, zone = _to_new_york(asof), "ET"  # the repository names New York time ET
        else:
            name = asof.tzname() or ""
            if re.fullmatch(r"[A-Z]{2,5}", name):
                zone = name
            else:
                mins = int(off.total_seconds() // 60)
                sign = "+" if mins >= 0 else "-"
                zone = f"UTC{sign}{abs(mins) // 60:02d}:{abs(mins) % 60:02d}"
        when = f"{asof.strftime('%Y-%m-%d %H:%M')} {zone}"
    elif isinstance(asof, date):
        when = asof.isoformat()
    else:
        when = str(asof)
    return parse_asof(when)


def check_units(units):
    """Units as one text ('mb, %'), checked against UNITS when a repository sets it."""
    if units is None:
        return None
    if isinstance(units, str):
        items = [units]
    else:
        try:
            items = list(units)
        except TypeError:
            raise ValueError(f"units {units!r} must be a string or a list of strings") from None
    out = []
    for u in items:
        if not isinstance(u, str) or not u.strip():
            raise ValueError(f"units {units!r} must be a string or a list of strings")
        if UNITS is not None and u not in UNITS:
            raise ValueError(
                f"units {u!r} is not an allowed spelling; paper_style.UNITS allows {sorted(UNITS)}"
            )
        out.append(_clean(u))
    return ", ".join(out) or None


def _text_field(name, value):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} {value!r} must be a non-empty string")
    return _clean(value)


def _check_title(title):
    t = _text_field("title", title)
    if not t:
        raise ValueError("title is required: state the finding")
    words = t.rstrip(".").split()
    last = words[-1].lower() if words else ""
    if len(words) < 3 or last in TITLE_BAD_ENDINGS:
        raise ValueError(
            f"title {t!r} must state a finding (a claim with a number or a verb), not name the series"
        )
    return t


def _no_layout_engine(fig):
    """Remove a constrained or tight layout engine: it would override the margins `frame` sets."""
    import matplotlib.pyplot as plt

    if hasattr(fig, "set_layout_engine"):  # matplotlib 3.6 and later
        with plt.rc_context(_PINNED):
            fig.set_layout_engine(None)
    else:
        fig.set_tight_layout(False)
        fig.set_constrained_layout(False)


def _check_given(given):
    """The optional repository rules on the fields that were given (CADENCE_PATTERN etc.)."""
    if CADENCE_PATTERN and given["cadence"] and not re.match(CADENCE_PATTERN, given["cadence"]):
        raise ValueError(
            f"cadence {given['cadence']!r} must match paper_style.CADENCE_PATTERN {CADENCE_PATTERN!r}"
        )
    src = given["source"]
    if SOURCE_SHAPE and src and (len(src) < 12 or not re.search(r"[0-9(]", src)):
        raise ValueError(
            f"source {src!r} must name the table or series id (12 or more characters, "
            "with a digit or a bracket), not just an agency (paper_style.SOURCE_SHAPE)"
        )
    if LICENCE_CHECK is not None and given["licence"] is not None:
        LICENCE_CHECK(given["licence"])


def frame(
    fig,
    *,
    title,
    source=None,
    asof=None,
    units=None,
    cadence=None,
    licence=None,
    subtitle=None,
    xlabel=None,
    ylabel=None,
    margins=None,
):
    """Record the caption fields, lay out the panels and label them (P2: nothing is drawn).

    Nothing is drawn on the image for the title, units, cadence, source or as-of: a paper
    puts them in the caption, and `save()` writes that caption to `<name>.tex`.

    `title`    states the finding ("Demand fell 4% in a year"); required.
    `source`   the table or series id, not only an agency.
    `asof`     'YYYY-MM-DD', 'YYYY-MM-DD HH:MM UTC', a date or a timezone-aware datetime.
    `units`    a spelling, or a list of them ("GW", ("mb", "%")); checked against UNITS if set.
    `cadence`  'weekly, Wednesday 10:30 ET'.   `licence`  'CC BY 4.0'.
    `subtitle` what the axes show, or "(a) ... (b) ..." for panels: sentence 2 of the caption.
    `ylabel` / `xlabel` label the data panels that have no label yet: a string goes on every
    first column (y) or bottom row (x); a list goes on the panels in reading order. Write
    them with units, "Demand (GW)", because a paper figure must read without its caption.
    `margins` (left, right, top, bottom) in inches; default (0.6, 18% of width, 0.2, 0.5) with
    the right margin left free for end labels.

    Fields named in REQUIRE must be given; every field that is given is validated.
    """
    given = {
        "title": _check_title(title),
        "source": _text_field("source", source),
        "asof": _asof_text(asof) if asof is not None else None,
        "units": check_units(units),
        "cadence": _text_field("cadence", cadence),
        "licence": _text_field("licence", licence),
        "subtitle": _text_field("subtitle", subtitle),
        "xlabel": xlabel,
        "ylabel": ylabel,
    }
    for name in tuple(REQUIRE) + ("title",):
        if name not in _FIELDS:
            raise ValueError(f"REQUIRE names {name!r}; the fields are {_FIELDS}")
        if not given[name]:
            raise ValueError(f"{name} is required (paper_style.REQUIRE = {tuple(REQUIRE)})")
    _check_given(given)
    from_gg = getattr(fig, "_ps_plotnine", False)
    if from_gg and margins is not None:
        raise ValueError(
            "a plotnine figure keeps the layout plotnine computed: set its margins in the plot "
            "(theme(plot_margin_right=0.14)), not with frame(margins=...)"
        )
    fig._ps_frame = {k: given[k] for k in _FIELDS[:7]}
    if LEGACY_PREFIX:  # a repository whose own code reads fig._<prefix>_frame / _<prefix>_licence
        setattr(fig, f"_{LEGACY_PREFIX}_frame", fig._ps_frame)
        setattr(fig, f"_{LEGACY_PREFIX}_licence", given["licence"])
    _no_layout_engine(fig)
    if from_gg:  # plotnine placed panels, strips and legend itself: moving the axes would split them
        axis_labels(fig, xlabel, ylabel)
        panel_letters(fig)
        for ax in fig.axes:
            _fit_bar_labels(ax)
        return fig
    w, h = fig.get_size_inches()
    # Margins in inches so they mean the same on a column and a full-width figure.
    left, right, top, bottom = margins or (
        min(0.6, 0.17 * w),
        min(1.3, 0.18 * w),  # room for a sans end label: "Demand · 424.1 · Oct 30"
        0.2,
        0.5,
    )
    fig.subplots_adjust(
        top=1 - top / h, bottom=bottom / h, left=left / w, right=1 - right / w
    )
    axis_labels(fig, xlabel, ylabel)
    panel_letters(fig)
    _space_panels(fig)
    for ax in fig.axes:  # the margins changed the axes size: bar labels may need more room
        _fit_bar_labels(ax)
    return fig


_GAP_PAD = 0.08  # inches of white between one panel's labels and the next panel
_MIN_PANEL = 0.6  # inches: the gaps never squeeze a panel narrower or shorter than this


def _space_panels(fig, rounds=2):
    """Set wspace and hspace in inches, from what is drawn between the panels.

    The gap between two columns holds the right panel's y tick labels and axis title (and
    anything the left panel draws past its right edge: end labels, a twin's scale); the gap
    between two rows holds the upper panel's x tick labels and title and the lower panel's
    letter and title. A gap the caller set wider (`subplots_adjust(wspace=...)`) is kept.
    Only figures whose panels sit on one grid (`figure`, `plt.subplots`) are spaced.
    """
    axes = [a for a in fig.axes if a.get_visible() and a.get_subplotspec() is not None]
    grids = {id(a.get_subplotspec().get_gridspec()) for a in axes}
    if len(grids) != 1:
        return
    gs = axes[0].get_subplotspec().get_gridspec()
    nrows, ncols = gs.get_geometry()
    if nrows == 1 and ncols == 1:
        return
    w, h = fig.get_size_inches()
    for _ in range(rounds):
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        dpi = fig.dpi
        need_l = need_r = need_t = need_b = 0.0  # inches past the axes, by side
        for a in axes:
            spec = a.get_subplotspec()
            box = a.get_window_extent(r)
            tight = a.get_tightbbox(r)
            if tight is None:
                continue
            if spec.colspan.start > 0:
                need_l = max(need_l, (box.x0 - tight.x0) / dpi)
            if spec.colspan.stop < ncols:
                need_r = max(need_r, (tight.x1 - box.x1) / dpi)
            if spec.rowspan.start > 0:
                need_t = max(need_t, (tight.y1 - box.y1) / dpi)
            if spec.rowspan.stop < nrows:
                need_b = max(need_b, (box.y0 - tight.y0) / dpi)
        sp = fig.subplotpars
        changed = {}
        for key, n, span, space, need in (
            ("wspace", ncols, (sp.right - sp.left) * w, sp.wspace, need_l + need_r),
            ("hspace", nrows, (sp.top - sp.bottom) * h, sp.hspace, need_t + need_b),
        ):
            if n < 2:
                continue
            gap_now = space * span / (n + (n - 1) * space)
            gap = max(gap_now, need + _GAP_PAD)
            gap = min(gap, max(gap_now, (span - n * _MIN_PANEL) / (n - 1)))
            changed[key] = gap / ((span - (n - 1) * gap) / n)
        if not changed:
            return
        if all(abs(changed[k] - getattr(sp, k)) < 1e-3 for k in changed):
            return
        fig.subplots_adjust(**changed)


def skip_panel(ax):
    """Mark `ax` as not a data panel (a hand-made legend or inset): no letter, no auto label."""
    ax.set_gid(_gid("skip"))
    return ax


def as_panel(ax):
    """Count a switched-off axes (an image or map panel) as a data panel: it gets a letter."""
    ax._ps_as_panel = True
    return ax


def _panels(fig):
    """The data panels in reading order (top to bottom, then left to right).

    Colour bars and axes marked with `skip_panel` are not panels. An axes that sits exactly
    on an earlier one (`twinx`, `twiny`) is the same panel, so it gets no letter of its own.
    An axes that is switched off (`set_axis_off`, an image or map, or a helper axes that only
    holds a hand-drawn key) is not a panel either, as in the energy house style; mark an
    axis-off image that should get a letter with `as_panel(ax)`.
    """
    out, seen = [], set()
    for ax in fig.axes:
        if not ax.get_visible() or ax.get_label() == "<colorbar>" or ax.get_gid() in _gids("skip"):
            continue
        if not ax.axison and not getattr(ax, "_ps_as_panel", False):
            continue
        key = tuple(round(v, 3) for v in ax.get_position().bounds)
        if key in seen:
            continue
        seen.add(key)
        out.append(ax)
    return sorted(
        out,
        key=lambda a: (-round(a.get_position().y1, 2), round(a.get_position().x0, 2)),
    )


def axis_labels(fig, xlabel=None, ylabel=None):
    """Label the data panels that have no label yet (what `frame(xlabel=, ylabel=)` calls).

    A string labels every panel of the first column (y) or of the bottom row (x); a list
    labels the panels in reading order. A label already set on an axis is never replaced.
    Panels whose axes are switched off (images) and twin axes are not labelled: set the
    label of a twin's own scale by hand (`ax2.set_ylabel`).
    """
    gg = getattr(fig, "_ps_gg_titles", None)
    if gg is not None:  # plotnine: one axis title per figure, drawn by plotnine; reword it
        for name, label in (("x", xlabel), ("y", ylabel)):
            if label is None:
                continue
            if not isinstance(label, str):
                raise ValueError(
                    f"a plotnine figure has one {name} axis title: pass a string, or write "
                    f"labs({name}=...) in the plot"
                )
            if gg.get(name) is None:
                raise ValueError(
                    f"the plotnine figure draws no {name} axis title (is axis_title_{name} "
                    f"blank?); write labs({name}=...) and keep the title"
                )
            gg[name].set_text(label)
        return
    panels = _panels(fig)
    if not panels:
        return
    left = min(round(a.get_position().x0, 2) for a in panels)
    bottom = min(round(a.get_position().y0, 2) for a in panels)
    if ylabel is not None:
        names = [ylabel] * len(panels) if isinstance(ylabel, str) else list(ylabel)
        for ax, name in zip(panels, names):
            if not name or ax.get_ylabel() or not ax.axison:
                continue
            if isinstance(ylabel, str) and round(ax.get_position().x0, 2) != left:
                continue  # one string labels the first column only
            ax.set_ylabel(name)
    if xlabel is not None:
        names = [xlabel] * len(panels) if isinstance(xlabel, str) else list(xlabel)
        for ax, name in zip(panels, names):
            if not name or ax.get_xlabel() or not ax.axison:
                continue
            if isinstance(xlabel, str) and round(ax.get_position().y0, 2) != bottom:
                continue  # one string labels the bottom row only
            ax.set_xlabel(name)


def _top_strips(fig):
    """plotnine facet strips above each axes: {axes: the topmost strip text over it}."""
    from matplotlib.text import Text

    out = {}
    for t in fig.findobj(Text):  # plotnine adds strips as figure artists, not to fig.texts
        info = getattr(t, "draw_info", None)
        ax = getattr(info, "ax", None)
        if ax is None or getattr(info, "position", None) != "top":
            continue
        if not hasattr(t, "_ps_strip"):
            t._ps_strip = t.get_text()  # the facet name as plotnine wrote it
        y = t.get_position()[1]
        if ax not in out or y > out[ax].get_position()[1]:
            out[ax] = t
    return out


def panel_letters(fig):
    """Bold (a), (b), ... above the top-left corner of each panel of a multi-panel figure.

    On a plotnine figure the letter goes in front of the facet name in the strip above the
    panel ("(a)  Dublin"), because plotnine leaves only a small gap between facets: a letter
    in that gap would print over the strip of the facet to its left and over the y axis
    title. A plotnine panel with no strip above it (the lower rows of `facet_grid`) gets the
    letter inside its own top-left corner, with a white halo: plotnine leaves almost no gap
    between rows, so a letter above the panel would print on the bottom of the panel above.
    On a matplotlib figure the letter sits above the top-left corner and `frame` leaves room
    for it between the rows. Lint P6 reports a letter that lands on other text or on another
    panel.
    """
    panels = _panels(fig)
    for ax in fig.axes:  # framing twice must not stack a second set of letters
        for t in list(ax.texts):
            if t.get_gid() in _gids("panel"):
                t.remove()
    from_gg = getattr(fig, "_ps_plotnine", False)
    strips = _top_strips(fig) if from_gg else {}
    for t in strips.values():
        t.set_text(t._ps_strip)
        t._ps_letter = None
    if len(panels) < 2:
        return
    for i, ax in enumerate(panels[:26]):
        letter = f"({chr(ord('a') + i)})"
        strip = strips.get(ax)
        if strip is not None:
            strip.set_text(f"{letter}  {strip._ps_strip}")
            strip._ps_letter = letter
            continue
        if from_gg:  # no strip and no gap above: inside the panel's own top-left corner
            ax.annotate(
                letter,
                xy=(0, 1),
                xycoords="axes fraction",
                xytext=(3, -3),
                textcoords="offset points",
                ha="left",
                va="top",
                fontsize=8,
                fontweight="bold",
                color=TOKENS["text"],
                annotation_clip=False,
                path_effects=halo(),
                zorder=10,
                gid=_gid("panel"),
            )
            continue
        ax.annotate(
            letter,
            xy=(0, 1),
            xycoords="axes fraction",
            xytext=(-1, 3),
            textcoords="offset points",
            ha="right",
            va="bottom",
            fontsize=8,
            fontweight="bold",
            color=TOKENS["text"],
            annotation_clip=False,
            gid=_gid("panel"),
        )


# ------------------------------------------------------------------ caption

_TEX = {
    # TeX's own special characters.
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    # Under the default OT1 encoding these three print as inverted marks and a dash.
    "<": r"\textless{}",
    ">": r"\textgreater{}",
    "|": r"\textbar{}",
    # Minus, hyphens, dashes, quotes, spaces.
    MINUS: "$-$",
    "\u2010": "-",
    "\u2011": r"\mbox{-}",
    "\u2012": "--",
    "\u2013": "--",
    "\u2014": "---",
    "\u2015": "---",
    "\u2018": "`",
    "\u2019": "'",
    "\u201a": r"\quotesinglbase{}",
    "\u201c": "``",
    "\u201d": "''",
    "\u201e": r"\quotedblbase{}",
    "\u2039": r"\guilsinglleft{}",
    "\u203a": r"\guilsinglright{}",
    "\u00ab": r"\guillemotleft{}",
    "\u00bb": r"\guillemotright{}",
    "\u2026": r"\ldots{}",
    "\u2022": r"\textbullet{}",
    "\u00a0": "~",
    "\u2002": r"\enspace{}",
    "\u2003": r"\quad{}",
    "\u2009": r"\,",
    "\u202f": r"\,",
    "\u200b": "",
    "\u2060": "",
    "\ufeff": "",
    "\u00ad": r"\-",
    # Units, currency and symbols that the textcomp package prints.
    "\u00b5": r"\textmu{}",
    "\u00b7": r"\textperiodcentered{}",
    "\u00b0": r"\textdegree{}",
    "\u2103": r"\textcelsius{}",
    "\u2116": r"\textnumero{}",
    "\u2030": r"\textperthousand{}",
    "\u20ac": r"\texteuro{}",
    "\u00a3": r"\pounds{}",
    "\u00a5": r"\textyen{}",
    "\u00a2": r"\textcent{}",
    "\u00a4": r"\textcurrency{}",
    "\u00a9": r"\textcopyright{}",
    "\u00ae": r"\textregistered{}",
    "\u2122": r"\texttrademark{}",
    "\u00a7": r"\S{}",
    "\u00b6": r"\P{}",
    "\u00a1": r"\textexclamdown{}",
    "\u00bf": r"\textquestiondown{}",
    "\u00bd": r"\textonehalf{}",
    "\u00bc": r"\textonequarter{}",
    "\u00be": r"\textthreequarters{}",
    "\u00aa": r"\textordfeminine{}",
    "\u00ba": r"\textordmasculine{}",
    "\u00ac": r"\textlnot{}",
    "\u00a6": r"\textbrokenbar{}",
    "\u00a8": r"\textasciidieresis{}",
    "\u00af": r"\textasciimacron{}",
    "\u00b4": r"\textasciiacute{}",
    # Maths symbols.
    "\u00d7": r"$\times$",
    "\u00f7": r"$\div$",
    "\u00b1": r"$\pm$",
    "\u2213": r"$\mp$",
    "\u2265": r"$\geq$",
    "\u2264": r"$\leq$",
    "\u2260": r"$\neq$",
    "\u2248": r"$\approx$",
    "\u223c": r"$\sim$",
    "\u226a": r"$\ll$",
    "\u226b": r"$\gg$",
    "\u221e": r"$\infty$",
    "\u221d": r"$\propto$",
    "\u221a": r"$\surd$",
    "\u2202": r"$\partial$",
    "\u2211": r"$\sum$",
    "\u2206": r"$\Delta$",
    "\u2219": r"$\cdot$",
    "\u22c5": r"$\cdot$",
    "\u2032": "$'$",
    "\u2033": "$''$",
    "\u2190": r"$\leftarrow$",
    "\u2192": r"$\rightarrow$",
    "\u2191": r"$\uparrow$",
    "\u2193": r"$\downarrow$",
    "\u2194": r"$\leftrightarrow$",
    "\u21d2": r"$\Rightarrow$",
    "\u25b2": r"$\blacktriangle$",
    "\u25bc": r"$\blacktriangledown$",
    "\u25cf": r"$\bullet$",
}
# Greek letters as maths (a capital that looks like a Latin capital becomes that letter).
for _c, _n in zip(
    "\u03b1\u03b2\u03b3\u03b4\u03b5\u03b6\u03b7\u03b8\u03b9\u03ba\u03bb\u03bc\u03bd\u03be\u03c0"
    "\u03c1\u03c2\u03c3\u03c4\u03c5\u03c6\u03c7\u03c8\u03c9\u0393\u0394\u0398\u039b\u039e\u03a0"
    "\u03a3\u03a6\u03a8\u03a9",
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi pi rho varsigma sigma "
    "tau upsilon phi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Phi Psi Omega".split(),
):
    _TEX[_c] = "$\\%s$" % _n
for _c, _n in zip("\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c\u039d\u039f\u03a1\u03a4\u03a5\u03a7", "ABEZHIKMNOPTYX"):
    _TEX[_c] = "$%s$" % _n
_TEX["\u03bf"] = "$o$"

# Super- and subscript digits and signs (CO\u2082, m\u207b\u00b2, 10\u2076). A run becomes one \textsuperscript or
# \textsubscript, which is what LaTeX can print without a maths font.
_SUP = dict(zip("\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079\u207a\u207b\u207c\u207d\u207e\u2071\u207f", "0123456789+-=()in"))
_SUB = dict(zip("\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089\u208a\u208b\u208c\u208d\u208e", "0123456789+-=()"))
_SCRIPTS = re.compile(
    "(?P<sup>[%s]+)|(?P<sub>[%s]+)|(?P<one>.)" % ("".join(_SUP), "".join(_SUB)), re.DOTALL
)


def _script_tex(chars):
    return "".join("$-$" if c == "-" else c for c in chars)


def _tex_char(c, bad):
    """One character in LaTeX. Latin-1 and Latin Extended-A letters pass: inputenc utf8 reads them."""
    mapped = _TEX.get(c)
    if mapped is not None:
        return mapped
    if ord(c) < 128 or 0xC0 <= ord(c) <= 0x17F:
        return c
    bad.append(c)
    return r"\textbf{?}"


def _latex_escape(text):
    out, bad = [], []
    for m in _SCRIPTS.finditer(str(text)):
        if m.group("sup"):
            out.append(r"\textsuperscript{%s}" % _script_tex(_SUP[c] for c in m.group("sup")))
        elif m.group("sub"):
            out.append(r"\textsubscript{%s}" % _script_tex(_SUB[c] for c in m.group("sub")))
        else:
            out.append(_tex_char(m.group("one"), bad))
    return "".join(out), bad


def _warn_unmapped(bad, where):
    chars = " ".join("%s (U+%04X)" % (c, ord(c)) for c in sorted(set(bad)))
    warnings.warn(
        f"{where}: no LaTeX form for {chars}; the caption prints '?' there. "
        "Write the symbol in ASCII, or add it to paper_style._TEX",
        UserWarning,
        stacklevel=3,
    )


def latex_escape(text, *, warn=True):
    """`text` safe inside a LaTeX caption with pdflatex (amssymb, textcomp loaded).

    Escapes TeX's special characters and `< > |`; maps sub- and superscript digits (CO\u2082,
    m\u207b\u00b2), the minus sign, Greek letters, quotes, dashes and common symbols; passes
    Latin-1 and Latin Extended-A letters (LaTeX reads UTF-8 since 2018). Any other character
    cannot be typeset: it becomes a bold ? and `warn=True` raises a UserWarning naming it.
    """
    tex, bad = _latex_escape(text)
    if bad and warn:
        _warn_unmapped(bad, "latex_escape")
    return tex


def unmapped_chars(text):
    """The characters of `text` that `latex_escape` cannot typeset (empty list = all fine)."""
    return sorted(set(_latex_escape(text)[1]))


def _fields(fig):
    f = getattr(fig, "_ps_frame", None)
    if f is None:
        raise ValueError("figure has no caption fields: call paper_style.frame first")
    return f


def caption(fig):
    """The caption as plain text: finding, then what the axes show, then provenance.

    Sentence case and a closing full stop. Fields that were not given are left out:
    "Units: GW; weekly." / "Source: Grid table 3; CC BY 4.0; as of 2026-11-04." The figure
    number is added by LaTeX. Raises if the figure was never framed.
    """
    f = _fields(fig)
    parts = [_sentence(f["title"])]
    if f["subtitle"]:
        parts.append(_sentence(f["subtitle"]))
    if f["units"] and f["cadence"]:
        parts.append(f"Units: {f['units']}; {f['cadence']}.")
    elif f["units"]:
        parts.append(f"Units: {f['units']}.")
    elif f["cadence"]:
        parts.append(f"Cadence: {f['cadence']}.")
    segs = []
    if f["source"]:
        segs.append(f"Source: {f['source']}")
    if f["licence"]:
        segs.append(f["licence"] if f["source"] else f"Licence: {f['licence']}")
    if f["asof"]:
        segs.append(f"as of {f['asof']}" if segs else f"As of {f['asof']}")
    if segs:
        line = "; ".join(segs)
        parts.append(line if line.endswith(".") else line + ".")
    return " ".join(parts)


def field(fig, name):
    """One caption field as a single line, for tests, indexes and cover pages.

    'title'     the finding
    'subtitle'  what the axes show: subtitle, units, cadence, as-of (those that were given)
    'footer'    the provenance: source, licence, as-of (those that were given)
    """
    f = _fields(fig)
    if name == "title":
        return f["title"]
    if name == "subtitle":
        bits = [f["subtitle"], f["units"], f["cadence"]]
        if f["asof"]:
            bits.append(f"as of {f['asof']}")
        return " \u00b7 ".join(b for b in bits if b)
    if name == "footer":
        bits = []
        if f["source"]:
            bits.append(f"Source: {f['source']}")
        if f["licence"]:
            bits.append(f["licence"])
        if f["asof"]:
            bits.append(f"As of {f['asof']}")
        return " \u00b7 ".join(bits)
    raise KeyError(name)


def latex_figure(fig, stem, *, warn=True):
    """A ready `figure` environment for `<stem>.pdf`, with the caption and a label."""
    w, _ = fig.get_size_inches()
    env = "figure*" if w > COLUMN + 0.5 else "figure"
    label = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    cap, bad = _latex_escape(caption(fig))
    if bad and warn:
        _warn_unmapped(bad, f"{stem}.tex")
    return (
        f"{MARK}; edit the figure code, not this file.\n"
        "% Needs \\usepackage{graphicx,amssymb,textcomp} in the preamble.\n"
        f"\\begin{{{env}}}[t]\n"
        "  \\centering\n"
        f"  \\includegraphics[width=\\linewidth]{{{stem}.pdf}}\n"
        f"  \\caption{{{cap}}}\n"
        f"  \\label{{fig:{label}}}\n"
        f"\\end{{{env}}}\n"
    )


# -------------------------------------------------------------- annotations


HALO_WIDTH = 2.5  # points: the white stroke behind helper text


def halo(width=HALO_WIDTH, color=None):
    """Path effects for a white halo behind text, so a label reads over lines and fills.

    `ax.text(x, y, "label", path_effects=ps.halo())`. Every label the helpers below draw
    (`end_label`, `note`, `ref_line`, `event_rule`, `provisional`, `bar_labels`) has one. In
    plotnine: `geom_text(..., path_effects=ps.halo())`.
    """
    from matplotlib import patheffects

    return [patheffects.withStroke(linewidth=width, foreground=color or TOKENS["bg"])]


def end_label(ax, x, y, name, value_text, *, color=None, dy=0):
    """Direct label at a line's end with a dot: 'Brent \u00b7 84.1 \u00b7 Oct 2' (instead of a legend)."""
    c = color or TOKENS["series_1"]
    ax.plot([x], [y], "o", color=c, markersize=3.5, zorder=5)
    return ax.annotate(
        f"{name} \u00b7 {value_text}",
        (x, y),
        xytext=(6, dy),
        textcoords="offset points",
        va="center",
        ha="left",
        fontsize=7.5,
        color=c,
        annotation_clip=False,
        path_effects=halo(),
        zorder=6,
    )


def ref_line(ax, y, words, *, side="right"):
    """Horizontal reference line that carries words ('recent low 18.6')."""
    t = TOKENS
    ax.axhline(y, color=t["text_muted"], linewidth=0.8, linestyle=(0, (4, 3)), zorder=1)
    x, ha = (0.995, "right") if side == "right" else (0.005, "left")
    return ax.text(
        x,
        y,
        words,
        transform=ax.get_yaxis_transform(),
        ha=ha,
        va="bottom",
        fontsize=7,
        color=t["text_muted"],
        path_effects=halo(),
        zorder=6,
    )


def event_rule(ax, x, label):
    """Thin vertical rule with a plain label. No boxes or arrows."""
    t = TOKENS
    ax.axvline(x, color=t["text_muted"], linewidth=0.6, zorder=1)
    return ax.text(
        x,
        0.99,
        f" {label}",
        transform=ax.get_xaxis_transform(),
        ha="left",
        va="top",
        fontsize=7,
        color=t["text_muted"],
        path_effects=halo(),
        zorder=6,
    )


def note(ax, xy, text, xytext=(30, 25)):
    """The one on-chart note: typed text and a thin leader line."""
    return ax.annotate(
        text,
        xy,
        xytext=xytext,
        textcoords="offset points",
        fontsize=7.5,
        color=TOKENS["text"],
        arrowprops={"arrowstyle": "-", "color": TOKENS["text_muted"], "lw": 0.6},
        path_effects=halo(),
        zorder=6,
    )


def provisional(ax, xs, ys, label="provisional", *, color=None):
    """First prints and incomplete periods: hollow markers and a muted word under the last one."""
    t = TOKENS
    xs, ys = list(xs), list(ys)
    ax.plot(
        xs,
        ys,
        "o",
        mfc=t["bg"],
        mec=color or t["series_1"],
        mew=0.8,
        markersize=4.5,
        zorder=6,
        linestyle="none",
    )
    return ax.annotate(
        label,
        (xs[-1], ys[-1]),
        xytext=(0, -10),
        textcoords="offset points",
        ha="center",
        va="top",
        fontsize=7,
        color=t["text_muted"],
        annotation_clip=False,
        path_effects=halo(),
        zorder=6,
    )


def band(ax, x, lower, upper, *, color=None, alpha=0.18, **kw):
    """A light fill between `lower` and `upper` with no edge (a range or an interval)."""
    kw.setdefault("zorder", 1.5)  # above the grid, below the lines
    return ax.fill_between(
        x, lower, upper, color=color or TOKENS["series_2"], alpha=alpha, linewidth=0, **kw
    )


def hbar_axes(ax):
    """Turn the look for a horizontal bar chart: the value axis is x.

    Vertical gridlines instead of horizontal ones, the baseline on the left (where the bars
    start), no x tick marks, and categories on y without tick marks. Call after `ax.barh`.
    """
    t = TOKENS
    ax.grid(False, axis="y")
    ax.grid(True, axis="x", which="major", color=t["grid"], linewidth=0.5)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color(t["rule"])
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="x", length=0)
    ax.tick_params(axis="y", length=0, pad=4)
    return ax


def bar_labels(ax, bars, fmt="{:.1f}", *, color=None):
    """Value labels just past the ends of bars (vertical or horizontal), with a halo, 7 pt.

    `bars` is what `ax.bar` / `ax.barh` returned; `fmt` is a format string or a function.
    A negative value is written with a true minus sign.

    The value axis is widened until every label sits inside the axes: otherwise the label of
    the most negative bar of a horizontal chart lands on its category name and its halo
    erases it. `frame` widens it again once the margins are final, so limits set between
    this call and `frame` are widened too if the labels need it.
    """
    labels = ax.bar_label(
        bars,
        labels=[
            (fmt(v) if callable(fmt) else fmt.format(v)).replace("-", MINUS) for v in bars.datavalues
        ],
        padding=3,
        fontsize=7,
        color=color or TOKENS["text"],
    )
    for lab in labels:
        lab.set_path_effects(halo())
    horizontal = getattr(bars, "orientation", None) == "horizontal"
    ax._ps_bar_labels = getattr(ax, "_ps_bar_labels", []) + [(list(labels), horizontal)]
    _fit_bar_labels(ax)
    return labels


def _fit_bar_labels(ax, pad=2.0):
    """Widen the value axis of `ax` until the labels `bar_labels` drew fit inside it.

    A label keeps its offset in points from its bar's end, so widening the limits moves it
    inward less than the bar: a few rounds converge. Limits are only ever widened.
    """
    groups = getattr(ax, "_ps_bar_labels", None)
    if not groups or ax.figure is None:
        return
    renderer = ax.figure.canvas.get_renderer()
    for horizontal in (True, False):
        texts = [
            t
            for labels, h in groups
            if h == horizontal
            for t in labels
            if t.axes is ax and t.get_visible() and t.get_text().strip()
        ]
        if not texts:
            continue
        for _ in range(8):
            box = ax.get_window_extent(renderer)
            extents = [t.get_window_extent(renderer) for t in texts]
            # pixels by which the labels (plus `pad`) stick out on the low and the high side
            if horizontal:
                lo = box.x0 - min(e.x0 for e in extents) + pad
                hi = max(e.x1 for e in extents) - box.x1 + pad
            else:
                lo = box.y0 - min(e.y0 for e in extents) + pad
                hi = max(e.y1 for e in extents) - box.y1 + pad
            if lo <= 0.25 and hi <= 0.25:
                break
            lo, hi = max(lo, 0), max(hi, 0)
            inv = ax.transData.inverted()
            if horizontal:
                y = box.y0
                a = inv.transform((box.x0 - lo, y))[0]
                b = inv.transform((box.x1 + hi, y))[0]
                ax.set_xlim(a, b)
            else:
                x = box.x0
                a = inv.transform((x, box.y0 - lo))[1]
                b = inv.transform((x, box.y1 + hi))[1]
                ax.set_ylim(a, b)


def date_axis(ax):
    """'Oct 16' / '2026-10' ticks, never rotated m/d/yyyy."""
    import matplotlib.dates as mdates

    loc = mdates.AutoDateLocator(minticks=4, maxticks=8)
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc, show_offset=False))


_SUPERSCRIPT = str.maketrans(
    "0123456789-", "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079\u207b"
)


def _log_text(v, style):
    """Text for a log-axis tick at value v: '100', '10\u00b3', '2\u00d710\u207b\u2075'."""
    if v == 0:
        return "0"
    sign = MINUS if v < 0 else ""
    a = abs(v)
    exp = int(math.floor(math.log10(a) + 1e-9))
    mant = a / 10.0 ** exp
    if abs(mant - round(mant)) > 1e-6:  # not a one-digit number: a free-form tick
        return sign + format(a, ".3g")
    mant = int(round(mant))
    if mant == 10:
        mant, exp = 1, exp + 1
    if style == "plain" or (style == "auto" and -3 <= exp <= 4):
        if exp >= 0:
            return f"{sign}{mant}{'0' * exp}"
        return f"{sign}0.{'0' * (-exp - 1)}{mant}"
    lead = "" if mant == 1 else f"{mant}\u00d7"
    return f"{sign}{lead}10{str(exp).translate(_SUPERSCRIPT)}"


_PLAIN_DECADES = (-3, 4)  # 'auto' writes digits when every visible decade is in 10^-3 .. 10^4


def _axis_log_style(axis, style):
    """'plain' or 'power' for a whole axis: one notation on every tick, never a mix.

    'auto' looks at the major ticks inside the view: if any of them (or, with none visible,
    either end of the view) lies in a decade outside 10^-3 .. 10^4, every tick is written
    as a power of ten; otherwise every tick is written in digits.
    """
    if style != "auto":
        return style
    lo, hi = sorted(axis.get_view_interval())
    try:
        locs = [v for v in axis.get_majorticklocs() if lo <= v <= hi and v != 0]
    except Exception:  # a locator that cannot run yet: judge by the view alone
        locs = []
    if not locs:
        locs = [v for v in (lo, hi) if v != 0 and math.isfinite(v)]
    first, last = _PLAIN_DECADES
    for v in locs:
        exp = int(math.floor(math.log10(abs(v)) + 1e-9))
        if abs(v) / 10.0 ** exp >= 10 - 1e-6:
            exp += 1
        if not first <= exp <= last:
            return "power"
    return "plain"


def log_axis(ax, axis="both", *, style="auto"):
    """Plain tick labels on a log (or symlog) axis, in place of matplotlib's mathtext.

    Matplotlib writes log ticks as `$\\mathdefault{10^{0}}$`. With maths parsing off (as
    `apply` sets it) those print literally, and lint P8 refuses them. Call this after
    `ax.set_xscale("log")` / `semilogy` / `loglog`:

        ax.semilogy(x, y); ps.log_axis(ax, "y")

    `axis` is "x", "y" or "both" (log axes only; "both" skips a linear one). `style`:
      "auto"   one notation for the whole axis: digits (0.01, 100, 10000) when every visible
               decade lies in 10^-3 to 10^4, else powers on every tick (10\u207b\u2075 ... 10\u2077)
      "plain"  always digits (100000, 0.00001)
      "power"  always 10\u207f (10\u2070, 10\u00b9, 10\u00b2)
    When the axis spans less than a decade or so, minor ticks are labelled too (2, 3, 5 ...), so
    a narrow log axis still reads. Returns `ax`.
    """
    from matplotlib import ticker

    if style not in ("auto", "plain", "power"):
        raise ValueError("style must be 'auto', 'plain' or 'power'")
    if axis not in ("x", "y", "both"):
        raise ValueError("axis must be 'x', 'y' or 'both'")
    for name in ("x", "y"):
        if axis not in (name, "both"):
            continue
        ax_ = ax.xaxis if name == "x" else ax.yaxis
        if ax_.get_scale() not in ("log", "symlog"):
            if axis == name:
                raise ValueError(f"the {name} axis is not logarithmic: call set_{name}scale('log') first")
            continue

        def major(v, pos=None, _style=style, _axis=ax_):
            return _log_text(v, _axis_log_style(_axis, _style))

        def minor(v, pos=None, _style=style, _axis=ax_):
            lo, hi = sorted(abs(x) for x in _axis.get_view_interval())
            if lo <= 0 or hi / lo > 40 or v == 0:
                return ""
            lead = int(round(abs(v) / 10.0 ** math.floor(math.log10(abs(v)) + 1e-9)))
            keep = (2, 3, 5) if hi / lo > 10 else tuple(range(2, 10))
            return _log_text(v, _axis_log_style(_axis, _style)) if lead in keep else ""

        ax_.set_major_formatter(ticker.FuncFormatter(major))
        ax_.set_minor_formatter(ticker.FuncFormatter(minor))
    return ax


# -------------------------------------------------------------- desk rules

_FORBIDDEN_HUE = ((0, 18), (342, 360), (85, 160))  # reds and greens
_STATE = {TOKENS["state_hit"].lower(), TOKENS["state_miss"].lower()}


def _hue_forbidden(rgb):
    import colorsys

    r, g, b = rgb[:3]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.35 or v < 0.25:  # greys, near-black and pale tints are fine
        return False
    deg = h * 360
    return any(lo <= deg <= hi for lo, hi in _FORBIDDEN_HUE)


def _cmap_colours(artist, n=11):
    """Colours a mapped artist (image, pcolormesh, scatter with an array) can show."""
    import numpy as np

    cmap = getattr(artist, "cmap", None)
    if cmap is None or getattr(artist, "get_array", lambda: None)() is None:
        return []
    return [tuple(cmap(x)) for x in np.linspace(0, 1, n)]


def _artist_colours(fig):
    """Every colour the figure can paint: marks, text, spines, ticks, arrows, colour maps."""
    from matplotlib.collections import Collection
    from matplotlib.colors import to_hex, to_rgba
    from matplotlib.image import AxesImage
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.text import Annotation, Text

    def norm(c):
        try:
            rgba = to_rgba(c)
        except ValueError:
            return None
        return None if rgba[3] == 0 else (to_hex(rgba).lower(), rgba)

    # Tick labels are empty strings until the figure has been drawn, so draw first.
    fig.canvas.draw()
    seen = []
    for a in fig.findobj():
        cols = []
        if isinstance(a, Line2D):
            cols = [a.get_color()]
            if a.get_visible() and a.get_marker() not in (None, "None", "", " "):
                cols += [a.get_markerfacecolor(), a.get_markeredgecolor()]
        elif isinstance(a, Patch) and a.get_visible():
            if a is not getattr(getattr(a, "axes", None), "patch", None):
                cols = [a.get_facecolor(), a.get_edgecolor()]
        elif isinstance(a, Collection):
            cols = (
                list(a.get_facecolors()) + list(a.get_edgecolors()) + _cmap_colours(a)
            )
        elif isinstance(a, AxesImage):
            cols = _cmap_colours(a)
        elif isinstance(a, Text) and a.get_visible():
            if a.get_text().strip():
                cols = [a.get_color()]
                bbox = a.get_bbox_patch()  # text box (annotate bbox=...)
                if bbox is not None:
                    cols += [bbox.get_facecolor(), bbox.get_edgecolor()]
            if isinstance(a, Annotation) and a.arrow_patch is not None:
                # An arrow needs no text, and a filled head has a face colour as well
                # as an edge colour.
                cols += [a.arrow_patch.get_edgecolor(), a.arrow_patch.get_facecolor()]
        for c in cols:
            n = norm(c)
            if n:
                seen.append(n)
    for ax in fig.axes:
        for sp in ax.spines.values():
            if sp.get_visible():
                n = norm(sp.get_edgecolor())
                if n:
                    seen.append(n)
        for lab in (*ax.get_xticklabels(), *ax.get_yticklabels()):
            if lab.get_visible():
                n = norm(lab.get_color())
                if n:
                    seen.append(n)
    return seen


def _desk_problems(fig, scored):
    """Legend box, twin axes, red or green, scored-result colours (STRICT_DESK only)."""
    problems = []
    if fig.legends or any(ax.get_legend() is not None for ax in fig.axes):
        problems.append("legend box: label lines at their ends (STRICT_DESK)")
    # Twin axes share a position exactly; stacked panels do not.
    boxes = [
        tuple(round(v, 4) for v in ax.get_position().bounds)
        for ax in fig.axes
        if ax.get_label() != "<colorbar>"
    ]
    if len(boxes) != len(set(boxes)):
        problems.append(
            "two axes on one panel: dual axis is banned (STRICT_DESK); stack panels"
        )
    for hexc, rgba in _artist_colours(fig):
        if hexc in _STATE:
            if not scored:
                problems.append(
                    f"{hexc} is a scored-result colour; use it only on scored results (STRICT_DESK)"
                )
            continue
        if _hue_forbidden(rgba):
            problems.append(f"{hexc} is red or green (STRICT_DESK)")
    return problems


# --------------------------------------------------------------------- lint


def _drawn_texts(fig):
    """Every non-empty visible text that is actually drawn.

    Matplotlib keeps tick-label objects for ticks outside the view limits and never draws
    them, and it does not draw anything of an axes or an axis that is switched off, so those
    are left out.
    """
    from matplotlib.text import Text

    unseen = set()

    def hide(artist):
        unseen.update(id(t) for t in artist.findobj(Text))

    for ax in fig.axes:
        if not ax.get_visible():
            hide(ax)
            continue
        for axis in (ax.xaxis, ax.yaxis):
            if not (ax.axison and axis.get_visible()):
                hide(axis)
                continue
            lo, hi = sorted(axis.get_view_interval())
            slack = 1e-9 * max(hi - lo, 1e-12)
            axis.get_major_ticks()  # make sure the tick objects exist and are positioned
            for tick in axis.majorTicks + axis.minorTicks:
                if not (lo - slack <= tick.get_loc() <= hi + slack):
                    unseen.update((id(tick.label1), id(tick.label2)))
    return [
        t
        for t in fig.findobj(Text)
        if t.get_visible() and t.get_text().strip() and id(t) not in unseen
    ]


def axis_label_problems(fig):
    """Data axes that show tick labels but have no axis label (a paper figure must read alone).

    Every visible axes counts, a twin's own scale included; axes that are switched off
    (images) and axes that hide their tick labels do not.
    """
    fig.canvas.draw()
    gg = getattr(fig, "_ps_gg_titles", None)  # plotnine: the figure-level axis titles
    out = []
    for ax in fig.axes:
        if not ax.get_visible() or not ax.axison:
            continue
        if ax.get_label() == "<colorbar>" or ax.get_gid() in _gids("skip"):
            continue
        for axis, name in ((ax.xaxis, "x"), (ax.yaxis, "y")):
            if not axis.get_visible():
                continue
            shown = any(t.get_visible() and t.get_text() for t in axis.get_ticklabels())
            label = axis.get_label().get_text().strip()
            if gg is not None and gg.get(name) is not None and gg[name].get_visible():
                label = label or gg[name].get_text().strip()
            if shown and not label:
                out.append(f"P7 {name} axis has no label (write the quantity and its unit)")
    return out


# Mathtext that would print literally now that maths parsing is off: matplotlib's own log tick
# labels ("$\mathdefault{10^{0}}$"), or a "$...$" pair that holds a command, ^, _ or braces,
# or one bare word ("$x$"). A lone dollar sign ("$/bbl", "$2.67 against $0.79") is plain text.
_MATH_MARKUP = re.compile(r"\\mathdefault|\$[^$\n]*[\\^_{}][^$\n]*\$|\$[A-Za-z][^$\s]*\$")


def _paper_problems(fig):
    """Rules P0 to P6: what makes a figure fit a paper."""
    import matplotlib as mpl

    problems = []
    f = getattr(fig, "_ps_frame", None)
    if f is None:
        problems.append("P0 missing caption fields: call paper_style.frame")
    else:
        for name in REQUIRE:
            if name in f and not f[name]:
                problems.append(
                    f"P0 caption field {name!r} is missing (paper_style.REQUIRE); pass it to frame"
                )
    w, h = fig.get_size_inches()
    if min(abs(w - COLUMN), abs(w - FULL)) > _WIDTH_TOL:
        problems.append(
            f"P1 figure is {w:.4f} in wide; a paper figure is exactly {COLUMN} (column) or "
            f"{FULL} (full width), so the 300 dpi PNG is {round(COLUMN * DPI)} or "
            f"{round(FULL * DPI)} px wide"
        )
    if h > MAX_HEIGHT + 0.02:
        problems.append(
            f"P1 figure is {h:.2f} in tall; at most {MAX_HEIGHT} to leave room for the caption"
        )
    engine = fig.get_layout_engine() if hasattr(fig, "get_layout_engine") else None
    if engine is not None and type(engine).__name__ != "PlaceHolderLayoutEngine":
        problems.append(
            "P1 a layout engine (constrained or tight layout) is active; it overrides the "
            "margins that paper_style.frame sets"
        )
    on_image = [
        t.get_text()[:30]
        for t in fig.texts
        if t.get_gid() in tuple(g for k in ("title", "subtitle", "footer") for g in _gids(k))
        or t.get_text().startswith("Source:")
    ]
    if getattr(fig, "_suptitle", None) is not None and fig._suptitle.get_text():
        on_image.append(fig._suptitle.get_text()[:30])
    panels = _panels(fig)
    if len(panels) == 1:  # on one panel an axes title is the figure title
        for ax in fig.axes:  # a twin axes counts too
            if not ax.get_visible():
                continue
            for loc in ("center", "left", "right"):
                text = ax.get_title(loc=loc)
                if text.strip():
                    on_image.append(text[:30])
    if on_image:
        problems.append(
            f"P2 title, subtitle or footer drawn on the image ({on_image[0]!r}): "
            "they go in the caption (paper_style.frame)"
        )
    fig.canvas.draw()  # tick labels are empty strings until the figure has been drawn
    drawn = _drawn_texts(fig)
    sizes = {round(t.get_fontsize(), 2) for t in drawn}
    bad = sorted(s for s in sizes if s < MIN_FONT - 1e-6 or s > MAX_FONT + 1e-6)
    if bad:
        problems.append(
            f"P3 text at {', '.join(f'{s:g}' for s in bad)} pt; use {MIN_FONT:g} to {MAX_FONT:g} pt"
        )
    markup = [t.get_text() for t in drawn if _MATH_MARKUP.search(t.get_text())]
    if markup:
        problems.append(
            f"P8 text shows mathtext markup literally ({markup[0][:30]!r}); write Unicode "
            "(m\u00b3, CO\u2082) instead of $...$, and call paper_style.log_axis(ax) on a log axis"
        )
    renderer = fig.canvas.get_renderer()
    edge = fig.bbox
    for t in drawn:
        box = t.get_window_extent(renderer)
        if (
            box.x0 < edge.x0 - 1
            or box.x1 > edge.x1 + 1
            or box.y0 < edge.y0 - 1
            or box.y1 > edge.y1 + 1
        ):
            problems.append(f"P6 text runs off the figure edge: {t.get_text()[:40]!r}")
            break
    problems += _placement_problems(fig, drawn, renderer)
    rc = mpl.rcParams
    if rc["pdf.fonttype"] != 42 or rc["ps.fonttype"] != 42:
        problems.append("P4 PDF/PS fonts must be Type 42 (paper_style.apply sets it)")
    if rc["text.usetex"]:
        problems.append("P4 text.usetex is on; paper_style.apply sets it off (it needs a TeX install)")
    house = _installed_fonts()
    if list(rc["font.family"]) != house:
        problems.append(
            "P4 font family is not the house sans-serif (Helvetica Neue, Helvetica, Arial, "
            "DejaVu Sans; paper_style.apply sets it)"
        )
    if rc["mathtext.fontset"] != "dejavusans":
        problems.append("P4 mathtext.fontset is not dejavusans (paper_style.apply sets it)")
    for t in drawn:  # a text may name its own family (ax.text(..., family="serif"), plotnine)
        fam = t.get_fontfamily()
        first = fam[0] if isinstance(fam, (list, tuple)) and fam else fam
        if first not in house:
            problems.append(
                f"P4 text {t.get_text()[:30]!r} is set in {first!r}, not the house sans-serif"
            )
            break
    for t in drawn:  # a glyph none of the text's fonts has prints as an empty box
        missing = _missing_glyphs(t)
        if missing:
            problems.append(
                f"P4 text {t.get_text()[:30]!r} has characters no font of its family draws "
                f"({' '.join(f'U+{ord(c):04X}' for c in missing[:3])}): they print as empty "
                "boxes; give the text the house font list (paper_style.apply, theme_paper)"
            )
            break
    return problems


_CHARMAPS = {}


def _missing_glyphs(t):
    """Characters of text `t` that none of the fonts its family list resolves to can draw."""
    from matplotlib import font_manager

    chars = sorted({c for c in t.get_text() if not c.isspace() and ord(c) > 0x7E})
    if not chars:  # plain ASCII: every house font and DejaVu Sans have it
        return []
    props = t.get_fontproperties()
    try:  # matplotlib 3.6+: the fonts of the family list, in fallback order
        paths = font_manager.fontManager._find_fonts_by_props(props)
    except Exception:
        paths = [font_manager.findfont(props)]
    have = set()
    for path in paths:
        key = str(path)
        if key not in _CHARMAPS:
            try:
                _CHARMAPS[key] = set(font_manager.get_font(key).get_charmap())
            except Exception:
                _CHARMAPS[key] = None
        if _CHARMAPS[key] is None:
            return []  # a font we cannot read: do not guess
        have |= _CHARMAPS[key]
    return [c for c in chars if ord(c) not in have]


def _overlap(a, b, tol=1.0):
    """True if boxes a and b share more than `tol` pixels in both directions."""
    return (
        min(a.x1, b.x1) - max(a.x0, b.x0) > tol and min(a.y1, b.y1) - max(a.y0, b.y0) > tol
    )


def _placement_problems(fig, drawn, renderer):
    """P6 beyond the figure edge: text cut at its panel, run into another panel, or on top of text.

    Checked for the texts placed in or around a panel (labels in the axes, bar labels, notes,
    geom_text, panel letters and plotnine strips) against every other drawn text: a tick label,
    an axis title, a strip or a letter. Two texts inside the same axes may still overlap
    (that is left to the eye, as before).
    """
    problems = []
    boxes = {id(t): t.get_window_extent(renderer) for t in drawn}
    in_axes = {id(t) for ax in fig.axes for t in ax.texts}
    letters = {id(t) for t in drawn if t.get_gid() in _gids("panel")}
    strips = {id(t) for t in drawn if getattr(t, "draw_info", None) is not None}
    placed = [t for t in drawn if id(t) in in_axes or id(t) in strips]
    # Cut: a text clipped to its axes that reaches past them prints only in part.
    for t in drawn:
        if not t.get_clip_on():
            continue
        clip = t.clipbox
        if clip is None and t.get_clip_path() is not None:
            clip = t.get_clip_path().get_fully_transformed_path().get_extents()
        if clip is None:
            continue
        b = boxes[id(t)]
        if b.x0 < clip.x0 - 1 or b.x1 > clip.x1 + 1 or b.y0 < clip.y0 - 1 or b.y1 > clip.y1 + 1:
            problems.append(
                f"P6 text is cut at the panel edge: {t.get_text()[:40]!r} (widen the axis "
                "limits, or draw it with clip_on=False)"
            )
            break
    # Into another panel: a text of one panel printed over the next one: a label or note in
    # the axes, a panel letter, a tick label or an axis title (a y scale too wide for the gap
    # between two columns puts the tick labels of the right panel on the left one).
    panels = [
        ax
        for ax in fig.axes
        if ax.get_visible() and (ax.axison or getattr(ax, "_ps_as_panel", False))
    ]
    extents = {id(ax): ax.get_window_extent(renderer) for ax in fig.axes}

    def nested(a, b):  # one box inside the other: an inset and the panel that holds it
        return (a.x0 >= b.x0 - 1 and a.x1 <= b.x1 + 1 and a.y0 >= b.y0 - 1 and a.y1 <= b.y1 + 1) or (
            b.x0 >= a.x0 - 1 and b.x1 <= a.x1 + 1 and b.y0 >= a.y0 - 1 and b.y1 <= a.y1 + 1
        )

    def own_texts(ax):
        yield from ax.texts
        for axis in (ax.xaxis, ax.yaxis):
            yield axis.label
            for tick in axis.majorTicks + axis.minorTicks:
                yield tick.label1
                yield tick.label2

    done = False
    for ax in fig.axes:
        if done:
            break
        key = tuple(round(v, 3) for v in ax.get_position().bounds)
        for t in own_texts(ax):
            if done or id(t) not in boxes:
                continue
            decor = t not in ax.texts  # a tick label or axis title, drawn outside the axes
            for other in panels:
                if tuple(round(v, 3) for v in other.get_position().bounds) == key:
                    continue  # the same axes, or a twin on top of it
                box = extents[id(other)]
                if decor and nested(extents[id(ax)], box):
                    continue  # an inset's scale inside the panel that holds it
                if _overlap(boxes[id(t)], box):
                    if id(t) in letters:
                        fix = "leave room between the panels, or draw it inside its own panel"
                    elif decor:
                        fix = "widen the gap between the panels (wspace, hspace) or shorten it"
                    else:
                        fix = "widen its axis limits or shorten it"
                    problems.append(
                        f"P6 text runs into another panel: {t.get_text()[:40]!r} ({fix})"
                    )
                    done = True
                    break
    # On top of other text: a panel letter on a strip or an axis title, a bar label on a
    # category name, a strip on the next strip.
    for t in placed:
        for u in drawn:
            if u is t:
                continue
            both_labels = id(t) in in_axes and id(u) in in_axes
            if both_labels and id(t) not in letters and id(u) not in letters:
                continue
            if _overlap(boxes[id(t)], boxes[id(u)]):
                problems.append(
                    f"P6 text {t.get_text()[:30]!r} prints over {u.get_text()[:30]!r}"
                )
                return problems
    return problems


def lint(fig, *, scored=False, axis_labels=False):
    """Return a sorted list of rule breaks. Empty list = the figure passes.

    `axis_labels=True` adds P7 (every data axis has a label). `scored=True` allows teal and
    brick (state-hit and state-miss) on scored results, and matters only with STRICT_DESK.
    See the module docstring for what is and is not checked.
    """
    problems = _paper_problems(fig)
    if axis_labels:
        problems += axis_label_problems(fig)
    if STRICT_DESK:
        problems += _desk_problems(fig, scored)
    return sorted(set(problems))


# ------------------------------------------------------------------ plotnine
#
# plotnine is imported only inside these functions, so a repository without it still imports
# paper_style. A plotnine plot becomes a paper figure in two steps:
#
#     p = ggplot(df, aes("x", "y")) + geom_line(size=ps.gg_size(1.2)) + ps.theme_paper()
#     fig = ps.from_plotnine(p)                  # a matplotlib Figure at 7.0 x 4.2 in
#     ps.frame(fig, title=..., xlabel=..., ylabel=...)
#     ps.save(fig, "figures/name")               # never ggsave or p.save: the guard refuses them


def _plotnine():
    try:
        import plotnine
    except ImportError as exc:
        raise ImportError(
            "paper_style.theme_paper and from_plotnine need plotnine; add it to the plotting "
            "group with `uv add --group <group> plotnine` (see VENDORING.md)"
        ) from exc
    return plotnine


def gg_size(points):
    """The plotnine `size` that draws a line `points` wide (plotnine scales size by sqrt(pi)).

    `geom_line(size=ps.gg_size(1.2))` is the house 1.2 pt data line; `gg_size(0.6)` a rule.
    """
    return points / math.sqrt(math.pi)


def theme_paper(base_size=8, *, legend=False, base_family=None):
    """ggplot2 `theme_minimal` with the paper look, for plotnine.

    `theme_minimal(base_size=8, base_family=<first installed house sans>)` plus: grey text
    (#333333 labels, #4D4D4D ticks), faint horizontal major gridlines only, a #B3B3B3 baseline
    and short x ticks, no y ticks, bold left-aligned strip text with no strip background, no
    plot title, subtitle or caption (they belong in the LaTeX caption: `ps.frame`), and the
    legend off (`legend=False`) or at the bottom without a title (`legend=True`).
    Add it last, or add your own `theme(...)` after it to change one element.
    """
    p9 = _plotnine()
    t = TOKENS
    # One name: plotnine reads a list in element_text as one value per axis break (the tick
    # labels would cycle through the fonts). `from_plotnine` gives every text in a house font
    # the whole fallback list, so a glyph Helvetica lacks still prints (from DejaVu Sans).
    fam = base_family or house_font()
    blank = p9.element_blank()
    return p9.theme_minimal(base_size=base_size, base_family=fam) + p9.theme(
        text=p9.element_text(family=fam, color=t["text"], size=base_size),
        axis_title=p9.element_text(size=8, color=t["text"]),
        axis_text=p9.element_text(size=7, color=t["text_ticks"]),
        legend_text=p9.element_text(size=7, color=t["text"]),
        legend_title=blank,
        legend_position="bottom" if legend else "none",
        legend_key=blank,
        panel_grid_major_x=blank,
        panel_grid_minor=blank,
        panel_grid_major_y=p9.element_line(color=t["grid"], size=0.5),
        panel_background=blank,
        plot_background=p9.element_rect(fill=t["bg"], color=t["bg"]),
        axis_line_x=p9.element_line(color=t["rule"], size=0.6),
        axis_line_y=blank,
        axis_ticks_major_x=p9.element_line(color=t["rule"], size=0.6),
        axis_ticks_major_y=blank,
        axis_ticks_minor=blank,
        axis_ticks_length_major_x=2.5,
        axis_ticks_length_major_y=0,
        strip_text=p9.element_text(size=8, weight="bold", ha="left", color=t["text"]),
        strip_background=blank,
        plot_title=blank,
        plot_subtitle=blank,
        plot_caption=blank,
    )


def _gg_text_fixes(fig):
    """Two fixes to the texts plotnine drew; returns how many texts changed.

    Fonts: a text set in one house font (a `theme(text=element_text(family="Helvetica Neue"))`
    after `theme_paper`, or a plotnine that passes one name on) gets the whole fallback list,
    so a glyph that font lacks (an arrow, a triangle from `delta`) comes from DejaVu Sans
    instead of printing as an empty box.

    Clipping: plotnine clips text to its panel, as ggplot2 does, so an end label that runs
    past the last data point is cut at the panel edge however much margin the plot has. Text
    inside a panel is drawn whole instead; lint P6 then reports one that runs off the figure,
    into another panel or over other text.
    """
    from matplotlib.text import Text

    house = _installed_fonts()
    changed = 0
    for t in fig.findobj(Text):
        fam = t.get_fontfamily()
        names = [fam] if isinstance(fam, str) else list(fam)
        if len(names) == 1 and names[0] in house:
            t.set_fontfamily(_family_list(names[0]))
            changed += 1
    for ax in fig.axes:
        for t in ax.texts:
            if t.get_clip_on():
                t.set_clip_on(False)
                changed += 1
    return changed


def from_plotnine(p, rows=1, width=FULL, height=None, size=None):
    """Draw a plotnine plot at its printed size and return the matplotlib Figure.

    The size follows `figure`: `width` is COLUMN or FULL, the height is 4.2 in plus 1.5 in per
    extra row of facets (`rows`), or `height` in inches; `size=(w, h)` overrides both (lint P1
    then judges it). plotnine lays the figure out once; its layout engine is then removed, so
    `frame` keeps that layout (it adds axis labels and panel letters, not margins). Go on
    exactly as for a matplotlib figure: `ps.frame(fig, ...)`, the annotation helpers on
    `fig.axes`, then `ps.save(fig, path)`. A title, subtitle or caption the plot still draws
    is reported by lint P2; use `theme_paper()`, which blanks them.

    Two changes to what plotnine drew: every text in one house font gets the whole fallback
    list (so an arrow or a `delta` triangle prints, not an empty box), and text inside a
    panel (`geom_text`, `annotate`) is no longer clipped to it. An end label then prints
    whole; give it room inside the panel by widening the x scale,
    `scale_x_continuous(expand=(0, 0, 0.2, 0))`, which also works on facets, where the next
    facet starts right after the panel. `theme(plot_margin_right=...)` only adds room to the
    right of the last column. Lint P6 reports a label that runs into the next facet, off the
    figure or over other text. Panel letters go in front of the facet names in the strips.
    """
    p9 = _plotnine()
    if not isinstance(p, p9.ggplot):
        raise TypeError(f"from_plotnine needs a plotnine ggplot, not {type(p).__name__}")
    apply()
    if size is None:
        w, h = default_size(rows, width)
        if height is not None:
            h = float(height) + _EPS
        size = (w, h)
    p = p + p9.theme(figure_size=(float(size[0]), float(size[1])), dpi=100)
    try:
        fig = p.draw(show=False)
    except TypeError:  # plotnine before 0.12: draw() has no `show`
        fig = p.draw()
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    if not isinstance(fig.canvas, FigureCanvasAgg):  # plotnine makes figures outside pyplot
        FigureCanvasAgg(fig)
    _gg_text_fixes(fig)  # before the layout, so it measures the text as it will print
    engine = fig.get_layout_engine() if hasattr(fig, "get_layout_engine") else None
    if engine is not None and type(engine).__name__ != "PlaceHolderLayoutEngine":
        engine.execute(fig)  # place panels, strips and legend at the final size, once
    fig.canvas.draw()
    if _gg_text_fixes(fig):  # texts the first draw made (tick labels) get the same fixes
        fig.canvas.draw()
    _no_layout_engine(fig)
    labels = getattr(p, "labels", None)

    def label(name):
        value = getattr(labels, name, None) if labels is not None else None
        return value if isinstance(value, str) and value else None

    free = [t for t in fig.texts if t.get_visible() and t.get_gid() is None]
    # The axis titles: plotnine draws them as figure texts, x level and y turned 90 degrees.
    titles = {}
    for name, turned in (("x", False), ("y", True)):
        want = label(name)
        titles[name] = next(
            (
                t
                for t in free
                if want is not None
                and t.get_text() == want
                and (abs(t.get_rotation() % 180 - 90) < 1) == turned
            ),
            None,
        )
    fig._ps_gg_titles = titles
    # The plot title, subtitle and caption, if still drawn, are marked so P2 reports them.
    for name, kind in (("title", "title"), ("subtitle", "subtitle"), ("caption", "footer")):
        want = label(name)
        for t in free:
            if want is not None and t.get_text() == want and t not in titles.values():
                t.set_gid(_gid(kind))
    fig._ps_plotnine = True
    return fig


# --------------------------------------------------------------------- output


_KNOWN_EXT = tuple("." + e for e in FORMATS)
_MEDIABOX = re.compile(rb"/MediaBox\s*\[\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*\]")
_SVG_SIZE = re.compile(rb'<svg[^>]*?\swidth="([0-9.]+)pt"[^>]*?\sheight="([0-9.]+)pt"')


def split_path(path):
    """(folder, name) for an output path: only a known extension (.pdf .png .svg .tex) is removed.

    'figs/wpsr_2026.11.04' keeps its dots, so two such names never collide; 'figs/a.pdf' is 'a'.
    """
    p = Path(path)
    name = p.name
    for ext in _KNOWN_EXT:
        if name.lower().endswith(ext) and len(name) > len(ext):
            name = name[: -len(ext)]
            break
    if not name or name in (".", ".."):
        raise ValueError(f"{path!r} has no file name")
    return p.parent, name


def _check_written(ext, tmp, final, fig, check=True):
    """P5: the file just written has the printed size (PNG pixels, PDF and SVG points).

    The PNG is compared with width x dpi and height x dpi to within one pixel, because
    matplotlib rounds a size such as 2.26 in x 300 dpi (677.99999...) its own way. With
    `check` on, the width must also be one of the two journal widths.
    """
    w, h = fig.get_size_inches()
    if ext == "png":
        from PIL import Image

        with Image.open(tmp) as im:
            size = im.size
        exact = (w * DPI, h * DPI)
        if any(abs(got - want) > 1.0 + 1e-6 for got, want in zip(size, exact)):
            raise ValueError(
                f"{final}: PNG is {size[0]} x {size[1]} px, but the figure is {w:.4f} x {h:.4f} in "
                f"= {exact[0]:.1f} x {exact[1]:.1f} px at {DPI} dpi"
            )
        allowed = (round(COLUMN * DPI), round(FULL * DPI))
        if check and min(abs(size[0] - a) for a in allowed) > 1:
            raise ValueError(
                f"{final}: PNG is {size[0]} px wide; a paper figure is {allowed[0]} px "
                f"({COLUMN} in column) or {allowed[1]} px ({FULL} in full width) at {DPI} dpi "
                f"(use paper_style.figure())"
            )
    elif ext == "pdf":
        raw = Path(tmp).read_bytes()
        box = _MEDIABOX.search(raw)
        if not box:
            raise ValueError(f"{final}: cannot read the PDF page size")
        x0, y0, x1, y1 = (float(v) for v in box.groups())
        if abs((x1 - x0) - w * 72) > 0.5 or abs((y1 - y0) - h * 72) > 0.5:
            raise ValueError(
                f"{final}: PDF page is {x1 - x0:.1f} x {y1 - y0:.1f} pt, must be "
                f"{w * 72:.1f} x {h * 72:.1f} pt (is savefig.bbox or a layout engine cropping it?)"
            )
        if re.search(rb"/Subtype\s*/Type3\b", raw):
            raise ValueError(f"{final}: PDF has Type 3 fonts; paper_style needs Type 42")
    elif ext == "svg":
        m = _SVG_SIZE.search(Path(tmp).read_bytes()[:4000])
        if not m:
            raise ValueError(f"{final}: cannot read the SVG size")
        sw, sh = float(m.group(1)), float(m.group(2))
        if abs(sw - w * 72) > 0.5 or abs(sh - h * 72) > 0.5:
            raise ValueError(
                f"{final}: SVG is {sw:.1f} x {sh:.1f} pt, must be {w * 72:.1f} x {h * 72:.1f} pt"
            )


def save(fig, path, *, formats=FORMATS, scored=False, check=True, close=True):
    """Lint, then write the paper figure `path` + '.pdf', '.png', '.svg', '.tex'.

    A known extension on `path` (.pdf .png .svg .tex) is dropped; any other dot stays in the
    name, so `save(fig, "x/run_1.5")` writes `x/run_1.5.pdf`.

    `formats` picks from:
      pdf  vector original, Type 42 fonts: this is the file to put in an arXiv source tree
      png  300 dpi raster at the printed size, for a README or the web
      svg  vector with glyph outlines, for the web
      tex  `<name>.tex`: the `figure` environment with the caption and a label
    PDF, SVG, PNG and TEX are byte-stable between runs. The rcParams that decide the file
    size (`savefig.bbox`, layout engines, usetex) are pinned while writing, and every file is
    written under a temporary name, size-checked, and renamed only when all of them pass: a
    figure that fails leaves no file behind. `close=False` leaves the figure open (to show
    it, or add it to a multi-page PDF); a figure that fails a check is always closed.
    `check=False` skips the lint and the journal-width test of the PNG; a file whose size
    differs from the figure's own size is still refused. Returns the list of files written.
    """
    import matplotlib.pyplot as plt

    unknown = [e for e in formats if e not in FORMATS]
    if unknown:
        raise ValueError(f"unknown format {unknown}; choose from {FORMATS}")
    folder, name = split_path(path)
    try:
        if check:
            problems = lint(fig, scored=scored)
            if problems:
                raise ValueError(f"{path}: " + "; ".join(problems))
        if SAVE_GUARD is not None:
            SAVE_GUARD(folder / name, getattr(fig, "_ps_frame", None))
    except ValueError:
        plt.close(fig)
        raise
    folder.mkdir(parents=True, exist_ok=True)
    staged, made = [], []  # (temporary, final) pairs; every temporary file created
    try:
        with plt.rc_context(_PINNED):
            for ext in dict.fromkeys(formats):
                final = folder / f"{name}.{ext}"
                tmp = folder / f".{final.name}.tmp"
                if ext == "tex":
                    if getattr(fig, "_ps_frame", None) is None:
                        continue  # an unchecked, unframed figure has no caption to write
                    made.append(tmp)
                    tmp.write_text(latex_figure(fig, name), encoding="utf-8")
                else:
                    meta = {
                        "png": {"Software": None},
                        "svg": {"Date": None, "Creator": "paper_style"},
                        "pdf": {
                            "Creator": "paper_style",
                            "Producer": "matplotlib",
                            "CreationDate": None,
                        },
                    }[ext]
                    made.append(tmp)
                    fig.savefig(tmp, format=ext, dpi=DPI, bbox_inches=None, metadata=meta)
                    _check_written(ext, tmp, final, fig, check)
                staged.append((tmp, final))
        for tmp, final in staged:
            os.replace(tmp, final)
    except BaseException:
        for tmp in made:
            if tmp.exists():
                tmp.unlink()
        plt.close(fig)
        raise
    if close:
        plt.close(fig)
    return [final for _, final in staged]


def png_bytes(fig, dpi=150):
    """The figure as PNG bytes, in memory, for a report that embeds it. Writes no file."""
    import io

    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    with plt.rc_context(_PINNED):
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches=None, metadata={"Software": None})
    return buf.getvalue()


def show(fig, *, dpi=150, close=False, report=False):
    """Display the figure in a notebook, although the Agg backend is forced.

    Embeds `png_bytes(fig, dpi)` through `IPython.display`, so a figure appears under the
    cell whatever the backend. `report=True` also prints the lint problems (it does not
    raise); `close=True` closes the figure afterwards. Returns the PNG bytes. Raises
    ImportError with a hint if IPython is not installed (use `png_bytes` then).
    """
    try:
        from IPython.display import Image, display
    except ImportError as exc:
        raise ImportError("paper_style.show needs IPython; use png_bytes(fig) instead") from exc
    if report:
        for problem in lint(fig):
            print("paper_style:", problem)
    data = png_bytes(fig, dpi=dpi)
    display(Image(data=data, format="png"))
    if close:
        import matplotlib.pyplot as plt

        plt.close(fig)
    return data


def add_caption_band(fig, label=None, *, chars=125):
    """Print the caption under the panels, for a PDF page (a report), not for a paper.

    A paper gets its caption from LaTeX, so `save()` never draws one. A report page has no
    LaTeX, and a page without its as-of line is the stale-data mistake the style exists to
    prevent. The figure grows downward by the height of the caption; the panels keep their
    size. Call it after `save()`: the files written there stay caption-free.
    """
    text = caption(fig)
    if label:
        text = f"{label}: {text}"
    wrapped = fill(text, chars)
    w, h = fig.get_size_inches()
    band = 0.17 * (wrapped.count("\n") + 1) + 0.22
    new_h = h + band
    k = h / new_h
    for ax in fig.axes:
        x0, y0, bw, bh = ax.get_position().bounds
        ax.set_position([x0, (y0 * h + band) / new_h, bw, bh * k])
    for t in fig.texts:
        if t.get_transform() == fig.transFigure:
            x, y = t.get_position()
            t.set_position((x, (y * h + band) / new_h))
    fig.set_size_inches(w, new_h)
    fig.text(
        0.012,
        0.1 / new_h,
        wrapped,
        ha="left",
        va="bottom",
        fontsize=7.5,
        color=TOKENS["text_muted"],
        linespacing=1.3,
        gid=_gid("page-caption"),
    )
    return fig

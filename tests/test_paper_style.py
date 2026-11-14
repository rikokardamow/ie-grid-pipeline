"""Tests for paper_style.py. Vendoring: change the import below if the module lives in a package."""

import ast
import logging
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

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


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    import matplotlib.pyplot as plt

    plt.close("all")


FRAME = {
    "title": "Demand fell 4% below the five-year average",
    "units": "GW",
    "cadence": "weekly, Wednesday 10:30 ET",
    "asof": datetime(2026, 11, 4, 15, 30, tzinfo=timezone.utc),
    "source": "Grid operator, table 4 (D-123)",
    "licence": "CC BY 4.0",
}


def _good(**over):
    fig, axes = ps.figure()
    ax = axes[0][0]
    ax.plot([0, 1, 2], [3, 2, 4], color=ps.TOKENS["series_1"])
    ps.end_label(ax, 2, 4, "Demand", "424.1 · Oct 30")
    ps.frame(fig, **{**FRAME, **over})
    return fig, ax


# ------------------------------------------------------------------ basics


def test_good_figure_passes_lint():
    fig, _ = _good()
    assert ps.lint(fig) == []


def test_source_is_python_39_syntax():
    src = Path(ps.__file__).read_text(encoding="utf-8")
    ast.parse(src, feature_version=(3, 9))  # no match statement, no except*
    assert "strict=" not in src and "datetime.UTC" not in src
    assert "\nfrom zoneinfo" not in src and "\nimport zoneinfo" not in src  # only a lazy import


def test_apply_forces_agg_and_sets_type_42_serif():
    import matplotlib as mpl

    ps.apply()
    assert mpl.get_backend().lower() == "agg"
    assert mpl.rcParams["pdf.fonttype"] == 42 and mpl.rcParams["ps.fonttype"] == 42
    fams = mpl.rcParams["font.family"]
    assert fams[-1] == "DejaVu Serif"
    assert fams[0] in ("STIXGeneral", "Times New Roman", "Times", "DejaVu Serif")


def test_font_list_has_only_installed_fonts(caplog):
    ps.apply()
    with caplog.at_level(logging.WARNING, logger="matplotlib.font_manager"):
        fig, _ = _good()
        fig.canvas.draw()
    assert not [r for r in caplog.records if "not found" in r.getMessage()]


def test_unicode_units_have_glyphs_and_dollars_are_not_maths(recwarn):
    fig, ax = _good()
    ax.set_ylabel("Flow (m³/s) µg CO₂ ▲ ▼ − °C")
    ax.set_xlabel("Costs $2.67/bbl against $0.79 a year earlier")
    fig.canvas.draw()
    import matplotlib as mpl

    assert mpl.rcParams["text.parse_math"] is False
    assert not [w for w in recwarn if "missing from font" in str(w.message).lower()]


# ------------------------------------------------------------------ geometry


def test_a_figure_is_a_journal_width_and_nothing_else():
    fig, _ = ps.figure(width=ps.COLUMN)
    assert fig.get_size_inches()[0] == pytest.approx(3.4, abs=1e-3)
    fig, _ = ps.figure()
    assert fig.get_size_inches()[0] == pytest.approx(7.0, abs=1e-3)
    fig, ax = ps.figure(size=(5.0, 3.0))
    ax[0][0].plot([0, 1], [0, 1])
    ps.frame(fig, **FRAME)
    assert any(p.startswith("P1") for p in ps.lint(fig))


def test_more_rows_make_a_taller_figure_but_never_taller_than_a_page():
    one = ps.figure(1)[0].get_size_inches()[1]
    three = ps.figure(3)[0].get_size_inches()[1]
    assert one == pytest.approx(4.2, abs=1e-3)
    assert three == pytest.approx(one + 3.0, abs=1e-3)
    assert ps.figure(20)[0].get_size_inches()[1] <= ps.MAX_HEIGHT + 0.01
    assert ps.MAX_HEIGHT == 9.0 and ps.COLUMN == 3.4 and ps.FULL == 7.0


def test_a_too_tall_figure_fails_p1():
    fig, ax = ps.figure(size=(7.0, 10.5))
    ax[0][0].plot([0, 1], [0, 1])
    ps.frame(fig, **FRAME)
    assert any(p.startswith("P1") and "tall" in p for p in ps.lint(fig))


def test_type_scale():
    import matplotlib as mpl

    ps.apply()
    assert mpl.rcParams["xtick.labelsize"] == 7 and mpl.rcParams["ytick.labelsize"] == 7
    assert mpl.rcParams["axes.labelsize"] == 8 and mpl.rcParams["font.size"] == 8
    assert (ps.MIN_FONT, ps.MAX_FONT) == (6.0, 9.0)


# ------------------------------------------------------------------ P rules


def test_missing_frame_is_reported():
    fig, axes = ps.figure()
    axes[0][0].plot([0, 1], [0, 1])
    assert any(p.startswith("P0") and "caption fields" in p for p in ps.lint(fig))


def test_nothing_of_the_caption_is_drawn_on_the_image():
    fig, _ = _good()
    assert not [
        t for t in fig.texts if t.get_gid() in ("ps-title", "ps-subtitle", "ps-footer")
    ]
    fig.text(0.01, 0.99, "A title on the image", gid="ps-title")
    assert any(p.startswith("P2") for p in ps.lint(fig))
    fig2, _ = _good()
    fig2.suptitle("Demand fell")
    assert any(p.startswith("P2") for p in ps.lint(fig2))
    fig3, _ = _good()
    fig3.text(0.01, 0.01, "Source: somebody", fontsize=7)
    assert any(p.startswith("P2") for p in ps.lint(fig3))


def test_axes_title_on_a_single_panel_is_a_figure_title_but_not_on_several():
    fig, ax = _good()
    ax.set_title("Demand fell 4%")
    assert any(p.startswith("P2") for p in ps.lint(fig))
    fig2, axes = ps.figure(2, 1)
    for a in axes[:, 0]:
        a.plot([0, 1], [0, 1])
    axes[0][0].set_title("Winter")
    ps.frame(fig2, **FRAME)
    assert ps.lint(fig2) == []


@pytest.mark.parametrize("size", [5.0, 9.5, 14])
def test_text_outside_six_to_nine_points_fails(size):
    fig, ax = _good()
    ax.text(0.5, 0.5, "label", fontsize=size, transform=ax.transAxes)
    assert any(p.startswith("P3") for p in ps.lint(fig))


@pytest.mark.parametrize("size", [6.0, 7.5, 9.0])
def test_text_inside_the_scale_passes(size):
    fig, ax = _good()
    ax.text(0.5, 0.5, "label", fontsize=size, transform=ax.transAxes)
    assert ps.lint(fig) == []


def test_text_running_off_the_figure_edge_fails_and_hidden_ticks_do_not():
    fig, ax = _good()
    ax.text(1.0, 0.5, "a label that is far too long for the margin", transform=ax.transAxes)
    assert any(p.startswith("P6") for p in ps.lint(fig))
    fig2, _ = _good()
    assert ps.lint(fig2) == []  # tick labels beyond the axis limits are never drawn


def test_serif_and_type_42_are_enforced(monkeypatch):
    import matplotlib as mpl

    fig, _ = _good()
    monkeypatch.setitem(mpl.rcParams, "pdf.fonttype", 3)
    assert any(p.startswith("P4") for p in ps.lint(fig))
    monkeypatch.setitem(mpl.rcParams, "pdf.fonttype", 42)
    monkeypatch.setitem(mpl.rcParams, "font.family", ["DejaVu Sans"])
    assert any(p.startswith("P4") and "font family" in p for p in ps.lint(fig))


def test_axis_label_rule_p7_is_opt_in():
    fig, ax = ps.figure()
    ax[0][0].plot([0, 1], [0, 1])
    ps.frame(fig, **FRAME)
    assert ps.lint(fig) == []
    assert sum(p.startswith("P7") for p in ps.lint(fig, axis_labels=True)) == 2
    ps.axis_labels(fig, "Week", "Demand (GW)")
    assert ps.lint(fig, axis_labels=True) == []


def test_p7_ignores_the_hidden_x_axis_of_stacked_panels():
    fig, axes = ps.figure(2, 1)
    for a in axes[:, 0]:
        a.plot([0, 1], [0, 1])
    ps.frame(fig, **FRAME, ylabel="Demand (GW)", xlabel="Week")
    assert ps.lint(fig, axis_labels=True) == []


def test_save_refuses_a_failing_figure_and_closes_it(tmp_path):
    import matplotlib.pyplot as plt

    fig, ax = _good()
    ax.text(0.5, 0.5, "x", fontsize=20, transform=ax.transAxes)
    with pytest.raises(ValueError, match="P3"):
        ps.save(fig, tmp_path / "x")
    assert not list(tmp_path.glob("x.*"))
    assert fig.number not in plt.get_fignums()


def test_save_rejects_unknown_formats(tmp_path):
    fig, _ = _good()
    with pytest.raises(ValueError, match="unknown format"):
        ps.save(fig, tmp_path / "x", formats=("pdf", "gif"))


# ------------------------------------------------------------------ frame fields


def test_title_is_required_and_must_state_a_finding():
    fig, _ = ps.figure()
    with pytest.raises(TypeError):
        ps.frame(fig)
    for bad in ("", "   ", "US crude stocks", "Brent prices", "Demand chart", "Demand"):
        with pytest.raises(ValueError):
            ps.frame(fig, title=bad)
    ps.frame(fig, title="Demand fell 4% in a year")  # nothing else is needed by default


def test_every_other_field_is_optional_and_the_caption_copes():
    fig, _ = ps.figure()
    ps.frame(fig, title="Demand fell 4% in a year")
    assert ps.caption(fig) == "Demand fell 4% in a year."
    assert ps.field(fig, "footer") == "" and ps.field(fig, "subtitle") == ""
    fig2, _ = ps.figure()
    ps.frame(fig2, title="Demand fell 4% in a year", units="GW", asof="2026-11-04")
    assert ps.caption(fig2) == "Demand fell 4% in a year. Units: GW. As of 2026-11-04."
    fig3, _ = ps.figure()
    ps.frame(fig3, title="Demand fell 4%.", cadence="monthly", licence="CC BY 4.0", source="Table 2 (X1)")
    assert ps.caption(fig3) == "Demand fell 4%. Cadence: monthly. Source: Table 2 (X1); CC BY 4.0."


def test_caption_is_a_sentence_with_units_and_provenance():
    fig, _ = _good()
    cap = ps.caption(fig)
    assert cap.startswith("Demand fell 4% below the five-year average. ")
    assert "Units: GW; weekly, Wednesday 10:30 ET." in cap
    assert cap.endswith(
        "Source: Grid operator, table 4 (D-123); CC BY 4.0; as of 2026-11-04 15:30 UTC."
    )


def test_subtitle_is_sentence_two():
    fig, _ = _good(subtitle="(a) Level (b) Change")
    assert ps.caption(fig).startswith(
        "Demand fell 4% below the five-year average. (a) Level (b) Change. Units:"
    )


def test_field_returns_title_units_line_and_provenance_line():
    fig, _ = _good()
    assert ps.field(fig, "title") == FRAME["title"]
    assert ps.field(fig, "subtitle") == "GW · weekly, Wednesday 10:30 ET · as of 2026-11-04 15:30 UTC"
    assert (
        ps.field(fig, "footer")
        == "Source: Grid operator, table 4 (D-123) · CC BY 4.0 · As of 2026-11-04 15:30 UTC"
    )
    with pytest.raises(KeyError):
        ps.field(fig, "nope")
    fig2, _ = ps.figure()
    with pytest.raises(ValueError, match="frame"):
        ps.caption(fig2)


@pytest.mark.parametrize(
    "bad",
    [
        {"cadence": ""},
        {"cadence": 5},
        {"licence": "  "},
        {"source": ""},
        {"units": ""},
        {"units": ("GW", "")},
        {"units": 3},
        {"asof": "2026-11-05 (day ending)"},
        {"asof": "2026-13-45 25:99 ET"},
        {"asof": "2026-02-30"},
        {"asof": "October 2026, pulled 2026-10-29 07:14 UTC"},
        {"asof": "2026-11-04 10:30"},
        {"asof": "2026-11-04 10:30 utc"},
        {"asof": datetime(2026, 11, 4, 10, 30)},
    ],
)
def test_frame_validates_value_shapes_when_given(bad):
    fig, _ = ps.figure()
    with pytest.raises(ValueError):
        ps.frame(fig, **{**FRAME, **bad})


@pytest.mark.parametrize(
    "good",
    [
        "2026-11-04",
        "2026-11-04 10:30 ET",
        "2026-10-29 07:14 UTC",
        "2026-10-29 07:14 CET",
        "2026-10-29 07:14 UTC+05:30",
        "2025-12-24 (est.)",
    ],
)
def test_asof_accepts_the_documented_forms(good):
    assert ps.parse_asof(good) == good


@pytest.mark.parametrize(
    "bad",
    [
        "2026-11-04 10:30 ET\n",
        "2026-11-04\n",
        "٢٠٢٦-١١-٠٤",  # Arabic-Indic digits
        "2026-11-04 10:30 ET ",
        "2025-12-24 (estimate)",
        "2025-13-24 (est.)",
        "2025-12-24 10:30 (est.)",
    ],
)
def test_asof_is_ascii_and_exact(bad):
    with pytest.raises(ValueError):
        ps.parse_asof(bad)


def test_datetimes_and_dates_are_turned_into_labelled_strings():
    fig, _ = ps.figure()
    ps.frame(fig, title="Demand fell 4% in a year", asof=datetime(2026, 10, 29, 7, 14, tzinfo=timezone.utc))
    assert ps.field(fig, "footer") == "As of 2026-10-29 07:14 UTC"
    ps.frame(fig, title="Demand fell 4% in a year", asof=datetime(2026, 10, 29, 7, 14, tzinfo=timezone(timedelta(hours=5, minutes=30))))
    assert ps.field(fig, "footer") == "As of 2026-10-29 07:14 UTC+05:30"
    ps.frame(fig, title="Demand fell 4% in a year", asof=datetime(2026, 10, 29, 7, 14, tzinfo=timezone(timedelta(hours=-5))))
    assert ps.field(fig, "footer") == "As of 2026-10-29 07:14 UTC-05:00"
    ps.frame(fig, title="Demand fell 4% in a year", asof=date(2026, 11, 4))
    assert ps.field(fig, "footer") == "As of 2026-11-04"
    zoneinfo = pytest.importorskip("zoneinfo")
    try:
        ny = zoneinfo.ZoneInfo("America/New_York")
    except Exception:  # no tz database on this machine
        pytest.skip("no tzdata")
    ps.frame(fig, title="Demand fell 4% in a year", asof=datetime(2026, 7, 1, 10, 30, tzinfo=ny))
    assert ps.field(fig, "footer") == "As of 2026-07-01 10:30 EDT"


def test_several_units_are_joined():
    fig, _ = ps.figure()
    ps.frame(fig, title="Demand fell 4% in a year", units=("GW", "%"))
    assert "Units: GW, %." in ps.caption(fig)


def test_framing_twice_does_not_stack_panel_letters():
    fig, axes = ps.figure(2, 1)
    for a in axes[:, 0]:
        a.plot([0, 1], [0, 1])
    ps.frame(fig, **FRAME)
    ps.frame(fig, **FRAME)
    assert len([t for ax in axes[:, 0] for t in ax.texts if t.get_gid() == "ps-panel"]) == 2


# ------------------------------------------------------------------ generic switches


def test_require_makes_more_fields_mandatory(monkeypatch):
    monkeypatch.setattr(ps, "REQUIRE", ("title", "source", "asof"))
    fig, _ = ps.figure()
    with pytest.raises(ValueError, match="source is required"):
        ps.frame(fig, title="Demand fell 4% in a year", asof="2026-11-04")
    with pytest.raises(ValueError, match="asof is required"):
        ps.frame(fig, title="Demand fell 4% in a year", source="Table 3")
    ps.frame(fig, title="Demand fell 4% in a year", source="Table 3", asof="2026-11-04")


def test_title_stays_required_even_if_require_forgets_it(monkeypatch):
    monkeypatch.setattr(ps, "REQUIRE", ())
    fig, _ = ps.figure()
    with pytest.raises(ValueError):
        ps.frame(fig, title="")


def test_require_with_an_unknown_name_is_an_error(monkeypatch):
    monkeypatch.setattr(ps, "REQUIRE", ("title", "colour"))
    fig, _ = ps.figure()
    with pytest.raises(ValueError, match="REQUIRE names"):
        ps.frame(fig, title="Demand fell 4% in a year")


def test_lint_reports_a_field_that_require_added_after_framing(monkeypatch):
    fig, _ = ps.figure()
    fig.axes[0].plot([0, 1], [0, 1])
    ps.frame(fig, title="Demand fell 4% in a year")
    assert ps.lint(fig) == []
    monkeypatch.setattr(ps, "REQUIRE", ("title", "source"))
    assert any(p.startswith("P0") and "'source'" in p for p in ps.lint(fig))


def test_units_none_accepts_anything_and_a_set_restricts(monkeypatch):
    fig, _ = ps.figure()
    ps.frame(fig, title="Demand fell 4% in a year", units="Mb/d")
    monkeypatch.setattr(ps, "UNITS", {"mb/d", "GW"})
    with pytest.raises(ValueError, match="allowed spelling"):
        ps.frame(fig, title="Demand fell 4% in a year", units="Mb/d")
    with pytest.raises(ValueError, match="allowed spelling"):
        ps.frame(fig, title="Demand fell 4% in a year", units=("GW", "mmbbl"))
    ps.frame(fig, title="Demand fell 4% in a year", units=["mb/d", "GW"])
    assert "Units: mb/d, GW." in ps.caption(fig)


def test_desk_rules_are_off_by_default():
    assert ps.STRICT_DESK is False
    fig, ax = _good()
    ax.plot([0, 1], [0, 1], color="red", label="x")
    ax.twinx().plot([0, 1], [5, 6])
    ax.legend()
    fig.legend()
    ax.bar([0], [1], color=ps.TOKENS["state_miss"])
    assert ps.lint(fig) == []


@pytest.fixture
def strict(monkeypatch):
    monkeypatch.setattr(ps, "STRICT_DESK", True)


@pytest.mark.parametrize("colour", ["red", "#00A000", "#E03030", "limegreen"])
def test_strict_red_and_green_fail(strict, colour):
    fig, ax = _good()
    ax.plot([0, 1], [1, 1], color=colour)
    assert any("red or green" in p for p in ps.lint(fig))


def test_strict_state_colours_only_on_scored_results(strict):
    fig, ax = _good()
    ax.bar([0], [1], color=ps.TOKENS["state_miss"])
    assert any("scored-result" in p for p in ps.lint(fig))
    assert ps.lint(fig, scored=True) == []


def test_strict_twin_axes_fail_and_stacked_panels_pass(strict):
    fig, ax = _good()
    ax.twinx().plot([0, 1], [5, 6], color=ps.TOKENS["series_3"])
    assert any("dual axis" in p for p in ps.lint(fig))
    fig, axes = ps.figure(2, 1)
    for a in axes[:, 0]:
        a.plot([0, 1], [0, 1], color=ps.TOKENS["series_1"])
    ps.frame(fig, **FRAME)
    assert ps.lint(fig) == []


def test_strict_legend_box_fails_axes_and_figure_level(strict):
    fig, ax = _good()
    ax.plot([0, 1], [0, 1], color=ps.TOKENS["series_3"], label="x")
    ax.legend()
    assert any("legend" in p for p in ps.lint(fig))
    fig2, ax2 = _good()
    ax2.plot([0, 1], [0, 1], label="x")
    fig2.legend()
    assert any("legend" in p for p in ps.lint(fig2))


def test_strict_sees_red_in_text_spines_ticks_arrows_and_cmaps(strict):
    import numpy as np

    fig, ax = _good()
    a = ax.text(0.5, 0.5, "x", color="red")
    assert any("red or green" in p for p in ps.lint(fig))
    a.remove()
    ax.spines["left"].set_edgecolor("#00A000")
    assert any("red or green" in p for p in ps.lint(fig))
    ax.spines["left"].set_edgecolor(ps.TOKENS["border"])
    ax.tick_params(axis="y", labelcolor="#E03030")  # lint runs before any draw in save()
    assert any("red or green" in p for p in ps.lint(fig))
    ax.tick_params(axis="y", labelcolor=ps.TOKENS["text_muted"])
    ax.annotate("n", (1, 1), xytext=(5, 5), textcoords="offset points", arrowprops={"arrowstyle": "-", "color": "red"})
    assert any("red or green" in p for p in ps.lint(fig))
    fig2, ax2 = _good()
    ax2.imshow(np.arange(9).reshape(3, 3), cmap="RdYlGn")
    assert any("red or green" in p for p in ps.lint(fig2))


@pytest.mark.parametrize("style", ["simple", "fancy", "wedge"])
def test_strict_filled_arrow_heads_and_empty_text_arrows_are_checked(strict, style):
    fig, ax = _good()
    ax.annotate("", (1, 1), xytext=(0, 0), arrowprops={"arrowstyle": style, "fc": "red", "ec": "none"})
    assert any("red or green" in p for p in ps.lint(fig))


def test_strict_text_bbox_colours_are_checked_and_the_diverging_scale_passes(strict):
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap

    fig, ax = _good()
    ax.text(0.5, 0.5, "x", color=ps.TOKENS["text"], bbox={"fc": "#E03030", "ec": "none"})
    assert any("red or green" in p for p in ps.lint(fig))
    fig2, axes = ps.figure()
    axes[0][0].imshow(np.arange(9).reshape(3, 3), cmap=LinearSegmentedColormap.from_list("d", list(ps.DIVERGING)))
    ps.frame(fig2, **FRAME)
    assert ps.lint(fig2) == []


def test_strict_passes_the_default_palette(strict):
    fig, axes = ps.figure()
    for i in range(6):
        axes[0][0].plot([0, 1], [i, i + 1])  # the colour cycle picks the six colours
    ps.frame(fig, **FRAME)
    assert ps.lint(fig) == []


# ------------------------------------------------------------------ palette


def _oklab(hexc):
    h = hexc.lstrip("#")
    lin = [(int(h[i : i + 2], 16) / 255) for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in lin]
    return _oklab_from_linear(lin)


def _oklab_from_linear(rgb):
    r, g, b = rgb
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


_MACHADO = {  # Machado, Oliveira and Fernandes 2009, severity 1.0, linear RGB
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]],
}


def _delta_e(a, b, kind=None):
    def lab(hexc):
        if kind is None:
            return _oklab(hexc)
        h = hexc.lstrip("#")
        lin = [(int(h[i : i + 2], 16) / 255) for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in lin]
        sim = [min(1.0, max(0.0, sum(row[j] * lin[j] for j in range(3)))) for row in _MACHADO[kind]]
        return _oklab_from_linear(sim)

    return 100 * math.dist(lab(a), lab(b))


def test_palette_starts_with_the_house_colours_then_okabe_ito():
    assert ps.PALETTE[:3] == ("#0F2A4A", "#1F5FBF", "#7D8996")
    assert ps.PALETTE[3:] == ("#E69F00", "#56B4E9", "#CC79A7", "#F0E442")
    assert ps.YELLOW == "#F0E442" and ps.YELLOW not in ps.CYCLE


def test_palette_is_the_axes_colour_cycle():
    import matplotlib as mpl

    ps.apply()
    got = [c["color"] for c in mpl.rcParams["axes.prop_cycle"]]
    assert [c.upper() for c in got] == list(ps.CYCLE)


def test_first_four_colours_stay_apart_under_every_colour_vision_type():
    cols = ps.PALETTE[:4]
    for kind in (None, "protan", "deutan", "tritan"):
        worst = min(_delta_e(a, b, kind) for i, a in enumerate(cols) for b in cols[i + 1 :])
        assert worst > 10, (kind, worst)  # measured: 12.3 or more


def test_neighbouring_colours_of_the_whole_cycle_stay_apart_for_red_green_blindness():
    for kind in ("protan", "deutan"):
        worst = min(_delta_e(a, b, kind) for a, b in zip(ps.CYCLE, ps.CYCLE[1:]))
        assert worst > 8, (kind, worst)  # measured: 9.6 or more


def test_series_style_adds_a_dash_and_a_marker_for_the_pale_yellow():
    dashes = [ps.series_style(i)["linestyle"] for i in range(6)]
    assert len({str(d) for d in dashes}) == 6
    assert "marker" not in ps.series_style(0) and ps.series_style(0, marker=True)["marker"] == "o"
    y = ps.series_style(6)
    assert y["color"] == ps.YELLOW and y["markeredgecolor"] == ps.TOKENS["text"] and "marker" in y
    assert ps.series_style(7)["color"] == ps.PALETTE[0]  # wraps


# ------------------------------------------------------------------ output


def test_save_writes_pdf_png_svg_and_tex_at_the_printed_size(tmp_path):
    from PIL import Image

    fig, _ = _good()
    out = ps.save(fig, tmp_path / "ok")
    assert {p.suffix for p in out} == {".pdf", ".png", ".svg", ".tex"}
    assert Image.open(tmp_path / "ok.png").size == (2100, 1260)
    fig, ax = ps.figure(width=ps.COLUMN)
    ax[0][0].plot([0, 1], [0, 1])
    ps.frame(fig, **FRAME)
    ps.save(fig, tmp_path / "col")
    assert Image.open(tmp_path / "col.png").size == (1020, 1260)


def test_save_formats_nested_folders_and_known_extension_stripped(tmp_path):
    fig, _ = _good()
    out = ps.save(fig, tmp_path / "a" / "b" / "name.pdf", formats=("pdf", "tex"))
    assert [p.name for p in out] == ["name.pdf", "name.tex"]
    assert (tmp_path / "a" / "b" / "name.pdf").exists()


def test_unframed_figure_writes_no_tex_when_unchecked(tmp_path):
    fig, ax = ps.figure()
    ax[0][0].plot([0, 1], [0, 1])
    out = ps.save(fig, tmp_path / "raw", check=False)
    assert {p.suffix for p in out} == {".pdf", ".png", ".svg"}


def test_the_pdf_embeds_truetype_fonts_and_no_type_3(tmp_path):
    fig, _ = _good()
    ps.save(fig, tmp_path / "f", formats=("pdf",))
    raw = (tmp_path / "f.pdf").read_bytes()
    assert b"/FontFile2" in raw  # TrueType subset, embedded
    assert b"/Subtype /Type3" not in raw
    assert b"paper_style" in raw  # Creator


def test_pdf_svg_png_and_tex_are_byte_stable(tmp_path):
    for name in ("a", "b"):
        fig, _ = _good()
        ps.save(fig, tmp_path / name)
    for ext in ("pdf", "svg", "png", "tex"):
        a = (tmp_path / f"a.{ext}").read_bytes()
        b = (tmp_path / f"b.{ext}").read_bytes()
        assert a.replace(b"a.pdf", b"b.pdf").replace(b"fig:a", b"fig:b") == b, ext
    svg = (tmp_path / "a.svg").read_bytes()
    assert b"Matplotlib v" not in svg and b"<dc:date>" not in svg


def _png_of_size(path, size):
    from PIL import Image

    Image.new("RGB", size, "white").save(path)
    return path


def test_png_size_is_checked_against_the_figure(tmp_path):
    fig, _ = _good()
    with pytest.raises(ValueError, match=r"PNG is 2100 x 1000 px, but the figure is 7\.0001 x 4\.2001 in"):
        ps._check_written("png", _png_of_size(tmp_path / "a.png", (2100, 1000)), "x.png", fig)
    ps._check_written("png", _png_of_size(tmp_path / "b.png", (2100, 1260)), "x.png", fig)
    ps._check_written("png", _png_of_size(tmp_path / "c.png", (2100, 1261)), "x.png", fig)  # under one pixel of slack


def test_png_width_message_names_the_allowed_widths(tmp_path):
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(3.41, 3))  # 1023 px: matches the figure, is not a journal width
    path = _png_of_size(tmp_path / "w.png", (1023, 900))
    with pytest.raises(ValueError, match=r"1023 px wide.*1020 px.*2100 px"):
        ps._check_written("png", path, "x.png", fig)
    ps._check_written("png", path, "x.png", fig, check=False)  # check=False skips the width test


def test_default_matplotlib_figure_saves_with_check_false(tmp_path):
    import matplotlib.pyplot as plt
    from PIL import Image

    fig = plt.figure()  # 6.4 x 4.8 in: not a journal size, but the user asked for no checks
    out = ps.save(fig, tmp_path / "plain", formats=("png",), check=False)
    assert Image.open(out[0]).size == (1920, 1440)


def test_png_bytes_is_a_png_in_memory_and_writes_nothing(tmp_path, monkeypatch):
    from io import BytesIO

    from PIL import Image

    monkeypatch.chdir(tmp_path)
    fig, _ = _good()
    data = ps.png_bytes(fig)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert Image.open(BytesIO(data)).size == (1050, 630)  # 7.0 x 4.2 in at 150 dpi
    assert Image.open(BytesIO(ps.png_bytes(fig, dpi=300))).size == (2100, 1260)
    assert ps.png_bytes(fig) == data
    assert list(tmp_path.iterdir()) == []


# ------------------------------------------------------------------ show


def _fake_ipython(monkeypatch):
    import types

    shown = []
    display_mod = types.ModuleType("IPython.display")

    class Image:
        def __init__(self, data=None, format=None):
            self.data, self.format = data, format

    display_mod.Image = Image
    display_mod.display = lambda obj: shown.append(obj)
    pkg = types.ModuleType("IPython")
    pkg.display = display_mod
    pkg.get_ipython = lambda: None  # pyplot asks IPython for a running shell
    monkeypatch.setitem(sys.modules, "IPython", pkg)
    monkeypatch.setitem(sys.modules, "IPython.display", display_mod)
    return shown


def test_show_embeds_a_150_dpi_png_through_ipython(monkeypatch, capsys):
    shown = _fake_ipython(monkeypatch)
    fig, _ = _good()
    data = ps.show(fig)
    assert len(shown) == 1 and shown[0].format == "png" and shown[0].data == data == ps.png_bytes(fig, dpi=150)
    assert capsys.readouterr().out == ""


def test_show_can_report_lint_problems_and_close(monkeypatch, capsys):
    import matplotlib.pyplot as plt

    _fake_ipython(monkeypatch)
    fig, ax = ps.figure()
    ax[0][0].plot([0, 1], [0, 1])
    ps.show(fig, report=True, close=True)
    assert "P0" in capsys.readouterr().out
    assert fig.number not in plt.get_fignums()


def test_show_without_ipython_says_what_to_use(monkeypatch):
    monkeypatch.setitem(sys.modules, "IPython", None)
    monkeypatch.setitem(sys.modules, "IPython.display", None)
    fig, _ = _good()
    with pytest.raises(ImportError, match="png_bytes"):
        ps.show(fig)


# ------------------------------------------------------------------ tex


def test_latex_escape():
    assert ps.latex_escape("5% & R_1 #2 {x} $3 a~b ^") == (
        r"5\% \& R\_1 \#2 \{x\} \$3 a\textasciitilde{}b \textasciicircum{}"
    )
    assert ps.latex_escape("−3.2 ▼ ▲ °C € ± σ – —") == (
        r"$-$3.2 $\blacktriangledown$ $\blacktriangle$ \textdegree{}C \texteuro{} $\pm$ $\sigma$ -- ---"
    )
    assert ps.latex_escape("back\\slash") == r"back\textbackslash{}slash"


def test_tex_file_is_a_ready_figure_environment_with_escaped_caption(tmp_path):
    fig, _ = _good(title="Stocks fell −3.2 GW ▼ & rose 5% in R_1")
    ps.save(fig, tmp_path / "E12_percentile", formats=("tex",))
    tex = (tmp_path / "E12_percentile.tex").read_text()
    assert tex.startswith("% Written by paper_style.save")
    assert "\\begin{figure*}[t]" in tex and "\\end{figure*}" in tex
    assert "\\includegraphics[width=\\linewidth]{E12_percentile.pdf}" in tex
    assert "\\label{fig:e12-percentile}" in tex
    assert "$-$3.2" in tex and "$\\blacktriangledown$" in tex
    assert "\\&" in tex and "5\\%" in tex and "R\\_1" in tex


def test_a_column_figure_uses_figure_not_figure_star(tmp_path):
    fig, ax = ps.figure(width=ps.COLUMN)
    ax[0][0].plot([0, 1], [0, 1])
    ps.frame(fig, **FRAME)
    ps.save(fig, tmp_path / "narrow", formats=("tex",))
    tex = (tmp_path / "narrow.tex").read_text()
    assert "\\begin{figure}[t]" in tex and "figure*" not in tex


def test_the_mark_the_exporter_looks_for_is_what_save_writes():
    fig, _ = _good()
    assert ps.latex_figure(fig, "x").startswith(ps.MARK)


# ------------------------------------------------------------------ axes and panels


def test_axis_labels_go_on_unlabelled_panels_only():
    fig, axes = ps.figure(2, 1)
    for a in axes[:, 0]:
        a.plot([0, 1], [0, 1])
    axes[1][0].set_ylabel("Own label (kb/d)")
    ps.frame(fig, **FRAME, ylabel=["Demand (GW)", "ignored"], xlabel="Week ending")
    assert axes[0][0].get_ylabel() == "Demand (GW)"
    assert axes[1][0].get_ylabel() == "Own label (kb/d)"
    assert axes[1][0].get_xlabel() == "Week ending" and axes[0][0].get_xlabel() == ""


def test_one_string_labels_first_column_and_bottom_row_only():
    fig, axes = ps.figure(2, 2, sharex=False)
    for a in axes.ravel():
        a.plot([0, 1], [0, 1])
    ps.axis_labels(fig, "Week", "Demand (GW)")
    assert [a.get_ylabel() for a in axes[:, 0]] == ["Demand (GW)"] * 2
    assert [a.get_ylabel() for a in axes[:, 1]] == [""] * 2
    assert [a.get_xlabel() for a in axes[1]] == ["Week"] * 2
    assert [a.get_xlabel() for a in axes[0]] == [""] * 2


def test_multi_panel_figures_get_bold_panel_letters_in_reading_order():
    fig, axes = ps.figure(2, 2, sharex=False)
    for a in axes.ravel():
        a.plot([0, 1], [0, 1])
    ps.frame(fig, **FRAME)
    labelled = [(t, ax) for ax in axes.ravel() for t in ax.texts if t.get_gid() == "ps-panel"]
    assert sorted(t.get_text() for t, _ in labelled) == ["(a)", "(b)", "(c)", "(d)"]
    by_text = {t.get_text(): ax for t, ax in labelled}
    assert by_text["(a)"] is axes[0][0] and by_text["(b)"] is axes[0][1]
    assert by_text["(c)"] is axes[1][0] and by_text["(d)"] is axes[1][1]
    assert all(t.get_fontweight() == "bold" and t.get_fontsize() == 8 for t, _ in labelled)
    assert ps.lint(fig) == []
    _fig1, ax1 = _good()
    assert not [t for t in ax1.texts if t.get_gid() == "ps-panel"]  # one panel needs no letter


def test_colorbar_axes_are_not_panels():
    import numpy as np

    fig, axes = ps.figure()
    im = axes[0][0].imshow(np.arange(9).reshape(3, 3))
    fig.colorbar(im, ax=axes[0][0])
    ps.frame(fig, **FRAME)
    assert not [t for ax in fig.axes for t in ax.texts if t.get_gid() == "ps-panel"]


# ------------------------------------------------------------------ helpers


def test_signed_and_delta_use_a_true_minus():
    assert ps.signed(-1.25) == "−1.2" or ps.signed(-1.25) == "−1.3"
    assert ps.delta(-3.2, "GW") == "▼ −3.2 GW"
    assert ps.delta(1.05, "GW", 2) == "▲ +1.05 GW"
    assert ps.delta(0, "GW").startswith("●")


def test_annotation_helpers_keep_lint_clean():
    fig, ax = _good()
    ps.ref_line(ax, 2.5, "recent low 18.6")
    ps.ref_line(ax, 3.5, "left side", side="left")
    ps.event_rule(ax, 1, "Outage")
    ps.note(ax, (1, 2), "largest drop since June")
    assert ps.lint(fig) == []


def test_date_axis_gives_readable_ticks():
    import matplotlib.dates as mdates

    fig, axes = ps.figure()
    ax = axes[0][0]
    d = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(0, 200, 20)]
    ax.plot(d, range(len(d)))
    ps.date_axis(ax)
    ps.frame(fig, **FRAME)
    fig.canvas.draw()
    assert isinstance(ax.xaxis.get_major_formatter(), mdates.ConciseDateFormatter)
    assert ps.lint(fig) == []


# ------------------------------------------------------------------ caption band


def test_caption_band_grows_the_page_and_keeps_the_panels_the_same_size():
    fig, ax = _good()
    fig.canvas.draw()
    w0, h0 = fig.get_size_inches()
    height_in = ax.get_position().bounds[3] * h0
    ps.add_caption_band(fig, "Exhibit E12")
    w1, h1 = fig.get_size_inches()
    assert w1 == w0 and h1 > h0
    assert ax.get_position().bounds[3] * h1 == pytest.approx(height_in, rel=1e-6)
    cap = next(t for t in fig.texts if t.get_gid() == "ps-page-caption")
    flat = cap.get_text().replace("\n", " ")
    assert flat.startswith("Exhibit E12: Demand fell 4% below")
    assert "as of 2026-11-04 15:30 UTC" in flat
    fig.canvas.draw()
    box = cap.get_window_extent(fig.canvas.get_renderer())
    assert box.y0 >= 0 and box.x1 <= fig.bbox.x1  # the caption fits on the page


def test_caption_band_needs_a_framed_figure():
    fig, _ = ps.figure()
    with pytest.raises(ValueError, match="frame"):
        ps.add_caption_band(fig)


def test_files_saved_before_the_band_stay_caption_free(tmp_path):
    from PIL import Image

    fig, _ = _good()
    ps.save(fig, tmp_path / "f", close=False)
    ps.add_caption_band(fig)
    assert Image.open(tmp_path / "f.png").size == (2100, 1260)


# ------------------------------------------------------------------ fix round: log axes


def _log_fig(kind, **frame_over):
    import numpy as np

    fig, axes = ps.figure()
    ax = axes[0][0]
    x = np.logspace(0, 4, 10)
    getattr(ax, kind)(x, x if kind == "loglog" else np.arange(10) + 1.0)
    ps.frame(fig, title="Demand fell 4% in a year", xlabel="X (u)", ylabel="Y (u)", **frame_over)
    return fig, ax


@pytest.mark.parametrize("kind", ["semilogx", "semilogy", "loglog"])
def test_matplotlib_log_ticks_fail_lint_and_log_axis_fixes_them(kind, tmp_path):
    fig, ax = _log_fig(kind)
    assert any(p.startswith("P8") for p in ps.lint(fig))
    with pytest.raises(ValueError, match="P8"):
        ps.save(fig, tmp_path / "bad")
    assert not list(tmp_path.iterdir())  # nothing, not even a temporary file
    fig, ax = _log_fig(kind)
    ps.log_axis(ax)
    assert ps.lint(fig, axis_labels=True) == []
    fig.canvas.draw()
    texts = [t.get_text() for t in ax.xaxis.get_ticklabels() + ax.yaxis.get_ticklabels()]
    assert not any("$" in t or "mathdefault" in t for t in texts)
    ps.save(fig, tmp_path / "ok")


def test_log_axis_styles_and_values():
    t = ps._log_text
    assert [t(v, "auto") for v in (0.001, 1, 10, 100, 10000)] == ["0.001", "1", "10", "100", "10000"]
    assert t(1e5, "auto") == "10\u2075" and t(1e-4, "auto") == "10\u207b\u2074"
    assert t(2e-5, "auto") == "2\u00d710\u207b\u2075"
    assert t(1, "power") == "10\u2070" and t(1000, "power") == "10\u00b3"
    assert t(1e5, "plain") == "100000" and t(1e-5, "plain") == "0.00001"
    assert t(-100, "auto") == "\u2212100" and t(0, "auto") == "0"
    assert t(9.99999999, "plain") == "10"  # rounding up to the next decade


def test_log_axis_rules():
    fig, ax = _log_fig("semilogy")
    with pytest.raises(ValueError, match="not logarithmic"):
        ps.log_axis(ax, "x")
    with pytest.raises(ValueError):
        ps.log_axis(ax, style="nope")
    with pytest.raises(ValueError):
        ps.log_axis(ax, "z")
    assert ps.log_axis(ax, "y") is ax


def test_a_narrow_log_axis_labels_its_minor_ticks_and_a_wide_one_does_not():
    import numpy as np

    fig, axes = ps.figure()
    ax = axes[0][0]
    ax.semilogy(np.arange(5), np.linspace(1.5, 6, 5))
    ps.log_axis(ax, "y")
    ps.frame(fig, title="Demand fell 4% in a year", xlabel="X (u)", ylabel="Y (u)")
    fig.canvas.draw()
    shown = {t.get_text() for t in ax.get_yticklabels(which="both") if t.get_text()}
    assert {"2", "3", "4", "5", "6"} <= shown
    fig, axes = ps.figure()
    ax = axes[0][0]
    ax.semilogy(np.arange(5), np.logspace(-2, 6, 5))
    ps.log_axis(ax, "y")
    fig.canvas.draw()
    wide = [t.get_text() for t in ax.yaxis.get_minorticklabels() if t.get_text()]
    assert wide == []


def test_symlog_axis_gets_plain_labels():
    fig, axes = ps.figure()
    ax = axes[0][0]
    ax.plot([-1000, 0, 1000], [1, 2, 3])
    ax.set_xscale("symlog")
    ps.log_axis(ax, "x")
    ps.frame(fig, title="Demand fell 4% in a year", xlabel="X (u)", ylabel="Y (u)")
    assert ps.lint(fig) == []


@pytest.mark.parametrize(
    "text,bad",
    [
        (r"$\mathdefault{10^{0}}$", True),
        (r"$\mu$g", True),
        ("$x$", True),
        ("$10^3$", True),
        ("Price ($/bbl)", False),
        ("$2.67 against $0.79", False),
        ("CO\u2082 (Mt)", False),
    ],
)
def test_p8_flags_mathtext_markup_but_not_dollar_signs(text, bad):
    fig, ax = _good()
    ax.set_ylabel(text)
    got = any(p.startswith("P8") for p in ps.lint(fig))
    assert got is bad


# ------------------------------------------------------------------ fix round: ambient rcParams


def test_apply_pins_size_critical_rcparams(monkeypatch):
    import matplotlib as mpl

    for k, v in {"savefig.bbox": "tight", "figure.autolayout": True, "text.usetex": True}.items():
        monkeypatch.setitem(mpl.rcParams, k, v)
    ps.apply()
    assert mpl.rcParams["savefig.bbox"] is None  # matplotlib reads "standard" as None
    assert mpl.rcParams["figure.autolayout"] is False
    assert mpl.rcParams["figure.constrained_layout.use"] is False
    assert mpl.rcParams["text.usetex"] is False


def test_ambient_tight_bbox_cannot_change_the_page_size(tmp_path, monkeypatch):
    import matplotlib as mpl

    fig, _ = _good()
    monkeypatch.setitem(mpl.rcParams, "savefig.bbox", "tight")  # set after figure(), as a style file might
    out = ps.save(fig, tmp_path / "t")
    raw = (tmp_path / "t.pdf").read_bytes()
    assert b"/MediaBox [ 0 0 504.0072 302.4072 ]" in raw
    assert b'width="504.0072pt"' in (tmp_path / "t.svg").read_bytes()
    assert len(out) == 4
    fig, _ = _good()
    assert len(ps.png_bytes(fig)) > 1000
    from PIL import Image
    import io

    fig, _ = _good()
    assert Image.open(io.BytesIO(ps.png_bytes(fig, dpi=100))).size == (700, 420)


def test_pdf_and_svg_sizes_are_checked(tmp_path):
    fig, _ = _good()
    ps.save(fig, tmp_path / "ok", formats=("pdf", "svg"), close=False)
    wide, _ = ps.figure(width=ps.COLUMN)
    wide.canvas.draw()
    for ext in ("pdf", "svg"):
        with pytest.raises(ValueError, match="must be"):
            ps._check_written(ext, tmp_path / f"ok.{ext}", tmp_path / f"x.{ext}", wide)
    ps._check_written("pdf", tmp_path / "ok.pdf", tmp_path / "ok.pdf", fig)


def test_a_failed_check_leaves_no_file_and_keeps_an_older_one(tmp_path, monkeypatch):
    fig, _ = _good()
    ps.save(fig, tmp_path / "keep", formats=("pdf",))
    before = (tmp_path / "keep.pdf").read_bytes()
    real = ps._check_written

    def fail_on_png(ext, tmp, final, fig, *rest):
        if ext == "png":
            raise ValueError("boom")
        return real(ext, tmp, final, fig, *rest)

    monkeypatch.setattr(ps, "_check_written", fail_on_png)
    fig, ax = ps.figure()
    ax[0][0].plot([0, 1], [3, 1])
    ps.frame(fig, **{**FRAME, "title": "Demand fell 9 GW in a day"})
    with pytest.raises(ValueError, match="boom"):
        ps.save(fig, tmp_path / "keep")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep.pdf"]  # no .svg, .tex or .tmp left
    assert (tmp_path / "keep.pdf").read_bytes() == before


def test_constrained_layout_is_replaced_so_the_margins_apply(recwarn):
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=ps.default_size(), layout="constrained")
    fig.add_subplot().plot([0, 1], [0, 1])
    ps.frame(fig, title="Demand fell 4% in a year", xlabel="X (u)", ylabel="Y (u)")
    assert not [w for w in recwarn.list if issubclass(w.category, UserWarning)]
    assert fig.subplotpars.right == pytest.approx(1 - min(1.0, 0.14 * 7.0001) / 7.0001)
    assert ps.lint(fig) == []


def test_a_layout_engine_added_after_frame_fails_lint():
    fig, _ = _good()
    fig.set_layout_engine("tight")
    assert any("layout engine" in p for p in ps.lint(fig))


def test_usetex_fails_lint(monkeypatch):
    import matplotlib as mpl

    fig, _ = _good()
    monkeypatch.setitem(mpl.rcParams, "text.usetex", True)
    assert any("usetex" in p for p in ps.lint(fig))


# ------------------------------------------------------------------ fix round: caption text


def test_units_the_docs_recommend_become_ascii_latex():
    esc = ps.latex_escape
    assert esc("Mt CO\u2082") == r"Mt CO\textsubscript{2}"
    assert esc("W m\u207b\u00b2") == r"W m\textsuperscript{$-$2}"  # one run, one superscript
    assert esc("m\u00b3 and 10\u2076") == r"m\textsuperscript{3} and 10\textsuperscript{6}"
    assert esc("\u00b5g/m\u00b3") == r"\textmu{}g/m\textsuperscript{3}"
    assert esc("x\u2080\u2081 H\u2082O") == r"x\textsubscript{01} H\textsubscript{2}O"
    assert esc("a\u2212b") == "a$-$b"


def test_angle_brackets_and_bar_are_escaped_for_ot1():
    assert ps.latex_escape("Spread widened to >$5, a<b, x|y") == (
        r"Spread widened to \textgreater{}\$5, a\textless{}b, x\textbar{}y"
    )


def test_matching_quotes_hyphens_and_greek():
    esc = ps.latex_escape
    assert esc("\u2018API\u2019") == "`API'"
    assert esc("\u201cAPI\u201d") == "``API''"
    assert esc("a\u2011b a\u2010b") == r"a\mbox{-}b a-b"
    assert esc("\u03b1\u03b2 \u03a9 \u03a3 \u0391") == r"$\alpha$$\beta$ $\Omega$ $\Sigma$ $A$"
    assert esc("caf\u00e9 \u00dcber \u0142") == "caf\u00e9 \u00dcber \u0142"  # Latin letters pass
    assert esc("\u2116 5 \u2030 \u2026") == r"\textnumero{} 5 \textperthousand{} \ldots{}"


def test_unmapped_characters_warn_and_print_a_visible_question_mark():
    with pytest.warns(UserWarning, match="U\\+4E2D"):
        assert ps.latex_escape("a \u4e2d b") == r"a \textbf{?} b"
    assert ps.latex_escape("a \u4e2d", warn=False) == r"a \textbf{?}"
    assert ps.unmapped_chars("CO\u2082 \u4e2d \u4e2d \U0001f600") == ["\u4e2d", "\U0001f600"]
    assert ps.unmapped_chars("Mt CO\u2082 m\u207b\u00b2 \u00b5g \u03c3") == []


def test_saved_tex_is_ascii_except_latin_letters_and_warns_about_the_rest(tmp_path):
    fig, _ = _good(title="Mt CO\u2082 fell 4% in W m\u207b\u00b2 on \u2018API\u2019 crude", units="m\u00b3, \u00b5g")
    ps.save(fig, tmp_path / "u", formats=("tex",))
    tex = (tmp_path / "u.tex").read_text(encoding="utf-8")
    assert tex.isascii()
    assert "CO\\textsubscript{2}" in tex and "`API'" in tex
    fig, _ = _good(title="Demand fell 4% in \u4e2d\u56fd")
    with pytest.warns(UserWarning, match="u2.tex"):
        ps.save(fig, tmp_path / "u2", formats=("tex",))
    assert "\\textbf{?}" in (tmp_path / "u2.tex").read_text(encoding="utf-8")


# ------------------------------------------------------------------ fix round: twin axes


def _twin_fig(**over):
    fig, axes = ps.figure()
    a = axes[0][0]
    a.plot([0, 1, 2], [1, 2, 3])
    b = a.twinx()
    b.plot([0, 1, 2], [3, 2, 1])
    ps.frame(fig, **{**FRAME, "xlabel": "Year (yr)", "ylabel": "Demand (GW)", **over})
    return fig, a, b


def test_a_twin_is_not_a_panel_so_it_gets_no_letter_and_no_copied_label():
    fig, a, b = _twin_fig()
    assert [len(ax.texts) for ax in fig.axes] == [0, 0]
    assert a.get_ylabel() == "Demand (GW)" and b.get_ylabel() == ""
    assert a.get_xlabel() == "Year (yr)" and b.get_xlabel() == ""
    assert ps.lint(fig) == []  # no false P6 for the hidden twin x label


def test_a_twin_scale_needs_its_own_label_under_p7_and_then_saves(tmp_path):
    fig, a, b = _twin_fig()
    assert any("P7" in p for p in ps.lint(fig, axis_labels=True))
    b.set_ylabel("Price (EUR)")
    assert ps.lint(fig, axis_labels=True) == []
    assert len(ps.save(fig, tmp_path / "tw")) == 4


def test_axes_title_check_still_applies_with_a_twin():
    fig, a, b = _twin_fig()
    a.set_title("Demand and price")
    assert any(p.startswith("P2") for p in ps.lint(fig))
    a.set_title("")
    b.set_title("Demand and price")
    assert any(p.startswith("P2") for p in ps.lint(fig))


def test_twin_on_a_two_panel_figure_keeps_two_letters():
    fig, axes = ps.figure(2, 1)
    for a in axes[:, 0]:
        a.plot([0, 1], [0, 1])
    axes[0][0].twinx().plot([0, 1], [1, 0])
    ps.frame(fig, **{**FRAME, "xlabel": "x (u)", "ylabel": "y (u)"})
    letters = sorted(t.get_text() for ax in fig.axes for t in ax.texts)
    assert letters == ["(a)", "(b)"]


def test_skip_panel_excludes_a_helper_axes():
    fig, axes = ps.figure()
    axes[0][0].plot([0, 1], [0, 1])
    helper = ps.skip_panel(fig.add_axes([0.7, 0.7, 0.1, 0.1]))
    helper.axis("off")
    ps.frame(fig, **{**FRAME, "xlabel": "x (u)", "ylabel": "y (u)"})
    assert [len(ax.texts) for ax in fig.axes] == [0, 0]


# ------------------------------------------------------------------ fix round: image panels


def _image_fig():
    import numpy as np

    fig, axes = ps.figure(1, 2, sharex=False)
    for ax in axes[0]:
        ax.imshow(np.arange(16.0).reshape(4, 4))
        ax.axis("off")
    ps.frame(fig, **{**FRAME, "xlabel": "x (u)", "ylabel": "y (u)"})
    return fig, axes


def test_axis_off_image_panels_get_no_letters_as_in_the_reference(tmp_path):
    fig, axes = _image_fig()
    assert [[t.get_text() for t in ax.texts] for ax in axes[0]] == [[], []]
    assert ps.lint(fig, axis_labels=True) == []  # no false P7 on switched-off axes
    assert axes[0][0].get_ylabel() == ""  # an invisible axis is not labelled
    ps.save(fig, tmp_path / "img")


def test_as_panel_gives_an_axis_off_image_a_letter(tmp_path):
    import numpy as np

    fig, axes = ps.figure(1, 2, sharex=False)
    for ax in axes[0]:
        ax.imshow(np.arange(16.0).reshape(4, 4))
        ax.axis("off")
        ps.as_panel(ax)
    ps.frame(fig, **FRAME)
    assert [[t.get_text() for t in ax.texts] for ax in axes[0]] == [["(a)"], ["(b)"]]
    ps.save(fig, tmp_path / "img")


def test_a_colorbar_next_to_images_is_still_not_a_panel():
    import numpy as np

    fig, axes = ps.figure(1, 2, sharex=False)
    ims = [ax.imshow(np.arange(16.0).reshape(4, 4)) for ax in axes[0]]
    for ax in axes[0]:
        ax.axis("off")
        ps.as_panel(ax)
    fig.colorbar(ims[0], ax=list(axes[0]))
    ps.frame(fig, **FRAME)
    assert sorted(t.get_text() for ax in fig.axes for t in ax.texts) == ["(a)", "(b)"]


# ------------------------------------------------------------------ fix round: file names


def test_dotted_names_do_not_collide(tmp_path):
    names = ["wpsr_2026.11.04", "wpsr_2026.11.11", "a", "a.v2", "run_1.5"]
    for n in names:
        fig, _ = _good()
        out = ps.save(fig, tmp_path / n, formats=("pdf", "tex"))
        assert [p.name for p in out] == [f"{n}.pdf", f"{n}.tex"]
    assert len(list(tmp_path.glob("*.pdf"))) == 5 and len(list(tmp_path.glob("*.tex"))) == 5
    tex = (tmp_path / "wpsr_2026.11.04.tex").read_text()
    assert "{wpsr_2026.11.04.pdf}" in tex and "\\label{fig:wpsr-2026-11-04}" in tex


def test_split_path_strips_only_known_extensions():
    sp = ps.split_path
    assert sp("x/a.pdf") == (Path("x"), "a") and sp("x/a.TEX") == (Path("x"), "a")
    assert sp("x/a.v2") == (Path("x"), "a.v2") and sp("x/a.v2.png") == (Path("x"), "a.v2")
    assert sp("x/.pdf") == (Path("x"), ".pdf")
    with pytest.raises(ValueError):
        sp("")


# ------------------------------------------------------------------ fix round: repository switches


def test_asof_zones_switch(monkeypatch):
    monkeypatch.setattr(ps, "ASOF_ZONES", ("ET", "UTC"))
    assert ps.parse_asof("2026-11-04 10:30 ET") and ps.parse_asof("2026-11-04")
    with pytest.raises(ValueError, match="ASOF_ZONES"):
        ps.parse_asof("2026-11-04 10:30 CET")
    ny = datetime(2026, 11, 4, 15, 30, tzinfo=timezone(timedelta(hours=1)))
    assert ps._asof_text(ny) == "2026-11-04 09:30 ET"  # 14:30 UTC is 09:30 in New York in November
    assert ps._asof_text(datetime(2026, 11, 4, 15, 30, tzinfo=timezone.utc)) == "2026-11-04 15:30 UTC"
    monkeypatch.setattr(ps, "ASOF_ZONES", ("UTC",))
    with pytest.raises(ValueError, match="UTC datetime"):
        ps._asof_text(ny)


def test_cadence_source_and_licence_switches(monkeypatch):
    # permissive by default
    for over in ({"cadence": "sometimes"}, {"source": "EIA"}, {"licence": "Proprietary"}):
        fig, ax = ps.figure()
        ax[0][0].plot([0, 1], [0, 1])
        ps.frame(fig, **{**FRAME, "xlabel": "x (u)", "ylabel": "y (u)", **over})
    monkeypatch.setattr(ps, "CADENCE_PATTERN", r"^(daily|weekly|monthly)(, .+)?\Z")
    monkeypatch.setattr(ps, "SOURCE_SHAPE", True)

    def lic(v):
        if not v.startswith("Public domain"):
            raise ValueError(f"licence {v!r} not allowed")

    monkeypatch.setattr(ps, "LICENCE_CHECK", lic)
    for over, msg in (
        ({"cadence": "sometimes"}, "CADENCE_PATTERN"),
        ({"source": "EIA"}, "SOURCE_SHAPE"),
        ({"source": "Energy agency"}, "SOURCE_SHAPE"),
        ({"licence": "Proprietary"}, "not allowed"),
    ):
        fig, _ = ps.figure()
        with pytest.raises(ValueError, match=msg):
            ps.frame(fig, **{**FRAME, **over})
    fig, ax = ps.figure()
    ax[0][0].plot([0, 1], [0, 1])
    ps.frame(fig, **{**FRAME, "licence": "Public domain", "xlabel": "x (u)", "ylabel": "y (u)"})
    assert ps.lint(fig) == []


def test_save_guard_can_refuse_a_destination(tmp_path, monkeypatch):
    seen = []

    def guard(path, fields):
        seen.append((Path(path).name, fields["licence"]))
        if fields["licence"] != "Public domain":
            raise ValueError(f"{path}: not public")

    monkeypatch.setattr(ps, "SAVE_GUARD", guard)
    fig, _ = _good(licence="Proprietary")
    with pytest.raises(ValueError, match="not public"):
        ps.save(fig, tmp_path / "g")
    assert not list(tmp_path.iterdir())
    fig, _ = _good(licence="Public domain")
    ps.save(fig, tmp_path / "g")
    assert seen == [("g", "Proprietary"), ("g", "Public domain")]


def test_every_switch_set_strictly_restores_the_reference_rules(monkeypatch, tmp_path):
    """The home-repo settings of VENDORING.md: what the energy house style always enforced."""
    units = {"kb", "mb", "mb/d", "Bcf", "$/bbl", "%", "GW", "TWh"}
    monkeypatch.setattr(ps, "REQUIRE", ("title", "source", "asof", "units", "cadence", "licence"))
    monkeypatch.setattr(ps, "UNITS", units)
    monkeypatch.setattr(ps, "STRICT_DESK", True)
    monkeypatch.setattr(ps, "ASOF_ZONES", ("ET", "UTC"))
    monkeypatch.setattr(ps, "CADENCE_PATTERN", r"^(daily|weekly|monthly|quarterly|annual)(, .+)?\Z")
    monkeypatch.setattr(ps, "SOURCE_SHAPE", True)
    good = {"title": "Stocks fell 3 mb in the week", "units": "mb", "cadence": "weekly, Wednesday",
            "source": "EIA WPSR table 4 (WCESTUS1)", "licence": "Public domain", "asof": "2026-11-04"}

    def build(**over):
        fig, ax = ps.figure()
        ax[0][0].plot([0, 1], [0, 1], color=ps.TOKENS["series_1"])
        ps.frame(fig, **{**good, "xlabel": "Week (wk)", "ylabel": "Stocks (mb)", **over})
        return fig, ax[0][0]

    fig, _ = build()
    assert ps.lint(fig) == []
    for field_ in ("source", "asof", "units", "cadence", "licence"):
        fig, _ = ps.figure()
        with pytest.raises(ValueError, match=field_):
            ps.frame(fig, **{k: v for k, v in good.items() if k != field_})
    with pytest.raises(ValueError, match="allowed spelling"):
        build(units="MB")
    with pytest.raises(ValueError, match="CADENCE"):
        build(cadence="whenever")
    with pytest.raises(ValueError, match="SOURCE_SHAPE"):
        build(source="EIA")
    fig, ax = build()
    ax.legend(["x"])
    assert any("legend" in p for p in ps.lint(fig))
    fig, ax = build()
    ax.plot([0, 1], [1, 0], color="red")
    assert any("red or green" in p for p in ps.lint(fig))
    fig, ax = build()
    ax.twinx()
    assert any("dual axis" in p for p in ps.lint(fig))


# ------------------------------------------------------------------ fix round 2: sizes, legacy names, helper axes


@pytest.mark.parametrize("width", [ps.COLUMN, ps.FULL])
def test_every_height_in_steps_of_0_07_saves(tmp_path, width):
    """P5 once refused 1.14, 1.63, 2.26, 3.03, 5.06, 5.27, 6.81 in: matplotlib rounds its own way."""
    from PIL import Image

    bad = []
    for i in range(100, 900, 7):
        h = i / 100
        fig, ax = ps.figure(size=(width, h))
        ax[0][0].plot([0, 1], [0, 1])
        ps.frame(fig, **FRAME)
        try:
            out = ps.save(fig, tmp_path / "x", formats=("png",))
        except ValueError as e:  # pragma: no cover - the failure being tested for
            bad.append((h, str(e)))
            continue
        size = Image.open(out[0]).size
        assert abs(size[1] - h * 300) <= 1 and abs(size[0] - width * 300) <= 1
    assert not bad, bad[:3]


def test_the_known_failing_heights_save(tmp_path):
    for h in (1.14, 1.63, 2.26, 3.03, 5.06, 5.27, 6.81):
        fig, ax = ps.figure(size=(7.0, h))
        ax[0][0].plot([1, 2])
        ps.frame(fig, **FRAME)
        assert ps.save(fig, tmp_path / f"h{h}", formats=("png",))


def test_p1_and_p5_agree_on_width(tmp_path):
    fig, ax = ps.figure(size=(3.41, 3))
    ax[0][0].plot([1, 2])
    ps.frame(fig, **FRAME)
    problems = ps.lint(fig)
    assert len(problems) == 1 and problems[0].startswith("P1")
    assert "1020" in problems[0] and "2100" in problems[0]  # names the allowed pixel widths
    with pytest.raises(ValueError, match="P1.*3.4.*7.0"):
        ps.save(fig, tmp_path / "w")
    assert list(tmp_path.iterdir()) == []


def test_a_width_within_the_tolerance_passes_both(tmp_path):
    for w in (3.4005, 3.3995, 7.0005, 6.9995):
        fig, ax = ps.figure(size=(w, 3))
        ax[0][0].plot([1, 2])
        ps.frame(fig, **FRAME)
        assert ps.lint(fig) == [], w
        assert ps.save(fig, tmp_path / f"w{w}", formats=("png",)), w


class _Prefix:
    """LEGACY_PREFIX set for one test (a repository's shim does `ps.LEGACY_PREFIX = "hs"` once)."""

    def __init__(self, monkeypatch, value="hs"):
        monkeypatch.setattr(ps, "LEGACY_PREFIX", value)


def test_default_sets_no_legacy_attributes():
    fig, _ = _good()
    assert hasattr(fig, "_ps_frame") and not hasattr(fig, "_hs_frame") and not hasattr(fig, "_hs_licence")


def test_legacy_prefix_sets_frame_and_licence_aliases(monkeypatch):
    _Prefix(monkeypatch)
    fig, _ = _good()
    assert fig._hs_frame is fig._ps_frame
    assert fig._hs_licence == "CC BY 4.0"
    strings = [str(v) for v in fig._hs_frame.values() if v]  # what a public-figure leak scan reads
    assert "CC BY 4.0" in strings and FRAME["source"] in strings and FRAME["title"] in strings


def test_legacy_prefix_licence_alias_is_none_when_no_licence_given(monkeypatch):
    _Prefix(monkeypatch)
    fig, _ = _good(licence=None)
    assert fig._hs_licence is None and hasattr(fig, "_hs_frame")


def test_legacy_prefix_changes_the_gids(monkeypatch):
    _Prefix(monkeypatch)
    fig, axes = ps.figure(2, 1)
    for ax in axes[:, 0]:
        ax.plot([1, 2])
    ps.frame(fig, **FRAME)
    assert [t.get_gid() for ax in axes[:, 0] for t in ax.texts] == ["hs-panel", "hs-panel"]
    assert ps.skip_panel(fig.add_axes([0.9, 0.1, 0.05, 0.2])).get_gid() == "hs-skip"
    band = ps.add_caption_band(fig)
    assert any(t.get_gid() == "hs-page-caption" for t in band.texts)


def test_legacy_prefix_removes_letters_of_either_prefix_and_reads_either_title_gid(monkeypatch):
    fig, axes = ps.figure(2, 1)
    for ax in axes[:, 0]:
        ax.plot([1, 2])
    ps.frame(fig, **FRAME)  # letters with the ps- gid
    monkeypatch.setattr(ps, "LEGACY_PREFIX", "hs")
    ps.frame(fig, **FRAME)  # framing again must not stack a second set
    assert [t.get_text() for ax in axes[:, 0] for t in ax.texts] == ["(a)", "(b)"]
    fig.text(0.01, 0.99, "A title on the image", gid="hs-title")  # the home repo's own gid
    assert any(p.startswith("P2") for p in ps.lint(fig))
    monkeypatch.setattr(ps, "LEGACY_PREFIX", None)
    fig.texts[-1].set_gid("ps-title")
    assert any(p.startswith("P2") for p in ps.lint(fig))  # the ps- gids are always read


def test_a_legacy_skip_gid_is_honoured_in_either_mode(monkeypatch):
    fig, axes = ps.figure()
    axes[0][0].plot([1, 2])
    helper = fig.add_axes([0.9, 0.1, 0.05, 0.2])
    helper.set_gid("hs-skip")
    monkeypatch.setattr(ps, "LEGACY_PREFIX", "hs")
    assert ps._panels(fig) == [axes[0][0]]


def test_axis_off_helper_axes_are_not_panels():
    """The home repo draws a hand-made key with add_axes(...).set_axis_off(): it must get no letter."""
    fig, axes = ps.figure()
    axes[0][0].plot([1, 2])
    fig.add_axes([0.86, 0.1, 0.1, 0.5]).set_axis_off()
    ps.frame(fig, **FRAME, xlabel="Year", ylabel="Demand (GW)")
    assert [t.get_text() for ax in fig.axes for t in ax.texts] == []
    assert axes[0][0].get_ylabel() == "Demand (GW)"


def test_axis_off_helper_does_not_shift_the_letters_of_real_panels():
    fig, axes = ps.figure(2, 1)
    for ax in axes[:, 0]:
        ax.plot([1, 2])
    fig.add_axes([0.86, 0.1, 0.1, 0.5]).set_axis_off()
    ps.frame(fig, **FRAME)
    assert [t.get_text() for ax in axes[:, 0] for t in ax.texts] == ["(a)", "(b)"]
    assert len([t for ax in fig.axes for t in ax.texts]) == 2

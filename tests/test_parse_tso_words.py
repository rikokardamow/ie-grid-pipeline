"""Line reader for the older EirGrid contracted lists, on lines copied from the PDFs."""

from datetime import date
from decimal import Decimal

import pytest

from iegrid.parse_tso_words import parse_line


@pytest.mark.parametrize("line, want", [
    ("Cahernagh 110kV TG166 Cahernagh Mid Merit OCGT 101.0 Oct 2013",
     ("TG166", "Cahernagh Mid Merit", "OCGT", Decimal("101.0"), "Cahernagh", "110 kV", "",
      date(2013, 10, 1), None)),
    ("Aghada 220 kV TG377 Aghada BESS 01 post Gate 1 Battery 19.0 Aug 2020",
     ("TG377", "Aghada BESS 01", "Battery", Decimal("19.0"), "Aghada", "220 kV", "post Gate 1",
      date(2020, 8, 1), None)),
    ("Athea (2) 3 TG77 20.00 Gate 2 Athea 110kV May 2008",
     ("TG77", "Athea (2)", "Wind", Decimal("20.00"), "Athea", "110 kV", "Gate 2",
      date(2008, 5, 1), None)),
    ("Barnadivane (1) TG44 60.00 Gate 3 Barnadivine 110kV Aug 2014 Apr 2017",
     ("TG44", "Barnadivane (1)", "Wind", Decimal("60.00"), "Barnadivine", "110 kV", "Gate 3",
      date(2014, 8, 1), date(2017, 4, 1))),
    # a phase suffix after the ref, and a node the PDF set in overlapping type
    ("Kill Hill (1) - phase 2 1 TG69 ph2 22.50 Gate 3 Kill Hill 110kV Mar 2011",
     ("TG69", "Kill Hill (1) - phase 2", "Wind", Decimal("22.50"), "Kill Hill", "110 kV", "Gate 3",
      date(2011, 3, 1), None)),
    ("Loop-in Kinn1e1g0ad k- V TG315 Clonfad Solar ECP-1 Solar 100.0 Oct 2020",
     ("TG315", "Clonfad Solar", "Solar", Decimal("100.0"), None, None, "ECP-1",
      date(2020, 10, 1), None)),
    # the P-series and the demand-side refs, and a ref run into the next word
    ("Castletownmoor P230 120.00 Gate 3 Castletownmoor 110kV Mar 2015",
     ("P230", "Castletownmoor", "Wind", Decimal("120.00"), "Castletownmoor", "110 kV", "Gate 3",
      date(2015, 3, 1), None)),
    ("Arklow 220 kV D40d Pollahoney Autoproducer Autoproducer Autoproducer 288.0 Nov 2024",
     ("D40d", None, "Autoproducer", Decimal("288.0"), "Arklow", "220 kV", None,
      date(2024, 11, 1), None)),
    ("Gorman 110kV TG286Gorman (Graigs) Energy Storage Station Battery & Inverter 30.0 Aug 2019",
     ("TG286", None, None, Decimal("30.0"), "Gorman", "110 kV", None, date(2019, 8, 1), None)),
])
def test_lines(line, want):
    r = parse_line(line)
    got = (r["ref"], r["name"], r["technology"], r["mec_mw"], r["node"], r["voltage"],
           r["processing"], r["signed"], r["target"])
    for g, w in zip(got, want, strict=True):
        if w is not None:
            assert g == w, (g, w)


def test_a_line_without_a_ref_is_not_a_row():
    assert parse_line("Total TSO Contracted Wind: 1172.55") is None
    assert parse_line("Tobertooreen Wind Farm") is None


def test_no_mec_is_an_error_not_a_guess():
    assert "error" in parse_line("Athlone 110 kV TG495 Reciprocating")

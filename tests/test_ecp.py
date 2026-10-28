from decimal import Decimal
from pathlib import Path

import pytest

from iegrid.ecp import Layout, rows_on_page
from iegrid.store import ROOT


def w(text, x0, top, width=None):
    width = width or 6 * len(text)
    return {"text": text, "x0": x0, "x1": x0 + width, "top": top, "bottom": top + 9}


HEADER = [w("Name", 40, 100), w("of", 70, 100), w("Facility", 82, 100), w("Applicant", 200, 100),
          w("County", 320, 100), w("Easting", 380, 100), w("Gen", 450, 100), w("Type", 450, 110),
          w("MEC", 510, 100), w("Assumed", 560, 100), w("Node", 560, 110), w("PP", 640, 100)]


def test_rows_with_wrapped_names():
    words = HEADER + [
        # a name wrapped over two lines, centred on its county
        w("Ballymoneen", 40, 130), w("Solar", 40, 141), w("Park", 75, 141),
        w("Ballymoneen", 200, 135), w("Galway", 320, 135), w("143417", 380, 135),
        w("Solar", 450, 135), w("100", 510, 135), w("Cashla", 560, 135),
        w("Ballyroe", 40, 170), w("Solar", 90, 170), w("Cork", 320, 170), w("120", 510, 170),
        w("Charleville", 560, 170),
        # "Cork" in a name, outside the County column, is not a row
        w("Cork", 40, 200), w("Harbour", 70, 200), w("Kerry", 320, 200), w("50", 510, 200),
    ]
    rows, carry = rows_on_page(words, 4, 800)
    assert [(r.name, r.county, r.mec_mw, r.node) for r in rows] == [
        ("Ballymoneen Solar Park", "Galway", Decimal(100), "Cashla"),
        ("Ballyroe Solar", "Cork", Decimal(120), "Charleville"),
        ("Cork Harbour", "Kerry", Decimal(50), ""),
    ]
    assert isinstance(carry, Layout)


def test_table_runs_onto_a_page_without_a_header():
    _, carry = rows_on_page(HEADER + [w("A", 40, 130), w("Cork", 320, 130), w("5", 510, 130)],
                            5, 800)
    rows, _ = rows_on_page([w("Rath", 40, 50), w("Solar", 70, 50), w("Offaly", 320, 50),
                            w("119", 510, 50)], 6, 800, carry)
    assert [(r.page, r.name, r.county, r.mec_mw) for r in rows] == [
        (6, "Rath Solar", "Offaly", Decimal(119))]


def test_no_header_no_carry_no_rows():
    assert rows_on_page([w("Cork", 320, 50)], 1, 800) == ([], None)


# 2024-Batch-ECP-2.5-ECP-2.5.1-Results-JSO-Publication-May-2025.pdf, by archive digest
ECP_2_5 = "Y54YZWG6QXIBSSD22IDAKHIYHZPEJ6YZ"


def test_real_ecp_2_5_has_its_seventy_projects():
    """The May 2025 publication says 70 projects are due offers under Category A."""
    from iegrid.ecp import parse_ecp

    path = ROOT / "data" / "archive-cache" / f"{ECP_2_5}.pdf"
    if not path.exists():
        pytest.skip("ECP-2.5 file not on this machine")
    rows = parse_ecp(Path(path).read_bytes())
    assert len(rows) == 70
    assert ("Ballivor Wind Farm", "Westmeath", Decimal(182)) in {
        (r.name, r.county, r.mec_mw) for r in rows}

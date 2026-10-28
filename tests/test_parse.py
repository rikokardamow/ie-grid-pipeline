"""Parser tests on cells copied from the 28 Oct 2026 files, as pdfplumber returns them."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from iegrid import parse
from iegrid.store import ROOT

TSO_HEAD = ["Node and Associated\nVoltage", "Ref", "Name", "Processing\nType", "Type",
            "MEC\n(MW)", "Signed\nDate*"]
DSO_HEAD = ["", "ESBNG", "", "Project", "Type", "MEC_MW", "Feeding Station",
            "Designed_110kV_Station", "Offer_Type", "Status", "", "Conn", ""]
DSO_HEAD2 = [None, "Reference", None, None, None, None, None, None, None, None, None, "Voltage",
             None]
DSO_E_HEAD = ["", "ESBNG", "", "Project", "Type", "MEC_MW", "Feeding Station",
              "Designed_110kV_Station", "Offer_Type", "Status", "Connect_Date", "", "Conn", ""]
DSO_E_HEAD2 = [None, "Reference", *[None] * 10, "Voltage", None]


def tso(*rows, text=""):
    # the finder also returns wrapped header cells as one-column tables; they must be skipped
    return parse.parse_tso_pages([(1, [[TSO_HEAD, *rows], [["MEC"], ["(MW)"]]], text)])


def test_tso_row():
    got = tso(["Knockranny 110 kV", "TG443", "Ardderroo Wind Farm Extension", "ECP-2.1", "Wind",
               "18.0", "Jul 2023"], text="Total TSO Contracted Wind: 2053.45")
    (r,) = got.rows
    assert (r.project_ref, r.node, r.voltage, r.processing_type, r.technology) == (
        "TG443", "Knockranny", "110 kV", "ECP-2.1", "Wind")
    assert r.mec_mw == Decimal("18.0") and r.signed_month == date(2023, 7, 1)
    assert r.status == "Contracted" and r.energised_on is None
    assert got.printed_total_mw == Decimal("2053.45")


def test_tso_wrapped_cells_and_odd_refs():
    got = tso(
        ["Thornsberry 110 kV", "TG454", "Ballycosney Thornsberry Battery\nStorage", "ECP-2.3",
         "Battery", "150.0", "Jun 2024"],
        ["Derryiron 110 kV", "TG679", "Barrysbrook LDES", "T-4\n2028/2029", "Battery", "49.0",
         "Jan 2026"],
        ["Arklow 220 kV", "D40d", "Pollahoney Autoproducer", "Demand", "Autoproduce\nr", "288.0",
         "Nov 2024"],
        text="Total TSO Contracted: 12640.9",
    )
    a, b, c = got.rows
    assert a.name == "Ballycosney Thornsberry Battery Storage"
    assert b.processing_type == "T-4 2028/2029"
    assert c.project_ref == "D40d" and c.voltage == "220 kV"
    assert [r.row_order for r in got.rows] == [1, 2, 3]
    assert got.printed_total_mw == Decimal("12640.9")


def test_tso_bad_row_raises():
    with pytest.raises(parse.ParseError):
        tso(["Knockranny", "TG443", "x", "ECP-2.1", "Wind", "18.0", "Jul 2023"])  # no voltage
    with pytest.raises(parse.ParseError):
        tso(["Knockranny 110 kV", "TG443", "x", "ECP-2.1", "Wind", "n/a", "Jul 2023"])


def dso(head, head2, *rows):
    defs = [["CHP:", "Combined Heat and Power"]]
    return parse.parse_dso_pages([(1, [defs], ""), (2, [[head, head2, *rows]], "")])


def test_dso_contracted_rows_and_total():
    got = dso(DSO_HEAD, DSO_HEAD2,
              ["DG1510", None, None, "Farrangalway Solar PV Farm", "Solar", "4.95", "KINSALE",
               "BANDON", "ECP-2.1", "Contracted", "10 kV", None, None],
              ["DG2074", None, None, "Johnstown Solar Park", "Solar", "9.99", "", "CARLOW",
               "ECP-2.4", "Contracted", "38 kV", None, None],
              ["MZ953", None, None, "Tirlan Ballyragget Solar", "Solar", "0", "BALLYCONRA",
               "BALLYRAGGET", "Zero Mec", "Contracted", "38 kV", None, None],
              ["", None, None, "", "Total", "1836", "", "", "", "", "", None, None])
    a, b, c = got.rows
    assert (a.project_ref, a.node, a.station_110kv, a.voltage, a.page) == (
        "DG1510", "KINSALE", "BANDON", "10 kV", 2)
    assert b.node == ""  # a real empty feeding station stays empty, columns don't shift
    assert c.mec_mw == 0 and c.processing_type == "Zero Mec"
    assert got.printed_total_mw == Decimal(1836)


def test_dso_energised_dates():
    got = dso(DSO_E_HEAD, DSO_E_HEAD2,
              ["DG1403", None, None, "Creevy Solar", "Solar", "4", "ROSCOMMON", "LANESBORO",
               "Non GPA", "Energised", "24/04/2026", "10 kV", None, None],
              ["DG948", None, None, "Dairygold,\nMitchelstown (2)", "Nat. Gas", "8.55",
               "CASTLEFARM", "BARRYMORE", "Pre-Gate", "Energised", "Energisation\ndate pre 2005",
               "38 kV", None, None],
              ["DG93A", None, None, "x", "Wind", "1", "", "Y", "Gate 2", "Energised", "", "LV",
               None, None],
              ["", None, None, "", "", "", "", "", "", "", "", "", None, None],
              ["", None, None, "", "Total", "", "", "", "", "", "", "", None, None])
    a, b, c = got.rows
    assert a.energised_on == date(2026, 4, 24) and a.energised_note == ""
    assert b.energised_on is None and b.energised_note == "pre 2005"
    assert b.name == "Dairygold, Mitchelstown (2)"
    assert c.project_ref == "DG93A" and c.voltage == "LV" and c.energised_on is None
    assert got.printed_total_mw is None  # the energised renewable list prints a blank total


def test_dso_shifted_columns_raise():
    with pytest.raises(parse.ParseError):
        dso(DSO_HEAD, DSO_HEAD2,
            ["DG1510", None, None, "Farrangalway", "Solar", "4.95", "KINSALE", "BANDON",
             "ECP-2.1", "Contracted", "10 kV", "extra", None])


def test_text_ref_count():
    text = ("Distribution Contracted Renewable Q2 2026 2\n"
            "DG1510 Farrangalway Solar PV Farm Solar 4.95 KINSALE BANDON ECP-2.1 Contracted 10 kV\n"
            "MZ953 Tirlan Ballyragget Solar Solar 0 BALLYCONRA BALLYRAGGET Zero Mec Contracted 38 kV\n"
            "Knockranny 110 kV TG443 Ardderroo Wind Farm Extension ECP-2.1 Wind 18.0 Jul 2023\n")
    assert len(parse.TEXT_REF.findall(text)) == 3  # "Q2 2026" in the header is not a ref


# The real files of 28 Oct 2026, when they are on this machine (data/ is not in git).
REAL = {
    "eirgrid.tso_contracted_wind": ("4bac82f954fe", 30, Decimal("2053.45")),
    "eirgrid.tso_contracted_nonwind": ("458a66548bc2", 128, Decimal("12640.9")),
    "esb.dso_contracted_renewable": ("09da213e84c5", 167, Decimal(1836)),
    "esb.dso_energised_renewable": ("d0c7620f5387", 448, None),
    "esb.dso_contracted_nonrenewable": ("73ca781fdbaf", 10, Decimal(128)),
    "esb.dso_energised_nonrenewable": ("3596b9302425", 32, Decimal(264)),
}


@pytest.mark.parametrize("source_id", REAL)
def test_real_file(source_id):
    sha, n, printed = REAL[source_id]
    files = list((ROOT / "data" / "raw" / source_id).glob(f"*-{sha}.pdf"))
    if not files:
        pytest.skip("raw file not on this machine")
    content = Path(files[0]).read_bytes()
    got = parse.PARSERS[source_id](content)
    assert len(got.rows) == n == sum(parse.refs_in_text(content).values())
    assert got.printed_total_mw == printed
    if printed is not None:
        assert abs(sum(r.mec_mw for r in got.rows) - printed) <= 1

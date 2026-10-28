from decimal import Decimal

from iegrid.ecp import EcpRow
from iegrid.region import (
    Project,
    assign,
    key,
    norm_node,
    norm_substation,
    osm_county,
)


def P(ref, name, mec, node="", sid="eirgrid.tso_contracted_nonwind"):
    return Project(ref, sid, name, Decimal(mec), node)


def E(name, county, mec, node=""):
    return EcpRow(1, name, county, Decimal(mec), node)


def test_key_drops_filler_keeps_numbers():
    assert key("Ballyroe Solar Extension") == key("Ballyroe Solar") == ("ballyroe",)
    assert key("Ballymoneen Phase 2") != key("Ballymoneen Solar Park")
    assert key("Ballycore Solar (formerly Middleton)") == ("ballycore",)
    assert key("Rath Solar PV (ECP2.4+2.5)") == ("rath",)


def test_name_match_needs_close_mec_and_agreeing_counties():
    projects = [P("TG1", "Ballymoneen Solar Park", "100"),
                P("TG2", "Coole Wind Farm", "9.5"),          # MEC far from the ECP row
                P("TG3", "Kilmore Solar", "50")]             # two counties in ECP
    ecp = [E("Ballymoneen Solar", "Galway", "100"), E("Coole Wind Farm Extension", "Westmeath", "88"),
           E("Kilmore Solar Farm", "Wexford", "50"), E("Kilmore Solar", "Cork", "50")]
    got = {c.project_ref: (c.county, c.basis) for c in assign(projects, ecp)}
    assert got == {"TG1": ("Galway", "name"), "TG2": (None, "none"), "TG3": (None, "none")}


def test_node_vote_needs_enough_projects_and_a_clear_majority():
    ecp = [E("A", "Cork", "10", "Knockraha"), E("B", "Cork", "20", "Knockraha 220 kV"),
           E("C", "Cork", "30", "Knockraha"), E("D", "Kerry", "5", "Tarbert"),
           E("E", "Laois", "5", "Border"), E("F", "Offaly", "5", "Border")]
    projects = [P("TG9", "Celtic Interconnector", "700", "Knockraha"),
                P("TG8", "X", "100", "Tarbert"),     # one vote only
                P("TG7", "Y", "100", "Border")]      # split 50/50
    got = {c.project_ref: (c.county, c.basis) for c in assign(projects, ecp)}
    assert got == {"TG9": ("Cork", "node"), "TG8": (None, "none"), "TG7": (None, "none")}


def test_osm_only_when_one_county_has_that_substation():
    subs = [("Southbank 220kV Substation", "Dublin"), ("Ballybeg 38 kV Substation", "Wicklow"),
            ("Ballybeg Substation", "Meath")]
    projects = [P("TG5", "Poolbeg OCGT", "299", "Southbank"), P("TG6", "Z", "5", "Ballybeg")]
    got = {c.project_ref: (c.county, c.basis) for c in assign(projects, [], subs)}
    assert got == {"TG5": ("Dublin", "osm-node"), "TG6": (None, "none")}


def test_names_and_areas():
    assert norm_node("GALWAY 110KV") == norm_node("Galway") == "galway"
    assert norm_substation("Knockraha 220kV Substation") == "knockraha"
    assert osm_county("County Cork") == "Cork"
    assert osm_county("Fingal") == osm_county("Dún Laoghaire–Rathdown") == "Dublin"
    assert osm_county("Limerick City and County") == "Limerick"
    assert osm_county("Somewhere") is None

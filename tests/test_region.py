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
    got = {c.project_ref: (c.county, c.basis) for c in assign(projects, ecp, cited=[])}
    assert got == {"TG1": ("Galway", "name"), "TG2": (None, "none"), "TG3": (None, "none")}


def test_node_vote_needs_enough_projects_and_a_clear_majority():
    ecp = [E("Ballyvatta Solar", "Cork", "10", "Knockraha"),
           E("Carrigtwohill Solar", "Cork", "20", "Knockraha 220 kV"),
           E("Glounthaune Battery", "Cork", "30", "Knockraha"),
           E("Tarbert Battery", "Kerry", "5", "Tarbert"), E("Moneen Solar", "Kerry", "6", "Tarbert"),
           E("Abbeyleix Solar", "Laois", "5", "Border"), E("Ballyfin Solar", "Laois", "6", "Border"),
           E("Cloghan Solar", "Offaly", "5", "Border")]
    projects = [P("TG9", "Celtic Interconnector", "700", "Knockraha"),
                P("TG8", "X", "100", "Tarbert"),     # two distinct projects: enough
                P("TG7", "Y", "100", "Border")]      # 2 of 3, under 75%
    got = {c.project_ref: (c.county, c.basis) for c in assign(projects, ecp, cited=[])}
    assert got == {"TG9": ("Cork", "node"), "TG8": ("Kerry", "node"), "TG7": (None, "none")}


def test_osm_only_when_one_county_has_that_substation():
    subs = [("Southbank 220kV Substation", "Dublin"), ("Ballybeg 38 kV Substation", "Wicklow"),
            ("Ballybeg Substation", "Meath")]
    projects = [P("TG5", "Poolbeg OCGT", "299", "Southbank"), P("TG6", "Z", "5", "Ballybeg")]
    got = {c.project_ref: (c.county, c.basis) for c in assign(projects, [], subs, cited=[])}
    assert got == {"TG5": ("Dublin", "osm-node"), "TG6": (None, "none")}


def test_names_and_areas():
    assert norm_node("GALWAY 110KV") == norm_node("Galway") == "galway"
    assert norm_substation("Knockraha 220kV Substation") == "knockraha"
    assert osm_county("County Cork") == "Cork"
    assert osm_county("Fingal") == osm_county("Dún Laoghaire–Rathdown") == "Dublin"
    assert osm_county("Limerick City and County") == "Limerick"
    assert osm_county("Somewhere") is None


ROW = {"project_ref": "TG560", "name_in_list": "Poolbeg OCGT", "node": "Southbank",
       "county": "Dublin", "source_url": "https://www.pleanala.ie/x", "source_says": "Dublin 4",
       "checked_on": "2026-10-28"}


def test_cited_row_applies_only_to_the_same_project():
    projects = [P("TG560", "Poolbeg OCGT", "299", "Southbank"),
                P("TG86", "Oriel Wind Farm", "210", "Oriel")]
    reused = {**ROW, "project_ref": "TG86"}  # a ref reused for another name: not applied
    got = {c.project_ref: (c.county, c.basis) for c in assign(projects, [], cited=[ROW, reused])}
    assert got == {"TG560": ("Dublin", "cited"), "TG86": (None, "none")}


def test_a_printed_county_beats_a_cited_one():
    projects = [P("TG560", "Poolbeg OCGT", "299", "Southbank")]
    ecp = [E("Poolbeg OCGT", "Meath", "299")]
    (c,) = assign(projects, ecp, cited=[ROW])
    assert (c.county, c.basis) == ("Meath", "name")


def test_the_shipped_table_is_complete_and_sourced():
    from iegrid.ecp import COUNTIES
    from iegrid.region import cited_table
    rows = cited_table()
    assert rows and len({r["project_ref"] for r in rows}) == len(rows)
    for r in rows:
        assert r["county"] in COUNTIES and r["source_url"].startswith("https://")
        assert r["source_says"] and r["checked_on"]


# The g4 review's made-up names, and the real mismatches it found
REVIEW_ECP = [E("Knockmore Upper Solar Farm", "Cork", "10"), E("Garrane Wind Farm", "Cork", "12"),
              E("Rossmore Solar", "Wexford", "8"), E("Ballyduff Solar", "Wexford", "9"),
              E("Coolcarrigan Solar P2", "Meath", "180"), E("Lisbrien 2", "Cork", "5"),
              E("Liss Wind Farm", "Kilkenny", "2.35")]


def test_one_shared_word_is_not_a_match():
    projects = [P("T1", "Upper Solar Farm", "10"), P("T2", "Garrane Wind Farm Phase 2", "12"),
                P("T3", "Rossmore North Solar", "8"), P("T4", "Ballyduff ESB Solar Park", "9")]
    got = {c.project_ref: c.basis for c in assign(projects, REVIEW_ECP, cited=[])}
    assert got["T1"] == "none"   # "upper" alone is not a name
    assert got["T2"] == "none"   # a phase number never matches the unnumbered project
    assert got["T3"] == "none"   # "north" tells twins apart: Rossmore North is not Rossmore
    assert got["T4"] == "name"


def test_phase_number_keeps_projects_apart():
    projects = [P("T5", "Coolcarrigan Solar", "180"), P("T6", "Lisbrien", "5")]
    got = {c.project_ref: c.basis for c in assign(projects, REVIEW_ECP, cited=[])}
    assert got == {"T5": "none", "T6": "none"}


def test_small_projects_need_a_close_mec():
    # Liss Wind Farm 1.8 MW against a 2.35 MW row: over the 0.5 MW floor
    (c,) = assign([P("DG2159", "Liss Wind Farm", "1.8")], REVIEW_ECP, cited=[])
    assert c.basis == "none"


def test_a_project_votes_once_at_its_node():
    """One ECP project in five editions, placed by name too, is still one vote."""
    ecp = [E("Coolnabacky Solar", "Laois", "50", "Coolnabacky")] * 5
    projects = [P("T7", "Coolnabacky Solar", "50", "Coolnabacky"),
                P("T8", "Other Battery", "20", "Coolnabacky")]
    got = {c.project_ref: c.basis for c in assign(projects, ecp, cited=[])}
    assert got == {"T7": "name", "T8": "none"}


def test_rules_change_with_the_cited_table(tmp_path, monkeypatch):
    from iegrid import region
    before = region.rules()
    copy = tmp_path / "cited.csv"
    copy.write_text(region.CITED.read_text().replace(",Dublin,", ",Meath,"))
    monkeypatch.setattr(region, "CITED", copy)
    assert region.rules() != before


def test_twins_stay_apart_and_refs_in_names_are_ignored():
    ecp = [E("TG279 Timahoe South", "Kildare", "81"), E("Timahoe North Solar", "Kildare", "70")]
    projects = [P("TG279", "Timahoe South Solar", "81"), P("TG280", "Timahoe North", "81")]
    got = {c.project_ref: (c.county, c.basis) for c in assign(projects, ecp, cited=[])}
    assert got == {"TG279": ("Kildare", "name"), "TG280": (None, "none")}  # MEC 81 vs 70


def test_generic_words_alone_name_nothing():
    assert key("Upper Solar Farm") == key("North 2") == ()


def test_a_project_misread_twice_is_one_vote_and_never_votes_for_itself():
    ecp = [E("Blackwater Bog Solar 1", "Offaly", "65", "Shannonbridge"),
           E("Blackwater Bog Bord", "Offaly", "65", "Shannonbridge"),  # the same project
           E("Shannonbridge ESS", "Offaly", "63.2", "Shannonbridge")]
    projects = [P("TG557", "Shannonbridge TEG2", "260", "Shannonbridge"),
                P("TG289", "Blackwater Bog Solar Farm 1", "65", "Shannonbridge")]
    got = {c.project_ref: c for c in assign(projects, ecp, cited=[])}
    assert got["TG557"].evidence == "2 of 2 projects at Shannonbridge are in Offaly"
    # Blackwater Bog itself: its own rows don't vote, which leaves one project, not enough
    assert got["TG289"].basis in ("name", "none")

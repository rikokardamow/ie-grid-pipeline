from datetime import UTC, datetime
from decimal import Decimal

from iegrid import counties, parse, store
from iegrid.fetch import Download
from tests.test_store import PUB

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
E = "https://www.eirgridgroup.com/site-files/library/EirGrid/"


def test_which_files_are_results():
    assert counties.is_ecp_results(E + "2020-Batch-(ECP-2.1)-Results-Joint-SO-Publication_January-2021.pdf")
    assert counties.is_ecp_results(
        "https://x/sept-2025-batch-ecp-gss-1-results-initial-publication.pdf")
    assert not counties.is_ecp_results(
        "https://x/ECP-2.3-Solar-and-Wind-Constraints-Report-Results-for-Area-A-v1.0.pdf")
    assert not counties.is_ecp_results("https://x/ECP-2-2-Results-Webinar-Slides-All-Area.pdf")


def add_contracted(con, rows):
    pid = store.insert(con, PUB)
    for i, (ref, name, mec, node) in enumerate(rows, start=1):
        con.execute("insert into project_row values (?, ?, ?, 1, ?, ?, 'Solar', ?, ?, '', '110 kV', "
                    "'ECP-2.1', 'Contracted', null, null, '', '[]')",
                    [pid, parse.PARSER_VERSION, i, ref, name, Decimal(mec), node])
    return pid


def test_build_once_per_editions_and_rules(con, monkeypatch):
    add_contracted(con, [("TG1", "Ballymoneen Solar Park", "100", "Cashla"),
                         ("TG2", "Nowhere Solar", "5", "Atlantis")])
    monkeypatch.setattr(counties.ecp, "parse_ecp", lambda content: [
        counties.ecp.EcpRow(4, "Ballymoneen Solar", "Galway", Decimal(100), "Cashla")])
    notes = counties.read_ecp_files(
        con, NOW, rows_for=lambda p: [], live=["https://x/ecp-2.4-results.pdf"],
        download=lambda url: Download(url, b"%PDF ecp", None))
    assert notes == ["read 1 rows from ecp-2.4-results.pdf (live)"]
    assert counties.build(con, NOW) == "build 1: 2 projects"
    got = con.execute("select project_ref, county, basis from project_county order by 1").fetchall()
    assert got == [("TG1", "Galway", "name"), ("TG2", None, "none")]
    # nothing new: no second build, and the same file isn't read twice
    assert counties.read_ecp_files(con, NOW, rows_for=lambda p: [],
                                   live=["https://x/ecp-2.4-results.pdf"],
                                   download=lambda url: Download(url, b"%PDF ecp", None)) == []
    assert counties.build(con, NOW) == "build: unchanged"
    monkeypatch.setattr(counties.region, "RULES", "changed")
    assert counties.build(con, NOW).startswith("build 2")
    con.execute("insert into osm_node values ('cashla', 'Galway', 'node/1', 'Cashla', ?)", [NOW])
    assert counties.build(con, NOW).startswith("build 3")  # new input, new build


KNOCKRAHA = [{"osm_type": "way", "osm_id": 1043280618, "category": "landuse", "type": "construction",
              "name": "Gogganstown 400-kV substation",
              "display_name": "Gogganstown 400-kV substation, Knockraha, Municipal District of Cobh, "
                              "County Cork, Munster",
              "address": {"hamlet": "Knockraha", "county": "County Cork"}}]


def test_substation_found_by_its_locality():
    county, r = counties.substation_county("knockraha", KNOCKRAHA)
    assert county == "Cork" and r["osm_id"] == 1043280618


def test_not_a_substation_or_not_this_place_is_ignored():
    shop = [{**KNOCKRAHA[0], "name": "Knockraha Stores", "type": "shop"}]
    assert counties.substation_county("knockraha", shop) is None
    elsewhere = [{**KNOCKRAHA[0], "display_name": "Gogganstown 400-kV substation, Glanmire, "
                  "County Cork", "address": {"county": "County Cork"}}]
    assert counties.substation_county("knockraha", elsewhere) is None


def test_two_counties_is_no_answer():
    other = {**KNOCKRAHA[0], "osm_id": 2, "name": "Knockraha Substation",
             "address": {"county": "County Kerry"}}
    assert counties.substation_county("knockraha", KNOCKRAHA + [other]) is None


def test_lookups_cached_and_stored(con, tmp_path):
    asked = []

    def search(q):
        asked.append(q)
        return KNOCKRAHA if q.startswith("knockraha") else []

    counties.NOMINATIM_PAUSE_S = 0
    assert counties.lookup_nodes(con, ["Knockraha", "Atlantis"], NOW, tmp_path, search) == []
    assert counties.lookup_nodes(con, ["Knockraha"], NOW, tmp_path, search) == []
    assert asked == ["atlantis substation", "atlantis", "knockraha substation", "knockraha"]
    assert con.execute("select node, county from osm_node").fetchall() == [("knockraha", "Cork")]


def test_killonan_gis_substation_matches():
    r = {"osm_type": "way", "osm_id": 5, "type": "construction", "name": "Killonan 220-kV GIS Substation",
         "display_name": "Killonan 220-kV GIS Substation, Ballysimon ED, Limerick, County Limerick",
         "address": {"city": "Limerick", "county": "County Limerick"}}
    assert counties.substation_county("killonan", [r])[0] == "Limerick"


def test_place_fallback_only_when_one_county():
    def place(county, i):
        return {"osm_type": "node", "osm_id": i, "type": "village", "name": "Doon",
                "display_name": f"Doon, County {county}", "address": {"county": f"County {county}"}}
    assert counties.place_county("doon", [place("Limerick", 1)])[0] == "Limerick"
    assert counties.place_county("doon", [place("Limerick", 1), place("Offaly", 2)]) is None


def test_a_namesake_anywhere_else_makes_the_place_ambiguous():
    townland = {"osm_type": "relation", "osm_id": 1, "type": "administrative", "name": "Oaklands",
                "display_name": "Oaklands, New Ross, County Wexford",
                "address": {"county": "County Wexford"}}
    estate = {"osm_type": "way", "osm_id": 2, "type": "residential", "name": "Oaklands",
              "display_name": "Oaklands, Cork, County Cork", "address": {"county": "County Cork"}}
    assert counties.place_county("oaklands", [townland]) == ("Wexford", townland)
    assert counties.place_county("oaklands", [townland, estate]) is None

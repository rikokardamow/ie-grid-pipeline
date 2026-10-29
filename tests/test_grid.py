"""g7b: list nodes placed on OpenStreetMap substations, and their distance to the backbone."""

import json

import pytest

from iegrid import grid

S = grid.Substation


def idx(*subs):
    return grid._index(list(subs))


def test_a_node_matches_its_substation_by_name():
    i = idx(S("Cashla 220 kV Substation", 220, -8.85, 53.31))
    assert grid.match("Cashla 220kV", i) == (S("Cashla 220 kV Substation", 220, -8.85, 53.31),
                                             "exact")


def test_a_transmission_project_needs_a_transmission_substation():
    # g7b review: Raheenmeel (Offaly) was drawn at Raheen 38 kV in Limerick by prefix,
    # Curraghdoo (Meath) at an untagged Curragh in Kerry
    i = idx(S("Raheen 38 kV Substation", 38, -8.6, 52.6), S("Curragh Substation", 0, -9.5, 52.1))
    assert grid.place(True, "Raheenmeel", "", i) == (None, "none")
    assert grid.place(True, "Curraghdoo", "", i) == (None, "none")


def test_a_feeding_station_must_be_near_its_110kv_station_or_the_project_is_drawn_there():
    # g7b review: "MILLTOWN (SR)" under OUGHTRAGH (Kerry) was drawn at Milltown in Dublin
    parent = S("Oughtragh 110kV Substation", 110, -9.7, 52.15)
    dublin = S("Milltown 110 kV Substation", 110, -6.25, 53.31)
    kerry = S("Milltown 38 kV Substation", 38, -9.72, 52.14)
    assert grid.place(False, "MILLTOWN (SR)", "OUGHTRAGH", idx(parent, dublin)) == (parent, "parent")
    assert grid.place(False, "MILLTOWN", "OUGHTRAGH", idx(parent, dublin, kerry)) == (kerry, "exact")
    # no 110 kV station on the map: the feeding station alone decides
    assert grid.place(False, "MILLTOWN", "NOWHERE", idx(kerry)) == (kerry, "exact")


def test_a_spelling_variant_matches_by_prefix_only_when_it_is_the_one_candidate():
    lanes = S("Lanesborough 110kV Substation", 110, -7.99, 53.67)
    assert grid.match("Lanesboro", idx(lanes)) == (lanes, "prefix")
    two = idx(lanes, S("Lanesboroughmore 38 kV Substation", 38, -8.5, 52.1))
    assert grid.match("Lanesboro", two) == (None, "none")
    # short names never match by prefix ("Arva" is not "Arvagh...")
    assert grid.match("Arva", idx(S("Arvagh 38 kV", 38, -7.5, 53.9))) == (None, "none")


def test_one_name_in_two_places_is_not_placed_but_one_site_drawn_twice_is():
    far = idx(S("Newbridge 38 kV", 38, -6.8, 53.18), S("Newbridge 38 kV", 38, -8.2, 52.4))
    assert grid.match("Newbridge", far) == (None, "ambiguous")
    near = idx(S("Kinnegad 110kV", 110, -7.1427, 53.4303),
               S("Kinnegad 38kV", 38, -7.1430, 53.4310))
    s, how = grid.match("Kinnegad", near)
    assert how == "exact" and s.kv == 110  # the higher voltage of one site


def test_distance_to_a_line_is_to_its_nearest_segment():
    line = grid.Line(400, ((-8.0, 53.0), (-6.0, 53.0)))
    # on the line, and 0.1 deg of latitude off it (11.1 km)
    assert grid.km_to_lines((-7.0, 53.0), [line]) == pytest.approx(0.0, abs=1e-6)
    assert grid.km_to_lines((-7.0, 53.1), [line]) == pytest.approx(11.13, abs=0.01)
    # past the end: the distance to the end point
    assert grid.km_to_lines((-5.9, 53.0), [line]) == pytest.approx(
        grid.km_between((-5.9, 53.0), (-6.0, 53.0)))
    assert grid.km_to_lines((-7.0, 53.0), []) is None


def test_simplify_keeps_the_ends_and_closed_rings():
    straight = tuple((x / 10, 53.0) for x in range(11))
    assert grid.simplify(straight) == [straight[0], straight[-1]]
    ring = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0))
    assert len(grid.simplify(ring)) == 5  # a square stays a square, not a point


def test_every_mw_is_placed_or_listed_as_unplaced(tmp_path, monkeypatch):
    cache = tmp_path / "grid.json"
    cache.write_text(json.dumps({
        "fetched_at": "2026-10-28T20:25:46+00:00",
        "lines": [{"tags": {"voltage": "220000"}, "geometry": [
            {"lon": -8.0, "lat": 53.0}, {"lon": -6.0, "lat": 53.0}]}],
        "substations": [{"tags": {"name": "Cashla 220 kV", "voltage": "220000"},
                         "center": {"lon": -7.0, "lat": 53.3}}],
    }))

    class Con:
        def execute(self, sql):
            assert "Interconnector" in sql
            return self

        def fetchall(self):
            return [(True, "Cashla", "", 100, "TG1", "A"), (True, "Cashla 220kV", "", 50, "TG2", "B"),
                    (False, "Nowhere", "", 25, "DG1", "C"), (False, "", "", 5, "DG2", "D")]

    out = grid.nodes(Con(), cache, ecp={})
    placed = sum(n["mw"] for n in out["nodes"])
    unplaced = sum(u["mw"] for u in out["unplaced"])
    assert (placed, unplaced) == (150, 30)
    assert out["placed_share"] == pytest.approx(150 / 180, abs=1e-3)
    assert out["nodes"][0]["km_backbone"] == pytest.approx(33.4, abs=0.1)
    assert out["far_gw"] == pytest.approx(0.15)  # 33 km is past FAR_KM
    assert [u["node"] for u in out["unplaced"]] == ["Nowhere", "(no node)"]
    assert [b["label"] for b in out["bands"]] == [
        "under 2 km", "2-10 km", "10-20 km", "20 km and over"]
    assert [b["gw"] for b in out["bands"]] == [0, 0, 0, 0.15]


def test_far_and_the_last_band_are_one_rule(tmp_path):
    # g7b review: far used > 20 and counted no-distance as 0, the bands >= 20 and infinity
    cache = tmp_path / "grid.json"
    cache.write_text(json.dumps({
        "fetched_at": "x",
        "lines": [{"tags": {"voltage": "400000"}, "geometry": [
            {"lon": -8.0, "lat": 53.0}, {"lon": -6.0, "lat": 53.0}]}],
        "substations": [{"tags": {"name": "Edge 110kV", "voltage": "110000"},
                         "center": {"lon": -7.0, "lat": 53.0 + 20 / grid.KM_PER_DEG_LAT}}],
    }))

    class Con:
        def execute(self, sql):
            return self

        def fetchall(self):
            return [(True, "Edge", "", 10, "TG1", "Edge Solar")]

    out = grid.nodes(Con(), cache, ecp={})
    assert out["nodes"][0]["km_backbone"] == 20.0
    assert (out["far_gw"], out["far_nodes"]) == (out["bands"][-1]["gw"], 1)


def test_the_ecp_results_node_places_a_new_station_and_catches_a_wrong_one():
    from decimal import Decimal

    waterford = S("Waterford 110kV Substation", 110, -7.10, 52.25)
    kinnegad = S("Kinnegad 110kV", 110, -7.14, 53.43)
    knockanure = S("Knockanure 220kV Substation", 220, -9.40, 52.48)
    i = idx(waterford, kinnegad, knockanure)
    ecp = {grid.region.key("Castlebanny Wind Farm"): [("Waterford", Decimal("138.6"))],
           grid.region.key("Kilmorna Energy Storage Facility"): [("Knockanure", Decimal(170))]}

    class Con:
        def execute(self, sql):
            return self

        def fetchall(self):
            return [(True, "Kilvinoge", "", 138.6, "TG541", "Castlebanny Wind Farm"),
                    (True, "Kinnegad", "", 170.0, "TG485", "Kilmorna Energy Storage Facility")]

    got = {p.ref: p for p in grid.placements(Con(), i, ecp)}
    # a new station OSM doesn't have: drawn at the station the results name
    assert (got["TG541"].at, got["TG541"].how) == (waterford, "ecp")
    # list and results 185 km apart: one of them is wrong, so it isn't drawn
    assert (got["TG485"].at, got["TG485"].how) == (None, "conflict")
    assert got["TG485"].conflict["km"] > grid.CONFLICT_KM
    assert got["TG485"].label == "Kinnegad (list) or Knockanure (ECP results)"


def test_the_results_node_is_refused_when_it_is_not_one_station():
    from decimal import Decimal

    k = grid.region.key("Milltown Solar")
    # two stations: no node; MEC far off: no node; two readings of one station: that one
    assert grid.results_node("Milltown Solar", 115, {k: [("Navan", Decimal(115)),
                                                         ("Cloon", Decimal(115))]}) is None
    assert grid.results_node("Milltown Solar", 115, {k: [("Cloon", Decimal(5))]}) is None
    m = grid.region.key("Mount Lucas Wind Farm")
    assert grid.results_node("Mount Lucas Wind Farm", 84, {m: [
        ("Mount", Decimal(84)), ("Mount Lucas", Decimal(84))]}) == "mount"


def test_a_long_connection_is_not_a_conflict_and_distribution_rows_ignore_the_results():
    from decimal import Decimal

    knockraha = S("Knockraha 220kV Substation", 220, -8.35, 51.95)
    woodhouse = S("Woodhouse 110kV Substation", 110, -7.80, 52.10)  # about 40 km
    i = idx(knockraha, woodhouse)
    ecp = {grid.region.key("Lyrenacarriga Windfarm and BESS"): [("Woodhouse", Decimal(145))],
           grid.region.key("Some Solar"): [("Woodhouse", Decimal(5))]}

    class Con:
        def execute(self, sql):
            return self

        def fetchall(self):
            return [(True, "Knockraha", "", 145.0, "TG577", "Lyrenacarriga Windfarm and BESS"),
                    (False, "Nowhere", "", 5.0, "DG9", "Some Solar")]

    got = {p.ref: p for p in grid.placements(Con(), i, ecp)}
    assert grid.km_between((knockraha.lon, knockraha.lat), (woodhouse.lon, woodhouse.lat)) < 80
    assert (got["TG577"].at, got["TG577"].how) == (knockraha, "exact")
    assert (got["DG9"].at, got["DG9"].how) == (None, "none")


def test_grid_references_are_not_nodes(tmp_path):
    from decimal import Decimal

    con = grid.store.connect(":memory:")
    con.execute("insert into ecp_row values ('d', ?, 1, 1, 'Eastmont DC Generators', 'Cork', "
                "9.5, '174653 071951'), ('d', ?, 2, 1, 'Kilmorna Energy', 'Kerry', 170, "
                "'Knockanure')", [grid_ecp_version(), grid_ecp_version()])
    got = grid.ecp_nodes(con)
    assert dict(got) == {grid.region.key("Kilmorna Energy"): [("Knockanure", Decimal(170))]}


def grid_ecp_version():
    from iegrid import ecp

    return ecp.READER_VERSION


def test_mw_still_sums_with_an_ecp_placement_and_a_conflict(tmp_path):
    from decimal import Decimal

    cache = tmp_path / "grid.json"
    subs = [("Waterford 110kV", 110, -7.10, 52.25), ("Kinnegad 110kV", 110, -7.14, 53.43),
            ("Knockanure 220kV", 220, -9.40, 52.48)]
    cache.write_text(json.dumps({
        "fetched_at": "x",
        "lines": [{"tags": {"voltage": "220000"}, "geometry": [
            {"lon": -9.5, "lat": 52.0}, {"lon": -6.0, "lat": 53.5}]}],
        "substations": [{"tags": {"name": n, "voltage": f"{kv}000"},
                         "center": {"lon": x, "lat": y}} for n, kv, x, y in subs],
    }))
    ecp = {grid.region.key("Castlebanny Wind Farm"): [("Waterford", Decimal("138.6"))],
           grid.region.key("Kilmorna Energy Storage Facility"): [("Knockanure", Decimal(170))]}

    class Con:
        def execute(self, sql):
            return self

        def fetchall(self):
            return [(True, "Kilvinoge", "", 138.6, "TG541", "Castlebanny Wind Farm"),
                    (True, "Kinnegad", "", 170.0, "TG485", "Kilmorna Energy Storage Facility"),
                    (True, "Nowhere", "", 10.0, "TG1", "Other")]

    out = grid.nodes(Con(), cache, ecp=ecp)
    placed = sum(n["mw"] for n in out["nodes"])
    unplaced = sum(u["mw"] for u in out["unplaced"])
    assert placed + unplaced == pytest.approx(318.6)
    assert [c["ref"] for c in out["conflicts"]] == ["TG485"]
    assert out["nodes"][0]["match"] == "ecp"


def townland(name, county, lon, lat):
    return {"category": "boundary", "type": "administrative", "name": name,
            "lon": str(lon), "lat": str(lat), "address": {"county": f"County {county}"}}


def test_a_new_station_is_drawn_at_its_one_townland_in_the_projects_county():
    got = grid.site("townland", "pollagh", "Kerry", [townland("Pollagh", "Kerry", -9.44, 52.50)])
    assert (got.name, got.lon, got.lat) == ("Pollagh (townland, Kerry)", -9.44, 52.50)
    # one in another county says nothing (the g4 review's Barnakyle)
    assert grid.site("townland", "pollagh", "Kerry",
                     [townland("Pollagh", "Galway", -8.5, 53.2)]) is None
    # two of the name in the county: which one isn't known
    assert grid.site("townland", "bellewstown", "Meath", [
        townland("Bellewstown", "Meath", -6.35, 53.65),
        townland("Bellewstown", "Meath", -6.86, 53.54)]) is None
    # a village or a cafe of the name isn't a townland
    cafe = {**townland("Southbank", "Dublin", -6.27, 53.33), "category": "amenity"}
    assert grid.site("townland", "southbank", "Dublin", [cafe]) is None


def test_a_cited_site_is_its_first_answer_in_the_cited_county():
    plant = {"category": "landuse", "type": "industrial", "name": "Poolbeg Power Station",
             "lon": "-6.185", "lat": "53.340", "address": {"city": "Dublin"}}
    cafe = {**plant, "category": "amenity", "name": "Southbank Cafe"}
    got = grid.site("cited", "southbank", "Dublin", [cafe, plant], "Poolbeg power station")
    assert got.name == "Southbank (cited site)" and got.kv == 0 and got.lon == -6.185
    # g7b review: any first answer in the county was taken, a cafe included
    assert grid.site("cited", "southbank", "Dublin", [cafe], "Poolbeg power station") is None


def test_every_cited_station_names_a_source():
    for node, r in grid.cited_stations().items():
        assert node and r["county"] and r["place_query"]
        assert r["source_url"].startswith("https://") and r["source_says"]


def test_place_queries_skip_conflicts_and_projects_without_a_county():
    P = grid.Placement
    pls = [P("TG1", "A", True, 10, "Pollagh", None, "none"),
           P("TG2", "B", True, 10, "Kinnegad (list) or Knockanure (ECP results)", None,
             "conflict"),
           P("TG3", "C", True, 10, "Nowhere", None, "none"),
           P("TG4", "D", True, 10, "Southbank", None, "none"),
           P("TG5", "E", True, 10, "Cashla", S("Cashla", 220, -8.8, 53.3), "exact")]
    cited = {"southbank": {"county": "Dublin", "place_query": "Poolbeg power station"}}
    got = grid.place_queries(pls, {"pollagh": "Kerry"}, cited)
    assert got == {"pollagh, County Kerry": ("townland", "pollagh", "Kerry"),
                   "Poolbeg power station": ("cited", "southbank", "Dublin")}


def test_places_are_asked_once_and_a_failure_is_asked_again(tmp_path, monkeypatch):
    monkeypatch.setattr(grid.time, "sleep", lambda s: None)
    cache, asked = tmp_path / "places.json", []

    def search(q):
        asked.append(q)
        if q == "bad":
            raise OSError("timed out")
        return [{"q": q}]

    assert grid.fetch_places(["a", "bad"], cache, search) == ["nominatim 'bad': timed out"]
    assert grid.fetch_places(["a", "bad"], cache, search) == ["nominatim 'bad': timed out"]
    assert asked == ["a", "bad", "bad"]
    assert json.loads(cache.read_text()) == {"a": [{"q": "a"}]}


def test_a_station_takes_one_county_from_all_its_projects():
    # g7b review: per project, Coolnabacky was drawn for TG461 and unplaced for TG282
    # (no g4 county), and Fieldstown Extension 2 (g4: Dublin) hid behind Timoney
    P = grid.Placement
    pls = [P("TG461", "A", True, 25, "Coolnabacky", None, "none"),
           P("TG282", "B", True, 55, "Coolnabacky", None, "none"),
           P("TG433", "C", True, 105, "Timoney", None, "none"),
           P("TG594", "Fieldstown Extension 2", True, 60, "Timoney", None, "none")]
    node_county, odd = grid.node_counties(pls, {"TG461": "Laois", "TG433": "Tipperary",
                                                "TG594": "Dublin"})
    assert node_county == {"coolnabacky": "Laois", "timoney": "Tipperary"}
    assert odd == {"TG594": "Dublin"}
    got = grid.place_queries([p for p in pls if p.ref not in odd], node_county, {})
    assert set(got) == {"coolnabacky, County Laois", "timoney, County Tipperary"}

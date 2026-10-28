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
            return [(True, "Cashla", "", 100), (True, "Cashla 220kV", "", 50),
                    (False, "Nowhere", "", 25), (False, "", "", 5)]

    out = grid.nodes(Con(), cache)
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
            return [(True, "Edge", "", 10)]

    out = grid.nodes(Con(), cache)
    assert out["nodes"][0]["km_backbone"] == 20.0
    assert (out["far_gw"], out["far_nodes"]) == (out["bands"][-1]["gw"], 1)

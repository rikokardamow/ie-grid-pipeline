from datetime import date
from decimal import Decimal as D

from iegrid import flows


def run(monkeypatch, eds):
    monkeypatch.setattr(flows, "editions", lambda con: {"eirgrid.tso_contracted_wind": eds})
    return [(f.kind, f.ref, f.other_ref, f.mw) for f in flows.flows(None)]


def test_joined_and_left(monkeypatch):
    got = run(monkeypatch, [
        (date(2024, 1, 1), {"TG1": ("Aught Wind Farm", D(57))}),
        (date(2025, 1, 1), {"TG2": ("Coole Wind Farm", D(88))}),
    ])
    assert got == [("left", "TG1", "", D(57)), ("joined", "TG2", "", D(88))]


def test_a_relabel_is_neither(monkeypatch):
    got = run(monkeypatch, [
        (date(2025, 2, 26), {"D74": ("Pollahoney Autoproducer", D(288))}),
        (date(2025, 9, 17), {"D40d": ("Pollahoney Autoproducer", D(288))}),
    ])
    assert got == [("relabel", "D40d", "D74", D(288))]


def test_twins_relabelled_pair_by_mec(monkeypatch):
    name = "Beenanaspock and Tobertooreen Wind Farm"
    got = run(monkeypatch, [
        (date(2019, 1, 18), {"TG319a": (name, D("17.50")), "TG319": (name, D("16.65"))}),
        (date(2019, 5, 28), {"DG141a": (name, D("17.50")), "TG22b": (name, D("16.65"))}),
    ])
    assert sorted(got) == [("relabel", "DG141a", "TG319a", D("17.50")),
                           ("relabel", "TG22b", "TG319", D("16.65"))]


def test_a_reused_ref_is_a_leave_and_a_join(monkeypatch):
    got = run(monkeypatch, [
        (date(2018, 1, 1), {"TG166": ("Cahernagh Mid Merit", D(101))}),
        (date(2019, 1, 1), {"TG166": ("Kelwin Power Plant Phase 2", D(20))}),
    ])
    assert got == [("left", "TG166", "", D(101)), ("joined", "TG166", "", D(20))]


def test_the_first_edition_is_stock_not_joins(monkeypatch):
    assert run(monkeypatch, [(date(2015, 8, 31), {"TG1": ("Athea", D(18))})]) == []


def test_a_rename_the_new_name_declares_is_the_same_project_whatever_the_spelling_or_mec(monkeypatch):
    # five real cases were counted as a leave and a join (151 MW in 2018, 199 MW in 2019);
    # TG44's old name is spelt differently from the "formerly" in the new one
    cases = [("TG44", "Barnadivane (1)", D(60), "Carrigdangan (formerly Barnadivine)", D(60)),
             ("TG49", "Keelderry (1)", D("26.88"), "Knockalassa (formerly Keelderry)", D("26.88")),
             ("DG1012", "Buffy Wind Farm", D("64.2"), "Ardderoo 2 (Formerly Buffy)", D("64.2")),
             ("TG71", "Oweninny (5)**", D("198.9"), "Oweninny 3 (Previously Oweninny 5)", D(50))]
    for ref, old, old_mw, new, new_mw in cases:
        got = run(monkeypatch, [(date(2018, 1, 1), {ref: (old, old_mw)}),
                                (date(2019, 1, 1), {ref: (new, new_mw)})])
        assert got == [], ref


def test_a_formerly_in_the_old_name_or_no_formerly_at_all_is_still_a_reuse(monkeypatch):
    # the marker has to be on the NEW name, announcing a rename; without it a changed name on a
    # continuing ref is a different project (TG166), and a project already carrying the marker
    # that changes again is not a rename
    for old, new in (("Cahernagh Mid Merit", "Kelwin Power Plant Phase 2"),
                     ("Carrigdangan (formerly Barnadivine)", "Quarry Solar")):
        got = run(monkeypatch, [(date(2018, 1, 1), {"TG166": (old, D(101))}),
                                (date(2019, 1, 1), {"TG166": (new, D(20))})])
        assert [k for k, *_ in got] == ["left", "joined"], (old, new)

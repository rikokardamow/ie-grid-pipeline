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

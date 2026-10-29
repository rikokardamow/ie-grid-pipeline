"""The funnel: distinct offers, strict matching, and the match's validation against batch tags."""

from decimal import Decimal

from iegrid import funnel, region


def listed(ref, name, mw, tag=None, sid="eirgrid.tso_contracted_wind"):
    return funnel.Listed(ref, region.key(name), name, Decimal(str(mw)), sid, tag)


def test_a_project_in_several_status_updates_is_one_offer():
    rows = [("Ballyroe Solar Farm", Decimal(100)), ("Ballyroe Solar Farm", Decimal(104)),
            ("Ballyroe Solar Farm", Decimal(180)), ("Cashla Wind Farm", Decimal(50))]
    got = funnel.distinct_offers(rows, "ECP-2.3")
    # 100 and 104 are one offer (an MEC within tolerance); 180 is another (a re-sized project)
    assert [(o.name, o.mw) for o in got] == [("Ballyroe Solar Farm", Decimal(100)),
                                             ("Ballyroe Solar Farm", Decimal(180)),
                                             ("Cashla Wind Farm", Decimal(50))]


def test_a_name_with_nothing_distinctive_can_not_be_matched_so_it_is_not_an_offer():
    assert funnel.distinct_offers([("Upper Solar Farm", Decimal(10))], "ECP-1") == []


def test_an_offer_matches_a_list_row_of_the_same_name_and_a_close_mec_only():
    offers = funnel.distinct_offers([("Ballyroe Solar", Decimal(100)),
                                     ("Cashla Wind", Decimal(50))], "ECP-2.3")
    rows = [listed("TG1", "Ballyroe Solar Farm", 102), listed("TG2", "Cashla Wind Farm", 80)]
    hits = funnel.match(offers, rows)
    assert [[x.ref for x in h] for h in hits.values()] == [["TG1"], []]  # 50 vs 80 MW: not it


def test_precision_and_recall_are_measured_against_the_lists_own_tags():
    offers = funnel.distinct_offers([("Ballyroe Solar", Decimal(100)),
                                     ("Cashla Wind", Decimal(50)),
                                     ("Kilmorna Energy", Decimal(170))], "ECP-2.3")
    rows = [listed("TG1", "Ballyroe Solar", 100, "ECP-2.3"),     # matched, right batch
            listed("TG2", "Cashla Wind", 50, "ECP-2.2"),          # matched, tagged another batch
            listed("TG3", "Quarry Solar", 30, "ECP-2.3"),         # tagged, no offer matches it
            listed("TG4", "Kilmorna Energy", 170)]                # matched, untagged: not scored
    v = funnel.validate(funnel.match(offers, rows), rows, "ECP-2.3")
    assert v["tagged_matches"] == 2 and v["precision"] == 0.5
    assert v["tagged_refs"] == 2 and v["recall"] == 0.5  # TG1 matched, TG3 not


def test_no_tags_means_no_precision_rather_than_a_perfect_one():
    offers = funnel.distinct_offers([("Ballyroe Solar", Decimal(100))], "GSS-1")
    rows = [listed("TG1", "Ballyroe Solar", 100)]
    v = funnel.validate(funnel.match(offers, rows), rows, "GSS-1")
    assert (v["precision"], v["recall"]) == (None, None)

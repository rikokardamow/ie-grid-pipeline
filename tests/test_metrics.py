from datetime import date

import pytest

from iegrid import metrics


@pytest.mark.parametrize("text, batch", [
    ("2020-batch-(ecp-2.1)-results-joint-so-publication-january-2021.pdf", "ECP-2.1"),
    ("2018-batch-(ecp-1)-results-joint-so-publication-nov2018.pdf", "ECP-1"),
    ("2024-batch-ecp-2-5-results-joint-so-publication.pdf", "ECP-2.5"),
    ("sept-2025-batch-ecp-gss-1-results-initial-publication.pdf", "GSS-1"),
    ("ECP-2.2 - Non-Batch", None),   # rolling offers, not the batch's
    ("ECP 2.3", "ECP-2.3"), ("ECP2.3", "ECP-2.3"), ("ECP-2.5.1", "ECP-2.5"),
    ("ECP-1", "ECP-1"),
    ("Gate 3", None),
])
def test_batch_of(text, batch):
    assert metrics.batch_of(text) == batch


@pytest.mark.parametrize("ptype, route", [
    ("ECP-2.3", "ECP-2.3"), ("Gate 3", "Gate 3"), ("post Gate 1", "Gate 1"),
    ("Pre-Gate 1", "Gate 1"), ("Non GPA", "Non GPA"), ("T-4 2027/2028", "T-4 capacity auction"),
    ("T-3 2024/2025", "T-3 capacity auction"), ("T- 2027/28", "capacity auction"),
    ("PCI", "PCI"), ("ECP-2.4 - Non-Batch", "Non-Batch"), ("", "other"),
])
def test_route(ptype, route):
    assert metrics.route(ptype) == route


def test_month_in_a_results_file_name():
    assert metrics._name_month("joint-so-publication_nov2018.pdf") == date(2018, 11, 1)
    assert metrics._name_month("results-joint-so-publication-january-2021.pdf") == date(2021, 1, 1)
    assert metrics._name_month("results-joint-so-publication.pdf") is None
    assert metrics._name_month("cru-decision-2023.pdf") is None   # 'dec' inside a word


def test_share_is_of_projects_still_listed():
    from decimal import Decimal as D
    b = metrics.Burndown("ECP-1", metrics.BatchDate(date(2018, 11, 1), True), D(196), D(244),
                         19, 28, (), 92)
    assert round(b.share, 3) == round(196 / 440, 3)


OLD = """Wexford 110 kV 19 Wexford Synchronous Condenser LCIS 2024 Synchronous Condenser 0.0 Aug 2025
Erkina 110 kV TG433 Erkina Solar Park ECP-2.1 Solar 66.6 Jun 2021
Clahane 110 kV TG275 Banemore Solar Farm Non GPA Solar 34.0 Jun 2018"""


def test_a_misprinted_ref_fails_the_name_check():
    """g5 review: TG619 was printed as '19' in Sep 2025, so its 'join' was a relabel."""
    assert metrics._vanished_namesake("Wexford Synchronous Condenser", "TG619", OLD,
                                      persisting={"TG433"})


def test_a_namesake_still_listed_is_another_project():
    # Erkina 2 joins; Erkina Solar Park (TG433) is in both editions
    assert not metrics._vanished_namesake("Erkina Solar", "TG633", OLD, persisting={"TG433"})


def test_a_genuine_join_passes():
    assert not metrics._vanished_namesake("Culmullin Solar Farm", "TG607", OLD,
                                          persisting={"TG433"})


def test_share_at_compares_batches_at_the_same_age():
    from decimal import Decimal as D
    b = metrics.Burndown("ECP-1", metrics.BatchDate(date(2018, 11, 1), True), D(30), D(70),
                         2, 5, ((10, D(10)), (40, D(20))), 92)
    assert b.share_at(12) == 0.1
    assert b.share_at(48) == 0.3
    assert b.share_at(100) is None   # not that old yet

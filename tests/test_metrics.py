from datetime import date

import pytest

from iegrid import metrics


@pytest.mark.parametrize("text, batch", [
    ("2020-batch-(ecp-2.1)-results-joint-so-publication-january-2021.pdf", "ECP-2.1"),
    ("2018-batch-(ecp-1)-results-joint-so-publication-nov2018.pdf", "ECP-1"),
    ("2024-batch-ecp-2-5-results-joint-so-publication.pdf", "ECP-2.5"),
    ("sept-2025-batch-ecp-gss-1-results-initial-publication.pdf", "GSS-1"),
    ("ECP-2.2 - Non-Batch", "ECP-2.2"),
    ("ECP-1", "ECP-1"),
    ("Gate 3", None),
])
def test_batch_of(text, batch):
    assert metrics.batch_of(text) == batch


@pytest.mark.parametrize("ptype, route", [
    ("ECP-2.3", "ECP-2.3"), ("Gate 3", "Gate 3"), ("post Gate 1", "Gate 1"),
    ("Pre-Gate 1", "Gate 1"), ("Non GPA", "Non GPA"), ("T-4 2027/2028", "T-4 capacity auction"),
    ("T-3 2024/2025", "T-3 capacity auction"), ("PCI", "PCI"), ("", "other"),
])
def test_route(ptype, route):
    assert metrics.route(ptype) == route


def test_month_in_a_results_file_name():
    assert metrics._name_month("joint-so-publication_nov2018.pdf") == date(2018, 11, 1)
    assert metrics._name_month("results-joint-so-publication-january-2021.pdf") == date(2021, 1, 1)
    assert metrics._name_month("results-joint-so-publication.pdf") is None


def test_share_is_of_projects_still_listed():
    from decimal import Decimal as D
    b = metrics.Burndown("ECP-1", date(2018, 11, 1), D(196), D(244), 19, 28, 48)
    assert round(b.share, 3) == round(196 / 440, 3)

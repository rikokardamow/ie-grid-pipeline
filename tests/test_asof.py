from datetime import date

import pytest

from iegrid.asof import as_of_from_pdf, as_of_from_text
from tests.conftest import make_pdf


@pytest.mark.parametrize("text, expected", [
    ("Contracted TSO (Wind) Generators\nCorrect as of 05/08/2026\n", date(2026, 8, 5)),
    ("Distribution Contracted Renewable Q2 2026 1\nInformation correct: 01/07/2026 Rev. 9",
     date(2026, 7, 1)),
    ("Renewable summary\nData as of 01/07/2026", date(2026, 7, 1)),
    # day/month, not month/day
    ("Correct as of 1/2/2025", date(2025, 2, 1)),
])
def test_as_of_wordings(text, expected):
    assert as_of_from_text(text) == expected


def test_repeated_on_every_page_is_fine():
    text = "Correct as of 05/08/2026\nrows\nCorrect as of 05/08/2026"
    assert as_of_from_text(text) == date(2026, 8, 5)


def test_conflicting_dates_refused():
    with pytest.raises(ValueError):
        as_of_from_text("Correct as of 05/08/2026\nCorrect as of 17/09/2025")


def test_other_dates_are_not_as_of():
    # an energisation date in a row must not be read as the list's as-of
    assert as_of_from_text("ZG1060 Balleally Energised 01/01/2004 20 kV") is None


def test_reads_from_a_pdf():
    pdf = make_pdf(["Contracted TSO (Wind) Generators", "Correct as of 05/08/2026"])
    assert as_of_from_pdf(pdf) == date(2026, 8, 5)


@pytest.mark.parametrize("text, expected", [
    ("Correct as of 01/May/2017", date(2017, 5, 1)),
    ("Correct as of 18 January 2019", date(2019, 1, 18)),
    ("Correct as of 01-Oct-2019", date(2019, 10, 1)),
    ("it. Correct as of the 29th of Aug 2016", date(2016, 8, 29)),
    ("it. Correct as of the 1th of Feb 2017", date(2017, 2, 1)),
    ("Data Accurate as of 1st March 2017", date(2017, 3, 1)),
    ("As of the 19/07/2010 715 744 1459", date(2010, 7, 19)),
    ("As of the 31st Dec 2011 862.40 768.30 1630.70", date(2011, 12, 31)),
    ("Updated 1st December 2016", date(2016, 12, 1)),
    ("Information correct: 20-Apr-23 Rev. 0", date(2023, 4, 20)),
    ("it. Correct as of 01/Mar/2017.", date(2017, 3, 1)),
])
def test_archived_wordings(text, expected):
    assert as_of_from_text(text) == expected


@pytest.mark.parametrize("text", [
    "updated July 2016",                                      # no day
    "It would not however be updated for a non-MEC related amendment",
    "Correct as of 31/02/2017",                               # not a calendar date
])
def test_not_an_as_of(text):
    assert as_of_from_text(text) is None


def test_as_of_on_a_late_page():
    pdf = make_pdf(["rows"], ["more rows"], ["more rows"], ["more rows"], ["As of the 19/07/2010"])
    assert as_of_from_pdf(pdf) == date(2010, 7, 19)

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

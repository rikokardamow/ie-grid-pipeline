from datetime import date

import pytest

from iegrid.asof import AsOfConflict, as_of_from_pdf, as_of_from_text, date_in_name
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
    ("Updated 1st December 2016", date(2016, 12, 1)),
    ("Information correct: 20-Apr-23 Rev. 0", date(2023, 4, 20)),
    ("it. Correct as of 01/Mar/2017.", date(2017, 3, 1)),
    ("Information correct: 01Oct 2024 Rev. 2", date(2024, 10, 1)),   # no space before month
    ("Connected Wind Report 05/08/2009\nInstalled Capacity", date(2009, 8, 5)),
    ("Installed Wind Report \u2013 30th June 2011", date(2011, 6, 30)),
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
    pdf = make_pdf(["rows"], ["more rows"], ["more rows"], ["more rows"],
                   ["Correct as of 19/07/2010"])
    assert as_of_from_pdf(pdf) == date(2010, 7, 19)


# Review of g3: a table label carrying the previous edition's date must not win.
def test_heading_beats_stale_table_label():
    text = "Connected Wind Report 05/08/2009\nAs of the 25/05/2009 575 531 1106"
    assert as_of_from_text(text) == date(2009, 8, 5)


def test_weak_label_used_only_when_the_name_agrees():
    text = "Installed Wind Capacity DSO TSO Total\nAs of the 24/05/2010 694 685 1379"
    assert as_of_from_text(text, name_date=date(2010, 5, 24)) == date(2010, 5, 24)
    with pytest.raises(AsOfConflict):
        as_of_from_text(text)  # no name to confirm it


def test_stale_label_refused():
    # "Connected Wind Report 24 05 2010.pdf" carries the 8 Feb label over 24 May figures
    text = "Installed Wind Capacity DSO TSO Total\nAs of the 08/02/2010 694 685 1379"
    with pytest.raises(AsOfConflict):
        as_of_from_text(text, name_date=date(2010, 5, 24))


def test_typo_far_from_the_name_refused():
    # "31th of May 2015" in a list named 22-June-2016
    with pytest.raises(AsOfConflict):
        as_of_from_text("it. Correct as of the 31th of May 2015", name_date=date(2016, 6, 22))


def test_text_a_few_weeks_before_the_name_is_fine():
    assert as_of_from_text("Correct as of the 31th of Dec 2015",
                           name_date=date(2016, 1, 25)) == date(2015, 12, 31)
    assert as_of_from_text("Information correct: 30/05/2018",
                           name_date=date(2018, 7, 1)) == date(2018, 5, 30)  # q2-2018


@pytest.mark.parametrize("name, expected", [
    ("connected-wind-report-05aug09-v1.pdf", date(2009, 8, 5)),
    ("connected-wind-report-30sept09.pdf", date(2009, 9, 30)),
    ("contracted-wind-2june10.pdf", date(2010, 6, 2)),
    ("connected-tso-wind-farms-16-nov-12.pdf", date(2012, 11, 16)),
    ("connected-tso-non-wind-generators-23rd-july-2012.pdf", date(2012, 7, 23)),
    ("contractedtsowindfarms18thsept2015.pdf", date(2015, 9, 18)),
    ("connected-tso-non-wind-generators-1th-dec-2016.pdf", date(2016, 12, 1)),
    ("contracted-tso-nonwind-generators-22-june-2016.pdf", date(2016, 6, 22)),
    ("tso-wind-contracted-31.03.2022.pdf", date(2022, 3, 31)),
    ("tso-connected-renewable-generation-22.08.18.pdf", date(2018, 8, 22)),
    ("contracted-tso-non-wind-generators-7-11-2024.pdf", date(2024, 11, 7)),
    ("connected-wind-report-20090827.pdf", date(2009, 8, 27)),
    ("contracted-wind-14092009.pdf", date(2009, 9, 14)),
    ("contracted-wind-10-06-09.pdf", date(2009, 6, 10)),
    ("dso-contracted-wind-generators-q4-2022.pdf", date(2023, 1, 1)),
    ("dso-contracted-wind-generators-sept-2017.pdf", date(2017, 9, 1)),
    ("contracted-tso-wind-farms.pdf", None),
    ("tso-wind-contracted-2019.pdf", None),
])
def test_dates_in_names(name, expected):
    assert date_in_name(name) == expected

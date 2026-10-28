"""The page is drawn from the report dict alone (g6 done-when)."""

from iegrid import checks, report

REP = {
    "report_date": "2026-11-04", "editions": {}, "new": [],
    "queue": {"transmission_gw": 14.69, "transmission_projects": 158, "distribution_gw": 1.96,
              "distribution_projects": 177},
    "moved": {
        "transmission": {"editions": ["2025-09-17 to 2026-08-05"], "joined_count": 29,
                         "joined_gw": 3.0, "left_count": 2, "left_gw": 0.07, "all_confirmed": True,
                         "joined": [{"ref": "TG676", "name": "Moor OCGT", "mw": 340.0}],
                         "left": [{"ref": "TG280", "name": "Shantallow Solar", "mw": 35.0}]},
        "distribution": {"before": "2026-04-01", "after": "2026-07-01", "count": 8, "mw": 31.0,
                         "projects": [{"ref": "DG1", "name": "The Dell PV", "mw": 20.0,
                                       "energised_on": None, "technology": "Solar"}]}},
    "stuck": {"as_of": "2026-08-05",
              "longest_waiting": [{"ref": "TG71", "name": "Oweninny 3", "mw": 50.0,
                                   "route": "Gate 3", "months": 175, "years_part": 14,
                                   "months_part": 7, "first_signed": "2012-01-01"}],
              "burndown": [{"batch": "ECP-1", "results": "Nov 2018", "age_months": 92,
                            "share_now": 0.45, "share_at_3y": 0.09, "projects": 45}]},
    "where": {"placed_share": 0.956, "counties": [{"county": "Offaly", "gw": 1.7}]},
    "caveats": ["Lists as of 5 Aug 2026."],
}


def test_every_number_on_the_page_comes_from_the_dict(tmp_path):
    pdf = report.render(REP, tmp_path / "r.pdf")
    assert checks.untraced_numbers(pdf, REP) == []


def test_a_number_not_in_the_dict_is_caught(tmp_path):
    pdf = report.render(REP, tmp_path / "r.pdf")
    smaller = {**REP, "queue": {**REP["queue"], "transmission_projects": 999}}
    assert "158" in checks.untraced_numbers(pdf, smaller)


def test_one_page_and_no_new_list_said_plainly(tmp_path):
    import pdfplumber
    pdf = report.render(REP, tmp_path / "r.pdf")
    with pdfplumber.open(pdf) as p:
        assert len(p.pages) == 1
        text = p.pages[0].extract_text()
    assert "no new list published" in text
    assert "date not given" in text

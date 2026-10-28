"""The page is drawn from the report dict alone (g6 done-when)."""

from iegrid import checks, report

REP = {
    "report_date": "2026-11-04", "editions": {}, "warnings": [],
    "new": {"first_report": False, "since": "2026-10-28", "lists": []},
    "queue": {"transmission_gw": 14.694, "transmission_projects": 158, "interconnector_gw": 1.204,
              "distribution_gw": 1.964, "distribution_projects": 177},
    "moved": {
        "transmission": {"editions": ["2025-09-17 to 2026-08-05"], "joined_count": 29,
                         "joined_gw": 3.0, "left_count": 2, "left_gw": 0.069, "all_confirmed": True,
                         "joined": [{"ref": "TG676", "name": "Moor OCGT", "mw": 340.0}],
                         "left": [{"ref": "TG280", "name": "Shantallow Solar", "mw": 35.0}]},
        "distribution": {"editions": ["2026-04-01 to 2026-07-01"], "count": 7, "mw": 29.8,
                         "projects": [{"list": "ESB energised renewable", "ref": "DG1",
                                       "name": "The Dell PV", "mw": 20.0,
                                       "energised_on": "2026-05-14", "note": None}],
                         "newly_listed_count": 1, "newly_listed": []}},
    "stuck": {"as_of": "2026-08-05", "large_mw": 50, "at_years": 3,
              "longest_waiting": [{"ref": "TG71", "name": "Oweninny 3", "mw": 50.0,
                                   "route": "Gate 3", "months": 175, "years_part": 14,
                                   "months_part": 7, "first_signed": "2012-01-01"}],
              "burndown": [{"batch": "ECP-1", "results": "Nov 2018", "age_months": 92,
                            "share_now": 0.446, "share_at": 0.095, "projects": 45},
                           {"batch": "ECP-2.1", "results": "Nov 2020", "age_months": 68,
                            "share_now": 0.23, "share_at": 0.011, "projects": 33}],
              "burndown_first": "ECP-1", "burndown_first_at": 0.095,
              "burndown_later_max_at": 0.011},
    "where": {"generation_placed_share": 0.953, "counties": [{"county": "Offaly", "gw": 1.682}]},
    "caveats": ["Lists as of 5 Aug 2026."],
}


def test_every_number_on_the_page_comes_from_the_report(tmp_path):
    assert checks.numbers_not_from_report(REP, report.render, tmp_path) == []


def test_a_number_written_by_the_renderer_is_caught(tmp_path):
    def render_with_a_literal(rep, path):
        import matplotlib.pyplot as plt
        out = report.render(rep, path)
        # re-draw with a hard-coded figure, as a buggy renderer would
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.text(0.1, 0.5, "Queue 13.69 GW")
        fig.text(0.1, 0.4, "3 left")
        fig.savefig(out)
        plt.close(fig)
        return out

    assert checks.numbers_not_from_report(REP, render_with_a_literal, tmp_path) == ["3", "13.69"]


def test_one_page_and_first_report_said_plainly(tmp_path):
    import pdfplumber
    first = {**REP, "new": {"first_report": True, "lists": []}}
    pdf = report.render(first, tmp_path / "r.pdf")
    with pdfplumber.open(pdf) as p:
        assert len(p.pages) == 1
        text = p.pages[0].extract_text()
    assert "First report" in text


def test_new_lists_are_named_for_a_reader_and_wrap(tmp_path):
    import pdfplumber
    many = {**REP, "new": {"first_report": False, "since": "2026-10-28", "lists": [
        {"list": report.LIST_NAMES[s], "as_of": "2026-10-01"} for s in report.LIST_NAMES]}}
    pdf = report.render(many, tmp_path / "r.pdf")
    with pdfplumber.open(pdf) as p:
        words = p.pages[0].extract_words()
        width = p.pages[0].width
    assert all(w["x1"] <= width for w in words)
    assert not any("esb.dso" in w["text"] for w in words)


def test_new_compares_editions_not_ingest_times():
    from datetime import date
    eds = {"eirgrid.tso_contracted_wind": date(2026, 8, 5),
           "esb.dso_contracted_renewable": date(2026, 10, 1)}
    last = {"report_date": "2026-10-28", "editions": {"eirgrid.tso_contracted_wind": "2026-08-05",
                                                      "esb.dso_contracted_renewable": "2026-07-01"}}
    got = report._new(eds, last)
    assert got["lists"] == [{"list": "ESB contracted renewable", "as_of": "2026-10-01"}]
    assert report._new(eds, None)["first_report"] is True


def test_last_report_ignores_other_json(tmp_path):
    (tmp_path / "2026-10-28.json").write_text('{"report_date": "2026-10-28", "editions": {}}')
    (tmp_path / "notes.json").write_text('{"x": 1}')
    (tmp_path / "2026-11-04T0900.json").write_text("not json")
    assert report.last_report(tmp_path)["report_date"] == "2026-10-28"


def test_a_page_that_would_overflow_is_an_error(tmp_path):
    import pytest
    long = {**REP, "caveats": ["A caveat that goes on. " * 6] * 40}
    with pytest.raises(ValueError, match="overflows"):
        report.render(long, tmp_path / "r.pdf")

"""ESB's 2017-2023 lists: statuses, cut cells repaired only when the text line verifies them,
and the real files (skipped where the raw PDFs aren't)."""


import pytest

from iegrid import esb_legacy, store

HEADER = ["ref", "name", "technology", "mec", "feeding", "station110", "offer", "status",
          "date", "voltage"]


def test_a_known_status_passes_and_an_overprint_is_read_as_the_one_it_hides():
    assert esb_legacy.normalise_status("Energised") == ("Energised", None)
    status, note = esb_legacy.normalise_status("DSCOontracted")  # "DSO" printed over "Contracted"
    assert status == "Contracted" and "overprinted" in note


def test_a_status_that_fits_nothing_is_refused_not_guessed():
    with pytest.raises(esb_legacy.LegacyParseError, match="unknown status"):
        esb_legacy.normalise_status("On Hold")
    with pytest.raises(esb_legacy.LegacyParseError):
        esb_legacy.normalise_status("Contracted by the DSO and then some")  # too many extra letters


def test_a_prefix_is_the_start_of_the_line_with_the_same_letters():
    line = "DG1814 Templederry Windfarm (extension to DG184) 0.7MWWind 0.700 N/A NENAGH"
    joined = "DG1814 Temp" + "lederry Windfarm (extension to DG184) 0." + "7MWWind"
    assert esb_legacy._spaced_prefix(line, joined) == (
        "DG1814 Templederry Windfarm (extension to DG184) 0.7MWWind")
    assert esb_legacy._spaced_prefix(line, "DG1814 Something else") is None


def test_a_row_cut_through_a_word_is_rebuilt_from_its_text_line():
    # the borders fell mid-word: "DG1814 Temp" | "lederry..." (g-layer: the real 2023-01 list)
    cells = ["DG1814 Temp", "lederry Windfarm (extension to DG184) 0.", "7MWWind", "0.700", "N/A",
             "NENAGH", "ECP-1", "Contracted", "Date unavailable at this time", "20 kV"]
    line = ("DG1814 Templederry Windfarm (extension to DG184) 0.7MWWind 0.700 N/A NENAGH ECP-1 "
            "Contracted Date unavailable at this time 20 kV")
    got = esb_legacy._repair(cells, HEADER, [line], {"Wind", "Solar"})
    assert got == {"ref": "DG1814", "name": "Templederry Windfarm (extension to DG184) 0.7MW",
                   "technology": "Wind", "mec": "0.700"}


def test_a_number_that_lost_its_prefix_to_the_next_cell_is_found_again():
    # "Battery Storag" | "e 30.000": the MEC cell holds the end of the type
    cells = ["DG1799", "Kilmannock Battery Storage Facility B", "attery Storag", "e 30.000",
             "N/A", "Great Island", "ECP-1", "Contracted", "Date unavailable at this time", "38 kV"]
    line = "DG1799 Kilmannock Battery Storage Facility Battery Storage 30.000 N/A Great Island ECP-1"
    got = esb_legacy._repair(cells, HEADER, [line], {"Battery Storage", "Solar"})
    assert (got["name"], got["technology"], got["mec"]) == (
        "Kilmannock Battery Storage Facility", "Battery Storage", "30.000")


def test_a_cut_row_the_text_line_cannot_verify_is_not_repaired():
    cells = ["DG1 Fo", "o Farm", "Wind", "1.0", "", "", "", "Contracted", "", ""]
    assert esb_legacy._repair(cells, HEADER, ["DG1 Something Else Farm Wind 1.0"], {"Wind"}) is None


def raw(source: str, as_of: str) -> bytes | None:
    found = sorted((store.ROOT / "data" / "raw" / source).glob(f"{as_of}-*.pdf"))
    return found[0].read_bytes() if found else None


@pytest.mark.skipif(raw("esb.dso_contracted_wind", "2017-09-07") is None,
                    reason="the 2017 ESB lists are not on this machine")
def test_a_shared_ref_is_two_rows_and_a_publishers_duplicate_is_counted_once():
    rows, _ = esb_legacy.read(raw("esb.dso_contracted_wind", "2017-09-07"))
    assert [r.name for r in rows if r.ref == "DG249"] == [
        "Coomleagh Wind Farm", "Coomleagh Wind Farm (extension)"]
    rows, notes = esb_legacy.read(raw("esb.dso_energised_nonwind", "2017-12-11"))
    assert sum(1 for r in rows if r.ref == "DG943a") == 1
    assert any("DG943a" in n and "printed twice" in n for n in notes)


@pytest.mark.skipif(raw("esb.dso_contracted_nonwind", "2023-01-04") is None,
                    reason="the 2023 ESB lists are not on this machine")
def test_the_2023_list_reads_its_cut_rows_and_its_overprinted_status():
    rows, notes = esb_legacy.read(raw("esb.dso_contracted_nonwind", "2023-01-04"))
    by = {r.ref: r for r in rows}
    assert by["DG1799"].mec_mw == 30 and by["DG1799"].technology == "Battery Storage"
    assert by["TG175"].status == "Contracted" and any("TG175" in n for n in notes)
    assert all(r.status in esb_legacy.STATUSES for r in rows)

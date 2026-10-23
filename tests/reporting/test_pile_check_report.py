"""0612 / 0622 基礎の照査 of a pile foundation (decision 89): the table of the responses, the limits and the checks, laid out in
the grid of the sample (Example橋脚4 III-3.3); every number is a value of the calc result."""

import pymupdf

from pile_check_support import result
from webpier.reporting.stages.pile_check import (LONGITUDINAL, TRANSVERSE, build_pile_check, grid_documents, records,
                                                 render_pile_check)


def test_the_semantic_records_have_the_headings_the_formulas_and_the_table():
    found = records(result(), LONGITUDINAL)
    keys = [record["id"] for record in found]
    assert keys[0] == "0612/heading" and keys[-1] == "0612/table"
    assert [record["text"] for record in found if record["id"] in (
        "0612/vertical", "0612/pull_out", "0612/horizontal", "0612/rotation")] == [
        "γi・Vd / Rvd ≦ 1.0", "γi・Vud / Rud ≦ 1.0", "γi・δd / δLd ≦ 1.0", "γi・θd / θLd ≦ 1.0"]
    assert "9.11 基礎の照査" in [record["text"] for record in records(result(), TRANSVERSE)]


def test_the_table_prints_the_values_the_result_has_and_dashes_where_there_is_no_tension(tmp_path):
    path = render_pile_check(result(), tmp_path / "check.pdf", LONGITUDINAL)
    with pymupdf.open(path) as document:
        text = "".join(page.get_text() for page in document)
    for words in ("4000.0", "12.000", "0.00060", "8000.0", "0.00200", "1.20", "0.50", "ＮＧ", "ＯＫ"):
        assert words in text
    assert "－" in text  # Vud, and the pull-out check, of a pile with no tension
    assert render_pile_check(result(), tmp_path / "again.pdf", LONGITUDINAL).read_bytes() == path.read_bytes()


def test_the_grid_workbook_is_the_whole_report():
    assert len(grid_documents(result(), LONGITUDINAL)) == 1
    assert build_pile_check(result(), LONGITUDINAL) is not None

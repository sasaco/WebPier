"""0800 of a pile foundation (decision 96): the widths and the section forces as the report prints them (from the result alone)."""

import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parents[1] / "calc"))

from pile_footing_support import result  # noqa: E402
from webpier.reporting.stages import pile_footing  # noqa: E402


def test_the_report_has_the_widths_and_the_forces_of_both_directions(tmp_path):
    found = result()
    path = pile_footing.render_pile_footing(found, tmp_path / "0800.pdf")
    with pymupdf.open(path) as document:
        text = "".join(page.get_text() for page in document)
    assert text.startswith("§12. フーチングの照査\n12.1 応答値の算定\n(1) 線路方向の計算")  # decision 117
    for expected in ("(1) 線路方向の計算", "(2) 線路直角方向の計算", "1) 有効幅", "2) 設計断面力", "b + 2d ≦ B", "D + 2(d/2 + a) ≦ B", "Σ(D + d) ≦ B",
                     "Lp + D ≦ B", "く体前面（せん断）", "復旧性", "設計せん断力"):
        assert expected in text
    first = found.longitudinal.points[0]
    assert f"{first.point.width.be.value:.0f}" in text


def test_the_same_result_gives_the_same_bytes_and_a_grid_workbook_document(tmp_path):
    found = result()
    first = pile_footing.render_pile_footing(found, tmp_path / "a.pdf").read_bytes()
    assert first == pile_footing.render_pile_footing(found, tmp_path / "b.pdf").read_bytes()
    assert len(pile_footing.grid_documents(found)) == 1

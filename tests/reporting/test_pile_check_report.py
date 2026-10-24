"""0612 / 0622 基礎の照査 of a pile foundation (decision 89): the table of the responses, the limits and the checks, laid out in
the grid of the sample (Example橋脚4 III-3.3); every number is a value of the calc result."""

import pymupdf

from pile_check_support import result
from webpier.reporting.stages.pile_check import (LONGITUDINAL, TRANSVERSE, build_pile_check, content, grid_documents,
                                                 insertions, records, render_pile_check)


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


def joint_result_of(rows=(1, 2)):
    from dataclasses import replace
    from pile_joint_support import joint_result
    return replace(result(), joint=joint_result(rows))


def test_the_joint_is_the_sample_section_b_after_the_pile_body(tmp_path):
    found = records(joint_result_of(), LONGITUDINAL)
    texts = [record["text"] for record in found]
    assert "(b) 杭とフーチングの結合部" in "".join(str(text) for text in texts)
    assert [record["id"] for record in found if "joint." in record["id"]][:3] == [
        "0612/joint.heading", "0612/joint.text1", "0612/joint.text2"]
    path = render_pile_check(joint_result_of(), tmp_path / "joint.pdf", LONGITUDINAL)
    with pymupdf.open(path) as document:
        text = "".join(page.get_text() for page in document)
    for words in ("杭とフーチングの結合部", "設計曲げ耐力Mud", "2957.2", "2449.8", "284.6", "3847.9", "1338.1", "0.12", "0.14",
                  "押込み側", "引抜き側", "18240.0", "せん断力に対する照査"):
        assert words in text
    assert render_pile_check(joint_result_of(), tmp_path / "again.pdf", LONGITUDINAL).read_bytes() == path.read_bytes()


def cast_result_of(**changes):
    from dataclasses import replace
    from pile_cast_support import cast_result
    return replace(result(), cast=cast_result(**changes))


def pdf_text(path) -> str:
    with pymupdf.open(path) as document:
        return "".join(page.get_text() for page in document)


def test_the_cast_in_place_pile_body_is_the_first_part_and_the_stability_the_second():
    found = records(cast_result_of(), LONGITUDINAL)
    keys = [record["id"] for record in found]
    assert keys[:3] == ["0612/heading", "0612/cast.heading", "0612/cast.section.title"]
    assert keys.index("0612/cast.row2") < keys.index("0612/cast.bending.heading") < keys.index("0612/cast.shear.heading")
    assert keys.index("0612/cast.shear.heading") < keys.index("0612/stability.heading")
    texts = {record["id"]: record["text"] for record in found}
    assert texts["0612/stability.heading"] == "(2) 杭基礎の安定に対する検討"
    assert texts["0612/cast.heading"] == "(1) 杭体の照査（場所打ち杭）"
    assert [texts[key] for key in ("0612/cast.bending.heading", "0612/cast.shear.heading")] == [
        "a) 曲げモーメントと軸方向力に対する照査", "b) せん断力に対する照査"]
    # a steel pipe pile's report and a report without a pile body keep their numbering
    assert {record["id"]: record["text"] for record in records(result(), LONGITUDINAL)}["0612/stability.heading"] == (
        "(1) 杭基礎の安定に対する検討")


def test_capacitas_pages_go_after_the_heading_of_each_check_in_the_order_of_the_report(tmp_path):
    found = cast_result_of()
    path = render_pile_check(found, tmp_path / "cast.pdf", LONGITUDINAL)
    text = pdf_text(path)
    order = ["(1) 杭体の照査（場所打ち杭）", "場所打ち杭の諸元", "a) 曲げモーメントと軸方向力に対する照査", "CAPACITA bending 1/1",
             "b) せん断力に対する照査", "CAPACITA shear 1/2", "CAPACITA shear 2/2", "(2) 杭基礎の安定に対する検討"]
    positions = [text.index(words) for words in order]
    assert positions == sorted(positions)
    for words in ("D32-20本", "15884.0", "132.0", "0.80", "0.90", "自然泥水", "圧縮最大", "引張最大", "杭列 2 の設計断面力（杭1本当り，2本）"):
        assert words in text
    assert insertions(found, LONGITUDINAL)[0].key == "0612/cast.bending.heading"
    # WebPier's parts are the same bytes for the same result; the pages are Capacita's, here the same bytes too
    assert render_pile_check(found, tmp_path / "again.pdf", LONGITUDINAL).read_bytes() == path.read_bytes()


def test_a_row_with_no_tension_prints_dashes_in_the_column_of_the_tension_case(tmp_path):
    from dataclasses import replace
    from pile_cast_support import COMPRESSED, LINES, cast_input
    from webpier.calc.pile_cast import assemble, section, select
    rows = [select(1, 7, 3, LINES), select(2, 8, 2, COMPRESSED)]  # only the first row has a tension
    found = replace(result(), cast=assemble(section(cast_input()), rows, "5.0.1", "ab" * 32, (), {}))
    tables = {unit.key: unit.value for unit in content(found, LONGITUDINAL) if unit.kind == "table"}
    first, second = tables["0612/cast.row1"].rows, tables["0612/cast.row2"].rows
    assert [span.value for span in first[0]][-1] == second[0][-1].value == "引張最大"
    assert first[4][-1].value == "-200.0"  # the N'd row: a tension is negative
    assert [row[-1].value for row in second[1:]] == ["－"] * 5  # the second row has no such case


def test_a_check_skipped_for_zero_forces_ends_with_the_reason_and_has_no_pages(tmp_path):
    found = cast_result_of(skipped=("shear_safety_destruction",), pages={
        "bending_safety_destruction": __import__("pile_cast_support").PAGES["bending_safety_destruction"]})
    texts = {record["id"]: record["text"] for record in records(found, LONGITUDINAL)}
    assert texts["0612/cast.shear.heading.omitted"] == "せん断力が生じないため，せん断に対する照査を省略する．"
    assert [(item.name, item.key, item.optional) for item in insertions(found, LONGITUDINAL)] == [
        ("bending_safety_destruction", "0612/cast.bending.heading", False),
        ("shear_safety_destruction", "0612/cast.shear.heading.omitted", True)]
    text = pdf_text(render_pile_check(found, tmp_path / "skipped.pdf", LONGITUDINAL))
    assert "CAPACITA bending 1/1" in text and "CAPACITA shear" not in text and "せん断に対する照査を省略する" in text


def test_the_grid_workbook_of_a_cast_in_place_pile_is_the_documents_between_capacitas_pages():
    found = cast_result_of()
    documents = grid_documents(found, LONGITUDINAL)
    assert len(documents) == 3  # up to the heading of the bending check, the shear heading, and the stability
    assert len(grid_documents(result(), LONGITUDINAL)) == 1 and not insertions(result(), LONGITUDINAL)


def test_a_missing_page_of_a_check_that_was_not_skipped_stops_the_report(tmp_path):
    import pytest
    from pile_cast_support import PAGES
    found = cast_result_of(pages={"bending_safety_destruction": PAGES["bending_safety_destruction"]})
    with pytest.raises(ValueError, match="差し込むページ shear_safety_destruction がありません"):
        render_pile_check(found, tmp_path / "missing.pdf", LONGITUDINAL)

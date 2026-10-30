"""0800 of a pile foundation (decision 96): the widths and the section forces as the report prints them (from the result alone);
and the parts WebPier lays out before Capacita's sections in 0810 / 0820 of a pile foundation, the deep beam shear of 安全性 and
of 復旧性（地震時） (decision 124)."""

import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parents[1] / "calc"))

from pile_footing_support import check, result  # noqa: E402
from webpier.reporting.stages import footing_check, pile_footing  # noqa: E402
from webpier.reporting.stages.frame_report import plain  # noqa: E402


def test_the_report_has_the_widths_and_the_forces_of_both_directions(tmp_path):
    found = result()
    path = pile_footing.render_pile_footing(found, tmp_path / "0800.pdf")
    with pymupdf.open(path) as document:
        text = "".join(page.get_text() for page in document)
    assert text.startswith("§12. フーチングの照査\n12.1 応答値の算定\n(1) 線路方向の計算")  # decision 117
    for expected in ("(1) 線路方向の計算", "(2) 線路直角方向の計算", "1) 有効幅", "2) 設計断面力", "b + 2d ≦ B", "D + 2(d/2 + a) ≦ B", "Σ(D + d) ≦ B",
                     "Σ{0.65√(a1² + d1²) + D}", "≦ Lp + D ≦ B", "く体前面（せん断）", "復旧性", "設計せん断力"):
        assert expected in text
    first = found.longitudinal.points[0]
    assert f"{first.point.width.be.value:.0f}" in text
    # the shear width of the face: each pile's a1 and be (decision 124; calc.pile_footing's test has the values)
    for name, amount in found.longitudinal.points[4].point.width.terms:
        assert f"{name} = {amount.value:.1f}" in text or f"{name} = {amount.value:.0f}" in text


def test_the_deep_beam_shear_of_the_earthquake_is_printed_with_that_of_safety(tmp_path):
    """Decision 124: the shear force of 復旧性（地震時） at the points of the deep beam shear (made-up lines: 400 at the pile
    position, the 安全性 times γR 1.2 = 480)."""
    path = pile_footing.render_pile_footing(result(), tmp_path / "0800.pdf")
    with pymupdf.open(path) as document:
        text = "".join(page.get_text() for page in document)
    assert "480.0" in text and "400.0" in text


def test_a_case_without_a_deep_beam_shear_of_the_sense_is_printed_as_a_dash():
    """Decision 124: a case of 安全性（破壊） or 復旧性（地震時） without a shear of the point's sense has no Vd: its three
    shear rows are "－", as those of 耐久性."""
    from dataclasses import replace  # noqa: PLC0415

    from webpier.calc.pile_footing import Case  # noqa: PLC0415

    forces = result().longitudinal.points[5]  # 杭位置（上側引張）の Vsd
    missing = replace(forces, forces=tuple(
        replace(force, vd=None, vd_end=None, vd_combination=None, vd_md=None) if force.case is Case.SEISMIC else force
        for force in forces.forces))
    rows = pile_footing._forces_table(missing).rows
    # the header, then Vd, its No and its end: the columns 安全性, 耐久性 ×2, 復旧性（地震時）
    assert [[cell.value for cell in row[2:]] for row in rows[1:]] == [
        ["480.0", pile_footing.DASH, pile_footing.DASH, pile_footing.DASH],
        ["2", pile_footing.DASH, pile_footing.DASH, pile_footing.DASH],
        [rows[3][2].value, pile_footing.DASH, pile_footing.DASH, pile_footing.DASH]]
    assert rows[3][2].value != pile_footing.DASH


def test_the_pieces_of_a_pile_position_are_printed_when_they_are_apart(tmp_path):
    from dataclasses import replace  # noqa: PLC0415

    from webpier.core.printed import Precision  # noqa: PLC0415

    found = result()
    width = Precision(0, "mm")
    point = found.longitudinal.points[2]
    apart = replace(point.point.width, terms=(*point.point.width.terms, ("be(1)", width(2522.0)), ("be(2)", width(2522.0))),
                    pieces=(width(2522.0), width(2522.0)))
    points = (*found.longitudinal.points[:2], replace(point, point=replace(point.point, width=apart)),
              *found.longitudinal.points[3:])
    changed = replace(found, longitudinal=replace(found.longitudinal, points=points))
    path = pile_footing.render_pile_footing(changed, tmp_path / "0800.pdf")
    with pymupdf.open(path) as document:
        text = "".join(page.get_text() for page in document)
    assert "be(1) = 2522" in text and "be(2) = 2522" in text


def test_0810_of_a_pile_foundation_has_the_deep_beam_shear_of_safety_and_of_the_earthquake():
    """Decision 124: the parts before Capacita's sections, 2) of 復旧性（地震時） with the sentence of the sample V-138 and γi 1.0."""
    found = check()
    assert found.sections == ("bending_safety_destruction", "shear_deep_beam_safety_destruction", "bending_durability",
                              "bending_restorability_eq", "shear_deep_beam_restorability_eq", "bending_rebar_amount")
    parts = dict((section, units) for units, section in footing_check.parts(found, footing_check.LONGITUDINAL))
    texts = {section: " ".join(plain(unit.value) for unit in units) for section, units in parts.items()}
    keys = [unit.key for unit in parts["shear_deep_beam_restorability_eq"]]
    assert keys[:2] == ["0810/restorability.deep.heading", "0810/restorability.deep.text"]
    assert [unit.key for unit in parts["shear_deep_beam_safety_destruction"]][:2] == [
        "0810/safety.deep.heading", "0810/safety.deep.face.heading"]  # the safety's has no sentence
    assert "設計引抜せん断耐力Vsdを設計限界値として，以下に述べる式により照査する．" in texts["shear_deep_beam_restorability_eq"]
    assert "構造物係数(= 1.0)" in texts["shear_deep_beam_restorability_eq"]  # 復旧性（損傷）地震時 (the sample V-138)
    assert "構造物係数(= 1.2)" in texts["shear_deep_beam_safety_destruction"]


def _without_shear(found, deep_beam, case):
    """*found* with no Vd of *case* at the points of the deep beam shear *deep_beam* (no shear of the point's sense)."""
    from dataclasses import replace  # noqa: PLC0415

    def strip(item):
        if item.point.deep_beam != deep_beam:
            return item
        forces = tuple(replace(force, vd=None, vd_end=None, vd_combination=None, vd_md=None) if force.case is case
                       else force for force in item.forces.forces)
        return replace(item, forces=replace(item.forces, forces=forces))

    return replace(found, points=tuple(strip(item) for item in found.points))


def test_both_deep_beam_checks_have_their_formulas_when_both_have_a_shear():
    parts = dict((section, units) for units, section in footing_check.parts(check(), footing_check.LONGITUDINAL))
    for section in ("shear_deep_beam_safety_destruction", "shear_deep_beam_restorability_eq"):
        text = " ".join(plain(unit.value) for unit in parts[section])
        assert "γi・Vd / Vfdd ≦ 1.0" in text and "γi・Vd / Vsd ≦ 1.0" in text
        assert "照査を省略する" not in text


def test_a_pile_position_without_a_pull_out_shear_is_said_to_be_omitted():
    """Decision 124: the Vsd of 復旧性（地震時） without a Vd: (b) with the one sentence in place of its formula; the face's
    check and the safety's are unchanged."""
    from webpier.calc.pile_footing import Case  # noqa: PLC0415

    found = _without_shear(check(), "upper_tension", Case.SEISMIC)
    assert "shear_deep_beam_restorability_eq" in found.sections  # Vfdd still has its Vd
    parts = dict((section, units) for units, section in footing_check.parts(found, footing_check.LONGITUDINAL))
    units = parts["shear_deep_beam_restorability_eq"]
    keys = [unit.key for unit in units]
    pile = keys.index("0810/restorability.deep.pile.heading")
    assert keys[pile:] == ["0810/restorability.deep.pile.heading", "0810/restorability.deep.pile.omitted"]
    assert plain(units[-1].value) == footing_check.PILE_OMITTED == "杭が引き抜かれる向きの設計せん断力が生じないため，照査を省略する．"
    text = " ".join(plain(unit.value) for unit in units)
    assert "Vsd ≦ 1.0" not in text and "設計引抜きせん断耐力" not in text and "γi・Vd / Vfdd ≦ 1.0" in text
    assert keys[:2] == ["0810/restorability.deep.heading", "0810/restorability.deep.text"]  # the lead as it is
    assert "γi・Vd / Vsd ≦ 1.0" in " ".join(plain(unit.value) for unit in parts["shear_deep_beam_safety_destruction"])


def test_a_face_without_a_push_shear_is_said_to_be_omitted():
    from webpier.calc.pile_footing import Case  # noqa: PLC0415

    found = _without_shear(check(), "lower_tension", Case.SAFETY)
    parts = dict((section, units) for units, section in footing_check.parts(found, footing_check.LONGITUDINAL))
    units = parts["shear_deep_beam_safety_destruction"]
    keys = [unit.key for unit in units]
    assert keys[:3] == ["0810/safety.deep.heading", "0810/safety.deep.face.heading", "0810/safety.deep.face.omitted"]
    assert plain(units[2].value) == "杭が押し込まれる向きの設計せん断力が生じないため，照査を省略する．"
    text = " ".join(plain(unit.value) for unit in units)
    assert "Vfdd ≦ 1.0" not in text and "γi・Vd / Vsd ≦ 1.0" in text


def test_the_same_result_gives_the_same_bytes_and_a_grid_workbook_document(tmp_path):
    found = result()
    first = pile_footing.render_pile_footing(found, tmp_path / "a.pdf").read_bytes()
    assert first == pile_footing.render_pile_footing(found, tmp_path / "b.pdf").read_bytes()
    assert len(pile_footing.grid_documents(found)) == 1

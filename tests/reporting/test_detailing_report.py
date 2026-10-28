"""0400 照査の前提 (decision 73, ADR-0012): what the report prints, from the calc result as printed.

The sections the checks with section forces refer to are those of 0611 / 0621, 0810 / 0820 and 0910 after the switch
to R5 (orchestrator 2026-10-21, sasa/0400-r5 eca5fcd): the numbers Capacita gave 0611 / 0621's sections in the same
generation (8.10・8.7 and 9.10・9.7 when every group is printed), none without them (decision 121); 12.5・12.3 and
12.9・12.7; 13.8 or, with 0910's appearance check, 13.9, and 13.5. The judgements follow the result; the PDF is the same bytes for the same
result.
"""

import json
import re
from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest
from gridlayoutpdf import Figure, Line

from dataclasses import replace

from webpier.calc.column_check import LONGITUDINAL, TRANSVERSE, calculate_column_check
from webpier.calc.detailing import calculate_detailing
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.inputs import parse_input
from webpier.inputs.outputs import FootingParts
from webpier.reporting.stages.detailing import (FigureSpec, build_detailing, content, grid_documents, records,
                                                references, render_detailing)
from webpier.reporting.stages.frame_report import plain
from example4_support import EXAMPLE4_INPUT

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))


def data():
    return deepcopy(CURRENT)


def result(document=None):
    return calculate_detailing(parse_input(document if document is not None else data()))


def texts(document=None) -> dict[str, str]:
    return {record["id"].removeprefix("0400/"): record["text"] for record in records(result(document))}


# The numbers Capacita gives the commentary headings of 0611 (every group printed) and of 0621 for Example2 (使用性
# skipped for zero forces: 使用性（損傷） 9.8, 最小鉄筋量及び最大鉄筋量 9.9), as pipeline.capacita returns them.
ALONG = {"section_forces": "8.5", "bending_safety_destruction": "8.6", "shear_safety_destruction": None,
         "bending_durability": "8.7", "shear_durability": None, "bending_serviceability": "8.8",
         "bending_restorability": "8.9", "shear_restorability": None, "bending_rebar_amount": "8.10"}
ACROSS = {"section_forces": "9.5", "bending_safety_destruction": "9.6", "shear_safety_destruction": None,
          "bending_durability": "9.7", "bending_restorability": "9.8", "shear_restorability": None,
          "bending_rebar_amount": "9.9"}


def columns(document=None, along=ALONG, across=ACROSS):
    """The column checks of the same generation, by direction, with the numbers Capacita gave their sections."""
    pier = parse_input(document if document is not None else data())
    reaction, foundation = calculate_reaction(pier), calculate_foundation(pier)
    return {"線路": replace(calculate_column_check(pier, calculate_longitudinal(pier, foundation, reaction), LONGITUDINAL),
                          headings=along),
            "直角": replace(calculate_column_check(pier, calculate_transverse(pier, foundation, reaction), TRANSVERSE),
                          headings=across)}


def test_the_sections_referred_to():
    refs = references(False)
    # decision 121: without the column checks of the same generation the column's sections have no number
    assert dict(refs.column) == {"線路": (None, None), "直角": (None, None)}
    assert dict(references(False, columns=columns()).column) == {"線路": ("8.10", "8.7"), "直角": ("9.9", "9.7")}
    # one direction checked, the other not; a column check not yet checked by Capacita (no headings)
    only = columns()
    assert dict(references(False, columns={"線路": only["線路"]}).column) == {"線路": ("8.10", "8.7"),
                                                                          "直角": (None, None)}
    assert dict(references(False, columns={"直角": replace(only["直角"], headings=None)}).column)["直角"] == (None,
                                                                                                         None)
    assert refs.beam == ("13.8", "13.5")
    assert dict(refs.footing) == {"線路": ("12.5", "12.3"), "直角": ("12.9", "12.7")}
    assert references(True).beam == ("13.9", "13.5")
    # decision 110: numbered by the parts of the footing the outputs choose; none without its frame part
    assert dict(references(False, FootingParts(frames=True, seismic=False)).footing) == {
        "線路": ("12.4", "12.3"), "直角": ("12.7", "12.6")}
    assert dict(references(False, FootingParts(frames=False, seismic=True)).footing) == {
        "線路": (None, None), "直角": (None, None)}


def test_the_column_references_take_capacitas_numbers():
    """Decision 121: the numbers Capacita gave the sections of the same generation; without them the check is named
    without a number."""
    found = {unit.key.removeprefix("0400/"): plain(unit.value) for unit in content(result(), columns=columns())}
    assert found["column.線路.minimum.crack.reference"] == "照査は「8.10 最小鉄筋量及び最大鉄筋量」に示す。"
    assert found["column.直角.maximum.reference"] == "照査は「9.9 最小鉄筋量及び最大鉄筋量」に示す。"
    assert found["column.直角.stress.reference"] == "照査は「9.7 耐久性の照査」に示す。"
    alone = texts()
    assert alone["column.線路.minimum.crack.reference"] == ("照査は、柱の断面照査を行うときに"
                                                           "「最小鉄筋量及び最大鉄筋量」で確かめる。")
    assert alone["column.直角.stress.reference"] == "照査は、柱の断面照査を行うときに「耐久性の照査」で確かめる。"


def test_the_report_prints_the_chapter_and_the_references():
    found = texts()
    assert found["heading"] == "§4. 照査の前提"
    assert [found[f"layout.{name}.heading"] for name in ("beam", "column", "footing")] == ["(1) 梁", "(2) 柱",
                                                                                          "(3) フーチング"]
    assert found["column.heading"] == "4.2 躯体の構造細目" and found["beam.heading"] == "4.3 梁の構造細目"
    assert found["footing.heading"] == "4.4 フーチングの構造細目"
    assert found["column.線路.heading"] == "(1) 線路方向" and found["column.直角.heading"] == "(2) 線路直角方向"
    assert found["beam.minimum.axial.reference"] == "照査は「13.8 最小鉄筋量及び最大鉄筋量」に示す。"
    assert found["beam.stress.reference"] == "照査は「13.5 耐久性の照査」に示す。"
    # current.json chooses no footing (decision 110): the footing references have no section
    assert found["footing.直角.maximum.reference"] == ("照査は、フーチングの断面照査で地震時以外の照査を行うときに"
                                                       "「最小鉄筋量及び最大鉄筋量」で確かめる。")
    assert found["footing.線路.stress.reference"] == ("照査は、フーチングの断面照査で地震時以外の照査を行うときに"
                                                     "「耐久性の照査」で確かめる。")
    document = data()
    document["outputs"] = dict.fromkeys(document["outputs"], True)
    every = texts(document)
    assert every["footing.直角.maximum.reference"] == "照査は「12.9 最小鉄筋量及び最大鉄筋量」に示す。"
    assert every["footing.直角.stress.reference"] == "照査は「12.7 耐久性の照査」に示す。"
    assert every["footing.線路.stress.reference"] == "照査は「12.3 耐久性の照査」に示す。"
    document = data()
    document["片持ち梁の照査"]["外観の照査"] = "行う"
    assert texts(document)["beam.maximum.reference"] == "照査は「13.9 最小鉄筋量及び最大鉄筋量」に示す。"


def test_the_whole_section_items_are_in_the_first_direction_only():
    found = texts()
    assert found["column.線路.minimum.heading"] == "1) 主鉄筋の最小鉄筋量の検討【RC標準第Ⅲ編2.3.3.1】"
    assert found["column.線路.minimum.ratio.heading"].startswith("(a) コンクリートの収縮")
    assert found["column.線路.minimum.crack.heading"].startswith("(b) 曲げひび割れ")
    assert found["column.線路.ratio.heading"].startswith("3) 軸方向力の最大値から定まる最大鉄筋量")
    assert found["column.線路.capacity.heading"].startswith("9) 帯鉄筋の設計せん断耐力の上限値の照査")
    assert "column.直角.minimum.ratio.heading" not in found and "column.直角.ratio.heading" not in found
    assert found["column.直角.minimum.crack.heading"].startswith("(a) 曲げひび割れ")
    assert found["column.直角.capacity.heading"].startswith("8) 帯鉄筋の設計せん断耐力の上限値の照査")
    assert found["footing.直角.ratio.heading"].startswith("3) ")  # a footing's Pc is its direction's
    assert found["footing.直角.faces.heading"] == "10) 配力鉄筋及び圧縮鉄筋【RC標準13.6.4】"


def test_the_values_of_the_column():
    found = texts()
    assert found["column.線路.minimum.ratio.symbols"] == (
        "ここに、As：軸方向鉄筋の量 (= 51220.6 mm2)（SD390）：引張・圧縮鉄筋 D32 − 58 本 (= 46063.6 mm2)"
        "：側方鉄筋 D19 − 18 本 (= 5157.0 mm2)b：部材の幅 (= 4500.0 mm)h：部材の高さ (= 2700.0 mm)"
        "A：断面積 (= 12150000 mm2)")
    assert found["column.線路.minimum.ratio.pc"] == "Pc=51220.6/12150000×100"
    assert found["column.線路.minimum.ratio.check"] == "=0.422 %＞0.15 %・・・・・・OK"
    assert found["column.線路.ratio.check"] == "Pc=0.422 %＜6.0 %・・・・・・OK"
    assert found["column.線路.clear.items"] == (
        "ここに、軸方向鉄筋ピッチ：150.0 mm主鉄筋径：D32軸方向鉄筋のあき：150.0 − 32 = 118.0 mm")
    assert found["column.線路.clear.table"] == (
        "部材あき(mm)備考躯体軸方向鉄筋のあき 118.0≧ 40 mm≧ 32 × 1.5 = 48.0 mm≧ 25.0 × 4/3 = 33.3 mm")
    assert found["column.線路.shear.bars.0"] == "外側帯鉄筋　D22 − 1.0 組　ctc 150.0"
    assert found["column.線路.shear.bars.1"] == "中間帯鉄筋　D22 − 4.0 組　ctc 150.0"
    assert found["column.線路.shear.ps"] == "Ps=10×387.1/(4500.0 × 150.0)×100"
    assert found["column.線路.shear.check"] == "=0.573 %＞0.15 %・・・・・・OK"
    assert found["column.線路.placement.general.half_d"] == "・有効高さの1/2=2592.0×1/2=1296mm"
    assert found["column.線路.placement.general.fixed_300"] == "・300mm以下"
    assert found["column.線路.placement.general.result"] == (
        "一般部：上記最小間隔は300mmに対して計算上の配置間隔は150.0mmより満足する。")
    assert found["column.線路.placement.confinement.main_8"] == "・圧縮・引張鉄筋の直径の8倍=32×8=256mm"
    assert found["column.線路.placement.lateral.result"] == (
        "中間帯鉄筋を4.0組配置し、帯鉄筋の横方向の間隔は最大600.0mmとなり満足する。")
    assert found["column.線路.ductility.pw"] == "pw=3871.0/(4500.0 × 150.0)×100=0.573%"
    assert found["column.線路.ductility.check"] == "0.021 × 1.15 × 0.573 ＋ 0.013 = 0.027 ≦ 0.040　・・・・・・ OK"
    assert found["column.線路.capacity.value"] == "0.00573 × 390 / (27.0 / 1.3) = 0.108 ＞ 0.10"
    assert "中間帯鉄筋" not in found.get("column.直角.shear.bars.2", "")


def test_the_values_of_the_beam_and_the_footing():
    found = texts()
    assert found["beam.skin.horizontal.bars"] == "・水平方向　D22 @ 125.0（17 本）を配置する。（側面鉄筋）"
    assert found["beam.skin.horizontal.ratio"] == (
        "17 × 387.1 / (2700.0 × 2700.0) × 100 = 0.090 % ≧ 0.080 %　・・・・・・ OK")
    assert found["beam.skin.vertical.bars"] == "・鉛直方向　D22 @ 125.0 を配置する。（スターラップ）"
    assert found["beam.skin.horizontal.spacing"] == "・水平方向の間隔 125.0 mm ≦ 300 mm　・・・・・・ OK"
    assert found["beam.skin.corbel.required"] == "0.40・As=0.40×19855.0=7942.0mm2"
    assert found["beam.skin.corbel.check"] == "両面　17 × 387.1 × 2 = 13161.4 mm2 ＞ 7942.0 mm2　・・・・・・ OK"
    assert found["beam.compression.check"] == "As' = 5157.0 mm2 ≧ 3309.2 mm2　・・・・・・ OK"
    assert found["beam.clear.table"].startswith("部材あき(mm)備考梁（上側）軸方向鉄筋のあき 32.0≧ 20 mm≧ 32 = 32.0 mm")
    assert found["beam.clear.result"] == "表より、鉄筋のあきは限界値を下回り満足しない。"
    assert "beam.clear.column" not in found and "footing.線路.clear.column" not in found
    assert found["footing.線路.shear.bars.0"] == "スターラップ　D16 − 2.00 本/m　ctc 250.0"
    assert found["footing.線路.shear.ps"] == "Ps=2.00×198.6/(1000 × 250.0)×100"
    assert found["footing.直角.faces.table"] == (
        "径－本数As\n(mm²)As/6\n(mm²)配置配力鉄筋\n＞As/6配置圧縮鉄筋\n＞As/6"
        "上側D25 − 8.00 本4053.6675.64053.6 (OK)5139.2 (OK)下側D29 − 8.00 本5139.2856.54053.6 (OK)4053.6 (OK)")
    assert found["footing.線路.capacity.value"] == "0.00159 × 390 / (27.0 / 1.3) = 0.030 ≦ 0.10"


def test_what_is_not_satisfied_says_so():
    document = data()
    column = document["鉄筋"]["柱"]
    column["materials"]["transverse"] = "SD295"
    column["column_hoops"]["direction_rows"][0].update(diameter_mm=32, pitch_mm=400, effective_legs=2)
    column["main_bars"]["線路"].update(diameter_mm=10, per_face_count=2, distribution={
        "mode": "両端＋中央ピッチ", "edge_center_mm": 108, "pitch_mm": None})
    column["main_bars"]["直角"].update(diameter_mm=10)
    document["鉄筋"]["梁"]["side_bars"] = None
    found = texts(document)
    # 2 × 2 + 9 × 2 = 22 bars D10: 22 × 71.33 = 1569.3; 1569.3 / 12150000 × 100 = 0.0129 → 0.013
    assert found["column.線路.minimum.ratio.check"] == "=0.013 %＜0.15 %・・・・・・NG"
    assert found["column.線路.minimum.ratio.result"] == "以上の結果より、Pc＜0.15%となり満足しない。"
    assert found["column.線路.placement.general.result"].endswith("配置間隔は400.0mmとなり満足しない。")
    assert found["column.線路.placement.lateral.result"].endswith("満足しない。")
    assert "column.線路.shear.bars.1" not in found  # two legs: the outer hoop only
    assert found["beam.skin.horizontal.bars"] == "・水平方向　側方鉄筋なし"
    assert found["beam.skin.horizontal.ratio"].startswith("0 / (2700.0 × 2700.0) × 100 = 0.000 % ＜ 0.080 %")
    assert found["beam.skin.corbel.check"].startswith("両面　0 = 0.0 mm2 ＜ 7942.0 mm2")
    assert "beam.skin.horizontal.spacing" not in found
    document = data()
    document["鉄筋"]["柱"]["column_hoops"]["direction_rows"][0].update(diameter_mm=32, pitch_mm=100)
    # pw = 10 × 794.2 / (4500 × 100) × 100 = 1.765; 0.021 × 1.15 × 1.765 + 0.013 = 0.05563 → 0.056
    assert texts(document)["column.線路.ductility.check"].endswith("= 0.056 ＞ 0.040　・・・・・・ NG")


def test_one_bar_a_line_prints_no_pitch():
    document = data()
    document["鉄筋"]["柱"]["main_bars"]["直角"]["per_face_count"] = 1
    document["鉄筋"]["柱"]["column_hoops"]["direction_rows"][1]["effective_legs"] = 2
    found = texts(document)
    assert found["column.直角.clear.items"] == "ここに、主鉄筋径：D19"
    assert "軸方向鉄筋のあき －" in found["column.直角.clear.table"]


def test_the_keys_of_the_units_are_unique(monkeypatch):
    from webpier.reporting.stages import detailing

    units = content(result())
    monkeypatch.setattr(detailing, "content", lambda result, figures=None, columns=None: (*units, units[0]))
    with pytest.raises(ValueError, match="帳票の単位に重複したキーがあります"):
        build_detailing(result())


def test_an_equal_ratio_is_satisfied():
    document = data()
    # 1 × 286.5 + … : the stirrups of the footing at a ratio of exactly 0.150 % (2 × 198.6 / (1000 × 264.8) = 0.15)
    document["鉄筋"]["フーチング"]["stirrups"]["線路"]["pitch_mm"] = 264.8
    assert texts(document)["footing.線路.shear.check"] == "=0.150 %≧0.15 %・・・・・・OK"


def test_a_hand_made_table_has_only_the_column_figure():
    """Decision 113: (2) 柱 of a hand-made table has its 配筋図 (the rows of the tables) and no table of the rows."""
    document = data()
    document["鉄筋"]["柱"]["custom_tables"]["線路"] = {"tension_rows": 1, "rows": [
        {"center_mm": 108, "diameter_mm": 32, "count": 29}, {"center_mm": 350, "diameter_mm": 19, "count": 2},
        {"center_mm": 2592, "diameter_mm": 32, "count": 29}]}
    figure = {"column": FigureSpec(Figure(4, 2, block_id="0400/test.figure"), ("柱の配筋図",))}
    keys = [unit.key for unit in content(result(document), figure)]
    heading = keys.index("0400/layout.column.heading")
    assert keys[heading + 1:heading + 3] == ["0400/layout.column", "0400/layout.footing.heading"]
    keys = [unit.key for unit in content(result(document))]
    assert keys[keys.index("0400/layout.column.heading") + 1] == "0400/layout.footing.heading"
    assert not any("鉄筋配置表" in text for text in texts(document).values())


def test_the_figures_of_4_1_stand_under_their_headings():
    units = content(result(), {"column": FigureSpec(Figure(4, 2, block_id="0400/test.figure"), ("柱の配筋図",))})
    keys = [unit.key for unit in units]
    assert keys.index("0400/layout.column") == keys.index("0400/layout.column.heading") + 1
    assert "0400/layout.beam" not in keys
    with pytest.raises(ValueError, match="配筋図の名前が不正です: drawing"):
        content(result(), {"drawing": FigureSpec(Figure(4, 2), ())})


def drawn(block_id: str) -> Figure:
    """A figure that draws (a 配筋図 always does): an empty one would leave its heading kept with nothing."""
    return Figure(4, 2, Line(5, 5, 20, 20), block_id=block_id)


def test_a_page_breaks_only_before_a_heading_or_a_lead():
    """A formula stays on the page of its text, its "ここに、" list, its judgement and "以上の結果より": every page
    begins with a heading or a lead (① 一般部, ディープビームの構造細目, …). 4.2, 4.3 and 4.4 and (2) 線路直角方向 of
    4.2 and 4.4 (to be read beside (1) 線路方向) begin a page, and no blank line is left before them. Without the
    figures of 4.1, 4.2 follows its headings."""
    figures = {name: FigureSpec(drawn(f"0400/test.{name}"), ()) for name in ("beam", "column", "footing")}
    pages = build_detailing(result(), figures).layout()
    firsts = [page.metadata["placements"][0]["block_id"] for page in pages]
    assert len(firsts) > 10
    assert all(re.search(r"\.(heading(\.row)?|lead)$|^0400/heading$", first) for first in firsts), firsts
    for key in ("0400/column.heading", "0400/column.直角.heading", "0400/beam.heading", "0400/footing.heading",
                "0400/footing.直角.heading"):
        before = pages[firsts.index(key) - 1]
        assert before.metadata["placements"][-1]["block_type"] != "Spacer"
    alone = build_detailing(result()).layout()
    assert [placement["block_id"] for placement in alone[0].metadata["placements"]][-1] != "0400/layout.footing.heading"


def test_the_pdf_is_the_same_bytes_and_the_workbook_the_same_document(tmp_path):
    detailing = result()
    first = render_detailing(detailing, tmp_path / "a.pdf").read_bytes()
    assert first == render_detailing(detailing, tmp_path / "b.pdf").read_bytes()
    (document,) = grid_documents(detailing)
    assert document.render(tmp_path / "c.pdf", invariant=True).read_bytes() == first
    with pymupdf.open(tmp_path / "a.pdf") as pdf:
        text = "".join(page.get_text() for page in pdf)
    assert "§4. 照査の前提" in text and "#REF!" not in text and "小判形" not in text
    figure = {"footing": FigureSpec(drawn("0400/test.figure"), ())}
    assert build_detailing(detailing, figure).render(tmp_path / "d.pdf", invariant=True).read_bytes() != first


# --- 4.5 杭の構造細目 of a 場所打ち杭 (decision 98) ------------------------------------------------------------------


def pile_result():
    """The sample 0440's pile (D 1200, D32 − 16 本 SD390, ds 156, f'ck 21, D19 ctc125 and D16 ctc125) on pile_seismic.json,
    with 1/β 3.55 m in both directions."""
    from types import SimpleNamespace
    document = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "pile_seismic.json").read_text(
        encoding="utf-8"))
    document["杭基礎"]["場所打ち杭"].update({"杭径": 1.2, "f'ck": 21.0})
    document["鉄筋"]["フーチング"]["concrete_strength_mpa"] = 24.0
    bars = document["鉄筋"]["杭"]
    bars.update({"pure_cover_mm": 121.0, "main_bars": {"diameter_mm": 32, "count": 16}})
    bars["materials"]["main"] = "SD390"
    bars["hoops"]["zone_2d"] = {"diameter_mm": 19, "sets": 1, "pitch_mm": 125.0}
    bars["hoops"]["lower"] = [{"length_m": 5.0, "diameter_mm": 16, "sets": 1, "pitch_mm": 125.0}]
    springs = SimpleNamespace(direction=lambda name: SimpleNamespace(inverse_beta=3.55))
    return calculate_detailing(parse_input(document), springs)


def test_a_cast_in_place_pile_adds_4_5_as_the_sample_0440_prints_it():
    found = {record["id"].removeprefix("0400/"): record["text"] for record in records(pile_result())}
    assert found["pile.heading"] == "4.5 杭の構造細目"
    assert found["layout.pile.heading"] == "(4) 杭"
    assert found["pile.minimum.reference"] == ("照査は「0711_線路方向非線形解析 杭頭反力の最大値から定める最小鉄筋量」と"
                                               "「0721_線路直角方向非線形解析 杭頭反力の最大値から定める最小鉄筋量」に示す。")
    assert "3176.8" in found["pile.bending.pt"] and "848.5" in found["pile.bending.pt"] and "0.359" in found["pile.bending.pt"]
    assert found["pile.bending.check"] == "0.359 % ＞ 0.20 %"
    assert found["pile.hoops.span.0.beta"] == "1／β ＝ 3.55 m　「0500_杭基礎より」"
    assert "1.85" in found["pile.hoops.span.0.ratio"] and found["pile.hoops.span.0.check"] == "1.85 ≦ 2.5"
    assert found["pile.hoops.span.result"] == "以上より、靭性の向上を考え帯鉄筋量は杭の側断面積の0.35％以上を配置する。"
    assert found["pile.hoops.head.check"] == "0.382 % ＞ 0.35 %" and found["pile.hoops.第1区間.check"] == "0.265 % ＞ 0.20 %"
    assert found["pile.anchorage.result"] == "以上より、基本定着長は、ld＝867mmとし、杭頭定着長は、100mm単位に切り上げて900mmとする。"
    assert "pile.heading" not in texts()  # a direct foundation has no 4.5


def test_4_5_begins_a_page_and_the_pdf_is_the_same_bytes(tmp_path):
    detailing = pile_result()
    pages = build_detailing(detailing).layout()
    firsts = [page.metadata["placements"][0]["block_id"] for page in pages]
    assert "0400/pile.heading" in firsts
    first = render_detailing(detailing, tmp_path / "a.pdf").read_bytes()
    assert first == render_detailing(detailing, tmp_path / "b.pdf").read_bytes()


# --- 4.5 杭の構造細目 of a 鋼管ソイルセメント杭 (decision 99) ------------------------------------------------------------


def steel_document(**steel):
    """The sample Example橋脚4's pile (D 800, t 18, 腐食代 1, Dsc 1000, D38 − 16 本 SD390 at 75 mm, 中詰め f'ck 27 and
    Dmax 25) on pile.json, with the footing's f'ck 27."""
    fixtures = Path(__file__).parents[1] / "fixtures" / "inputs"
    document = json.loads((fixtures / "pile.json").read_text(encoding="utf-8"))
    example4 = json.loads(EXAMPLE4_INPUT.read_text(encoding="utf-8"))
    document["下部構造"]["基礎形式"] = "鋼管ソイルセメント杭"
    document["杭基礎"]["鋼管ソイルセメント杭"] = example4["杭基礎"]["鋼管ソイルセメント杭"]
    document["杭基礎"]["鋼管ソイルセメント杭"]["結合部"]["粗骨材の最大寸法"] = 25.0
    document["杭基礎"]["鋼管ソイルセメント杭"].update(steel)
    document["鉄筋"]["フーチング"]["concrete_strength_mpa"] = 27.0
    return document


def steel_texts(document=None) -> dict[str, str]:
    return texts(document if document is not None else steel_document())


def test_a_steel_pile_adds_4_5_as_the_sample_ii_1_2_prints_it():
    found = steel_texts()
    assert found["pile.heading"] == "4.5 杭の構造細目" and found["layout.pile.heading"] == "(4) 杭"
    assert [found[key] for key in ("steel.pipe.heading", "steel.joint.heading", "steel.soil.heading")] == [
        "(1) 鋼管杭", "(2) 杭とフーチングの結合部", "(3) ソイルセメント"]
    assert found["steel.pipe.diameter.result"] == "採用した杭径は800mmのため、上記条件を満足する。"
    assert found["steel.pipe.made.ratio"] == "鋼管外径Dに対して　18 ／ 800 ＝ 0.0225 ≧ 0.01"
    assert found["steel.pipe.effective.ratio"] == "鋼管外径Dに対して　17 ／ 800 ＝ 0.0213 ≧ 0.0125"
    assert found["steel.pipe.joint.5"].endswith("溶接はJIS規格によるものとし、上記条件を満足する。")
    assert found["steel.pipe.tip.ribs.result"] == "配筋図より、ずれ止めの取付け長lspiは1050mmなので、上記条件を満足する。"
    assert found["steel.pipe.tip.penetration.value"] == "鋼管外径の1.5倍　：　800 × 1.5 ＝ 1200 mm"
    assert found["steel.pipe.tip.margin.value"] == "ソイルセメント体径の0.5倍　：　1000 × 0.5 ＝ 500 mm"
    assert "2.25 %" in found["steel.pipe.summary.table"] and "Df0 ＝ 1000 mm" in found["steel.pipe.summary.table"]
    assert found["steel.joint.cover.value"] == "75 － 18 － 38 ／ 2 ＝ 38 mmである。"
    assert "軸方向鉄筋のあき 90" in found["steel.joint.clear.table"] and "≧ 25 × 4/3 ＝ 33.3 mm" in found[
        "steel.joint.clear.table"]
    assert found["steel.joint.gap.value"] == "あきは、75 － 18 － 16 － 38 ／ 2 ＝ 22 mmである。"
    assert found["steel.joint.minimum.check"] == "3.63 % ＞ 1 %" and found["steel.joint.maximum.check"] == "3.63 % ＜ 6 %"
    assert "1054" in found["steel.joint.anchorage.basic.ld01"]
    assert found["steel.joint.anchorage.basic.result"] == "そのため、基本定着長は、20φとする。"
    assert found["steel.joint.anchorage.footing.l1"].endswith("＝ 760 ＋ 190 ＝ 950 mm → 950 mm")
    assert found["steel.joint.filling.sum"].endswith("＝ 100 ＋ 1170 ＋ 152 ＋ 100 ＝ 1522 mm")
    assert found["steel.joint.filling.value"].endswith("＝ 1522 mm → 1550 mm")
    assert found["steel.joint.hoops.diameter.text"] == ("フーチング内のアンカー鉄筋の帯鉄筋径は、アンカー鉄筋がD29以上の場合"
                                                         "は、D16以上とし、鋼管外径が1000mm以下の場合は、D22以下とする。")
    assert found["steel.joint.hoops.pitch.inner"] == "1198 ／ 4 → ctc 250 mm（D10－5本）"
    assert found["steel.joint.ribs.position.result"] == ("最上段のずれ止めの取付中心位置は、鋼管杭頭から 200 mm、最下段のずれ止め"
                                                         "の取付中心位置は、中詰めコンクリート下端から 1100 mm なので、"
                                                         "上記条件を満足する。")
    assert found["steel.joint.ribs.steps.result"] == "実際に配置したずれ止めは、2 段なので、上記条件を満足する。"
    assert "×" not in found["steel.joint.summary.table"] and "1.5φ以上" in found["steel.joint.summary.table"]
    assert found["steel.soil.nominal.result"] == "採用したソイルセメント体の公称径は1000mm、鋼管外径は800mmのため、上記条件を満足する。"
    assert "qu2 ＝ 15000 kN/m" in found["steel.soil.summary.table"]
    assert not any(key.startswith("steel.") for key in pile_texts())  # a 場所打ち杭 has its own 4.5


def pile_texts() -> dict[str, str]:
    return {record["id"].removeprefix("0400/"): record["text"] for record in records(pile_result())}


def test_a_steel_pile_that_breaks_the_rules_prints_that_it_does_not_satisfy_them():
    thin = steel_texts(steel_document(鋼管厚=9.0, 鋼管外径=1.3, ソイルセメント径=1.4))
    assert thin["steel.pipe.diameter.result"] == "採用した杭径は1300mmのため、上記条件を満足しない。"
    assert thin["steel.pipe.effective.result"] == "となるため、上記条件を満足しない。"
    assert thin["steel.pipe.tip.ribs.result"] == "鋼管外径 1300mm は表の範囲外のため、上記条件を満足しない。"
    assert thin["steel.joint.gap.result"] == "ずれ止めを配置できないため、上記条件を満足しない。"
    assert thin["steel.joint.ribs.thickness.result"] == ("鋼管の有効肉厚が8mmのため、表の厚さのずれ止めを配置できず、"
                                                         "上記条件を満足しない。")
    assert "steel.joint.ribs.width.text" not in thin
    assert "－" in thin["steel.pipe.summary.table"] and "×" in thin["steel.joint.summary.table"]
    assert thin["steel.soil.nominal.result"].endswith("上記条件を満足しない。")
    weak = steel_document()
    weak["鉄筋"]["フーチング"]["concrete_strength_mpa"] = 21.0
    assert steel_texts(weak)["steel.joint.anchorage.basic.result"] == "そのため、基本定着長は、ld01－10φとする。"
    small = steel_document(鋼管外径=1.1, ソイルセメント径=1.3)
    small["杭基礎"]["鋼管ソイルセメント杭"]["結合部"]["軸方向鉄筋"].update({"径": 25, "本数": 24})
    found = steel_texts(small)
    assert found["steel.joint.hoops.diameter.text"] == ("フーチング内のアンカー鉄筋の帯鉄筋径は、アンカー鉄筋がD25以下の場合"
                                                        "は、D13以上とする。")
    assert found["steel.joint.hoops.diameter.result"] == "上記より、帯鉄筋径は、D13以上となる。"
    small["杭基礎"]["鋼管ソイルセメント杭"]["結合部"]["軸方向鉄筋"].update({"径": 16, "本数": 24})
    assert "D16以下の場合は、D10以上" in steel_texts(small)["steel.joint.hoops.diameter.text"]


def test_the_steel_pile_s_4_5_lays_out_on_pages_and_the_pdf_is_the_same_bytes(tmp_path):
    for document in (steel_document(), steel_document(鋼管厚=9.0, 鋼管外径=1.3, ソイルセメント径=1.4)):
        detailing = result(document)
        pages = build_detailing(detailing).layout()
        assert "0400/pile.heading" in [page.metadata["placements"][0]["block_id"] for page in pages]
    first = render_detailing(detailing, tmp_path / "a.pdf").read_bytes()
    assert first == render_detailing(detailing, tmp_path / "b.pdf").read_bytes()

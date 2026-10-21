"""0400 照査の前提 (decision 73, ADR-0012): what the report prints, from the calc result as printed.

The sections the checks with section forces refer to are those of 0611 / 0621, 0810 / 0820 and 0910 after the switch
to R5 (orchestrator 2026-10-21, sasa/0400-r5 eca5fcd): 8.10・8.7 and 9.10・9.7; 12.5・12.3 and 12.9・12.7; 13.8 or, with
0910's appearance check, 13.9, and 13.5. The judgements follow the result; the PDF is the same bytes for the same
result.
"""

import json
import re
from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest
from gridlayoutpdf import Figure, Line

from webpier.calc.detailing import calculate_detailing
from webpier.inputs import parse_input
from webpier.reporting.stages.detailing import (FigureSpec, build_detailing, content, grid_documents, records,
                                                references, render_detailing)

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))


def data():
    return deepcopy(CURRENT)


def result(document=None):
    return calculate_detailing(parse_input(document if document is not None else data()))


def texts(document=None) -> dict[str, str]:
    return {record["id"].removeprefix("0400/"): record["text"] for record in records(result(document))}


def test_the_sections_referred_to():
    refs = references(False)
    assert dict(refs.column) == {"線路": ("8.10", "8.7"), "直角": ("9.10", "9.7")}
    assert refs.beam == ("13.8", "13.5")
    assert dict(refs.footing) == {"線路": ("12.5", "12.3"), "直角": ("12.9", "12.7")}
    assert references(True).beam == ("13.9", "13.5")


def test_the_report_prints_the_chapter_and_the_references():
    found = texts()
    assert found["heading"] == "§4. 照査の前提"
    assert [found[f"layout.{name}.heading"] for name in ("beam", "column", "footing")] == ["(1) 梁", "(2) 柱",
                                                                                          "(3) フーチング"]
    assert found["column.heading"] == "4.2 躯体の構造細目" and found["beam.heading"] == "4.3 梁の構造細目"
    assert found["footing.heading"] == "4.4 フーチングの構造細目"
    assert found["column.線路.heading"] == "(1) 線路方向" and found["column.直角.heading"] == "(2) 線路直角方向"
    assert found["column.線路.minimum.crack.reference"] == "照査は「8.10 最小鉄筋量及び最大鉄筋量」に示す。"
    assert found["column.直角.maximum.reference"] == "照査は「9.10 最小鉄筋量及び最大鉄筋量」に示す。"
    assert found["column.直角.stress.reference"] == "照査は「9.7 耐久性の照査」に示す。"
    assert found["beam.minimum.axial.reference"] == "照査は「13.8 最小鉄筋量及び最大鉄筋量」に示す。"
    assert found["beam.stress.reference"] == "照査は「13.5 耐久性の照査」に示す。"
    assert found["footing.直角.maximum.reference"] == "照査は「12.9 最小鉄筋量及び最大鉄筋量」に示す。"
    assert found["footing.直角.stress.reference"] == "照査は「12.7 耐久性の照査」に示す。"
    assert found["footing.線路.stress.reference"] == "照査は「12.3 耐久性の照査」に示す。"
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
    monkeypatch.setattr(detailing, "content", lambda result, figures=None: (*units, units[0]))
    with pytest.raises(ValueError, match="帳票の単位に重複したキーがあります"):
        build_detailing(result())


def test_an_equal_ratio_is_satisfied():
    document = data()
    # 1 × 286.5 + … : the stirrups of the footing at a ratio of exactly 0.150 % (2 × 198.6 / (1000 × 264.8) = 0.15)
    document["鉄筋"]["フーチング"]["stirrups"]["線路"]["pitch_mm"] = 264.8
    assert texts(document)["footing.線路.shear.check"] == "=0.150 %≧0.15 %・・・・・・OK"


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

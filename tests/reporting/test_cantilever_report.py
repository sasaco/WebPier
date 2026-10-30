"""The 0900 report (decision 59): 13.1 応答値の算定 and 13.2 設計作用の組合せ on the CantileverResult.

The manuscript is checked through its semantic records (what each unit prints, independent of the layout), against
the values of Example2 13-1 .. 13-37 where the inputs agree (tests/fixtures/example2/cantilever_notes.md lists the
deliberate differences: the end bearing's X 0.700, no snow shelter, Kh across the track 0.571), and the laid-out PDF
is hand-checked: every printed formula chain recomputes from its printed numbers (pdf_handcheck, which never imports
the report), the page count and the first page, and the same bytes twice.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from cantilever_report_support import TRANSVERSE, records, result_of, units
from pdf_handcheck import formula_checks
from webpier.calc.cantilever import Side
from webpier.reporting.stages.cantilever import PREFIX, SIDES, build_cantilever, render_cantilever


@pytest.fixture(scope="module")
def current():
    return result_of()


@pytest.fixture(scope="module")
def texts(current) -> dict[str, str]:
    return records(*current)


@pytest.fixture(scope="module")
def manuscript(current):
    return units(*current)


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory, current) -> Path:
    pier, reaction, result = current
    return render_cantilever(result, reaction, pier, tmp_path_factory.mktemp("0900") / "0900_片持ち梁.pdf")


# --- the manuscript -------------------------------------------------------------------------------------------------


def test_the_manuscript_starts_with_the_chapter_heading_and_13_1(manuscript):
    assert [(unit.kind, unit.value) for unit in manuscript[:2]] == [
        ("heading", "§13. 片持ち梁の照査"), ("heading", "13.1 応答値の算定")]  # decision 117
    headings = [unit.value for unit in manuscript if unit.kind == "heading"]
    assert sum(value.startswith("§") for value in headings) == 1
    assert "(1) 鉛直荷重" in headings and "(2) 水平荷重" in headings
    assert "4) 車両横荷重のトルクによる鉛直荷重" in headings and "7) 地震時列車荷重慣性力のトルクによる鉛直反力" in headings


def test_every_unit_has_a_unique_key_with_the_stage_prefix(manuscript):
    identifiers = [unit.identifier for unit in manuscript]
    assert len(set(identifiers)) == len(identifiers) > 500
    assert all(identifier.startswith(PREFIX) for identifier in identifiers)
    assert PREFIX == "0900/"


def test_the_dead_load_table_prints_every_bearing_and_the_pier_totals(texts):
    table = texts["0900/dead.table"]
    assert table.startswith("荷重|G1|G2|G3|G4|ΣR|")
    assert "起点側桁|固定死荷重（D1）|1530.00|1340.00|1340.00|1530.00|5740.00|" in table
    assert "付加死荷重（D2）|160.00|100.00|100.00|160.00|520.00|" in table
    assert "雪荷重 S 30年確率|360.00|50.00|50.00|360.00|820.00|" in table
    # the end girder has two bearings: its rows leave G3 and G4 blank
    assert "終点側桁|固定死荷重（D1）|930.00|930.00|||1860.00|" in table
    assert texts["0900/dead.table.title"] == "表 13.1 上部工死荷重反力"


def test_the_three_loadings_print_their_reactions(texts):
    assert texts["0900/train.loading.origin_max.heading"] == "a) B支点最大"
    # the axle at the joint (19.425 from A) counts on the origin girder for the RB maximum (decision 125; the sample's
    # 13-1 a) 18.850 + 16.650 + 13.850 + 11.650 → 517.77): 160 × 62.725 / 18.85 = 532.41
    assert texts["0900/train.loading.origin_max.b"] == (
        "RB=160.00×(19.425 + 17.225 + 14.425 + 12.225 + (-0.575))/18.850=532.41kN")
    assert texts["0900/train.loading.origin_max.a"] == "RA=160.00×5−532.41=267.59kN"
    assert texts["0900/train.loading.origin_max.c"] == "RC=0.00 kN"
    assert texts["0900/train.loading.end_max.c"] == "RC=160.00×(2.425 + 4.625 + 7.425 + 9.625)/9.250=416.86kN"
    assert texts["0900/train.loading.both_max.b"].endswith("/18.850=272.47kN")
    assert texts["0900/train.loading.both_max.c"] == "RC=160.00×(7.425 + 9.625)/9.250=294.92kN"
    assert texts["0900/train.loading.origin_max.figure"]  # the loading figure of 0600


def test_the_shoe_lines_multiply_the_reaction_by_the_share(texts):
    assert texts["0900/shoe.train.origin_max.single.label"] == "・単線"
    assert texts["0900/shoe.train.origin_max.single.origin.1"] == "Ｇ1桁=532.41×0.471=250.77kN"
    assert texts["0900/shoe.train.origin_max.double.origin.1"] == "Ｇ1桁=532.41×0.451=240.12kN"
    assert texts["0900/shoe.train.end_max.double.end.1"] == "Ｇ1桁=416.86×1.000=416.86kN"
    # the impact of 安全性 and of 使用性 (0.75 of it; the sample copied the 安全性 values, ADR-0001)
    assert texts["0900/shoe.impact.ultimate.origin_max.single.origin.1"] == "Ｇ1桁=250.77×0.245=61.44kN"
    assert texts["0900/shoe.impact.service.origin_max.single.origin.1"] == "Ｇ1桁=250.77×0.184=46.14kN"
    assert texts["0900/shoe.seismic.origin.1"] == "Ｇ1桁=320.00×0.471=150.72kN"
    assert texts["0900/shoe.seismic.end.1"] == "Ｇ1桁=160.00×0.857=137.12kN"


def test_the_lateral_torque_of_the_origin_loading(texts):
    assert texts["0900/lateral.origin_max.heading"] == "(a) B支点最大の場合"
    assert texts["0900/lateral.origin_max.origin.force"] == "水平力=HB=0.2×532.41=106.48kN"
    assert texts["0900/lateral.origin_max.origin.height"] == "作用位置=yB=3.850m"
    assert texts["0900/lateral.origin_max.origin.moment"] == "モーメント=MB=106.48×3.850=409.95kN・m"
    assert texts["0900/lateral.origin_max.origin.squares"] == "ΣXi²=3.800^2+1.500^2+1.500^2+3.800^2=33.3800m^2"
    assert texts["0900/lateral.origin_max.origin.vertical.1"] == "Ｇ1桁=409.95×3.800/33.3800=46.67kN"
    assert texts["0900/lateral.origin_max.origin.vertical.2"] == "Ｇ2桁=409.95×1.500/33.3800=18.42kN"
    # the end girder carries no lateral load in the B支点最大 loading: no lines for it
    assert "0900/lateral.origin_max.end.force" not in texts
    # the B+C loading takes 0600's junction loading at both girders
    assert texts["0900/lateral.both_max.origin.note"] == "（0600 の車両横荷重の載荷による）"
    assert texts["0900/lateral.both_max.origin.force"] == "水平力=HB=52.71kN"
    assert texts["0900/lateral.both_max.end.force"] == "水平力=HC=58.98kN"


def test_the_seismic_torques_print_the_response_coefficients(texts):
    assert texts["0900/seismic.kh"] == "最大応答震度=Kh=0.571"
    assert texts["0900/seismic.kh.source"] == f"（線路直角方向 Case{TRANSVERSE[1]} {TRANSVERSE[2]}）"
    assert texts["0900/seismic.origin.force"].startswith("水平力=HB=0.571×")
    assert texts["0900/seismic_train.kh"] == "設計震度=Kh=0.300"
    assert texts["0900/seismic_train.origin.force"] == "水平力=HB=96.00kN"
    assert texts["0900/seismic_train.origin.height"] == "作用位置=yB=5.350m"
    assert texts["0900/seismic_train.origin.moment"] == "モーメント=MB=96.00×5.350=513.60kN・m"
    assert texts["0900/seismic_train.origin.vertical.1"] == "Ｇ1桁=513.60×3.800/33.3800=58.47kN"


def test_the_girder_forces_along_the_track(texts):
    assert texts["0900/girder.rail.safety.origin"] == "起点側=TL1=400.00kN"
    assert texts["0900/girder.rail.service.end"] == "終点側=TL2=160.00kN"
    assert texts["0900/girder.brake.origin"] == "起点側=T=160.00kN"
    assert texts["0900/girder.seismic.kh"] == "最大応答震度=Kh=0.386"
    assert texts["0900/girder.seismic.kh.source"] == "（線路方向 Case1 安全性）"
    assert texts["0900/girder.seismic.origin"] == "起点側=T=0.386×13580.00=5241.88kN"
    assert texts["0900/girder.seismic.end"] == "終点側=T=0.386×4740.00=1829.64kN"
    assert texts["0900/girder.train.kh"] == "設計震度=Kh=0.200"
    assert texts["0900/girder.train.origin"] == "起点側=T=128.00kN"


def test_the_bearing_forces_of_each_case_are_written_as_the_example4_sample(texts):
    """Decision 125, as Example橋脚4 V-13〜V-25 writes them (test_cantilever_bearings has the hand calculations): each
    case with bearing forces under its limit state, its loading and combination, then for each girder T with its terms
    (γB × B + LR factor × LR; Kh × the girder's dead load + the seismic train) and T / n; at the movable origin end each
    bearing on a cantilever (Ｇ1 on the left, Ｇ4 on the right) takes min(Ts, μ・Ni), at the fixed end H = T / n."""
    assert texts["0900/bearing.heading"] == "2) シューに働く水平荷重"
    assert texts["0900/bearing.safety.heading"] == "(a) 安全性（破壊）"
    assert texts["0900/bearing.serviceability_damage.heading"] == "(b) 使用性（損傷）"
    assert texts["0900/bearing.restorability_eq.heading"] == "(c) 復旧性（地震時）"
    assert texts["0900/bearing.9.label"] == "・Case 9　B支点最大"
    assert texts["0900/bearing.9.combination"] == "[1.1D1 + 1.2D2 + 1.35(L+I) + 1.0LR + 1.23B + S10 の組合せ]"
    assert texts["0900/bearing.9.origin.label"] == "＜起点側（可動支承）＞"
    assert texts["0900/bearing.9.origin.applied"] == "T=1.23×160.00+1.0×400.00=596.80kN"
    assert texts["0900/bearing.9.origin.share"] == "Ts=596.80/4=149.20kN"
    assert texts["0900/bearing.9.origin.1.cap"] == "μ・NＧ1=0.10×2616.48=261.65kN"
    assert texts["0900/bearing.9.origin.1.adopted"] == "∴ HＧ1=min(149.20, 261.65)=149.20kN"
    assert texts["0900/bearing.9.origin.4.adopted"] == "∴ HＧ4=min(149.20, 261.65)=149.20kN"  # the right cantilever
    assert texts["0900/bearing.9.end.label"] == "＜終点側（固定支承）＞"
    assert texts["0900/bearing.9.end.applied"] == "T=1.0×200.00=200.00kN"  # ② has no train on the end girder
    assert texts["0900/bearing.9.end.share"] == "H=200.00/2=100.00kN"
    assert "0900/bearing.9.end.1.cap" not in texts
    assert texts["0900/bearing.12.combination"] == "[1.1D1 + 1.2D2 + 1.23L + 1.0LR + 1.35B + S10 の組合せ]"
    assert (texts["0900/bearing.18.label"], texts["0900/bearing.18.combination"]) == (
        "・Case 18", "[1.1D1 + 1.2D2 + 1.0LR + S30 の組合せ]")
    # 使用性（損傷）: the T of 9〜11, the vertical forces with the factors 1.0 (decision 125)
    assert texts["0900/bearing.24.combination"] == "[1.0D1 + 1.0D2 + 1.23(L+I) + 1.0LR + 1.23B + S10 の組合せ]"
    assert texts["0900/bearing.24.origin.applied"] == texts["0900/bearing.9.origin.applied"]
    assert texts["0900/bearing.24.origin.1.cap"] == "μ・NＧ1=0.10×2394.02=239.40kN"
    # the seismic case: the cap governs at the movable end, none at the fixed end
    assert texts["0900/bearing.28.combination"] == "[1.0D1 + 1.0D2 + 1.00L + 1.0EQ + S2 の組合せ]"
    assert texts["0900/bearing.28.origin.applied"] == "T=0.386×13580.00+128.00=5369.88kN"
    assert texts["0900/bearing.28.origin.1.adopted"] == "∴ HＧ1=min(1342.47, 204.07)=204.07kN"
    assert texts["0900/bearing.28.end.share"] == "H=1893.64/2=946.82kN"
    assert not any(".right." in key or ".left." in key for key in texts if key.startswith("0900/bearing."))


def test_the_self_weight_and_the_dead_action_of_the_left_cantilever(texts):
    assert texts["0900/left.weight.heading"] == "(3) 片持梁の自重（左側）"
    weight = texts["0900/left.weight.table"]
    assert "|①|24.5 × 2.700 × 2.000 × 2.250|297.68|1.125|334.89|" in weight
    assert "|②|24.5 × 2.700 × 0.700 × 2.250 × 1/2|52.09|0.750|39.07|" in weight
    assert weight.endswith("|合計|349.77|－|373.96")
    assert texts["0900/left.actions.heading"] == "(4) 荷重設計の集計（左側）"
    assert texts["0900/left.actions.D1.item"] == "1) 固定死荷重D1"
    table = texts["0900/left.actions.D1.table"]
    assert "|片持梁自重||349.77|－|373.96|||0.00|" in table  # no X, no e for the self weight (as the sample)
    assert "|上部工反力|起点側 Ｇ1桁|1530.00|1.550|2371.50||-0.325|-497.25|" in table
    assert "||終点側 Ｇ1桁|930.00|0.700|651.00||0.675|627.75|" in table  # X 0.700, not the sample's typed 0.645
    assert table.endswith("|合計|2809.77|－|3396.46|－|－|130.50")


def test_the_action_tables_are_headed_as_the_sample(texts):
    assert texts["0900/left.actions.S.S2.item"] == "3) 雪荷重S"
    assert texts["0900/left.actions.S.S2.heading"] == "(a) 2年確率"
    assert texts["0900/left.actions.L.ORIGIN_MAX.item"] == "4) 列車荷重L"
    assert texts["0900/left.actions.L.ORIGIN_MAX.heading"] == "(a) B支点最大の場合"
    assert texts["0900/left.actions.L.地震時.heading"] == "(d) 地震時列車荷重"
    assert texts["0900/left.actions.I.ULTIMATE:ORIGIN_MAX.heading"] == "(a) 安全性(破壊)　a) B支点最大の場合"
    assert texts["0900/left.actions.I.SERVICE:BOTH_MAX.heading"] == "(b) 使用性　c) B+C支点最大の場合"
    assert texts["0900/left.actions.LF.END_MAX.heading"] == "(b) C支点最大の場合"
    assert texts["0900/left.actions.W.WITHOUT_TRAIN.heading"] == "(b) 列車荷重がない場合"
    assert texts["0900/left.actions.EQ.線路直角方向.item"] == "8) 地震時直角方向EQ"
    assert texts["0900/left.actions.LRB.9.heading"] == "9) Case 9 1.0 LR + 1.23B B支点最大の支承に働く水平荷重"
    assert texts["0900/left.actions.LRB.9.combination"] == texts["0900/bearing.9.combination"]
    assert texts["0900/left.actions.LRB.24.combination"] == (
        "[1.0D1 + 1.0D2 + 1.23(L+I) + 1.0LR + 1.23B + S10 の組合せ]")  # 使用性（損傷）: D and L by 1.0 (× ρ)
    assert texts["0900/left.actions.LRB.18.heading"] == "18) Case 18 1.0 LRの支承に働く水平荷重"
    assert texts["0900/left.actions.LRB.28.heading"] == "22) Case 28 地震時線路方向"
    bearing = texts["0900/left.actions.LRB.9.table"]
    assert "|Y\n(m)|" in bearing and "|起点側|Ｇ1桁|||0.00|149.20|1.350|201.42|" in bearing
    assert "|終点側|Ｇ1桁|||0.00|100.00|1.350|135.00|" in bearing
    assert bearing.endswith("|合計|－|－|－|249.20|－|336.42")
    assert texts["0900/left.actions.LRB.28.table"].endswith("|合計|－|－|－|1150.89|－|1553.70")


def test_the_combination_tables_of_each_side(texts, manuscript):
    assert texts["0900/left.combinations.heading"] == "13.2 設計作用の組合せ（左側）"
    rotated = [unit for unit in manuscript if unit.kind == "rotated"]
    assert [unit.key for unit in rotated][:9] == [
        f"left.combinations.{quantity}.{first}" for quantity in ("bending", "shear", "torsion")
        for first in (1, 10, 19, 29)][:9]
    assert len(rotated) == 24
    # broken at the limit states: 使用性（損傷） 19〜26 with 復旧性（地震時） 27〜28, 耐久性 29〜32 with 安全性（疲労） 33〜35
    for first, last in ((1, 9), (10, 18), (19, 28), (29, 35)):
        unit = next(unit for unit in rotated if unit.key == f"left.combinations.shear.{first}")
        numbers = [int(row[0].content) for row in unit.value.rows[2:]]
        assert numbers == list(range(first, last + 1))
    torsion = texts["0900/left.combinations.torsion.10"]
    assert torsion.startswith("Case\nNo.|組合せ|Mt\n(kN・m)|性能項目|備考|摘要|D1|D2|S|L|I|LF|W|LR+B|EQ|10|")
    assert "|1.0LR+1.23B\n349.70||1118.50|安全性\n(破壊)|列車最大|C支点最大|" in torsion
    bending = texts["0900/left.combinations.bending.1"]
    assert "|1|1.1\n3736.11|1.2\n406.80|1.0S10\n636.00|1.35\n524.73|1.35\n128.56|1.23\n88.98|1.0\n" in bending
    summary = texts["0900/left.combinations.summary"]
    assert summary.count("|安全性\n(破壊)|") == 18 and summary.count("|耐久性|") == 4 and summary.count("|安全性\n(疲労)|") == 3
    assert summary.count("|使用性\n(損傷)|") == 8 and "|使用性\n(損傷)|風最大||" in summary
    assert "|28|" in summary and "|35|" in summary and "|復旧性\n地震時|〃|線路方向|" in summary
    assert texts["0900/left.combinations.summary.title"] == "設計作用のまとめ"
    # decision 125: the torsion of the bearing forces along the track is added on the side of the rest of the case
    assert texts["0900/left.combinations.torsion_sign"].startswith("線路方向の水平荷重（LR+B，地震時の線路方向 EQ）")
    assert "同じ向き（不利側）に加える．" in texts["0900/right.combinations.torsion_sign"]


def test_the_left_side_comes_before_the_right_and_both_have_their_parts(manuscript):
    keys = [unit.key for unit in manuscript]
    for part in ("weight.heading", "actions.heading", "combinations.heading", "combinations.summary",
                 "combinations.bending.1"):
        assert keys.index(f"left.{part}") < keys.index(f"right.{part}")
    assert keys.index("right.actions.heading") < keys.index("left.combinations.heading")
    assert keys[-1] == "adopted.table" and keys[-2] == "adopted.heading"


def test_the_adopted_table_names_the_governing_case_of_each_check(texts):
    assert texts["0900/adopted.heading"] == "(3) 照査に用いる設計作用"
    table = texts["0900/adopted.table"]
    assert table.startswith("照査|項目|側|Case|Md\n(kN・m)|Vd\n(kN)|Mt\n(kN・m)|耐久性 縁応力度検討用|曲げ|左側|31|")
    assert "|安全性（破壊）|曲げ|左側|3|5942.86|5142.22|621.53|" in table
    assert "||せん断|左側|2|5879.52|5249.37|856.68|" in table
    assert "||ねじり|左側|10|5504.12|4896.01|1118.50|" in table
    assert "|復旧性（損傷）地震時|曲げ|左側|27|" in table and "||ねじり|左側|28|" in table


def test_an_input_without_a_right_cantilever_prints_the_left_side_only():
    pier, reaction, result = result_of(**{"上部工反力/起点側/B支点/3/支承位置": 1.0, "上部工反力/終点側/C支点/1/支承位置": 1.0})
    assert set(result.sides) == {Side.LEFT} and SIDES[Side.LEFT] == "左側"
    texts = records(pier, reaction, result)
    assert "0900/left.weight.heading" in texts and "0900/right.weight.heading" not in texts
    assert not any(key.startswith("0900/right.") for key in texts)
    assert "右側" not in "".join(texts.values())
    assert all(cell == "左側" for cell in texts["0900/adopted.table"].split("|") if cell in ("左側", "右側"))
    build_cantilever(result, reaction, pier)


def test_a_girder_without_a_bearing_on_a_cantilever_has_no_lines_in_the_bearing_forces():
    pier, reaction, result = result_of(**{"上部工反力/終点側/C支点/0/支承位置": -0.5, "上部工反力/終点側/C支点/1/支承位置": 0.5})
    texts = records(pier, reaction, result)
    assert "0900/bearing.9.origin.applied" in texts
    assert not any(key.startswith("0900/bearing.9.end") for key in texts)
    build_cantilever(result, reaction, pier)


def test_without_snow_there_is_no_snow_table_and_the_items_after_it_move_up(tmp_path: Path):
    # Decision 69: every snow load blank makes no 雪荷重S table and no S part in the cases
    keys = ("雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率")
    changes = {f"上部工反力/{side}/{far}/{key}": None for side, far in (("起点側", "A支点"), ("終点側", "D支点"))
               for key in keys}
    changes |= {f"上部工反力/起点側/B支点/{index}/{key}": None for index in range(4) for key in keys}
    changes |= {f"上部工反力/終点側/C支点/{index}/{key}": None for index in range(2) for key in keys}
    pier, reaction, result = result_of(**changes)
    texts = records(pier, reaction, result)
    assert not any(".actions.S." in key for key in texts)
    assert texts["0900/left.actions.L.ORIGIN_MAX.item"] == "3) 列車荷重L"
    assert texts["0900/left.actions.EQ.線路直角方向.item"] == "7) 地震時直角方向EQ"
    assert texts["0900/left.actions.LRB.9.heading"].startswith("8) Case 9 1.0 LR + 1.23B")
    assert texts["0900/left.actions.LRB.28.heading"] == "21) Case 28 地震時線路方向"
    assert "1.0S" not in texts["0900/left.combinations.bending.1"]
    path = render_cantilever(result, reaction, pier, tmp_path / "0900_片持ち梁.pdf")
    assert [check for check in formula_checks(path) if not check.ok] == []


# --- the PDF --------------------------------------------------------------------------------------------------------


def test_every_printed_formula_reproduces_its_result(rendered: Path, manuscript):
    checks = formula_checks(rendered)
    declared = sum(unit.checked for unit in manuscript)
    assert len(checks) == declared > 150
    assert [check for check in checks if not check.ok] == []


def test_the_pdf_has_the_pages_of_the_sample_chapter_and_starts_with_the_chapter_heading(rendered: Path):
    with pymupdf.open(rendered) as pdf:
        assert len(pdf) >= 40
        first = pdf[0].get_text().strip().split("\n")
        assert first[:2] == ["§13. 片持ち梁の照査", "13.1 応答値の算定"]
        texts = [page.get_text() for page in pdf]
    assert any("13.2 設計作用の組合せ（左側）" in text for text in texts)
    assert any("13.2 設計作用の組合せ（右側）" in text for text in texts)
    assert "(3) 照査に用いる設計作用" in texts[-1]
    # the rotated tables: a page whose first line reads "Case" (the header column, now at the left)
    assert sum(text.strip().startswith("Case") for text in texts) >= 18


def test_every_page_stands_on_the_common_grid_and_the_combination_tables_turn_within_the_body(rendered: Path):
    """GridLayoutPdf 0.2.0's common grid (A4, 16.08 x 15.48 pt cells, 30 columns x 47 rows): nothing is drawn outside
    the body; a combination table is turned counterclockwise (its text runs up the page) and fits the body of a page
    of its own; the tables are framed medium and ruled hair."""
    from gridlayoutpdf import A4_PORTRAIT_REFERENCE

    grid = A4_PORTRAIT_REFERENCE.grid
    left, top = grid.origin_x - .5, grid.origin_y - .5
    right, bottom = grid.origin_x + grid.columns * grid.pitch_x + .5, grid.origin_y + grid.rows * grid.pitch_y + .5
    turned = 0
    with pymupdf.open(rendered) as pdf:
        for page in pdf:
            lines = [line for block in page.get_text("dict")["blocks"] for line in block.get("lines", [])]
            assert all(left <= line["bbox"][0] and line["bbox"][2] <= right and top <= line["bbox"][1]
                       and line["bbox"][3] <= bottom for line in lines), page.number + 1
            assert all(left <= drawing["rect"].x0 and drawing["rect"].x1 <= right and top <= drawing["rect"].y0
                       and drawing["rect"].y1 <= bottom for drawing in page.get_drawings()), page.number + 1
            up = [line for line in lines if line["dir"] == (0.0, -1.0)]
            if up:
                turned += 1
                assert len(up) == len(lines), page.number + 1  # nothing else on the page of a turned table
            widths = {round(drawing.get("width") or 0, 2) for drawing in page.get_drawings() if drawing["type"] == "s"}
            assert widths <= {.25, 1.0, .24, .96}, page.number + 1  # the tables' and the loading figures' lines
    assert turned == 2 * 3 * 4  # each side: Md, Vd and Mt of the cases 1〜9, 10〜18, 19〜28 and 29〜35


def test_the_same_input_gives_the_same_bytes(tmp_path: Path, current, rendered: Path):
    pier, reaction, result = current
    again = render_cantilever(result, reaction, pier, tmp_path / "again.pdf")
    assert again.read_bytes() == rendered.read_bytes()

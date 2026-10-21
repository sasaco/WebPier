"""The WDJ of the 0810 / 0820 フーチングの断面照査 (decision 60, ADR-0008): Capacita's section-force input mode (no
pickup), one member フーチング 1000 × H6, two points per direction (La is per point in Capacita: the direction's name
for 安全性・耐久性 with the safety La, "…（地震時）" for 復旧性（地震時） with the seismic La), the lower bars as the
tensile side, the stirrups, the forces of each check by Capacita's case id (Md0 耐久性 応力度 = 短期, Md1 耐久性
永久荷重 = 長期, Md5 安全性 破壊, Md7 復旧性 地震時; Vd5, Vd7 with their Md; N′d 0) and the shear span La in mm. The
document was tried on the real runner (2026-10-19): it returns the five sections in order. Expected values: the hand
calculation footing_hand.json through calc.footing_check; nothing of the WDJ is computed by the code under test."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from footing_wdj_support import footing_check
from webpier.export.capacita.footing_wdj import build_footing_wdj, write_footing_wdj
from webpier.export.capacita.wdj import SCHEMA, VERSION

HAND = json.loads((Path(__file__).parents[1] / "fixtures" / "example2" / "footing_hand.json").read_text(
    encoding="utf-8"))


def document(direction="0800_longitudinal"):
    return build_footing_wdj(footing_check(direction))


def test_the_document_is_an_rc_wdj_in_section_force_mode():
    wdj = document()
    assert (wdj["$schema"], wdj["format"], wdj["schema_version"], wdj["ver"], wdj["lang"]) == (
        SCHEMA, "wdj", VERSION, VERSION, "ja")
    assert (wdj["pickup_filename"], wdj["pickup_data"]) == ("", None)
    assert "steel" not in wdj
    assert wdj["calc"] == {"print_calculate_checked": True, "print_section_force_checked": False,
                           "print_safety_ratio_checked": False, "print_summary_table_checked": False,
                           "calculate_moment_checked": True, "calculate_shear_force": True,
                           "calculate_torsional_moment": False, "member_group_selection": []}


def point(index, name):
    return {"index": index, "m_no": 1, "position": 0, "p_name": name, "p_id": "ITAN", "isMyCalc": False,
            "isVyCalc": True, "isMzCalc": True, "isVzCalc": False, "isMtCalc": False, "axis_type": 2,
            "isUpperCalc": True, "isLowerCalc": True}


def test_the_member_and_the_two_points_are_the_footing_overhang():
    wdj = document()
    assert wdj["members"] == [{"m_no": 1, "m_len": None, "g_no": 1, "g_id": "1", "g_name": "フーチング", "shape": 1,
                               "B": 1000, "H": 2700, "Bt": None, "t": None, "n": 1}]
    assert wdj["points"] == [point(1, "線路方向"), point(2, "線路方向（地震時）")]
    assert [item["p_name"] for item in document("0800_transverse")["points"]] == ["線路直角方向", "線路直角方向（地震時）"]


def test_the_bar_row_has_the_lower_bars_and_the_stirrups_only():
    bar, seismic = document()["bar"]
    assert {key: value for key, value in seismic.items() if key not in ("index", "p_name")} == {
        key: value for key, value in bar.items() if key not in ("index", "p_name")}
    assert (seismic["index"], seismic["p_name"]) == (2, "線路方向（地震時）")
    assert bar["rebar1"] == {"title": "上側", "rebar_dia": None, "rebar_n": None, "rebar_cover": None,
                             "rebar_lines": None, "rebar_space": None, "rebar_ss": None, "cos": None, "enable": True}
    assert bar["rebar2"] == {"title": "下側", "rebar_dia": 25, "rebar_n": 8, "rebar_cover": 100, "rebar_lines": None,
                             "rebar_space": None, "rebar_ss": 125, "cos": None, "enable": True}
    assert bar["sidebar1"] == bar["sidebar2"] == {"side_dia": None, "side_n": None, "side_cover": None,
                                                  "side_ss": None}
    assert bar["stirrup"] == {"stirrup_dia": 16, "stirrup_n": 2, "stirrup_ss": 250}
    assert (bar["index"], bar["m_no"], bar["p_name"], bar["b"], bar["h"], bar["haunch_M"], bar["haunch_V"],
            bar["tan"]) == (1, 1, "線路方向", 1000, 2700, None, None, None)
    assert bar["bend"] == {"bending_dia": None, "bending_n": None, "bending_ss": None, "bending_angle": None}
    across = document("0800_transverse")["bar"][0]["rebar2"]
    assert (across["rebar_dia"], across["rebar_cover"]) == (29, 127)


def test_the_crack_rows_have_the_conditions_without_the_appearance_check():
    assert document()["crack"] == [
        {"index": index, "m_no": 1, "p_name": name, "con_u": 1, "con_l": 1, "con_s": 1, "vis_u": False,
         "vis_l": False, "ecsd_u": 300, "ecsd_l": 300, "kr": 0.5, "k4": 0.85}
        for index, name in ((1, "線路方向"), (2, "線路方向（地震時）"))]


@pytest.mark.parametrize("direction,safety,la,la_eq", [("0800_longitudinal", "safety_shear", 1096, 1942),
                                                       ("0800_transverse", "safety_moment", 1156, 1294)])
def test_the_forces_are_the_hand_calculation_by_capacitas_case_ids(direction, safety, la, la_eq):
    wdj = document(direction)
    columns, seismic = HAND["directions"][direction]["columns"], HAND["directions"][direction]["seismic_own_input"]
    assert wdj["force"] == [
        {"index": 1,
         "Md0_Md": columns["short_term"]["Md_design"], "Md0_Nd": 0,
         "Md1_Md": columns["long_term"]["Md_design"], "Md1_Nd": 0,
         "Md5_Md": columns[safety]["Md_design"], "Md5_Nd": 0,
         "Vd5_Vd": columns[safety]["Vd_design"], "Vd5_Md": columns[safety]["Md_design"], "Vd5_Nd": 0,
         "Md8_Md": columns["long_term"]["Md_design"], "Md8_Nd": 0},
        {"index": 2,
         "Md7_Md": seismic["Md_design"], "Md7_Nd": 0,
         "Vd7_Vd": seismic["Vd_design"], "Vd7_Md": seismic["Md_design"], "Vd7_Nd": 0}]
    name = wdj["points"][0]["p_name"]
    assert wdj["shear"] == [
        {"index": 1, "p_name": name, "m_no": 1, "g_name": "フーチング", "La": la, "fixed_end": False, "L": None},
        {"index": 2, "p_name": f"{name}（地震時）", "m_no": 1, "g_name": "フーチング", "La": la_eq, "fixed_end": False,
         "L": None}]


def test_the_basic_lists_name_capacitas_cases_without_pickup_numbers():
    basic = document()["basic"]
    assert [(item["id"], item["title"], item["no"]) for item in basic["pickup_moment"]] == [
        (0, "耐久性 応力度", None), (1, "耐久性 永久荷重", None), (2, "安全性 疲労限", None), (3, "安全性 永久作用", None),
        (4, "安全性 永久＋変動", None), (5, "安全性 破壊", None), (6, "使用性（損傷）", None), (7, "復旧性 地震時", None),
        (8, "最小鉄筋量", None)]
    assert [(item["id"], item["title"]) for item in basic["pickup_shear_force"]] == [
        (0, "耐久性 ひび割れ判定"), (1, "耐久性 永久荷重"), (2, "耐久性 変動荷重"), (3, "安全性 永久作用"),
        (4, "安全性 永久＋変動"), (5, "安全性 破壊"), (6, "使用性（損傷）"), (7, "復旧性 地震時")]
    assert all(item["no"] is None for item in basic["pickup_shear_force"] + basic["pickup_torsional_moment"])
    assert [(item["id"], item["selected"]) for item in basic["specification2_list"]] == [
        (0, False), (1, False), (2, False), (3, False), (4, True), (8, False)]  # R5_Shinkansen (decision 73)
    assert [(item["id"], item["selected"]) for item in basic["conditions_list"]] == [("JR-001", True),
                                                                                       ("JR-004", False)]


def test_the_safety_tables_are_the_columns_with_the_footing_concrete():
    safety = document()["safety"]
    # The six rows of calc.column_check.SAFETY_FACTORS (the same table as 0611).
    assert [row["id"] for row in safety["safety_factor"]["1"]] == [0, 2, 5, 6, 7, 8]
    assert safety["material_concrete"] == {"1": {"fck": 27, "dmax": 25}}
    assert safety["material_bar"]["1"] == [
        {"separate": 25, "tensionBar": {"fsy": 390, "fsu": 560}, "sidebar": {"fsy": 390, "fsu": 560},
         "stirrup": {"fsy": 390, "fsu": 560}},
        {"separate": 29, "tensionBar": {"fsy": 390, "fsu": 560}, "sidebar": {"fsy": 390, "fsu": 560},
         "stirrup": {"fsy": 390, "fsu": 560}}]
    assert safety["pile_factor"]["1"] == [{"id": "pile-000", "title": "使用しない", "rfck": 1.0, "rfbok": 1.0,
                                           "rEc": 1.0, "rVcd": 1.0, "selected": True}]


def test_the_bytes_are_the_json_webpier_writes():
    wdj = document()
    data = write_footing_wdj(wdj)
    assert json.loads(data.decode("utf-8")) == wdj
    assert not data.startswith(b"\xef\xbb\xbf")
    assert write_footing_wdj(wdj) == data

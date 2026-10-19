"""The WDJ of the 0910 片持ち梁の断面照査 (decision 59, ADR-0008) against the sample 13_片持ち梁照査/WebDan.wdj.

The expected values are the independent transcription tests/fixtures/example2/cantilever.json (its notes list the
deliberate differences: the number shape, the filled force rows, the shear span, one point, no steel rows, ε'csd
300). The document carries its section forces: Capacita calculates it as given (run-rc without --pickup)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.calc.cantilever import Quantity, calculate_cantilever, complete_cantilever
from webpier.calc.cantilever.check import calculate_cantilever_section
from webpier.calc.cantilever.response import MaxResponse, ResponseValue
from webpier.calc.reaction import calculate_reaction
from webpier.core.integrity import dump_json
from webpier.core.printed import Precision
from webpier.export.capacita import build_cantilever_wdj, write_wdj
from webpier.export.capacita.cantilever import MOMENT_ROWS, SHEAR_ROWS, TORSION_ROWS
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
SAMPLE = json.loads((FIXTURES / "example2" / "cantilever.json").read_text(encoding="utf-8"))
KH = Precision(3, "")


def _response(kh: float) -> MaxResponse:
    value = ResponseValue(1, "Case1", "安全性", KH(kh))
    return MaxResponse("x_Aggre-SE.xlsx", (value,), value)


def result_of(**changes):
    """The completed 0900 result for current.json with each 'a/b/0/c' path replaced by its value."""
    data = deepcopy(CURRENT)
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value
    pier = parse_input(data)
    reaction = calculate_reaction(pier)
    basis = calculate_cantilever(pier, reaction)
    return pier, reaction, complete_cantilever(pier, reaction, basis, _response(0.386), _response(0.552))


SAFETY_KEYS = ("id", "M_rc", "M_rs", "M_rbs", "V_rc", "V_rs", "V_rbc", "V_rbs", "V_rbv", "T_rbt", "ri", "range")


@pytest.fixture(scope="module")
def built():
    pier, _, result = result_of()
    section = calculate_cantilever_section(pier, result)
    return result, section, build_cantilever_wdj(section)


def test_it_is_an_rc_document_of_capacita_with_its_own_forces(built):
    _, _, document = built
    assert (document["$schema"], document["format"], document["schema_version"], document["lang"]) == (
        "urn:webdan:wdj:1.0.0", "wdj", "1.0.0", "ja")
    assert document["pickup_filename"] == "" and document["pickup_data"] is None
    assert "steel" not in document
    assert set(document) == {"$schema", "format", "schema_version", "ver", "lang", "pickup_filename", "pickup_data",
                             "basic", "members", "crack", "points", "bar", "shear", "fatigues", "safety", "force",
                             "calc"}


def test_the_member_and_the_point(built):
    _, _, document = built
    expected = SAMPLE["wdj"]
    (member,) = document["members"]
    assert {key: member[key] for key in ("m_no", "g_name", "shape", "B", "H", "n")} == expected["member"]
    assert member["m_len"] is None and member["g_id"] == "1" and member["g_no"] == 1
    assert isinstance(member["B"], int) and isinstance(member["shape"], int)
    (point,) = document["points"]
    assert {key: point[key] for key in expected["point"]} == expected["point"]
    assert (point["index"], point["m_no"], point["position"], point["axis_type"]) == (1, 1, None, 2)
    assert point["isUpperCalc"] and point["isLowerCalc"]
    (shear,) = document["shear"]
    assert (shear["index"], shear["m_no"], shear["p_name"], shear["La"]) == (1, 1, "柱前面", 1550)  # a = 1.55 m, in mm
    assert isinstance(shear["La"], int)  # RcDan reads La in mm (La / d); 1.55 would be a deep beam of 1.55 mm


def test_the_bars(built):
    _, _, document = built
    expected = SAMPLE["wdj"]["bar"]
    (bar,) = document["bar"]
    assert (bar["index"], bar["m_no"], bar["p_name"], bar["b"], bar["h"]) == (1, 1, "柱前面", 2700, 2700)
    upper = bar["rebar1"]
    assert {key: upper[key] for key in ("title", "rebar_dia", "rebar_n", "rebar_cover", "rebar_lines", "rebar_space")} == {
        key: expected["rebar1"][key] for key in ("title", "rebar_dia", "rebar_n", "rebar_cover", "rebar_lines", "rebar_space")}
    assert upper["rebar_ss"] == 145.8  # (2700 − 2 × 184)/16 at 1 decimal; the sample 145.75
    assert upper["enable"] is True and upper["cos"] is None
    lower = bar["rebar2"]
    assert {key: lower[key] for key in expected["rebar2"]} == expected["rebar2"]
    assert lower["rebar_lines"] is None and lower["rebar_space"] is None
    assert bar["sidebar1"] == expected["sidebar1"]
    assert bar["sidebar2"] == {"side_dia": None, "side_n": None, "side_cover": None, "side_ss": None}
    assert bar["stirrup"] == expected["stirrup"]
    assert bar["bend"] == {"bending_dia": None, "bending_n": None, "bending_ss": None, "bending_angle": None}
    assert bar["haunch_M"] is None and bar["haunch_V"] is None and bar["tan"] is None


def test_the_crack_row_has_the_environment_of_each_face(built):
    _, _, document = built
    expected = SAMPLE["wdj"]["crack"]
    (crack,) = document["crack"]
    assert {key: crack[key] for key in ("con_u", "con_l", "con_s", "vis_u", "vis_l", "kr", "k4")} == {
        key: expected[key] for key in ("con_u", "con_l", "con_s", "vis_u", "vis_l", "kr", "k4")}
    assert crack["ecsd_u"] == crack["ecsd_l"] == expected["ecsd_13_55"] == 300 and isinstance(crack["ecsd_u"], int)
    assert (crack["index"], crack["m_no"], crack["p_name"]) == (1, 1, None)


def test_the_fatigue_conditions(built):
    _, _, document = built
    expected = SAMPLE["wdj"]["fatigues"]
    fatigues = document["fatigues"]
    assert (fatigues["train_A_count"], fatigues["train_B_count"], fatigues["service_life"]) == (
        expected["train_A_count"], expected["train_B_count"], expected["service_life"])
    (row,) = fatigues["fatigue_list"]
    assert (row["index"], row["m_no"], row["p_name"]) == (1, None, None)
    for key in ("NA06", "NB06", "NA12", "NB12", "SA", "SB"):
        assert row["M1"][key] == row["V1"][key] == expected[key]
    assert (row["M1"]["A"], row["M1"]["B"], row["M1"]["r1_1"], row["M1"]["r1_3"]) == (1, 1, expected["M1_r1_1"], None)
    assert (row["V1"]["r1_2"], row["V1"]["r1_3"]) == (expected["V1_r1_2"], expected["V1_r1_3"])
    assert set(row["M2"]) == set(row["M1"]) and set(row["M2"].values()) == {None}
    assert set(row["V2"]) == set(row["V1"]) and set(row["V2"].values()) == {None}


def test_the_safety_tables_and_the_standard(built):
    _, _, document = built
    expected = SAMPLE["wdj"]
    rows = document["safety"]["safety_factor"]["1"]
    assert [row["id"] for row in rows] == expected["safety_factor_ids"]
    fatigue = next(row for row in rows if row["id"] == 2)
    assert {key: fatigue[key] for key in SAFETY_KEYS} == expected["fatigue_row"]
    assert all(row["T_rbt"] == 1 for row in rows if row["id"] != 8)
    assert document["safety"]["material_concrete"]["1"] == expected["material_concrete"]
    bars = document["safety"]["material_bar"]["1"]
    assert [row["separate"] for row in bars] == [25, 29]
    assert all(row[kind] == {"fsy": 390, "fsu": 560} for row in bars for kind in ("tensionBar", "sidebar", "stirrup"))
    assert document["safety"]["pile_factor"]["1"][0]["id"] == "pile-000"
    basic = document["basic"]
    assert [item["id"] for item in basic["specification2_list"] if item["selected"]] == [expected["specification2_selected"]]
    assert basic["specification1_list"][0]["selected"] is True
    assert [item["selected"] for item in basic["conditions_list"]] == [True, False]
    assert all(item["no"] is None for key in ("pickup_moment", "pickup_shear_force", "pickup_torsional_moment")
               for item in basic[key])
    assert [item["id"] for item in basic["pickup_moment"]] == list(range(9))
    assert [item["id"] for item in basic["pickup_torsional_moment"]] == [0, 1, 5, 6, 7]
    assert document["calc"] == {"print_calculate_checked": True, "print_section_force_checked": False,
                                "print_safety_ratio_checked": False, "print_summary_table_checked": False,
                                "calculate_moment_checked": True, "calculate_shear_force": True,
                                "calculate_torsional_moment": True, "member_group_selection": []}


def test_the_force_table_holds_the_governing_cases_of_0900(built):
    result, section, document = built
    (force,) = document["force"]
    assert force["index"] == 1
    assert MOMENT_ROWS == tuple(range(9)) and SHEAR_ROWS == tuple(range(8)) and TORSION_ROWS == (0, 1, 5, 6, 7)
    for row in MOMENT_ROWS:
        selected = result.selection(row, Quantity.BENDING)
        if selected is None:
            assert force[f"Md{row}_Md"] is None
        else:
            assert force[f"Md{row}_Md"] == -selected.md.value < 0
        assert force[f"Md{row}_Nd"] is None
    for row in SHEAR_ROWS:
        selected = result.selection(row, Quantity.SHEAR)
        assert force[f"Vd{row}_Vd"] == selected.vd.value > 0
        assert force[f"Vd{row}_Md"] == -selected.md.value and force[f"Vd{row}_Nd"] is None
    for row in TORSION_ROWS:
        selected = result.selection(row, Quantity.TORSION)
        assert force[f"Mt{row}_Mt"] == selected.mt.value > 0
        assert (force[f"Mt{row}_Md"], force[f"Mt{row}_Vd"], force[f"Mt{row}_Nd"]) == (-selected.md.value,
                                                                                      selected.vd.value, None)
    expected = SAMPLE["wdj_forces"]
    assert [row for row in MOMENT_ROWS if force[f"Md{row}_Md"] is not None] == expected["filled_moment_rows"]
    assert [row for row in MOMENT_ROWS if force[f"Md{row}_Md"] is None] == expected["blank_moment_rows"]
    assert all(force[f"Vd{row}_Vd"] is not None for row in SHEAR_ROWS)  # Vd6 too (the sample leaves it blank)
    assert all(force[f"Mt{row}_Mt"] is not None for row in TORSION_ROWS)
    # the shear row of a limit state carries its own case's Md: the sample's Vd5 (5096.14) has Md −5576.6, not −5654.81
    assert force["Vd5_Md"] != force["Md5_Md"] and force["Mt5_Md"] != force["Md5_Md"]
    assert force["Vd1_Md"] == force["Md1_Md"] == force["Md3_Md"]  # 永久作用: one case
    assert force["Vd2_Vd"] == force["Vd2_Vd"] and force["Vd2_Vd"] < force["Vd0_Vd"]  # the variable part alone


def test_the_appearance_check_asks_for_both_faces(built):
    pier, _, result = result_of(**{"片持ち梁の照査/外観の照査": "行う"})
    document = build_cantilever_wdj(calculate_cantilever_section(pier, result))
    assert document["crack"][0]["vis_u"] is True and document["crack"][0]["vis_l"] is True


def test_without_side_bars_the_sidebar_row_is_blank_and_the_strengths_are_the_main_bars(built):
    pier, _, result = result_of(**{"鉄筋/梁/side_rows": []})
    document = build_cantilever_wdj(calculate_cantilever_section(pier, result))
    assert document["bar"][0]["sidebar1"] == {"side_dia": None, "side_n": None, "side_cover": None, "side_ss": None}
    assert document["safety"]["material_bar"]["1"][0]["sidebar"] == {"fsy": 390, "fsu": 560}


def test_the_bytes_are_utf8_json_without_a_bom(built):
    _, _, document = built
    data = write_wdj(document)
    assert data == dump_json(document) and not data.startswith(b"\xef\xbb\xbf")
    assert json.loads(data.decode("utf-8")) == document

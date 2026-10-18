"""The WDJ of the 0611 柱の断面照査 (decision 48, ADR-0008) against the sample 08_線路/WebDan.wdj.

The expected values are the independent transcription tests/fixtures/example2/column_section_check.json (its notes
list the deliberate differences: the number shape, the column bottom only, 復旧性のせん断, the section force list,
no bar position, no steel rows). The document carries no pickup data: Capacita imports the PIK (run-rc --pickup).
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.calc.column_check import calculate_column_check
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.core.integrity import dump_json
from webpier.export.capacita import build_wdj, point_index, write_wdj
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
SAMPLE = json.loads((FIXTURES / "example2" / "column_section_check.json").read_text(encoding="utf-8"))
SAFETY_KEYS = ("id", "M_rc", "M_rs", "M_rbs", "V_rc", "V_rs", "V_rbc", "V_rbs", "V_rbv", "T_rbt", "ri", "range")


def wdj(**conditions):
    data = deepcopy(CURRENT)
    data["柱の断面照査"] |= conditions
    pier = parse_input(data)
    reaction = calculate_reaction(pier)
    longitudinal = calculate_longitudinal(pier, calculate_foundation(pier), reaction)
    return build_wdj(calculate_column_check(pier, longitudinal))


@pytest.fixture(scope="module")
def document():
    return wdj()


def test_it_is_an_rc_document_of_capacita_without_pickup_data(document):
    assert (document["$schema"], document["format"], document["lang"]) == ("urn:webdan:wdj:1.0.0", "wdj", "ja")
    assert (document["pickup_filename"], document["pickup_data"]) == ("", None)
    assert "steel" not in document and document["force"] == [] and document["shear"] == []


def test_the_column_member_and_the_point_of_its_bottom(document):
    sample, point = SAMPLE["member"], SAMPLE["check_point"]
    (member,) = document["members"]
    assert {key: member[key] for key in ("m_no", "g_name", "shape", "B", "H", "n")} == {
        "m_no": sample["m_no"], "g_name": sample["g_name"], "shape": sample["shape"], "B": sample["B"],
        "H": sample["H"], "n": sample["n"]}
    assert member["m_len"] == point["member_length_m"]
    (written,) = document["points"]
    assert {key: written[key] for key in ("index", "m_no", "p_id", "position", "isMzCalc", "isVyCalc", "isMyCalc",
                                          "isVzCalc", "isMtCalc")} == {
        "index": point["index"], "m_no": point["member"], "p_id": point["p_id"], "position": point["position_m"],
        **{key: point[key] for key in ("isMzCalc", "isVyCalc", "isMyCalc", "isVzCalc", "isMtCalc")}}


def test_the_point_is_the_j_end_in_the_pik_of_fempython():
    assert [point_index(member) for member in (1, 2, 3)] == [2, 4, 6]


def test_the_bars(document):
    (bar,) = document["bar"]
    assert (bar["index"], bar["m_no"], bar["b"], bar["h"]) == (6, 3, 4500, 2700)
    for key, expected in SAMPLE["bar"].items():
        assert {name: bar[key][name] for name in expected} == expected, key
    assert (bar["rebar1"]["rebar_lines"], bar["rebar1"]["rebar_space"]) == (None, None)
    assert "position" not in bar


def test_the_extraction_cases(document):
    basic = document["basic"]
    for name in ("moment", "shear_force", "torsional_moment"):
        assert {row["id"]: row["no"] for row in basic[f"pickup_{name}"]} == {
            int(key): value for key, value in SAMPLE["pickup"][name].items()}, name


def test_the_standard_and_its_conditions(document):
    basic, standard = document["basic"], SAMPLE["standard"]
    assert [row["id"] for row in basic["specification1_list"] if row["selected"]] == [standard["specification1"]]
    assert [row["id"] for row in basic["specification2_list"] if row["selected"]] == [standard["specification2"]]
    assert {row["id"]: row["selected"] for row in basic["conditions_list"]} == standard["conditions"]


@pytest.mark.parametrize("body,selected", [("JR各社", 0), ("運輸機構", 1), ("JR東日本", 2)])
def test_the_body_selects_the_h16_base_of_its_standard(body, selected):
    rows = wdj(適用基準の機関=body)["basic"]["specification2_list"]
    assert [row["id"] for row in rows if row["selected"]] == [selected]


def test_the_safety_tables(document):
    safety = document["safety"]
    assert [{key: row[key] for key in SAFETY_KEYS} for row in safety["safety_factor"]["1"]] == [
        {key: row[key] for key in SAFETY_KEYS} for row in SAMPLE["safety_factor"]]
    steel = SAMPLE["material_bar"]
    for row in safety["material_bar"]["1"]:
        assert {key: row[key] for key in ("tensionBar", "sidebar", "stirrup")} == {
            key: steel[key] for key in ("tensionBar", "sidebar", "stirrup")}
    assert [row["separate"] for row in safety["material_bar"]["1"]] == [25, 29]
    assert safety["material_concrete"]["1"] == SAMPLE["material_concrete"]
    assert [row["id"] for row in safety["pile_factor"]["1"] if row["selected"]] == [SAMPLE["pile_factor_selected"]]


def test_the_crack_conditions(document):
    (crack,) = document["crack"]
    assert (crack["index"], crack["m_no"]) == (6, 3)
    assert {key: crack[key] for key in SAMPLE["crack"]} == SAMPLE["crack"]


def test_the_appearance_and_the_environment_are_the_input():
    (crack,) = wdj(外観の照査="行わない", 鋼材の腐食に対する環境条件="特に厳しい腐食性環境")["crack"]
    assert (crack["vis_u"], crack["vis_l"], crack["con_u"], crack["con_l"], crack["con_s"]) == (False, False, 3, 3, 3)


def test_the_calculation_and_print_switches(document):
    assert {key: document["calc"][key] for key in SAMPLE["calc"]} == SAMPLE["calc"]
    assert document["calc"]["print_safety_ratio_checked"] is False


def test_the_bytes_are_utf8_json_written_once(document):
    data = write_wdj(document)
    assert data == dump_json(document) and json.loads(data.decode("utf-8")) == document
    assert write_wdj(wdj()) == data


def test_whole_numbers_are_written_as_integers(document):
    """RcDan reads b, h, the bar sizes, ε'csd and the environment as int (Newtonsoft refuses "300.0" there)."""
    text = write_wdj(document).decode("utf-8")
    for written in ('"b": 4500,', '"h": 2700\n', '"stirrup_dia": 22,', '"ecsd_u": 300,', '"ecsd_l": 300,',
                    '"rebar_dia": 32,', '"con_u": 1,', '"B": 4500,'):
        assert written in text, written
    assert '"position": 4.9,' in text and '"kr": 0.5,' in text


def test_multi_layer_main_bars_and_no_side_bars():
    data = deepcopy(CURRENT)
    rows = data["鉄筋"]["柱"]["main_rows"]
    rows[1:] = [deepcopy(rows[0]) | {"layer": 2, "cover_mode": "自動", "center_mm": None, "clear_gap_mm": 50}]
    pier = parse_input(data)
    reaction = calculate_reaction(pier)
    check = calculate_column_check(pier, calculate_longitudinal(pier, calculate_foundation(pier), reaction))
    (bar,) = build_wdj(check)["bar"]
    assert (bar["rebar1"]["rebar_n"], bar["rebar1"]["rebar_lines"], bar["rebar1"]["rebar_space"]) == (58, 29, 82)
    assert set(bar["sidebar1"].values()) == {None}
    assert build_wdj(check)["safety"]["material_bar"]["1"][0]["sidebar"] == {"fsy": 390, "fsu": 560}

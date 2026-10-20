"""The WDJ of the 0611 / 0621 柱の断面照査 (decision 48, ADR-0008) against the samples 08_線路/WebDan.wdj and
09_直角/WebDan.wdj.

The expected values are the independent transcriptions tests/fixtures/example2/column_section_check.json and
column_section_check_09.json (their notes list the deliberate differences: the number shape, the column bottom only,
復旧性のせん断, the section force list, no bar position, no steel rows, the point in the PIK across the track). The
document carries no pickup data: Capacita imports the PIK (run-rc --pickup); the place of the check point among the
PIK's points is found in the PIK (point_index, tested here on PIK text written for the test).
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.calc.column_check import LONGITUDINAL, TRANSVERSE, calculate_column_check
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.core.integrity import dump_json
from webpier.export.capacita import PickupError, build_wdj, point_index, write_wdj
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
SAMPLE = json.loads((FIXTURES / "example2" / "column_section_check.json").read_text(encoding="utf-8"))
SAMPLE_09 = json.loads((FIXTURES / "example2" / "column_section_check_09.json").read_text(encoding="utf-8"))
SAFETY_KEYS = ("id", "M_rc", "M_rs", "M_rbs", "V_rc", "V_rs", "V_rbc", "V_rbs", "V_rbv", "T_rbt", "ri", "range")
ALONG = [(1, "ITAN", 0), (1, "JTAN", 2), (2, "ITAN", 0), (2, "JTAN", 0.7), (3, "ITAN", 0), (3, "JTAN", 4.9),
         (4, "ITAN", 0), (4, "JTAN", 1.35)]
ACROSS = [*ALONG[:5], (3, "1", 2.9), *ALONG[5:]]  # the wind load on member 3 ends inside it (0620)


def pik(*points, cases=("1",), forces=("M", "S", "N")):
    """A FEMPython PIK of (member, point, position) rows for each pickup and force, in its fixed columns."""
    lines = ["PickUpNo,着目力,部材No,最大CaseNo,最小CaseNo,着目点,着目点距離,最大Md,最大Vd,最大Nd,最小Md,最小Vd,最小Nd"]
    for case in cases:
        for force in forces:
            lines += [f"{case:>5}{force:>5}{member:>5}{'3':>5}{'3':>5}{point:>5}{position:>10.3f}" + f"{0:>10.2f}" * 6
                      for member, point, position in points]
    return ("\n".join(lines) + "\n").encode("utf-8")


def wdj(**conditions):
    data = deepcopy(CURRENT)
    data["柱の断面照査"] |= conditions
    pier = parse_input(data)
    reaction = calculate_reaction(pier)
    longitudinal = calculate_longitudinal(pier, calculate_foundation(pier), reaction)
    return build_wdj(calculate_column_check(pier, longitudinal, LONGITUDINAL), point_index(pik(*ALONG), 3))


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


def test_the_point_is_the_place_of_the_j_end_among_the_points_of_the_pik():
    """Capacita numbers the points of the first pickup and force from 1 (PickupImporter), so a point FEMPython adds
    inside a member moves the J end: 6 along the track (the sample 08), 7 across it (09 notes)."""
    assert point_index(pik(*ALONG), 3) == SAMPLE["check_point"]["index"]
    assert point_index(pik(*ACROSS, cases=("1", "2")), 3) == SAMPLE_09["check_point"]["index"]
    assert [point_index(pik(*ALONG), member) for member in (1, 2, 4)] == [2, 4, 8]
    assert point_index(b"\xef\xbb\xbf" + pik(*ALONG).replace(b"\n", b"\r\n"), 3) == 6


@pytest.mark.parametrize("content,member,message", [
    (pik(*ALONG), 5, "部材5のJTANがちょうど1つありません（0個）"),
    (pik(*ALONG[:6], *ALONG[4:6]), 3, "部材3のJTANがちょうど1つありません（2個）"),
    (b"PickUpNo\n\n", 3, "PIK に着目点の行がありません"),
    (b"PickUpNo\n\xff\xfe", 3, "PIK を UTF-8 として読めません"),
])
def test_a_pik_without_the_point_is_refused(content, member, message):
    with pytest.raises(PickupError, match=message):
        point_index(content, member)


def test_across_the_track_the_turned_section_its_bars_and_the_point_of_the_pik():
    pier = parse_input(deepcopy(CURRENT))
    transverse = calculate_transverse(pier, calculate_foundation(pier), calculate_reaction(pier))
    document = build_wdj(calculate_column_check(pier, transverse, TRANSVERSE), point_index(pik(*ACROSS), 3))
    sample, point = SAMPLE_09["member"], SAMPLE_09["check_point"]
    (member,) = document["members"]
    assert {key: member[key] for key in sample} == sample
    ((written,), (bar,), (crack,)) = document["points"], document["bar"], document["crack"]
    assert (written["index"], written["m_no"], written["p_id"], written["position"]) == (
        point["index"], point["member"], point["p_id"], point["position_m"])
    assert (bar["index"], crack["index"], bar["b"], bar["h"]) == (point["index"], point["index"], sample["B"],
                                                                  sample["H"])
    for key, expected in SAMPLE_09["bar"].items():
        assert {name: bar[key][name] for name in expected} == expected, key
    assert {key: document[key] for key in ("basic", "safety", "calc")} == {key: wdj()[key] for key in
                                                                            ("basic", "safety", "calc")}


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
    bars = data["鉄筋"]["柱"]["main_bars"]
    bars["線路"]["inner_layers"] = [{"per_face_count": 29, "clear_gap_mm": 50}]  # 108 + 32 + 50 = 190: spacing 82
    bars["直角"]["per_face_count"] = 0  # no side bars
    pier = parse_input(data)
    reaction = calculate_reaction(pier)
    check = calculate_column_check(pier, calculate_longitudinal(pier, calculate_foundation(pier), reaction),
                                   LONGITUDINAL)
    (bar,) = build_wdj(check, 6)["bar"]
    assert (bar["rebar1"]["rebar_n"], bar["rebar1"]["rebar_lines"], bar["rebar1"]["rebar_space"]) == (58, 29, 82)
    assert set(bar["sidebar1"].values()) == {None}
    assert build_wdj(check, 6)["safety"]["material_bar"]["1"][0]["sidebar"] == {"fsy": 390, "fsu": 560}

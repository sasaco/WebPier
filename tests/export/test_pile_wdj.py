"""The WDJ of the 0612 / 0622 pile body of a cast-in-place pile (decision 91, ADR-0008): Capacita's section force input mode, one
circular group, one member for each pile row with ``n`` its piles, one point for each case with the bundled forces. The document
was tried on the real runner (2026-10-24): it returns bending_safety_destruction (1 page) and shear_safety_destruction (2 pages),
with N'd positive in compression and per-pile forces on the pages. Expected values are written out from the input, not computed."""

import json

from pile_cast_support import COMPRESSED, LINES, cast_input, cast_result
from webpier.calc.pile_cast import pile_factor, section, select
from webpier.export.capacita.pile_wdj import build_pile_wdj, name, write_pile_wdj
from webpier.export.capacita.wdj import SCHEMA, VERSION


def document(lines=LINES, **changes):
    found = section(cast_input(**changes))
    rows = [select(1, 7, 3, lines), select(2, 8, 2, lines)]
    return build_pile_wdj(found, pile_factor(found), rows)


def test_the_document_is_an_rc_wdj_in_section_force_mode():
    wdj = document()
    assert (wdj["$schema"], wdj["format"], wdj["schema_version"], wdj["ver"], wdj["lang"]) == (
        SCHEMA, "wdj", VERSION, VERSION, "ja")
    assert (wdj["pickup_filename"], wdj["pickup_data"], wdj["crack"], wdj["shear"], "steel" in wdj) == ("", None, [], [], False)
    assert wdj["calc"]["print_section_force_checked"] is False and wdj["calc"]["calculate_torsional_moment"] is False
    assert [item["title"] for item in wdj["basic"]["specification2_list"] if item["selected"]] == ["R5_Rail"]
    assert [item["selected"] for item in wdj["basic"]["conditions_list"]] == [False, False]


def test_a_member_is_a_circle_of_the_pile_diameter_for_each_row_with_its_piles():
    members = document()["members"]
    assert [(member["m_no"], member["shape"], member["B"], member["H"], member["n"], member["c_type"]) for member in members] == [
        (1, 3, 1000, None, 3, 1), (2, 3, 1000, None, 2, 1)]
    assert {member["g_id"] for member in members} == {"1"} and {member["g_name"] for member in members} == {"場所打ち杭"}


def test_a_point_is_a_case_of_a_row_with_both_sides_calculated():
    wdj = document()
    points = wdj["points"]
    assert [point["index"] for point in points] == list(range(1, 9))  # 4 cases in each of the 2 rows
    assert [(point["m_no"], point["p_name"]) for point in points[:4]] == [
        (1, "杭列1 曲げ最大"), (1, "杭列1 せん断最大"), (1, "杭列1 圧縮最大"), (1, "杭列1 引張最大")]
    assert all(point["isUpperCalc"] and point["isLowerCalc"] and point["isMzCalc"] and point["isVyCalc"] for point in points)
    assert not any(point["isMyCalc"] or point["isVzCalc"] or point["isMtCalc"] for point in points)
    assert [point["position"] for point in points[:4]] == [3.0, 3.0, 19.0, 19.0]
    row = select(1, 7, 3, LINES)
    assert name(row, row.cases[0]) == "杭列1 曲げ最大"


def test_a_row_with_no_tension_has_a_point_less():
    assert len(document(COMPRESSED)["points"]) == 6


def test_the_bars_are_the_first_face_only_all_round_the_pile_at_the_centre_cover():
    bar = document()["bar"][0]
    assert bar["rebar1"] == {"title": "全周", "rebar_dia": 32, "rebar_n": 20, "rebar_cover": 132, "rebar_lines": None,
                             "rebar_space": None, "rebar_ss": None, "cos": None, "enable": True}
    assert all(value is None for key, value in bar["rebar2"].items() if key not in ("title", "enable"))
    assert bar["stirrup"] == {"stirrup_dia": 16, "stirrup_n": 2, "stirrup_ss": 200}  # a hoop crosses the section twice
    assert (bar["b"], bar["h"]) == (1000, 1000) and all(value is None for value in bar["sidebar1"].values())


def test_the_forces_are_the_bundled_members_per_pile_values_times_the_piles():
    force = document()["force"]
    # row 1 (3 piles), the case of the largest moment: 500.0, 1000.0 and 66.7 per pile; row 2 (2 piles) divides the same forces by 2
    assert force[0] == {"index": 1, "Md5_Md": 1500, "Md5_Nd": 3000, "Vd5_Vd": 200.1, "Vd5_Md": 1500, "Vd5_Nd": 3000}
    assert force[3]["Md5_Nd"] == -600.0 and force[3]["Vd5_Vd"] == 20.1  # the tension case: negative (compression is positive)
    # row 2 has the same bundled forces over two piles: 750.0 and 1500.0 per pile, given back × 2
    assert force[4]["Md5_Md"] == 1500 and force[4]["Md5_Nd"] == 3000


def test_the_safety_factors_are_the_columns_r5_rows_and_the_pile_factors_select_the_condition():
    safety = document()["safety"]
    destruction = next(row for row in safety["safety_factor"]["1"] if row["id"] == 5)
    assert (destruction["M_rc"], destruction["M_rbs"], destruction["V_rbc"], destruction["V_rbs"], destruction["ri"]) == (
        1.3, 1.1, 1.3, 1.1, 1.2)
    assert safety["material_concrete"]["1"] == {"fck": 18.8, "dmax": 25.0}
    assert [(row["id"], row["selected"]) for row in safety["pile_factor"]["1"]] == [
        ("pile-000", False), ("pile-001", True), ("pile-002", False), ("pile-003", False), ("pile-004", False)]
    assert safety["material_bar"]["1"][0]["tensionBar"] == {"fsy": 345, "fsu": 490}
    assert safety["material_bar"]["1"][0]["stirrup"] == {"fsy": 345, "fsu": 490}
    fluid = document(施工条件="安定液使用")["safety"]["pile_factor"]["1"]
    assert [row["id"] for row in fluid if row["selected"]] == ["pile-003"]


def test_the_bytes_are_utf8_json_and_the_same_every_time():
    first = write_pile_wdj(document())
    assert json.loads(first.decode("utf-8")) == document() and first == write_pile_wdj(document())
    assert cast_result().wdj_sha256 == "ab" * 32  # the pipeline records the SHA-256 of these bytes

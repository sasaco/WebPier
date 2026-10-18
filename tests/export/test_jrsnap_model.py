"""The NDU model of both directions: Example2 NDU values where WebPier has the same input, calc values otherwise.

The Example2 NDU files were saved by JRSNAP from the Example2 analysis (10 / 11). WebPier's current input is the
Example2 pier, so the frame, the section and its reinforcement, the springs, the analysis settings and most loads
are those of the files. Documented differences:

- Df / γ2 are derived from the input (calc.embedment: 4.700 m, 12.3 kN/m3); Example2 entered 3.78 / 11.6.
- The overburden of D2 acts at the footing centroid in 0610 / 0620 (Example2 NDU: footing top, node 5).
- 0720 EQ1 is the 0600 transverse girder inertia, H 9090 / M 27103.86 (Example2 NDU 9080 / 27105).
- 0720 has both tracks as cases 5 (up, M +1028.62 as Example2) and 6 (down) and a combination for each
  (decision 21); the Example2 file has the up track only.
- Positions are printed values: the Example2 node x of −2.980232E-07 (Single noise) is 0, the footing centroid 1.35.
- The origin is the footing top in both directions (Example2 transverse: the footing base); y differs by 2.7.
"""

import re
from copy import deepcopy
from dataclasses import replace

import pytest

from jrsnap_support import D, PEDESTAL, PROFILES, ROW0, ROW1, document, example2, model, results
from webpier.calc.column_rebar import column_layout
from webpier.calc.seismic_longitudinal import MemberLoad
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.export.jrsnap import LONGITUDINAL, build_ndu, validate_ndu, write_ndu
from webpier.inputs import parse_input


def values(fields):
    return [D(field) for field in fields]


@pytest.fixture(scope="module")
def longitudinal():
    return model("longitudinal")


@pytest.fixture(scope="module")
def transverse():
    return model("transverse")


@pytest.mark.parametrize("direction,shift", [("longitudinal", 0), ("transverse", D("2.7"))])
def test_joints_are_those_of_example2(direction, shift):
    built, sample = model(direction), example2(direction)
    assert len(built.joints) == int(sample["JointNum"][0])
    for joint in built.joints:
        x, y, number = sample[f"JointXY{joint.number}"]
        assert (D(joint.x), D(joint.y), joint.number) == (D(round(float(x), 6)), D(y) + shift, int(number))


def test_longitudinal_frame(longitudinal):
    assert (longitudinal.origin, longitudinal.control) == (5, 1)  # Example2 JointOrg 5, DataInfo control 1
    assert [(e.i, e.j, e.length.value, e.nonlinear) for e in longitudinal.elements] == [
        (1, 2, 2.0, False), (2, 3, 0.7, False), (3, 4, 4.89, False), (4, 5, 0.01, True), (5, 6, 1.35, False),
        (6, 7, 1.35, False)]  # Example2 ElementInfo / MemberDvid
    assert [e.title for e in longitudinal.elements] == ["はり", "ハンチ", "柱", "柱下端", "フーチング上", "フーチング下"]


def test_transverse_frame(transverse):
    sample = example2("transverse")
    assert transverse.control == 1 and transverse.origin == 6
    assert [(e.i, e.j, e.nonlinear) for e in transverse.elements] == [
        (int(sample[f"ElementInfo{n}"][4]), int(sample[f"ElementInfo{n}"][5]), sample[f"ElementInfo{n}"][0] == "2")
        for n in range(1, 8)]
    assert transverse.elements[0].title == "桁" and transverse.elements[0].length.value == 2.75


@pytest.mark.parametrize("direction", ["longitudinal", "transverse"])
def test_section_is_that_of_example2(direction):
    section, sample = model(direction).section, example2(direction)
    info = sample["SectInfo1"]
    assert (D(section.width), D(section.height), D(section.shear_span)) == (D(info[4]), D(info[5]), D(info[9]))
    fck, _, ec, _, dmax = sample["SectConc1"]
    assert (D(section.fck), D(section.ec), D(section.aggregate_max)) == (D(fck), D(ec), D(dmax))
    rows, layers = int(sample["SectJikuNum1"][0]), int(sample["SectJikuNum1"][1])
    assert len(section.rows) == rows and section.main_layers == layers
    fyk, es, _, _, pitch = sample["SectJiku1"][:5]
    assert (D(section.yield_strength), D(section.main_pitch)) == (D(fyk), D(pitch))
    for index, row in enumerate(section.rows, 1):
        assert (D(row.center), D(row.diameter), row.count) == tuple(
            [*values(sample[f"SectRein1-{index}"][:2]), int(sample[f"SectRein1-{index}"][2])])
    shear = section.shear
    assert (D(shear.yield_strength), D(shear.diameter), shear.legs, D(shear.pitch)) == tuple(
        [*values(sample["SectSher1"][:2]), int(sample["SectSher1"][2]), D(sample["SectSher1"][3])])
    # 5.1 SectSafe has 11 factors; 5.2 adds GBVO = 1.3.
    assert [D(value) for value in section.safety] == values(sample["SectSafe1"]) + [D("1.3")]


@pytest.mark.parametrize("direction", ["longitudinal", "transverse"])
def test_springs_and_footing(direction):
    built, sample = model(direction), example2(direction)
    node = int(sample["SuppotInfo1"][1])  # the footing base: 7 / 8
    assert [(s.direction, D(s.stiffness)) for s in built.springs] == [
        (1, D(sample["SuppotInfo1"][3])), (2, D(sample["SuppotInfo2"][3]))]
    assert {s.node for s in built.springs} == {built.footing.node} == {node}
    foot = built.footing
    info = sample["FootInfo1"]
    assert (D(foot.b), D(foot.l), D(foot.kv), D(foot.gamma1), D(foot.phi)) == (
        D(info[3]), D(info[4]), D(info[5]), D(info[8]), D(info[10]))
    assert (foot.depth, foot.gamma2) == (Printed(4.7, 3, "m"), Printed(12.3, 1, "kN/m3"))  # Example2 3.78 / 11.6


def test_longitudinal_loads(longitudinal):
    sample = example2("longitudinal")
    assert [(c.number, c.title, c.increment) for c in longitudinal.cases] == [
        (n, sample[f"LoadTitle{n}"][0], int(sample[f"JLoadInfo{j}"][3]))
        for n, j in zip(range(1, 9), (1, 3, 5, 6, 7, 8, 9, 10))]
    joints = [[(load.node, D(load.h), D(load.n), D(load.m), load.label) for load in case.joint_loads]
              for case in longitudinal.cases]
    assert joints == [
        [(1, 0, D("8299.53"), D(-610), "上部工反力"), (6, 0, D("4167.45"), 0, "フーチング自重")],
        [(1, 0, 780, D("6.5"), "上部工反力"), (6, 0, D("1830.6"), 0, "上載土")],
        [(6, 0, -1701, 0, "浮力")],
        [(1, 0, 710, D("19.25"), "雪荷重")],
        [(1, 0, 480, 4, "列車荷重")],
        [(1, -11530, 0, 0, "上部工慣性力")],
        [(1, -128, 0, 0, "列車慣性力")],
        [(6, D("-1105.65"), 0, 0, "フーチング慣性力")]]
    members = [[(load.element, load.kind, load.start.value, None if load.end is None else load.end.value, load.label)
                for load in case.member_loads] for case in longitudinal.cases]
    assert members[0] == [(n, 4, 297.68, None, "柱自重") for n in (1, 2, 3, 4)]  # Example2 MLoadInfo1
    # ← inertia is +local y of a top-to-bottom element (Example2 MLoadInfo2-4: 595.35 / 297.68).
    assert members[7] == [(1, 1, 595.35, 595.35, "自重慣性力"), (2, 1, 595.35, 297.68, "自重慣性力"),
                          (3, 1, 297.68, 297.68, "自重慣性力"), (4, 1, 297.68, 297.68, "自重慣性力")]
    assert all(not case for case in members[1:7])
    combination, = longitudinal.combinations
    assert (combination.rho_m.value, combination.alpha_f.value, combination.coefficients) == (1.0, 1.0, (1,) * 8)


def test_transverse_loads(transverse):
    assert [(c.number, c.increment) for c in transverse.cases] == [
        (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), (7, 1), (8, 4), (9, 1)]
    assert [c.title for c in transverse.cases][4:6] == ["列車荷重（地震時・上り線）", "列車荷重（地震時・下り線）"]
    joints = [[(load.node, D(load.h), D(load.n), D(load.m)) for load in case.joint_loads] for case in transverse.cases]
    assert joints[3] == [(2, 0, 710, 0)]
    assert joints[4] == [(2, 0, 480, D("1028.62"))] and joints[5] == [(2, 0, 480, D("-1028.62"))]
    assert joints[6] == [(2, 9090, 0, D("27103.86"))] and joints[7] == [(2, 144, 0, D("770.4"))]
    assert joints[8] == [(7, D("1105.65"), 0, 0)]
    # → inertia is −local y (Example2 MLoadInfo2-4: −595.35 / −297.68).
    assert [(m.element, m.start.value, m.end.value) for m in transverse.cases[8].member_loads] == [
        (2, -595.35, -595.35), (3, -595.35, -297.68), (4, -297.68, -297.68), (5, -297.68, -297.68)]
    up, down = transverse.combinations
    assert up.coefficients == (1, 1, 1, 1, 1, 0, 1, 1, 1) and down.coefficients == (1, 1, 1, 1, 0, 1, 1, 1, 1)


def test_the_conditions_are_the_input_of_the_direction():
    built = model("transverse", **{"jrsnap_transverse/shear_factor_vcd": 1.3, "jrsnap_longitudinal/shear_factor_vcd": 9})
    assert built.section.safety[6].value == 1.3
    assert model("longitudinal", **{"jrsnap_longitudinal/aggregate_max_mm": 40}).section.aggregate_max.value == 40


@pytest.mark.parametrize("direction,steps,limited,target", [
    ("longitudinal", 300, 200, -0.3), ("transverse", 350, 300, 0.35)])  # Example2 NDU DataInfo 3, 6, 19
def test_the_analysis_settings_are_the_input(direction, steps, limited, target):
    analysis = model(direction).analysis
    assert (analysis.steps, analysis.limited_final_step, analysis.target) == (steps, limited, Printed(target, 3, "m"))
    changed = model(direction, **{f"jrsnap_{direction}/analysis_steps": 500,
                                  f"jrsnap_{direction}/limited_final_step": 120,
                                  f"jrsnap_{direction}/target_displacement_m": abs(target) * 2}).analysis
    assert (changed.steps, changed.limited_final_step, changed.target.value) == (500, 120, target * 2)


@pytest.mark.parametrize("direction,signed", [("longitudinal", -0.3), ("transverse", 0.3)])
def test_the_target_displacement_takes_the_sign_of_the_earthquake(direction, signed):
    """Decision 43: the input is a magnitude; 0710 shakes toward −x, 0720 toward +x, and DataInfo 19 follows."""
    analysis = model(direction, **{f"jrsnap_{direction}/target_displacement_m": 0.3}).analysis
    assert analysis.target == Printed(signed, 3, "m")
    assert analysis.target.value * float(PROFILES[direction].earthquake) > 0


@pytest.mark.parametrize("direction", ["longitudinal", "transverse"])
@pytest.mark.parametrize("target", [-0.3, 0])
def test_a_signed_or_zero_target_displacement_is_an_input_error(direction, target):
    with pytest.raises(InputError, match=re.escape(f"jrsnap_{direction}.target_displacement_m: 正の数値が必要です")):
        model(direction, **{f"jrsnap_{direction}/target_displacement_m": target})


@pytest.mark.parametrize("key", ["shear_factor_vcd", "shear_factor_vsd", "shear_factor_vdd", "aggregate_max_mm",
                                 "analysis_steps", "limited_final_step", "target_displacement_m"])
def test_blank_conditions_are_errors(key):
    with pytest.raises(InputError, match=re.escape(f"jrsnap_longitudinal.{key}: 値が必要です")):
        model("longitudinal", **{f"jrsnap_longitudinal/{key}": None})


def test_a_pedestal_adds_a_rigid_arm_and_a_reversed_member():
    built = model("longitudinal", **PEDESTAL)
    arm, pedestal = built.elements[6], built.elements[7]
    assert arm.title == "桁受け腕" and arm.length.value == 0.35  # horizontal, left to right
    left, right = (built.joints[n - 1] for n in (arm.i, arm.j))
    assert left.y == right.y and left.x.value < right.x.value
    assert pedestal.title == "桁受け" and pedestal.length.value == 0.3
    top, bottom = (built.joints[n - 1] for n in (pedestal.i, pedestal.j))
    assert top.y.value == -7.9 and bottom.y.value == -7.6  # upper end first
    loads = {m.element: m for m in built.cases[7].member_loads}
    assert loads[pedestal.number].start == loads[pedestal.number].end  # uniform B3 × W3 × γ
    assert [load.node for load in built.cases[0].joint_loads][0] == pedestal.i  # the bearing seat (decision 29)


def test_a_reversed_member_swaps_its_end_values():
    p, foundation, embedment, layout, seismic = results("longitudinal", document(**PEDESTAL))
    pedestal = seismic.frame.members[-1]
    case = seismic.basic_cases[7]
    tapered = replace(case, member_loads=(MemberLoad(pedestal.number, Printed(-1.0, 2, "kN/m"),
                                                     Printed(-2.0, 2, "kN/m")),))
    built = build_ndu(PROFILES["longitudinal"], p, foundation, embedment, layout,
                      replace(seismic, basic_cases=(*seismic.basic_cases[:7], tapered)))
    load, = built.cases[7].member_loads
    assert (load.start.value, load.end.value) == (2.0, 1.0)  # frame start (bottom) value is now at j


@pytest.mark.parametrize("n,expected", [
    (None, [(1, 4, 297.68, None), (1, 1, 5.0, 5.0)]),
    (Printed(0.0, 2, "kN/m"), [(1, 1, 5.0, 5.0), (2, 1, 5.0, 5.0)]),  # no axial row for a zero axial load
])
def test_a_horizontal_line_load_is_a_local_y_load(n, expected):
    p, foundation, embedment, layout, seismic = results("longitudinal")
    case = seismic.basic_cases[0]
    line = replace(case.line_loads[0], h=Printed(-5.0, 2, "kN/m"), n=n or case.line_loads[0].n)
    built = build_ndu(PROFILES["longitudinal"], p, foundation, embedment, layout,
                      replace(seismic, basic_cases=(replace(case, line_loads=(line,)), *seismic.basic_cases[1:])))
    kinds = [(m.element, m.kind, m.start.value, None if m.end is None else m.end.value)
             for m in built.cases[0].member_loads]
    assert kinds[:2] == expected


def test_zero_loads_have_no_rows():
    built = model("longitudinal")
    assert all(load.h.value or load.n.value or load.m.value for case in built.cases for load in case.joint_loads)
    p_document = document()
    for slot in p_document["上部工反力"]["起点側"]["B支点"] + p_document["上部工反力"]["終点側"]["C支点"]:
        if slot is not None:
            for key in ("雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率"):
                slot[key] = 0.0
    for end in (p_document["上部工反力"]["起点側"]["A支点"], p_document["上部工反力"]["終点側"]["D支点"]):
        for key in ("雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率"):
            end[key] = 0.0
    snowless = model("longitudinal", data=p_document)
    assert snowless.cases[3].title == "雪荷重" and snowless.cases[3].joint_loads == ()


ASYMMETRIC = {"下部構造/寸法/側面/B7": 2.5, "下部構造/寸法/側面/B9": 1.8}  # column axis (B7 − B9)/2 = 0.350 off


def test_an_inclined_rigid_member_is_a_vertical_and_a_horizontal_rigid_element():
    # Decision 40: the rigid offset from the column axis to the footing centroid of an asymmetric footing.
    built = model("longitudinal", **ASYMMETRIC)
    top, centroid, base = (built.joints[n - 1] for n in (5, 6, 7))
    assert abs(top.x.value) == 0.35 and (centroid.x.value, base.x.value) == (0, 0)
    corner = built.joints[-1]
    assert (corner.number, corner.x, corner.y) == (8, top.x, centroid.y)  # a new joint below the footing top
    vertical, horizontal, lower = built.elements[4:7]
    assert (vertical.i, vertical.j, vertical.length.value, vertical.nonlinear) == (5, 8, 1.35, False)
    left, right = sorted((8, 6), key=lambda n: built.joints[n - 1].x.value)
    assert (horizontal.i, horizontal.j, horizontal.length.value) == (left, right, 0.35)
    assert vertical.title == horizontal.title == "フーチング上"
    assert (lower.number, lower.i, lower.j) == (7, 6, 7) and len(built.elements) == 7
    summary = validate_ndu(write_ndu(built), LONGITUDINAL)
    assert (summary.joints, summary.elements) == (8, 7)


def test_member_loads_follow_the_renumbered_elements():
    built = model("longitudinal", **ASYMMETRIC, **PEDESTAL)
    pedestal = built.elements[-1]
    assert pedestal.title == "桁受け" and pedestal.number == 9  # member 8 after the split footing member
    assert pedestal.number in {load.element for load in built.cases[7].member_loads}


def test_an_inclined_elastic_member_is_not_supported():
    p, foundation, embedment, layout, seismic = results("longitudinal", document(**ASYMMETRIC))
    frame = seismic.frame
    upper = frame.members[4]
    elastic = replace(upper, section=frame.column_section, material=frame.materials.column)
    broken = replace(seismic, frame=replace(frame, members=(*frame.members[:4], elastic, *frame.members[5:])))
    with pytest.raises(InputError, match=re.escape("骨組の部材5（フーチング上）が斜めの弾性部材です")):
        build_ndu(PROFILES["longitudinal"], p, foundation, embedment, layout, broken)


def test_girders_at_different_heights_have_no_single_control_node():
    with pytest.raises(InputError, match=re.escape("上部構造: 起点側と終点側の桁の高さ h1+h2 が異なり")):
        model("transverse", **{"上部構造/終点側/高さ/h1": 0.5})


def test_a_short_shear_span_is_outside_the_bending_profile():
    with pytest.raises(InputError, match=re.escape("La/d = 3700/2592 が2未満")):
        model("longitudinal", **{"下部構造/寸法/高さ/H4": 1.0})


def test_the_support_must_be_sandy_with_no_cohesion():
    with pytest.raises(InputError, match=re.escape("地盤データ.層[1].土質区分: JRSNAP の直接基礎（砂質土系）")):
        model("longitudinal", **{"地盤データ/層/1/土質区分": "粘性土"})
    with pytest.raises(InputError, match=re.escape("地盤データ.層[1].一軸圧縮強度_qu: qu = 0 が必要です")):
        model("longitudinal", **{"地盤データ/層/1/一軸圧縮強度_qu": 50})
    with pytest.raises(InputError, match=re.escape("地盤データ.層[1].単位体積重量.水中: 値が必要です")):
        model("longitudinal", **{"地盤データ/層/1/単位体積重量/水中": None})


def test_two_layers_of_main_bars():
    second = {"diameter_mm": 32, "material": None, "cover_mode": "自動", "center_mm": None, "clear_gap_mm": 40,
              "face_direction": "線路", "layer": 2, "per_face_count": 27, "endpoints": None,
              "distribution": {"mode": "中央ピッチ", "edge_center_mm": None, "pitch_mm": 150}}
    rows = deepcopy(document()["鉄筋"]["柱"]["main_rows"]) + [second]
    section = model("longitudinal", **{"鉄筋/柱/main_rows": rows}).section
    # 108 + 16 + 40 + 16 = 180 from each face; DRTU = DRTL = 2 rows, both at 150.
    assert section.main_layers == 2 and section.main_pitch.value == 150
    assert [(r.center.value, r.count) for r in section.rows[:2]] == [(108, 29), (180, 27)]
    assert [(r.center.value, r.count) for r in section.rows[-2:]] == [(2520, 27), (2592, 29)]


@pytest.mark.parametrize("changes,message", [
    ({f"{ROW1}/distribution/pitch_mm": 330},  # the 直角 D19 bars start at 30, outside the 線路 main bars at 108
     "鉄筋.柱.main_rows: 線路方向の表の先頭・末尾1行が線路の主鉄筋と一致しません"),
    ({f"{ROW0}/per_face_count": 2}, "鉄筋.柱.main_rows: 線路の主鉄筋の間隔が一つに定まりません"),
    ({f"{ROW0}/per_face_count": 0}, "鉄筋.柱.main_rows: 線路の主鉄筋の行が必要です"),
    ({f"{ROW1}/material": "SD345"}, "鉄筋.柱: 主鉄筋の材質が1種類ではありません（SD345・SD390）"),
])
def test_section_reinforcement_outside_v1(changes, message):
    with pytest.raises(InputError, match=re.escape(message)):
        model("longitudinal", **changes)


def test_more_than_100_table_rows_are_rejected():
    many = {f"{ROW0}/diameter_mm": 10, f"{ROW0}/per_face_count": 120, f"{ROW0}/distribution/mode": "等分"}
    with pytest.raises(InputError, match=re.escape("直角方向の表が122行です（JRSNAP は100行まで）")):
        model("transverse", **many)


HOOPS = "鉄筋/柱/column_hoops/direction_rows"


@pytest.mark.parametrize("changes,message", [
    ({f"{HOOPS}/1/direction": "線路"}, "鉄筋.柱.column_hoops.direction_rows: 線路の帯鉄筋はちょうど1行が必要です（2行）"),
    ({f"{HOOPS}/0/start_mm": 0}, "鉄筋.柱.column_hoops.direction_rows[0]: 区間を指定した帯鉄筋は未対応です"),
    ({f"{HOOPS}/0/effective_legs": None}, "鉄筋.柱.column_hoops.direction_rows[0].effective_legs: 値が必要です"),
    ({f"{HOOPS}/0/material": None, "鉄筋/柱/materials/transverse": None},
     "鉄筋.柱.column_hoops.direction_rows[0].material: 値が必要です（行と鉄筋.柱.materials.transverse が空欄）"),
])
def test_the_hoop_of_the_direction(changes, message):
    with pytest.raises(InputError, match=re.escape(message)):
        model("longitudinal", **changes)


def test_the_hoop_material_may_be_the_shared_one():
    built = model("longitudinal", **{f"{HOOPS}/0/material": None, "鉄筋/柱/materials/transverse": "SD345"})
    assert built.section.shear.yield_strength.value == 345


def manual(**changes):
    data = document(**changes)
    column = data["鉄筋"]["柱"]
    auto = model("longitudinal").section
    bars = column_layout(parse_input(document())).bars
    column["position_mode"] = "指定"
    column["manual_positions"] = [{"x_mm": b.x.value, "y_mm": b.y.value, "diameter_mm": b.diameter.value,
                                   "material": b.material} for b in bars]
    source = document()["鉄筋"]["柱"]
    column["manual_basis"] = {"generator_version": 1, "geometry": {"width_mm": 4500, "height_mm": 2700},
                              "inputs": {key: deepcopy(source[key]) for key in
                                         ("main_rows", "materials", "pure_cover_mm", "column_hoops")}}
    return data, auto


def test_detail_positions_equal_to_the_generated_bars():
    data, auto = manual()
    assert model("longitudinal", data=data).section == auto


def test_detail_positions_from_another_basis_or_moved_are_rejected():
    data, _ = manual(**{f"{ROW1}/distribution/pitch_mm": 240})
    with pytest.raises(InputError, match=re.escape("鉄筋.柱.manual_basis: 詳細位置の生成元が現在の基本入力と一致しません")):
        model("longitudinal", data=data)
    data, _ = manual()
    data["鉄筋"]["柱"]["manual_positions"][0]["x_mm"] = 120
    with pytest.raises(InputError, match=re.escape("鉄筋.柱.manual_positions: 移動した詳細位置は")):
        model("longitudinal", data=data)

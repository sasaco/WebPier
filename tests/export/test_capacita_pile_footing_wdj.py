"""The WDJ of the footing of a pile foundation (decision 96): five points, a member each, the bars of the input per 1 m scaled to the
member's width, the forces of the checks by Capacita's case id and the deep beam blocks of the shear."""

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "calc"))

from pile_footing_support import check as make_check, pier as make_pier  # noqa: E402
from webpier.calc.footing_rebar import main_bars  # noqa: E402
from webpier.export.capacita.pile_footing_wdj import build_pile_footing_wdj, write_pile_footing_wdj  # noqa: E402


def document():
    return build_pile_footing_wdj(make_check())


def test_every_point_is_a_member_of_its_own_with_the_effective_width():
    found, pier = make_check(), make_pier()
    wdj = build_pile_footing_wdj(found)
    assert [m["m_no"] for m in wdj["members"]] == [1, 2, 3, 4, 5] == [p["index"] for p in wdj["points"]]
    assert [m["B"] for m in wdj["members"]] == [point.point.width.be.value for point in found.points]
    assert {m["H"] for m in wdj["members"]} == {pier.substructure.h[6].value * 1000}
    assert [b["b"] for b in wdj["bar"]] == [m["B"] for m in wdj["members"]]
    assert wdj["pickup_filename"] == "" and wdj["pickup_data"] is None


def test_the_tension_side_and_the_checks_of_each_point():
    points = {p["p_name"] + str(p["index"]): p for p in document()["points"]}
    assert [(p["isLowerCalc"], p["isUpperCalc"], p["isMzCalc"], p["isVyCalc"]) for p in document()["points"]] == [
        (True, False, True, False), (False, True, True, False), (True, False, True, False), (False, True, True, True),
        (True, False, False, True)]
    assert len(points) == 5


def test_the_bars_are_the_inputs_per_metre_times_the_width_of_the_member():
    found, pier = make_check(), make_pier()
    wdj = build_pile_footing_wdj(found)
    per_metre = {"rebar2": main_bars(pier, "線路", "下"), "rebar1": main_bars(pier, "線路", "上")}
    for bar, item in zip(wdj["bar"], found.points):
        width = Decimal(str(item.point.width.be.value)) / 1000
        for face, bars in per_metre.items():
            total = sum(Decimal(str(count.value)) for count in bars.counts)
            assert abs(Decimal(str(bar[face]["rebar_n"])) - total * width) <= Decimal("0.005") * len(bars.counts)
            assert bar[face]["rebar_dia"] == bars.diameter.value and bar[face]["rebar_ss"] == bars.pitch.value
        assert bar["stirrup"]["stirrup_n"] == 1 and bar["stirrup"]["stirrup_ss"] == found.stirrups.pitch.value


def test_the_forces_are_given_by_capacitas_case_id_with_the_sign_of_the_tension():
    wdj = document()
    force = {row["index"]: row for row in wdj["force"]}
    # the made-up lines: a sagging moment 1000 + the member at the ends, −50 as the smallest; the 安全性（破壊）(5) times
    # the 応答値係数 γR 1.2 (decision 104), the earthquake (7) not
    assert force[1]["Md0_Md"] == force[1]["Md1_Md"] == force[1]["Md8_Md"] == 1011.0  # the right member's
    assert force[1]["Md5_Md"] == 1213.2
    assert force[2]["Md5_Md"] == -60.0 and force[2]["Md7_Md"] == -50.0
    assert "Vd5_Vd" not in force[1] and "Vd5_Vd" not in force[3]
    assert force[4]["Vd5_Vd"] == 480.0 and force[4]["Vd5_Md"] == -60.0 and force[4]["Md5_Md"] == -60.0
    assert set(force[5]) == {"index", "Vd5_Vd", "Vd5_Md", "Vd5_Nd"} and force[5]["Vd5_Vd"] == 480.0


def test_the_deep_beam_blocks_of_the_shear_rows():
    found = make_check()
    wdj = build_pile_footing_wdj(found)
    shear = {row["index"]: row for row in wdj["shear"]}
    assert [i for i, row in shear.items() if "deep_beam" in row] == [4, 5]
    assert shear[5]["deep_beam"] == {"mode": "lower_tension", "a1_mm": 1650, "pile_diameter_mm": 1000,
                                     "stirrup_b1_mm": found.stirrup_spacing.value}
    assert shear[4]["deep_beam"] == {"mode": "upper_tension", "stirrup_count_in_range": found.points[3].point.stirrup_count,
                                     "theta_deg": 45}


def test_the_bytes_are_json_and_the_same_every_time():
    first, second = (write_pile_footing_wdj(build_pile_footing_wdj(make_check())) for _ in range(2))
    assert first == second and json.loads(first.decode("utf-8"))["format"] == "wdj"

"""The WDJ of the footing of a pile foundation (decision 96): six points (decision 124), a member each, the bars of the input per 1 m scaled to the
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
    assert [m["m_no"] for m in wdj["members"]] == [1, 2, 3, 4, 5, 6] == [p["index"] for p in wdj["points"]]
    assert [m["B"] for m in wdj["members"]] == [point.point.width.be.value for point in found.points]
    assert {m["H"] for m in wdj["members"]} == {pier.substructure.h[6].value * 1000}
    assert [b["b"] for b in wdj["bar"]] == [m["B"] for m in wdj["members"]]
    assert wdj["pickup_filename"] == "" and wdj["pickup_data"] is None


def test_the_tension_side_and_the_checks_of_each_point():
    points = {p["p_name"] + str(p["index"]): p for p in document()["points"]}
    assert [(p["isLowerCalc"], p["isUpperCalc"], p["isMzCalc"], p["isVyCalc"]) for p in document()["points"]] == [
        (True, False, True, False), (False, True, True, False), (True, False, True, False), (False, True, True, False),
        (True, False, False, True), (False, True, False, True)]
    assert len(points) == 6


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
    assert not any(key.startswith("Vd") for index in (1, 2, 3, 4) for key in force[index])
    assert force[4]["Md5_Md"] == -60.0  # the bending of the pile position (upper tension), its Vsd a point of its own
    # Vsd (decision 124): the 安全性 480 with its −60, the 復旧性（地震時） the earthquake's 400 with its −50, no γR; no bending
    assert set(force[6]) == {"index", "Vd5_Vd", "Vd5_Md", "Vd5_Nd", "Vd7_Vd", "Vd7_Md", "Vd7_Nd"}
    assert (force[6]["Vd5_Vd"], force[6]["Vd5_Md"], force[6]["Vd7_Vd"], force[6]["Vd7_Md"], force[6]["Vd7_Nd"]) == (
        480.0, -60.0, 400.0, -50.0, 0)
    assert set(force[5]) == {"index", "Vd5_Vd", "Vd5_Md", "Vd5_Nd", "Vd7_Vd", "Vd7_Md", "Vd7_Nd"}
    assert (force[5]["Vd5_Vd"], force[5]["Vd7_Vd"]) == (480.0, 400.0)
    assert not any(key.startswith(("Vd0", "Vd1")) for row in force.values() for key in row)  # no shear of 耐久性


def test_the_deep_beam_blocks_of_the_shear_rows():
    found = make_check()
    wdj = build_pile_footing_wdj(found)
    shear = {row["index"]: row for row in wdj["shear"]}
    assert [i for i, row in shear.items() if "deep_beam" in row] == [5, 6]
    # a1: the largest of the row's (decision 124), that of the end piles, √(1650² + 750²) = 1812 (calc.pile_footing's test)
    assert shear[5]["deep_beam"] == {"mode": "lower_tension", "a1_mm": 1812, "pile_diameter_mm": 1000,
                                     "stirrup_b1_mm": found.stirrup_spacing.value}
    assert shear[6]["deep_beam"] == {"mode": "upper_tension", "stirrup_count_in_range": found.points[5].point.stirrup_count,
                                     "theta_deg": 45}
    # Vsd's member is the footing's whole width B (decision 124)
    assert wdj["members"][5]["B"] == found.points[5].point.width.full.value


def test_the_earthquake_alone_has_the_deep_beam_shear_of_its_own():
    """Decision 124 (amending decision 110): with the nonlinear analyses alone the six points are made, the deep beam ones
    with the shear of 復旧性（地震時） (Vd7) alone."""
    from pile_footing_support import direction, frames  # noqa: PLC0415
    from webpier.calc import pile_footing as pf  # noqa: PLC0415
    from webpier.calc.footing import LONGITUDINAL  # noqa: PLC0415
    from webpier.calc.pile_footing_check import calculate_pile_footing_check  # noqa: PLC0415

    pier = make_pier()
    found = calculate_pile_footing_check(pier, direction(pf.prepare(pier, frames(pier)[0], LONGITUDINAL), frames=False))
    assert found.sections == ("bending_restorability_eq", "shear_deep_beam_restorability_eq")
    force = {row["index"]: row for row in build_pile_footing_wdj(found)["force"]}
    assert set(force[4]) == {"index", "Md7_Md", "Md7_Nd"}
    assert set(force[5]) == set(force[6]) == {"index", "Vd7_Vd", "Vd7_Md", "Vd7_Nd"}


def _without_shear(check, *missing):
    """*check* with no Vd at the points and cases *missing* ((index, case)), as 0800 gives a case without a shear of the
    point's sense (decision 124)."""
    from dataclasses import replace  # noqa: PLC0415

    points = []
    for item in check.points:
        forces = tuple(replace(force, vd=None, vd_end=None, vd_combination=None, vd_md=None)
                       if (item.index, force.case) in missing else force for force in item.forces.forces)
        points.append(replace(item, forces=replace(item.forces, forces=forces)))
    return replace(check, points=tuple(points))


def test_a_case_without_a_shear_of_the_sense_gives_capacita_no_vd():
    """Decision 124: a case without a shear of the point's sense has no Vd in the WDJ (never a Vd of 0), so Capacita does
    not check it (RcDan: no force row of the case, forces.Count == 0); the section of the deep beam shear, shared by the
    points of Vfdd and Vsd, is asked for while a point has a Vd of its case."""
    from webpier.calc.pile_footing import Case  # noqa: PLC0415

    check = make_check()
    # the Vsd of 安全性 and the Vfdd of the earthquake missing
    found = _without_shear(check, (6, Case.SAFETY), (5, Case.SEISMIC))
    force = {row["index"]: row for row in build_pile_footing_wdj(found)["force"]}
    assert set(force[5]) == {"index", "Vd5_Vd", "Vd5_Md", "Vd5_Nd"}
    assert set(force[6]) == {"index", "Vd7_Vd", "Vd7_Md", "Vd7_Nd"}
    assert found.sections == check.sections == (
        "bending_safety_destruction", "shear_deep_beam_safety_destruction", "bending_durability", "bending_restorability_eq",
        "shear_deep_beam_restorability_eq", "bending_rebar_amount")
    # no point with a Vd of the earthquake: its deep beam section is not asked for, that of 安全性 still is
    found = _without_shear(check, (5, Case.SEISMIC), (6, Case.SEISMIC))
    force = {row["index"]: row for row in build_pile_footing_wdj(found)["force"]}
    assert not any(key.startswith("Vd7") for row in force.values() for key in row)
    assert found.sections == ("bending_safety_destruction", "shear_deep_beam_safety_destruction", "bending_durability",
                              "bending_restorability_eq", "bending_rebar_amount")
    found = _without_shear(check, (5, Case.SAFETY), (6, Case.SAFETY))
    assert "shear_deep_beam_safety_destruction" not in found.sections and "shear_deep_beam_restorability_eq" in found.sections
    assert not any(key.startswith("Vd") for row in build_pile_footing_wdj(found)["force"] for key in row
                   if key.startswith("Vd5"))


def test_the_factors_of_the_earthquake_are_those_of_the_sample():
    """Decision 124: the row 7 (復旧性（地震時）) gives the deep beam shear γc 1.3, γbd 1.2 (Vfdd), γbs 1.1 (Vsd) and γi 1.0, as
    the sample's tables 2.4.2 and 2.4.3 (V-139, V-140) print them."""
    rows = {row["id"]: row for row in document()["safety"]["safety_factor"]["1"]}
    assert (rows[7]["V_rc"], rows[7]["V_rbv"], rows[7]["V_rbs"], rows[7]["ri"]) == (1.3, 1.2, 1.1, 1.0)
    assert (rows[5]["V_rc"], rows[5]["V_rbv"], rows[5]["V_rbs"], rows[5]["ri"]) == (1.3, 1.2, 1.1, 1.2)


def test_the_bytes_are_json_and_the_same_every_time():
    first, second = (write_pile_footing_wdj(build_pile_footing_wdj(make_check())) for _ in range(2))
    assert first == second and json.loads(first.decode("utf-8"))["format"] == "wdj"

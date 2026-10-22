"""0710 actions, basic cases and the combination: Example2 10 pp.10-8 to 10-12."""

from decimal import Decimal

from longitudinal_support import SECTIONS
from reaction_support import D, q, value
from seismic_longitudinal_support import S10, chain, diagram, inertia_item, points, seismic
from webpier.calc.longitudinal import BasicCase, Item
from webpier.calc.seismic_longitudinal import ActionDirection, Increment, SeismicCase

C = SeismicCase
ACTIONS = S10["actions"]


def test_10_8_train_vertical_single_track():
    rows = {row["key"]: row for row in ACTIONS["train_vertical"]["rows"]}
    train = seismic().train
    for item, key in ((Item.ORIGIN, "RB"), (Item.END, "RC")):
        row = train.row(item)
        assert [row.n.value, row.arm.value, row.m.value] == [rows[key][f]["value"] for f in ("vertical", "arm",
                                                                                              "moment")]
    total = ACTIONS["train_vertical"]["total"]
    assert [train.n.value, train.m.value] == [total["vertical"]["value"], total["moment"]["value"]]  # 480, 4.00


def test_10_8_train_vertical_is_the_0600_seismic_train():
    _, reaction, _, result = chain()
    # RB = RA = 32.00 kN/m × (0.575 + 18.850 + 0.575) × 1/2 = 320.00; RC = 32.00 × 10.000 / 2 = 160.00.
    assert result.train.row(Item.ORIGIN).n == reaction.train.seismic.origin
    assert result.train.row(Item.END).n == reaction.train.seismic.end


def test_10_8_bearing_horizontal_forces():
    rows = {row["key"]: row for row in ACTIONS["bearing_horizontal"]["rows"]}
    _, reaction, _, result = chain()
    for inertia, key, kh in ((result.girder_inertia, "EQ_girder", 1.0), (result.train_inertia, "EQ_train", 0.2)):
        assert [inertia.forces.origin.force.value, inertia.forces.end.force.value] == [
            rows[key]["start_girder"]["value"], rows[key]["end_girder"]["value"]]
        assert (inertia.kh.value, inertia.kh.digits) == (kh, 2)  # 10-11: Kh=1.00, Kh=0.20
    # The 0600 forces are taken as they are; the Kh is already in them (no second factor).
    assert result.girder_inertia.forces is reaction.longitudinal.seismic_girder
    assert result.train_inertia.forces is reaction.longitudinal.seismic_train


def test_10_8_self_weight_inertia_of_the_beam_and_the_column():
    inertia = seismic().self_weight
    assert (inertia.kh.value, inertia.kh.digits) == (1.0, 2)
    # Example2 prints the sizes with 2 decimals (2.70 × 9.00); we keep the entered 3 decimals (2.700 × 9.000),
    # the same values.
    for intensity, key in ((inertia.beam_top, "Hw1"), (inertia.column, "Hw3")):
        printed = inertia_item(key)
        operands = [o["value"] for o in printed["operands"]]
        assert sorted([intensity.along.value, intensity.across.value]) == sorted(operands[:2])
        assert [intensity.unit_weight.value, intensity.kh.value] == operands[2:]
        assert (intensity.value.value, intensity.value.digits) == (printed["result"]["value"], 2)
    # Hw3 = 4.50 × 2.70 × 24.5 × 1.00 = 297.675 -> 297.68 (half up).
    assert value(inertia.column.value) == q(D(4.5) * D(2.7) * D(24.5) * D(1), 2) == Decimal("297.68")
    # The haunch bottom: (B1 − B4 − B5) × (W1 − W4 − W5) = 2.700 × 4.500, × 24.5 × 1.00 = 297.675 -> 297.68.
    # Example2 does not print it; the 10-11 taper ends at Hw2, which has the same section.
    bottom = inertia.beam_bottom
    assert (bottom.along.value, bottom.across.value, bottom.value.value) == (2.7, 4.5, 297.68)
    assert inertia.pedestal is None  # H1 = 0


def test_10_8_footing_inertia_less_the_displaced_soil():
    printed = inertia_item("H_footing")
    operands = [o["value"] for o in printed["operands"]]  # 7.00, 9.00, 2.70, 24.5, 18.0, 1.00
    footing = seismic().self_weight.footing
    # Example2 prints B × W × H of the rectangular footing; we use the 0600 footing volume, which is the same
    # 170.100 m3 here and stays right for a haunched footing (H5 > 0).
    assert value(footing.volume) == D(operands[0]) * D(operands[1]) * D(operands[2]) == Decimal("170.1")
    assert [footing.unit_weight.value, footing.displaced.value, footing.kh.value] == operands[3:]
    # 170.100 × (24.5 − 18.0) × 1.00 = 1105.65
    assert (footing.force.value, footing.force.digits) == (printed["result"]["value"], 2)


def test_10_9_to_10_10_vertical_cases_are_those_of_0610():
    # 10-8: "下記以外の作用については §8 と同様": D1, D2, Wp (normal water) and S2 are the 0610 basic cases,
    # put on the 0710 frame (the footing centroid is node 6 here, node 5 in 0610).
    _, _, longitudinal, result = chain()
    for case, basic in ((C.D1, BasicCase.D1), (C.D2, BasicCase.D2), (C.BUOYANCY, BasicCase.BUOYANCY_NORMAL),
                        (C.SNOW, BasicCase.SNOW2)):
        ours, theirs = result.basic(case), longitudinal.basic(basic)
        assert [(p.anchor, p.n, p.h, p.m) for p in ours.points] == [(p.anchor, p.n, p.h, p.m) for p in theirs.points]
        assert [(line.n, line.h) for line in ours.line_loads] == [(line.n, line.h) for line in theirs.line_loads]
        assert ours.member_loads == ()


def test_10_9_to_10_11_load_diagrams():
    result = seismic()
    printed = diagram(1)
    assert points(result.basic(C.D1)) == {1: (printed["N"], 0.0, printed["M"]), 6: (printed["P"], 0.0, 0.0)}
    (line,) = result.basic(C.D1).line_loads
    assert (line.members, line.n.value, line.h.value) == ((1, 2, 3, 4), printed["q"], 0.0)  # q to the footing top
    printed = diagram(2)
    assert points(result.basic(C.D2)) == {1: (printed["N"], 0.0, printed["M"]), 6: (printed["P"], 0.0, 0.0)}
    # 10-10 prints Wp as −1701.0 (1 decimal, a digit slip: 08 and 11 print −1701.00); ours is a force, 2 decimals.
    assert points(result.basic(C.BUOYANCY)) == {6: (diagram(3)["P"], 0.0, 0.0)}
    assert result.basic(C.BUOYANCY).points[0].n.digits == 2
    printed = diagram(4)
    assert points(result.basic(C.SNOW)) == {1: (printed["N"], 0.0, printed["M"])}
    printed = diagram(5)
    assert points(result.basic(C.TRAIN)) == {1: (printed["N"], 0.0, printed["M"])}
    # The earthquake acts toward the origin side (← on 10-11, −x in the frame); H at the beam top with M = 0.
    assert points(result.basic(C.GIRDER_INERTIA)) == {1: (0.0, -diagram(6)["H"], 0.0)}
    assert points(result.basic(C.TRAIN_INERTIA)) == {1: (0.0, -diagram(7)["H"], 0.0)}
    for case in (C.TRAIN, C.GIRDER_INERTIA, C.TRAIN_INERTIA):
        assert result.basic(case).line_loads == () and result.basic(case).member_loads == ()


def test_10_11_self_weight_inertia_loads():
    result = seismic()
    printed = diagram(8)
    action = result.basic(C.SELF_INERTIA)
    assert points(action) == {6: (0.0, -printed["H"], 0.0)}  # footing H at the footing centroid
    hw1, hw2 = -printed["Hw1"], -printed["Hw2"]
    # Hw1 over the beam (2.000), linear from Hw1 to the haunch bottom over the haunch (0.700), Hw2 over the
    # column and the micro member down to the footing top (4.890 + 0.010 = the 4.900 of the drawing).
    assert [(load.member, load.start.value, load.end.value) for load in action.member_loads] == [
        (1, hw1, hw1), (2, hw1, hw2), (3, hw2, hw2), (4, hw2, hw2)]
    assert action.line_loads == ()


def test_10_12_basic_cases():
    rows = S10["basic_cases"]["rows"]
    result = seismic()
    assert [action.case.value for action in result.basic_cases] == [row["case"] for row in rows]
    arrows = {"↓": ActionDirection.DOWNWARD, "↑": ActionDirection.UPWARD, "←": ActionDirection.TOWARD_ORIGIN}
    kinds = {"固定": Increment.FIXED, "増分": Increment.INCREMENTAL, "限定増分": Increment.LIMITED}
    assert [a.direction for a in result.basic_cases] == [arrows[row["direction"]] for row in rows]
    assert [a.increment for a in result.basic_cases] == [kinds[row["type"]] for row in rows]
    # The case names print Kh=1.00 (6, 8) and Kh=0.20 (7).
    assert [result.girder_inertia.kh.value, result.train_inertia.kh.value, result.self_weight.kh.value] == [
        1.0, 0.2, 1.0]


def test_10_12_combination():
    (printed,) = S10["combinations"]["rows"]
    combinations = seismic().combinations
    combination = combinations[0]  # Example2 10-12 has the first 照査パターン only
    assert combination.number == printed["combination"]
    assert (combination.alpha_f.value, combination.alpha_f.digits) == (printed["alpha_f"]["value"], 1)
    assert (combination.rho_m.value, combination.rho_m.digits) == (printed["rho_m"]["value"], 1)
    # Decision 76: the four 照査パターン (ρm, αf), each pushed toward the earthquake.
    assert [(c.number, c.rho_m.value, c.alpha_f.value) for c in combinations] == [
        (1, 1.0, 1.0), (2, 1.2, 1.0), (3, 1.0, 2.0), (4, 1.2, 2.0)]
    for c in combinations:
        assert (c.rho_m.digits, c.alpha_f.digits, c.reverse) == (1, 1, False)
        assert c.direction is ActionDirection.TOWARD_ORIGIN
        # "1 + 2 + … + 8": every basic case once, no factor printed.
        assert [case.value for case in c.cases] == [int(n) for n in printed["printed_expression"].split(" + ")]
        assert c.ground_resistance_type == printed["ground_resistance_type"]["value"]


def test_0610_section_keys_still_match():
    # The 0610 transcription the vertical cases come from (08 8-3) agrees with the 0710 diagrams.
    printed = {item["key"]: item["value"] for item in SECTIONS["dead_load"]["items"] if "value" in item}
    assert printed["top_N"] == diagram(1)["N"] and printed["footing_P"] == diagram(1)["P"]

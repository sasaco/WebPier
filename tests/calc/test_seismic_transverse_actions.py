"""0720 actions, basic cases and the combinations: Example2 11 pp.11-8 to 11-13."""

from decimal import Decimal

import pytest

from reaction_support import D, pier, q, value
from seismic_transverse_support import S11, chain, diagram, inertia_item, points, seismic
from transverse_support import BEARING_KEYS
from webpier.calc.seismic_longitudinal import ActionDirection, Increment
from webpier.calc.seismic_transverse import SeismicCase
from webpier.calc.transverse import BasicCase, Item, Track

C = SeismicCase
ACTIONS = S11["actions"]
SIDES = {"起点側RB": "origin", "終点側RC": "end"}


def case_kh(case):
    return next(c for c in S11["load_cases"]["cases"] if c["case"] == case)["Kh"]["value"]


def printed_rows(line):
    """[(bearing key, (factor, N, arm, M))] of one 11-8 train table, in print order."""
    rows = []
    for row in ACTIONS["train_vertical"][line]["rows"]:
        key = ("RB_" if row["side"] == "起点側RB" else "RC_") + row["key"]
        rows.append((key, (row["operands"][1]["value"], row["vertical"]["value"], row["arm"]["value"],
                           row["moment"]["value"])))
    return rows


def test_11_8_train_vertical_up_and_down_track():
    result = seismic()
    for track, line in ((Track.UP, "up_line"), (Track.DOWN, "down_line")):
        table = result.train(track)
        assert table.track is track
        ours = [(BEARING_KEYS[(row.item.value, row.slot)], (row.share.value, row.n.value, row.arm.value,
                                                            row.m.value)) for row in table.rows]
        assert ours == printed_rows(line), track
        printed = ACTIONS["train_vertical"][line]
        assert (table.n.value, table.m.value) == (printed["sum_vertical"]["value"], printed["sum_moment"]["value"])
    # Up = L2 (decision 21): Σ M = +1028.62, the sum of the printed rows (the unrounded sum is 1028.624).
    assert result.train(Track.UP).m.value == 1028.62 and result.train(Track.DOWN).m.value == -1028.62


def test_11_8_train_vertical_is_the_0600_seismic_train_times_the_share():
    _, reaction, _, result = chain()
    for row in result.train(Track.UP).rows:
        seismic_r = reaction.train.seismic.origin if row.item is Item.ORIGIN else reaction.train.seismic.end
        assert row.reaction == seismic_r  # 320.00 / 160.00 (07 7-2), not the 0620 train reaction
        assert value(row.n) == q(value(row.reaction) * value(row.share), 2)
        assert value(row.m) == q(value(row.n) * value(row.arm), 2)
    # G4 of RB: 150.72 × 3.800 = 572.736 -> 572.74; G1 of RC: 22.88 × −2.950 = −67.496 -> −67.50.
    rows = {(row.item, row.slot): row for row in result.train(Track.UP).rows}
    assert rows[(Item.ORIGIN, 3)].m.value == 572.74 and rows[(Item.END, 0)].m.value == -67.5


def test_11_8_girder_inertia_by_side():
    # 11-8 prints H = 6720.00 + 2360.00 = 9080.00 and M = 27105.00: the girder 5520 × 2.750 (+ 1720 × 2.750) and
    # the shelter couples at the bearings. Our input folds the shelter into the equivalent height hs (current.json:
    # hs = 19838 / 6720 -> 2.952, 7267 / 2370 -> 3.066) and the end H is 2370 (D1 + D2 + S2 = 1860 + 260 + 250, the
    # documented +10 kN residual against 2360). So each side is the 0600 force at hs (07 7-18):
    #   B: 6720.00 × 2.952 = 19837.44 (Example2 19838.00), C: 2370.00 × 3.066 = 7266.42 (Example2 7267.00).
    _, reaction, _, result = chain()
    girder = result.girder_inertia
    assert (girder.kh.value, girder.kh.digits) == (case_kh(7), 2)  # Kh = 1.00 (11-12)
    origin, end = girder.rows
    sides = reaction.transverse
    assert (origin.item, origin.h, origin.y, origin.m) == (Item.ORIGIN, *_triple(sides.origin.seismic_girder))
    assert (end.item, end.h, end.y, end.m) == (Item.END, *_triple(reaction.transverse.end.seismic_girder))
    assert value(origin.m) == q(D(6720) * D(2.952), 2) == Decimal("19837.44")
    assert value(end.m) == q(D(2370) * D(3.066), 2) == Decimal("7266.42")
    # Σ of the printed rows: 6720.00 + 2370.00 = 9090.00 (Example2 9080.00), 19837.44 + 7266.42 = 27103.86
    # (Example2 27105.00; 11-8).
    assert (girder.h.value, girder.m.value) == (9090.0, 27103.86)
    assert girder.h.value - ACTIONS["girder_inertia"]["node_load"]["result"]["value"] == 10.0


def _triple(force):
    return force.force, force.height, force.moment


def test_11_8_train_inertia():
    _, reaction, _, result = chain()
    train = result.train_inertia
    assert (train.kh.value, train.kh.digits) == (case_kh(8), 2)  # Kh = 0.30 (11-12)
    origin, end = train.rows
    assert (origin.h, origin.y, origin.m) == _triple(reaction.transverse.origin.seismic_train)
    assert (end.h, end.y, end.m) == _triple(reaction.transverse.end.seismic_train)
    printed = ACTIONS["train_inertia"]
    # H = 96.00 + 48.00 = 144.00; M = 96.00 × 5.35 + 48.00 × 5.35 = 513.60 + 256.80 = 770.40.
    assert [origin.h.value, end.h.value] == [o["value"] for o in printed["node_load"]["operands"]]
    assert [origin.h.value, origin.y.value, end.h.value, end.y.value] == [
        o["value"] for o in printed["moment"]["operands"]]
    assert (train.h.value, train.m.value) == (printed["node_load"]["result"]["value"],
                                              printed["moment"]["result"]["value"])


def test_11_8_self_weight_inertia():
    inertia = seismic().self_weight
    assert (inertia.kh.value, inertia.kh.digits) == (1.0, 2)
    for intensity, key in ((inertia.beam_top, "Hw1"), (inertia.column, "Hw3")):
        printed = inertia_item(key)
        operands = [o["value"] for o in printed["operands"]]
        assert sorted([intensity.along.value, intensity.across.value]) == sorted(operands[:2])
        assert [intensity.unit_weight.value, intensity.kh.value] == operands[2:]
        assert (intensity.value.value, intensity.value.digits) == (printed["result"]["value"], 2)
    # The haunch bottom (B1 − B4 − B5) × (W1 − W4 − W5) = 2.700 × 4.500 × 24.5 = 297.675 -> 297.68, the Hw2 of 11-12.
    assert inertia.beam_bottom.value.value == diagram(9)["Hw2"]
    assert inertia.pedestal is None  # H1 = 0
    printed = inertia_item("H_footing")
    operands = [o["value"] for o in printed["operands"]]  # 7.00 × 9.00 × 2.70 × (24.5 − 18.0) × 1.00
    footing = inertia.footing
    assert value(footing.volume) == D(operands[0]) * D(operands[1]) * D(operands[2])
    assert [footing.unit_weight.value, footing.displaced.value, footing.kh.value] == operands[3:]
    assert footing.force.value == printed["result"]["value"] == 1105.65


# The bearings on an offset pedestal (H1 > 0): D1 splits at the seat and the bearing moments move to it.
PEDESTAL = {"下部構造/寸法/側面/B2": 1.025, "下部構造/寸法/側面/B3": 1.0, "下部構造/寸法/正面/W2": 1.0,
            "下部構造/寸法/正面/W3": 7.0, "下部構造/寸法/高さ/H1": 0.3}


@pytest.mark.parametrize("changes", [{}, PEDESTAL], ids=["current", "pedestal"])
def test_11_10_to_11_11_vertical_cases_are_those_of_0620(changes):
    # 11-8: D1, D2, Wp (normal water) and S2 are the 0620 basic cases, which 0720 calculates on its own frame
    # without reading 0620 (decision 78; one node lower: the girder level is node 1).
    _, _, transverse, result = chain(pier(**changes))
    for case, basic in ((C.D1, BasicCase.D1), (C.D2, BasicCase.D2), (C.BUOYANCY, BasicCase.BUOYANCY_NORMAL),
                        (C.SNOW, BasicCase.SNOW2)):
        ours, theirs = result.basic(case), transverse.basic(basic)
        assert [(p.anchor, p.n, p.h, p.m) for p in ours.points] == [(p.anchor, p.n, p.h, p.m) for p in theirs.points]
        assert [(line.n, line.h) for line in ours.line_loads] == [(line.n, line.h) for line in theirs.line_loads]
        assert ours.member_loads == ()
    assert result.fixed == transverse.fixed and result.additional == transverse.additional
    assert result.buoyancy == transverse.buoyancy[1] and result.snow == transverse.snow[0]


def test_11_10_to_11_12_load_diagrams():
    result = seismic()
    printed = diagram(1)
    # N, M at node 2 (the beam top), P at node 7 (the footing centroid); node 1 carries nothing.
    assert points(result.basic(C.D1)) == {2: (printed["N"], 0.0, printed["M"]), 7: (printed["P"], 0.0, 0.0)}
    (line,) = result.basic(C.D1).line_loads
    assert (line.members, line.n.value, line.h.value) == ((2, 3, 4, 5), printed["q"], 0.0)
    printed = diagram(2)
    assert points(result.basic(C.D2)) == {2: (printed["N"], 0.0, printed["M"]), 7: (printed["P"], 0.0, 0.0)}
    assert points(result.basic(C.BUOYANCY)) == {7: (diagram(3)["P"], 0.0, 0.0)}
    printed = diagram(4)
    assert points(result.basic(C.SNOW)) == {2: (printed["N"], 0.0, printed["M"])}
    for case in (5, 6):
        printed = diagram(case)
        assert points(result.basic(SeismicCase(case))) == {2: (printed["N"], 0.0, printed["M"])}
    # → (+x across the track): H and M = Σ H × y at node 2. Case 8 matches 11-12; case 7 is 9090.00 / 27103.86
    # against the printed 9080.00 / 27105.00 (the girder inertia above).
    assert points(result.basic(C.GIRDER_INERTIA)) == {2: (0.0, 9090.0, 27103.86)}
    assert points(result.basic(C.TRAIN_INERTIA)) == {2: (0.0, diagram(8)["H"], diagram(8)["M"])}
    for case in (C.TRAIN_UP, C.TRAIN_DOWN, C.GIRDER_INERTIA, C.TRAIN_INERTIA):
        assert result.basic(case).line_loads == () and result.basic(case).member_loads == ()


def test_11_12_self_weight_inertia_loads():
    result = seismic()
    printed = diagram(9)
    action = result.basic(C.SELF_INERTIA)
    assert points(action) == {7: (0.0, printed["H"], 0.0)}  # footing H at the footing centroid, →
    hw1, hw2 = printed["Hw1"], printed["Hw2"]
    # Hw1 from node 2 over the beam (2.000), linear to the haunch bottom (0.700), Hw2 over the column and the micro
    # member (4.890 + 0.010 = the 4.900 of 11-12); nothing on the girder member 1-2.
    assert [(load.member, load.start.value, load.end.value) for load in action.member_loads] == [
        (2, hw1, hw1), (3, hw1, hw2), (4, hw2, hw2), (5, hw2, hw2)]
    assert action.line_loads == ()


def test_11_13_basic_cases():
    rows = S11["basic_cases"]["rows"]
    result = seismic()
    assert [action.case.value for action in result.basic_cases] == [row["case"] for row in rows]
    arrows = {"↓": ActionDirection.DOWNWARD, "↑": ActionDirection.UPWARD, "→": ActionDirection.TOWARD_W9}
    kinds = {"固定": Increment.FIXED, "増分": Increment.INCREMENTAL, "限定増分": Increment.LIMITED}
    assert [a.direction for a in result.basic_cases] == [arrows[row["direction"]] for row in rows]
    assert [a.increment for a in result.basic_cases] == [kinds[row["type"]] for row in rows]
    # 11-13 names case 5 "下り" and case 6 "上り", but 11-8 and 11-11 load case 5 with the up-track numbers
    # (M = +1028.62) and the combination uses them: case 5 is up (L2), case 6 is down (decision 21).
    assert (result.basic(C.TRAIN_UP).track, result.basic(C.TRAIN_DOWN).track) == (Track.UP, Track.DOWN)
    assert all(result.basic(case).track is None for case in C if case not in (C.TRAIN_UP, C.TRAIN_DOWN))
    assert [result.girder_inertia.kh.value, result.train_inertia.kh.value, result.self_weight.kh.value] == [
        1.0, 0.3, 1.0]


def test_11_13_combinations_up_then_down_by_pattern():
    (printed,) = S11["combinations"]["rows"]
    combinations = seismic().combinations
    up = combinations[0]  # Example2 11-13 has the up track with the first 照査パターン only
    expression = [int(n) for n in printed["printed_expression"].split(" + ")]  # 1 + 2 + 3 + 4 + 5 + 7 + 8 + 9
    assert (up.number, up.track, [case.value for case in up.cases]) == (printed["combination"], Track.UP, expression)
    assert (up.alpha_f.value, up.alpha_f.digits) == (printed["alpha_f"]["value"], 1)
    assert (up.rho_m.value, up.rho_m.digits) == (printed["rho_m"]["value"], 1)
    # Decision 21: the down track is the same with case 6 in place of case 5; decision 76: each track by the four
    # 照査パターン (ρm, αf), the down track reversed (逆向, ←).
    patterns = [(1.0, 1.0), (1.2, 1.0), (1.0, 2.0), (1.2, 2.0)]
    assert [(c.number, c.track, (c.rho_m.value, c.alpha_f.value), c.reverse, c.direction) for c in combinations] == [
        *((n, Track.UP, p, False, ActionDirection.TOWARD_W9) for n, p in enumerate(patterns, 1)),
        *((n, Track.DOWN, p, True, ActionDirection.TOWARD_W1) for n, p in enumerate(patterns, 5))]
    for combination in combinations:
        down = combination.track is Track.DOWN
        assert [case.value for case in combination.cases] == ([1, 2, 3, 4, 6, 7, 8, 9] if down else expression)
        assert (combination.alpha_f.digits, combination.rho_m.digits) == (1, 1)
        assert combination.ground_resistance_type == printed["ground_resistance_type"]["value"]

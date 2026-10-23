"""0620 centrifugal load (decision 33): cases only on a curve, with the coefficient and the track of the train L.

The 0600 centrifugal forces carry ρf (R × ρf × α). The 0620 basic case takes the train load of the track without
ρf (the 9-5 rows of the side) times the 0600 α at the 0600 centrifugal height, so the combination coefficient of L
(ρ, 1.1 ρ or ρs) applies ρ once, as for the train and the vehicle lateral load.
"""

from decimal import Decimal

import pytest

from reaction_support import D, pier, q, value
from transverse_support import chain, dims, points, transverse
from webpier.calc.longitudinal import Basis, SpringTerm
from webpier.calc.transverse import BasicCase, Define, Item, Track

B = BasicCase
ORIGIN_CURVE = {"上部構造/起点側/曲線半径": 600, "上部構造/起点側/列車速度": 130}
END_CURVE = {"上部構造/終点側/曲線半径": 400, "上部構造/終点側/列車速度": 100}
CASES = {Track.UP: B.CENTRIFUGAL_UP, Track.DOWN: B.CENTRIFUGAL_DOWN, Track.DOUBLE: B.CENTRIFUGAL_DOUBLE}


def test_straight_track_has_no_centrifugal_cases():
    result = transverse()  # Example2: R = 0 on both sides
    assert result.centrifugal is None
    assert [a.case.value for a in result.basic_cases] == list(range(1, 18))
    assert [d.number for d in result.define_cases] == list(range(1, 16))
    assert all(len(c.coefficients) == 15 for c in result.combinations)


def hand_side(rows, item, alpha, height):
    train = sum(value(r.n) for r in rows if r.item is item)
    h = q(train * value(alpha), 2)
    return train, h, q(h * value(height), 2)


@pytest.mark.parametrize("curve", [ORIGIN_CURVE, END_CURVE, ORIGIN_CURVE | END_CURVE], ids=["origin", "end", "both"])
@pytest.mark.parametrize("track", list(Track))
def test_centrifugal_by_hand(curve, track):
    _, reaction, result = chain(pier(**curve))
    table = result.centrifugal.table(track)
    train = result.train.table(track)
    assert table.track is track
    total_h = total_m = Decimal(0)
    for row, side in zip(table.rows, (reaction.transverse.origin, reaction.transverse.end), strict=True):
        assert (row.coefficient, row.y) == (side.centrifugal_coefficient, side.centrifugal_height)  # 0600
        expected = hand_side(train.rows, row.item, row.coefficient, row.y)
        assert (value(row.train), value(row.h), value(row.m)) == expected
        total_h, total_m = total_h + expected[1], total_m + expected[2]
    assert [r.item for r in table.rows] == [Item.ORIGIN, Item.END]
    assert (value(table.h), value(table.m)) == (total_h, total_m)
    action = result.basic(CASES[track])
    assert points(action) == {1: (0.0, table.h.value, table.m.value)}
    assert (action.spring, action.track, action.horizontal) == (SpringTerm.SHORT, track, True)


def test_origin_curve_values():
    # α = 130² / (127 × 600) = 0.22178 -> 0.222 (0600); height 0.150 + 2.600 + 1.100 + 1.500 = 5.350.
    # Up: −5.45 + 47.95 + 101.63 + 128.33 = 272.46; × 0.222 = 60.48612 -> 60.49; × 5.350 = 323.6215 -> 323.62.
    # Double: 122.88 + 149.59 + 149.59 + 122.88 = 544.94; × 0.222 = 120.97668 -> 120.98; × 5.350 = 647.243.
    result = transverse(pier(**ORIGIN_CURVE))
    up, double = result.centrifugal.up, result.centrifugal.double
    assert [(r.train.value, r.coefficient.value, r.h.value, r.y.value, r.m.value) for r in up.rows] == [
        (272.46, 0.222, 60.49, 5.35, 323.62), (294.92, 0.0, 0.0, 5.35, 0.0)]
    assert (double.rows[0].h.value, double.rows[0].m.value) == (120.98, 647.24)
    assert [a.case.value for a in result.basic_cases] == list(range(1, 21))


def test_centrifugal_follows_the_coefficient_and_track_of_the_train():
    result = transverse(pier(**ORIGIN_CURVE))
    assert [(d.number, d.cases) for d in result.define_cases[15:]] == [
        (16, (B.CENTRIFUGAL_UP, B.CENTRIFUGAL_DOWN)), (17, (B.CENTRIFUGAL_DOUBLE,))]
    assert all(d.signs == (1,) for d in result.define_cases[15:])  # toward the outside of the curve only
    for combination in result.combinations:
        c = combination.coefficients
        assert len(c) == 17 and (c[15], c[16]) == (c[8], c[9])  # the coefficients of L single and L double
        defines = {component.define for component in combination.components}
        assert (Define.CENTRIFUGAL_SINGLE in defines) is (Define.TRAIN_SINGLE in defines)
        assert (Define.CENTRIFUGAL_DOUBLE in defines) is (Define.TRAIN_DOUBLE in defines)
        for variant in combination.variants():
            assert len({a.track for a in variant if a.track in (Track.UP, Track.DOWN)}) <= 1
    first = result.combinations[0].component(Define.CENTRIFUGAL_DOUBLE).alternatives[0]
    assert (first.factor.value, first.basis) == (1.35, Basis.BASIC)  # 1.1 ρ, as L double
    assert (value(first.points[0].h), value(first.points[0].m)) == (
        q(D(1.35) * value(result.centrifugal.double.h), 2), q(D(1.35) * value(result.centrifugal.double.m), 2))
    service = result.combinations[6]  # 変動作用: L single × ρs, centrifugal likewise
    assert [[a.case for a in v] for v in service.variants()] == [
        [B.TRAIN_UP, B.IMPACT_UP, B.CENTRIFUGAL_UP], [B.TRAIN_DOWN, B.IMPACT_DOWN, B.CENTRIFUGAL_DOWN]]
    assert service.component(Define.CENTRIFUGAL_SINGLE).alternatives[0].factor == result.factors.service
    assert result.combinations[2].coefficients[15:] == (None, None)  # 風最大 has no L


def test_both_curves_add_both_sides():
    result = transverse(pier(**ORIGIN_CURVE, **END_CURVE))
    # End: α = 100² / (127 × 400) = 0.19685 -> 0.197; up 42.17 + 252.75 = 294.92 × 0.197 = 58.09924 -> 58.10,
    # × (0.100 + 2.650 + 1.100 + 1.500 = 5.350) = 310.835 -> 310.84. Total 60.49 + 58.10 = 118.59.
    up = result.centrifugal.up
    assert (up.rows[1].coefficient.value, up.rows[1].h.value, up.rows[1].m.value) == (0.197, 58.1, 310.84)
    assert (up.h.value, up.m.value) == (118.59, 634.46)


def test_centrifugal_at_the_pedestal_top():
    result = transverse(pier(**ORIGIN_CURVE, **dims(B2=1.025, B3=1.0, W2=0.5, W3=7.0, H1=0.3)))
    (point,) = result.basic(B.CENTRIFUGAL_UP).points
    assert (point.node, point.h, point.m) == (1, result.centrifugal.up.h, result.centrifugal.up.m)  # top left

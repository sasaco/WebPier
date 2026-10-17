"""0610 boundaries by hand: pedestal, asymmetric footing, zero members, single track, signs, bearings, Ec range."""

from decimal import Decimal

import pytest

from longitudinal_support import chain, longitudinal
from reaction_support import D, END_SLOTS, ORIGIN_SLOTS, document, pier, q, value
from webpier.calc.frame import NodeRole
from webpier.calc.longitudinal import BasicCase, Item
from webpier.core.errors import InputError
from webpier.inputs import parse_input

DIMS = {"B": "下部構造/寸法/側面/", "W": "下部構造/寸法/正面/", "H": "下部構造/寸法/高さ/"}


def dims(**sizes):
    return {DIMS[key[0]] + key: size for key, size in sizes.items()}


def moment(n, arm):
    return q(D(n) * D(arm), 2)


PEDESTAL = dims(B2=0.5, B3=1.0, W2=1.0, W3=7.0, H1=0.3)


def test_pedestal_adds_its_row_at_the_beam_top():
    # 桁受け 1.000 × 7.000 × 0.300 = 2.100 m3 × 24.5 = 51.45 kN at (2·0.5 + 1.0 − 2.7)/2 = −0.350 from the column axis.
    result = longitudinal(pier(**PEDESTAL))
    fixed = result.fixed
    pedestal = fixed.table.row(Item.PEDESTAL)
    assert (pedestal.n.value, pedestal.arm.value) == (51.45, -0.35)
    assert value(pedestal.m) == q(D(51.45) * D(-0.35), 2) == Decimal("-18.01")  # −18.0075
    assert [row.item for row in fixed.table.rows] == [Item.ORIGIN, Item.END, Item.PEDESTAL, Item.BEAM]
    # N = (5740 + 1860 + 51.45 + 1503.27) − 297.68 × 2.700 = 9154.72 − 803.736 = 8350.984
    assert fixed.n.value == 8350.98
    assert fixed.m.value == -628.01  # −1865.50 + 1255.50 − 18.01 + 0.00 (about the column axis)
    assert result.basic(BasicCase.D1).line_loads[0].members == (1, 2, 3)  # not on the pedestal stub


def anchored(action):
    return [(p.anchor, p.node, p.n.value, p.h.value, p.m.value) for p in action.points]


def test_bearing_loads_act_at_the_pedestal_top():
    # Decision 29. The pedestal top (node 8) is 0.300 above the beam top and −0.350 from the column axis, so a
    # bearing at x = ∓f carries M about node 8 of Σ N·(x + 0.350) = Σ M − Σ N × (−0.350).
    result = longitudinal(pier(**PEDESTAL))
    seat, cap, footing = NodeRole.PEDESTAL_TOP, NodeRole.CAP_TOP, NodeRole.FOOTING_CENTROID
    assert result.frame.node(seat).number == 8
    # D1: bearings 5740 + 1860 = 7600.00; M = −610.00 − 7600.00 × (−0.350) = 2050.00 at the seat.
    # Pier parts at the beam top: 51.45 + 1503.27 − 297.68 × 2.700 = 750.984 -> 750.98; M = −18.01 + 0.00.
    assert anchored(result.basic(BasicCase.D1)) == [(seat, 8, 7600.0, 0.0, 2050.0), (cap, 1, 750.98, 0.0, -18.01),
                                                    (footing, 5, 4167.45, 0.0, 0.0)]
    # D2: 780.00, M = 6.50 + 780.00 × 0.350 = 279.50.
    assert anchored(result.basic(BasicCase.D2))[0] == (seat, 8, 780.0, 0.0, 279.5)
    # Snow 2: 710.00, 19.25 + 248.50 = 267.75; train single 567.39, 110.52 + 198.5865 = 309.1065 -> 309.11.
    assert anchored(result.basic(BasicCase.SNOW2)) == [(seat, 8, 710.0, 0.0, 267.75)]
    assert anchored(result.basic(BasicCase.TRAIN_SINGLE)) == [(seat, 8, 567.39, 0.0, 309.11)]
    # 227.79 × 0.350 = 79.7265; 87.00 + 79.7265 = 166.7265 -> 166.73.
    assert anchored(result.basic(BasicCase.IMPACT_SINGLE)) == [(seat, 8, 227.79, 0.0, 166.73)]
    # The horizontal bearing force acts at the seat: the frame carries H × H1 (0.300).
    assert anchored(result.basic(BasicCase.SAFETY_LR10_B)) == [(seat, 8, 0.0, 473.43, 0.0)]
    # A resolved combination keeps the anchors.
    assert [p.node for p in result.combinations[0].component(BasicCase.D1).points] == [8, 1, 5]


def test_a_centred_pedestal_moves_the_loads_without_moments():
    result = longitudinal(pier(**dims(B2=0.85, B3=1.0, W2=1.0, W3=7.0, H1=0.3)))
    assert result.frame.bearing_seat.number == 7
    d1 = anchored(result.basic(BasicCase.D1))
    assert d1[0] == (NodeRole.PEDESTAL_TOP, 7, 7600.0, 0.0, -610.0)  # 0.000 offset: the moment is unchanged


ASYMMETRIC = dims(B7=2.5, B9=1.8, H5=0.5, H6=2.2, B8=3.0, W8=5.0) | {"下部構造/土かぶり/終点側_df2": 1.5}


def test_asymmetric_footing_moments_about_the_footing_centre():
    _, reaction, result = chain(pier(**ASYMMETRIC))
    weights = reaction.self_weight
    assert weights.footing.x_l.value != 0 and weights.overburden.x_l.value != 0  # the case is really asymmetric
    for row, body in ((result.fixed.footing, weights.footing), (result.additional.soil, weights.overburden),
                      (result.buoyancy[0], weights.buoyancy_high.body), (result.buoyancy[1], weights.buoyancy_normal.body)):
        assert (row.n, row.arm) == (body.weight, body.x_l)
        assert value(row.m) == moment(body.weight.value, body.x_l.value)
    centroid = result.frame.node(NodeRole.FOOTING_CENTROID)
    assert centroid.x.value == 0.0  # the lever above is from this node
    footing_point = result.basic(BasicCase.D1).points[1]
    assert (footing_point.node, footing_point.m) == (centroid.number, result.fixed.footing.m)
    # The girder levers stay ±f from the column axis, where the beam-top node is.
    assert result.fixed.table.row(Item.ORIGIN).arm.value == -0.325
    assert result.frame.node(NodeRole.CAP_TOP).x.value == 0.35


def test_zero_beam_and_haunch():
    _, reaction, result = chain(pier(**dims(H2=0.0, H3=0.0)))
    fixed = result.fixed
    assert reaction.self_weight.beam.weight.value == 0.0
    assert fixed.overlap.value == 0.0
    assert fixed.n.value == 7600.0  # 5740 + 1860 + 0, nothing deducted
    assert result.basic(BasicCase.D1).line_loads[0].members == (1,)


def test_single_track_girders():
    # L2 = 0 on every bearing: one loaded track (track total 1.000), so the double-track load is R itself.
    changes = {f"{side}/{i}/列車分担/L2": 0.0 for side, n in ((ORIGIN_SLOTS, 4), (END_SLOTS, 2)) for i in range(n)}
    changes |= {f"{ORIGIN_SLOTS}/{i}/列車分担/L1": share for i, share in enumerate((0.25, 0.25, 0.25, 0.25))}
    changes |= {f"{END_SLOTS}/{i}/列車分担/L1": 0.5 for i in range(2)}
    _, reaction, result = chain(pier(**changes))
    assert reaction.dead.origin.track_total.value == reaction.dead.end.track_total.value == 1.0
    double, single = result.train.double, result.train.single
    assert [row.n for row in double.rows] == [row.n for row in single.rows]


def test_signs_follow_the_bearing_side():
    # The origin bearings are on the −x side (lever −f), the end bearings on +x (lever +f).
    result = longitudinal(pier(**{"上部構造/起点側/支承位置_f": 0.0, "上部構造/終点側/支承位置_f": 1.2}))
    rb, rc = result.fixed.table.row(Item.ORIGIN), result.fixed.table.row(Item.END)
    assert (rb.arm.value, rb.m.value) == (0.0, 0.0)
    assert (rc.arm.value, value(rc.m)) == (1.2, moment(1860.0, 1.2))  # 2232.00
    assert result.fixed.m.value == 2232.0
    mirrored = longitudinal(pier(**{"上部構造/起点側/支承位置_f": 1.2, "上部構造/終点側/支承位置_f": 0.0}))
    assert mirrored.snow[0].row(Item.ORIGIN).m.value == -q(D(460) * D(1.2), 2) == Decimal("-552.00")
    assert mirrored.train.single.m.value == float(moment(272.47, -1.2))  # −326.964 -> −326.96


def test_swapping_fixed_and_movable_bearings():
    data = document(**{"上部構造/支承データ/起点側/支承名": "固定", "上部構造/支承データ/終点側/支承名": "可動"})
    _, reaction, result = chain(parse_input(data))
    default = longitudinal()
    for row, case in zip(result.horizontal, reaction.longitudinal.cases, strict=True):
        assert (row.origin, row.end) == (case.origin.force, case.end.force)
        assert value(row.total) == value(case.origin.force) + value(case.end.force)
    assert [r.total for r in result.horizontal] != [r.total for r in default.horizontal]
    for number in range(13, 21):
        assert result.basic(BasicCase(number)).points[0].h == result.horizontal[number - 13].total


def test_concrete_outside_the_table_stops_0610():
    with pytest.raises(InputError, match=r"鉄筋\.柱\.concrete_strength_mpa"):
        longitudinal(pier(**{"鉄筋/柱/concrete_strength_mpa": 17.9}))

"""0620 boundaries by hand: pedestal, asymmetric footing, mirrored and swapped bearings, symmetric shares, errors."""

from decimal import Decimal

import pytest

from reaction_support import END_SLOTS, ORIGIN_SLOTS, D, pier, q, value
from transverse_support import chain, dims, key, points, transverse
from webpier.calc.frame import NodeRole
from webpier.calc.transverse import BasicCase, Define, Item, Track
from webpier.core.errors import InputError

B = BasicCase
# Pedestal 1.000 (B3) × 7.000 (W3) × 0.300 across the track at xC = (2·0.5 + 7.0 − 9.0 − 2.25 + 2.25)/2 = −0.500.
PEDESTAL = dims(B2=0.85, B3=1.0, W2=0.5, W3=7.0, H1=0.3)


def anchored(action):
    return [(p.anchor, p.node, p.n.value, p.h.value, p.m.value) for p in action.points]


def test_pedestal_row_and_loads_at_the_pedestal_top():
    result = transverse(pier(**PEDESTAL))
    seat, cap, footing = NodeRole.PEDESTAL_TOP, NodeRole.CAP_TOP, NodeRole.FOOTING_CENTROID
    assert result.frame.bearing_seat.number == 8 and result.frame.bearing_offset.value == -0.5
    fixed = result.fixed
    pedestal = fixed.table.row(Item.PEDESTAL)
    # 1.000 × 7.000 × 0.300 = 2.100 m3 × 24.5 = 51.45 kN; M = 51.45 × −0.500 = −25.725 -> −25.73.
    assert (pedestal.n.value, pedestal.arm.value, value(pedestal.m)) == (51.45, -0.5, q(D(51.45) * D(-0.5), 2))
    assert [row.item for row in fixed.table.rows][-2:] == [Item.PEDESTAL, Item.BEAM]
    # N = (7600 + 51.45 + 1503.27) − 297.68 × 2.700 = 8350.984; M = 0.00 − 25.73 + 0.00 about the column axis.
    assert (fixed.n.value, fixed.m.value) == (8350.98, -25.73)
    # Decision 29: the bearings at the pedestal top, M about it = Σ M − Σ N × (−0.500): 0.00 + 7600 × 0.5 = 3800.
    # The pier parts at the beam top: 51.45 + 1503.27 − 803.736 = 750.984 -> 750.98, M −25.73.
    assert anchored(result.basic(B.D1)) == [(seat, 8, 7600.0, 0.0, 3800.0), (cap, 1, 750.98, 0.0, -25.73),
                                           (footing, 5, 4167.45, 0.0, 0.0)]
    assert anchored(result.basic(B.D2)) == [(seat, 8, 780.0, 0.0, 390.0), (footing, 5, 1830.6, 0.0, 0.0)]
    # Train up: 567.38, M = 1210.09 + 567.38 × 0.500 = 1493.78.
    assert anchored(result.basic(B.TRAIN_UP)) == [(seat, 8, 567.38, 0.0, float(q(D("1210.09") + D("283.69"), 2)))]
    # Horizontal actions at the seat with their own M = H × y above it; the frame carries H × H1.
    assert anchored(result.basic(B.LATERAL)) == [(seat, 8, 0.0, 111.69, 430.01)]
    assert anchored(result.basic(B.WIND_WITH_TRAIN))[0][:4] == (seat, 8, 0.0, 305.88)
    # The pier wind stays on the column line (the beam top 10.300); the pedestal stub is not loaded.
    assert [m.member for m in result.basic(B.WIND_WITH_TRAIN).member_loads] == [1, 2, 3]
    assert result.basic(B.D1).line_loads[0].members == (1, 2, 3)
    # 変動作用 (7): the serviceability impact acts at the seat too.
    impact = result.combinations[6].component(Define.IMPACT_SINGLE).alternatives[0]
    assert impact.points[0].node == 8
    table = result.impact.service.table(Track.UP)
    assert value(impact.points[0].m) == q(value(table.m) - value(table.n) * D(-0.5), 2)


def test_centred_pedestal_shares_the_beam_top_node():
    result = transverse(pier(**dims(B2=0.85, B3=1.0, W2=1.0, W3=7.0, H1=0.3)))  # xC = 0
    assert result.frame.bearing_offset.value == 0.0
    assert anchored(result.basic(B.TRAIN_UP))[0] == (NodeRole.PEDESTAL_TOP, 7, 567.38, 0.0, 1210.09)


ASYMMETRIC = dims(W7=2.5, W9=2.0, H5=0.5, H6=2.2, B8=3.0, W8=5.0)


def test_asymmetric_footing_moments_about_the_footing_centre():
    _, reaction, result = chain(pier(**ASYMMETRIC))
    weights = reaction.self_weight
    assert weights.footing.x_c.value != 0 and weights.overburden.x_c.value != 0  # really asymmetric across
    for row, body in ((result.fixed.footing, weights.footing), (result.additional.soil, weights.overburden),
                      (result.buoyancy[0], weights.buoyancy_high.body),
                      (result.buoyancy[1], weights.buoyancy_normal.body),
                      (result.buoyancy[2], weights.buoyancy_low.body)):
        assert (row.n, row.arm) == (body.weight, body.x_c)
        assert value(row.m) == q(value(body.weight) * value(body.x_c), 2)
    centroid = result.frame.node(NodeRole.FOOTING_CENTROID)
    assert centroid.x.value == 0.0 and result.frame.node(NodeRole.CAP_TOP).x.value == 0.25  # (2.5 − 2.0)/2
    assert points(result.basic(B.D1))[centroid.number] == (result.fixed.footing.n.value, 0.0,
                                                           result.fixed.footing.m.value)
    assert points(result.basic(B.BUOYANCY_HIGH)) == {centroid.number: (result.buoyancy[0].n.value, 0.0,
                                                                       result.buoyancy[0].m.value)}
    # The bearing levers stay their positions from the column axis.
    assert result.fixed.table.bearings(Item.ORIGIN)[0].arm.value == -3.8


def test_asymmetric_beam_puts_the_beam_off_the_column_axis():
    # The prism at (2.5 − 2.0)/2 = 0.250 and the haunch nearer the axis: the 0600 beam centroid xC (0.227).
    _, reaction, result = chain(pier(**dims(W4=2.0, W5=2.5)))
    beam = result.fixed.table.row(Item.BEAM)
    assert (beam.n, beam.arm) == (reaction.self_weight.beam.weight, reaction.self_weight.beam.x_c)
    assert beam.arm.value == 0.227 and value(beam.m) == q(value(beam.n) * D(0.227), 2)
    assert result.fixed.m == beam.m  # the bearings are symmetric


MIRRORED = {f"{side}/{i}/支承位置": -position for side, positions in (
    (ORIGIN_SLOTS, (-3.8, -1.5, 1.5, 3.8)), (END_SLOTS, (-2.95, 2.95))) for i, position in enumerate(positions)}


def test_mirrored_bearing_positions_reverse_every_moment():
    default, mirrored = transverse(), transverse(pier(**MIRRORED))
    for track in Track:
        a, b = default.train.table(track), mirrored.train.table(track)
        assert [r.n for r in a.rows] == [r.n for r in b.rows]
        assert [value(r.m) for r in b.rows] == [-value(r.m) for r in a.rows]
        assert value(b.m) == -value(a.m)
        assert value(mirrored.impact.ultimate.table(track).m) == -value(default.impact.ultimate.table(track).m)


SWAPPED = {f"{side}/{i}/列車分担/{lane}": share for side, rows in (
    (ORIGIN_SLOTS, ((0.471, -0.02), (0.373, 0.176), (0.176, 0.373), (-0.02, 0.471))),
    (END_SLOTS, ((0.857, 0.143), (0.143, 0.857)))) for i, (l1, l2) in enumerate(rows)
    for lane, share in (("L1", l2), ("L2", l1))}


def test_swapped_shares_swap_up_and_down():
    default, swapped = transverse(), transverse(pier(**SWAPPED))
    assert (swapped.train.up.rows, swapped.train.up.n, swapped.train.up.m) == (
        default.train.down.rows, default.train.down.n, default.train.down.m)
    assert swapped.train.down.rows == default.train.up.rows and swapped.train.double == default.train.double
    assert swapped.basic(B.IMPACT_UP).points == default.basic(B.IMPACT_DOWN).points


SYMMETRIC = {f"{side}/{i}/列車分担/{lane}": share for side, count, share in (
    (ORIGIN_SLOTS, 4, 0.25), (END_SLOTS, 2, 0.5)) for i in range(count) for lane in ("L1", "L2")}


def test_symmetric_bearings_and_shares_give_no_eccentric_moment():
    result = transverse(pier(**SYMMETRIC))
    for track in Track:
        train = result.train.table(track)
        # 272.47 × 0.250 = 68.1175 -> 68.12 at ±3.8 and ±1.5; 294.92 × 0.500 = 147.46 at ±2.95.
        assert train.m.value == 0.0 and result.impact.ultimate.table(track).m.value == 0.0
        assert {key(r): r.n.value for r in train.rows if r.item is Item.ORIGIN} == (
            {k: 68.12 for k in ("RB_G1", "RB_G2", "RB_G3", "RB_G4")} if track is not Track.DOUBLE
            else {k: 136.24 for k in ("RB_G1", "RB_G2", "RB_G3", "RB_G4")})  # 272.47 × 0.500 = 136.235
    for case in (B.D1, B.D2, B.SNOW2, B.SNOW10, B.SNOW30):
        assert all(p.m.value == 0.0 for p in result.basic(case).points)


def test_empty_slots_are_skipped_and_slots_kept():
    result = transverse(pier(**{f"{ORIGIN_SLOTS}/1": None}))
    assert [r.slot for r in result.fixed.table.bearings(Item.ORIGIN)] == [0, 2, 3]
    assert [r.slot for r in result.train.up.rows if r.item is Item.ORIGIN] == [0, 2, 3]
    assert value(result.fixed.table.n) == Decimal("9103.27") - 1340


def test_curved_track_is_not_supported_by_0620():
    # 0620 has no centrifugal case (Example2 9-13); a curve would lose that load silently.
    with pytest.raises(InputError, match="曲線半径"):
        transverse(pier(**{"上部構造/終点側/曲線半径": 600}))


def test_concrete_outside_the_table_stops_0620():
    with pytest.raises(InputError, match=r"鉄筋\.梁\.concrete_strength_mpa"):
        transverse(pier(**{"鉄筋/梁/concrete_strength_mpa": 81.0}))

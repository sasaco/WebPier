"""支承作用 → 橋脚天端の等価作用 by hand (decisions 70, 81): rows N × lever + H × y by seat, each seat the sums of its
printed rows.

The test load model (addin_support) puts 300.00 / 250.00 kN on 起点側1 (支承位置 −3.800) and 終点側2 (+2.950);
current.json has f = 0.325 (origin) and 0.675 (end) and no pedestal.
"""

from decimal import Decimal
from pathlib import Path

from addin_support import chain, document, pier
from webpier.calc.bearing_actions import bearing_positions, bearing_table, load_model_context
from webpier.calc.frame import Direction, NodeRole, Region, build_frame
from webpier.calc.materials import calculate_materials
from webpier.core.printed import FORCE
from webpier.loadmodel import BasicCase, BearingAction, BearingRef, BearingSlot, Side, SpringTerm


def frames(p=None, **options):
    p, foundation, reaction, model = chain(p)
    built = {direction: build_frame(p, reaction.self_weight, foundation, calculate_materials(p), direction, **options)
             for direction in Direction}
    return p, built, {case.id: case for case in model.cases}


def values(table):
    """The rows and sums of the one seat (no pedestal: the beam top)."""
    (seat,) = table.seats
    assert seat.anchor is NodeRole.CAP_TOP
    return [(row.n.value, row.arm.value, row.nm.value, row.h.value, row.y.value, row.hm.value, row.m.value)
            for row in seat.rows], (seat.n.value, seat.h.value, seat.m.value)


def points(table):
    return [(point.anchor, point.n.value, point.h.value, point.m.value) for point in table.points]


def test_vertical_along_the_track():
    p, frame, cases = frames()
    table = bearing_table(p, frame[Direction.LONGITUDINAL], cases["L"])
    # 300 × (−0.325) = −97.50; 250 × 0.675 = 168.75; Σ 550.00, 71.25
    assert values(table) == ([(300.0, -0.325, -97.5, 0.0, 0.0, 0.0, -97.5), (250.0, 0.675, 168.75, 0.0, 0.0, 0.0, 168.75)],
                             (550.0, 0.0, 71.25))
    seat = frame[Direction.LONGITUDINAL].node(NodeRole.CAP_TOP).number
    assert [point.node for point in table.points] == [seat]
    assert points(table) == [(NodeRole.CAP_TOP, 550.0, 0.0, 71.25)]
    assert table.girders == () and table.seats[0].nm.value == 71.25


def test_vertical_across_the_track():
    p, frame, cases = frames()
    table = bearing_table(p, frame[Direction.TRANSVERSE], cases["L"])
    # 300 × (−3.800) = −1140.00; 250 × 2.950 = 737.50; Σ −402.50
    assert values(table)[1] == (550.0, 0.0, -402.5)
    assert [row.arm.value for row in table.seats[0].rows] == [-3.8, 2.95]


def test_horizontal_forces_with_their_heights():
    p, frame, cases = frames()
    along = bearing_table(p, frame[Direction.LONGITUDINAL], cases["BR"])
    # 20.00 × 1.500 = 30.00; 15.00 × 1.500 = 22.50
    assert values(along) == ([(0.0, -0.325, 0.0, 20.0, 1.5, 30.0, 30.0), (0.0, 0.675, 0.0, 15.0, 1.5, 22.5, 22.5)],
                             (0.0, 35.0, 52.5))
    # By girder at its seat: H and H × y.
    assert [(g.side, g.anchor, g.h.value, g.height.value, g.m.value) for g in along.girders] == [
        (Side.ORIGIN, NodeRole.CAP_TOP, 20.0, 1.5, 30.0), (Side.END, NodeRole.CAP_TOP, 15.0, 1.5, 22.5)]
    assert along.h.value == 35.0 and points(along) == [(NodeRole.CAP_TOP, 0.0, 35.0, 52.5)]
    across = bearing_table(p, frame[Direction.TRANSVERSE], cases["WG"])
    # 8.00 × 2.000 = 16.00; 6.00 × 2.500 = 15.00
    assert values(across)[1] == (0.0, 14.0, 31.0)
    # The other component of each is 0 in the other frame: no girder force, one zero load at the beam top.
    zero = bearing_table(p, frame[Direction.TRANSVERSE], cases["BR"])
    assert values(zero)[1] == (0.0, 0.0, 0.0) and zero.girders == ()
    assert points(zero) == [(NodeRole.CAP_TOP, 0.0, 0.0, 0.0)]
    assert values(bearing_table(p, frame[Direction.LONGITUDINAL], cases["WG"]))[1] == (0.0, 0.0, 0.0)


def test_the_earthquake_signs_the_horizontal_forces():
    p, frame, cases = frames()
    along = bearing_table(p, frame[Direction.LONGITUDINAL], cases["EQ1"], Decimal(-1))
    assert values(along)[1] == (0.0, -750.0, 0.0)  # toward the origin side; no height along the track
    across = bearing_table(p, frame[Direction.TRANSVERSE], cases["EQ1"], Decimal(1))
    # 400.00 × 1.000 + 350.00 × 1.200 = 400.00 + 420.00
    assert values(across)[1] == (0.0, 750.0, 820.0)


def pedestal_pier():
    data = document()
    dims = data["下部構造"]["寸法"]
    dims["側面"].update(B2=0.5, B3=1.0)
    dims["正面"].update(W3=7.0)
    dims["高さ"]["H1"] = 0.3
    return pier(data)


def test_each_bearing_acts_at_the_seat_of_its_girder():
    # Decision 80: the pedestal −0.350 ± 0.500 holds the origin bearing line −0.325, not the end one +0.675.
    p, frame, cases = frames(pedestal_pier())
    longitudinal = frame[Direction.LONGITUDINAL]
    assert longitudinal.seats == (NodeRole.PEDESTAL_TOP, NodeRole.CAP_TOP)
    table = bearing_table(p, longitudinal, cases["L"])
    # Beam top: 250 × 0.675 = 168.75. Pedestal top, the lever from its centre: 300 × (−0.325 + 0.350) = 7.50.
    # About the column axis as before: 168.75 + 7.50 + 300 × (−0.350) = 71.25.
    assert [(s.anchor, [r.arm.value for r in s.rows], s.n.value, s.m.value) for s in table.seats] == [
        (NodeRole.CAP_TOP, [0.675], 250.0, 168.75), (NodeRole.PEDESTAL_TOP, [0.025], 300.0, 7.5)]
    assert points(table) == [(NodeRole.CAP_TOP, 250.0, 0.0, 168.75), (NodeRole.PEDESTAL_TOP, 300.0, 0.0, 7.5)]
    # Across the track the pedestal centre is at (7.0 − 9.0)/2 = −1.000: the origin bearing −3.800 is −2.800 from it.
    across = bearing_table(p, frame[Direction.TRANSVERSE], cases["L"])
    assert [(s.anchor, [r.arm.value for r in s.rows]) for s in across.seats] == [
        (NodeRole.CAP_TOP, [2.95]), (NodeRole.PEDESTAL_TOP, [-2.8])]


def test_a_seat_without_a_load_has_no_point():
    p, frame, cases = frames(pedestal_pier())
    table = bearing_table(p, frame[Direction.LONGITUDINAL], cases["BR"])  # 20.00 at the origin, 15.00 at the end
    assert [s.anchor for s in table.seats] == [NodeRole.CAP_TOP, NodeRole.PEDESTAL_TOP]
    only = BasicCase("X", "X", SpringTerm.SHORT, (BearingAction(BearingRef(Side.END, 2), vertical=Decimal("10.00")),
                                                 BearingAction(BearingRef(Side.ORIGIN, 1))))
    table = bearing_table(p, frame[Direction.LONGITUDINAL], only)
    assert [s.anchor for s in table.seats] == [NodeRole.CAP_TOP]  # nothing on the pedestal
    assert points(table) == [(NodeRole.CAP_TOP, 10.0, 0.0, 6.75)]


def test_across_the_track_the_horizontal_forces_act_at_the_girder_levels():
    # Decision 80 (0720): H at the level of its girder, h1 + h2 = 2.750 above the seat, with H × (y − 2.750); N and
    # N × lever at the seat. Two bearings of a girder at different heights give no common height.
    p, frame, _ = frames(girder_levels=(FORCE(1), FORCE(1)))
    across = frame[Direction.TRANSVERSE]
    case = BasicCase("H", "H", SpringTerm.SHORT, (
        BearingAction(BearingRef(Side.ORIGIN, 1), vertical=Decimal("100.00"), transverse=Decimal("10.00"),
                      transverse_height=Decimal("2.750")),
        BearingAction(BearingRef(Side.ORIGIN, 2), transverse=Decimal("20.00"), transverse_height=Decimal("3.750"))))
    table = bearing_table(p, across, case)
    (girder,) = table.girders
    assert (girder.anchor, girder.h.value, girder.height, girder.m.value) == (NodeRole.GIRDER_ORIGIN, 30.0, None, 20.0)
    level = across.node(NodeRole.GIRDER_ORIGIN).number
    assert [(point.node, point.n.value, point.h.value, point.m.value) for point in table.points] == [
        (across.node(NodeRole.CAP_TOP).number, 100.0, 0.0, -380.0), (level, 0.0, 30.0, 20.0)]
    assert next(m for m in across.members if m.region is Region.GIRDER).start == level


def test_the_context_names_the_bearings_of_the_input():
    p = pier()
    context = load_model_context(p, Path("pre/input.json"))
    assert context.input_path == Path("pre/input.json")
    assert context.bearings[0] == BearingSlot(BearingRef(Side.ORIGIN, 1), Decimal("-3.800"))
    assert [slot.ref.slot for slot in context.bearings] == [1, 2, 3, 4, 1, 2]
    assert [slot.ref.side for slot in context.bearings] == [Side.ORIGIN] * 4 + [Side.END] * 2
    assert bearing_positions(p)[BearingRef(Side.END, 2)].value == 2.95

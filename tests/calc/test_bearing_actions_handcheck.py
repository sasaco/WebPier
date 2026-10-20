"""支承作用 → 橋脚天端の等価作用 by hand (decision 70): rows N × lever + H × y, the case the sums of the printed rows.

The test load model (addin_support) puts 300.00 / 250.00 kN on 起点側1 (支承位置 −3.800) and 終点側2 (+2.950);
current.json has f = 0.325 (origin) and 0.675 (end) and no pedestal.
"""

from decimal import Decimal
from pathlib import Path

from addin_support import chain, document, pier
from webpier.calc.bearing_actions import bearing_positions, bearing_table, load_model_context
from webpier.calc.frame import Direction, NodeRole, build_frame
from webpier.calc.materials import calculate_materials
from webpier.loadmodel import BearingRef, BearingSlot, Side


def frames(p=None):
    p, foundation, reaction, model = chain(p)
    built = {direction: build_frame(p, reaction.self_weight, foundation, calculate_materials(p), direction)
             for direction in Direction}
    return p, built, {case.id: case for case in model.cases}


def values(table):
    return [(row.n.value, row.arm.value, row.nm.value, row.h.value, row.y.value, row.hm.value, row.m.value)
            for row in table.rows], (table.n.value, table.h.value, table.m.value)


def test_vertical_along_the_track():
    p, frame, cases = frames()
    table = bearing_table(p, frame[Direction.LONGITUDINAL], cases["L"])
    # 300 × (−0.325) = −97.50; 250 × 0.675 = 168.75; Σ 550.00, 71.25
    assert values(table) == ([(300.0, -0.325, -97.5, 0.0, 0.0, 0.0, -97.5), (250.0, 0.675, 168.75, 0.0, 0.0, 0.0, 168.75)],
                             (550.0, 0.0, 71.25))
    seat = frame[Direction.LONGITUDINAL].node(NodeRole.CAP_TOP).number
    assert (table.point.node, table.point.n.value, table.point.h.value, table.point.m.value) == (seat, 550.0, 0.0,
                                                                                                 71.25)
    assert table.vertical


def test_vertical_across_the_track():
    p, frame, cases = frames()
    table = bearing_table(p, frame[Direction.TRANSVERSE], cases["L"])
    # 300 × (−3.800) = −1140.00; 250 × 2.950 = 737.50; Σ −402.50
    assert values(table)[1] == (550.0, 0.0, -402.5)
    assert [row.arm.value for row in table.rows] == [-3.8, 2.95]


def test_horizontal_forces_with_their_heights():
    p, frame, cases = frames()
    along = bearing_table(p, frame[Direction.LONGITUDINAL], cases["BR"])
    # 20.00 × 1.500 = 30.00; 15.00 × 1.500 = 22.50
    assert values(along) == ([(0.0, -0.325, 0.0, 20.0, 1.5, 30.0, 30.0), (0.0, 0.675, 0.0, 15.0, 1.5, 22.5, 22.5)],
                             (0.0, 35.0, 52.5))
    assert not along.vertical
    across = bearing_table(p, frame[Direction.TRANSVERSE], cases["WG"])
    # 8.00 × 2.000 = 16.00; 6.00 × 2.500 = 15.00
    assert values(across)[1] == (0.0, 14.0, 31.0)
    # The other component of each is 0 in the other frame.
    assert values(bearing_table(p, frame[Direction.TRANSVERSE], cases["BR"]))[1] == (0.0, 0.0, 0.0)
    assert values(bearing_table(p, frame[Direction.LONGITUDINAL], cases["WG"]))[1] == (0.0, 0.0, 0.0)


def test_the_earthquake_signs_the_horizontal_forces():
    p, frame, cases = frames()
    along = bearing_table(p, frame[Direction.LONGITUDINAL], cases["EQ1"], Decimal(-1))
    assert values(along)[1] == (0.0, -750.0, 0.0)  # toward the origin side; no height along the track
    across = bearing_table(p, frame[Direction.TRANSVERSE], cases["EQ1"], Decimal(1))
    # 400.00 × 1.000 + 350.00 × 1.200 = 400.00 + 420.00
    assert values(across)[1] == (0.0, 750.0, 820.0)


def test_the_moment_moves_to_a_pedestal_seat():
    data = document()
    dims = data["下部構造"]["寸法"]
    dims["側面"].update(B2=0.5, B3=1.0)
    dims["正面"].update(W3=7.0)
    dims["高さ"]["H1"] = 0.3
    p, frame, cases = frames(pier(data))
    longitudinal = frame[Direction.LONGITUDINAL]
    assert longitudinal.bearing_offset.value == -0.35
    table = bearing_table(p, longitudinal, cases["L"])
    # M′ = M − N × offset = 71.25 − 550.00 × (−0.350) = 263.75 at the pedestal top
    assert (table.m.value, table.point.m.value) == (71.25, 263.75)
    assert table.point.anchor is NodeRole.PEDESTAL_TOP


def test_the_context_names_the_bearings_of_the_input():
    p = pier()
    context = load_model_context(p, Path("pre/input.json"))
    assert context.input_path == Path("pre/input.json")
    assert context.bearings[0] == BearingSlot(BearingRef(Side.ORIGIN, 1), Decimal("-3.800"))
    assert [slot.ref.slot for slot in context.bearings] == [1, 2, 3, 4, 1, 2]
    assert [slot.ref.side for slot in context.bearings] == [Side.ORIGIN] * 4 + [Side.END] * 2
    assert bearing_positions(p)[BearingRef(Side.END, 2)].value == 2.95

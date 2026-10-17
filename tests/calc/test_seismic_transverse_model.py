"""0720 analysis model: Example2 11 pp.11-1 to 11-7 (transverse frame, girder level, column-base micro member)."""

import pytest

from reaction_support import pier
from seismic_transverse_support import S11, chain, seismic
from webpier.calc.frame import Direction, NodeRole, Region
from webpier.core.errors import InputError

MODEL = S11["model"]


def test_11_1_nodes_and_segment_lengths():
    frame = seismic().frame
    assert frame.direction is Direction.TRANSVERSE
    assert [node.number for node in frame.nodes] == MODEL["nodes"]["node_numbers_top_to_bottom"]
    segments = MODEL["nodes"]["segment_lengths"]
    assert [(m.start, m.end) for m in frame.members] == [(s["from_node"], s["to_node"]) for s in segments]
    assert [m.height.value for m in frame.members] == [s["value"] for s in segments]  # 2.750, 2.000 .. 1.350
    overall = {(o["from_node"], o["to_node"]): o["value"] for o in MODEL["nodes"]["overall_dimensions"]}
    y = {node.number: node.y.value for node in frame.nodes}
    assert y[1] - y[8] == overall[(1, 8)] == 13.05
    assert round(y[1] - y[5], 3) == overall[(1, 5)] and round(y[6] - y[8], 3) == overall[(6, 8)]


def test_11_1_girder_level_above_the_beam_top():
    # Node 1 is the girder level h1 + h2 above the bearing seat: 0.150 + 2.600 = 0.100 + 2.650 = 2.750
    # (07 7-18 y1). Both girders are at the same level here, so one node carries both roles.
    frame = seismic().frame
    top = frame.node(NodeRole.GIRDER_ORIGIN)
    assert top is frame.node(NodeRole.GIRDER_END)
    assert (top.number, top.x.value, top.y.value) == (1, 0.0, 13.05)
    (girder,) = [m for m in frame.members if m.region is Region.GIRDER]
    assert (girder.start, girder.end, girder.rigid) == (1, 2, True)
    assert frame.node(NodeRole.CAP_TOP).number == 2 and frame.bearing_seat.number == 2


def test_11_1_micro_member_is_cut_from_the_column():
    # CONTEXT.md 柱下端の微小部材: 0.010 m is cut from H4 = 4.900, never added to it (4.890 + 0.010).
    frame = seismic().frame
    column = [m for m in frame.members if m.region in (Region.COLUMN, Region.COLUMN_BASE)]
    assert [(m.region, m.height.value) for m in column] == [(Region.COLUMN, 4.89), (Region.COLUMN_BASE, 0.01)]
    assert frame.node(NodeRole.MICRO_TOP).number == 5 and frame.node(NodeRole.FOOTING_TOP).number == 6
    assert frame.node(NodeRole.FOOTING_CENTROID).number == 7
    # The column line of the D1 line load runs from the beam top to the footing top, not over the girder.
    assert [m.number for m in frame.column_line] == [2, 3, 4, 5]


def test_11_5_only_the_micro_member_has_a_section():
    frame = seismic().frame
    rows = MODEL["elements"]["rows"]
    assert [m.number for m in frame.members] == [row["element"] for row in rows]
    assert [(m.start, m.end) for m in frame.members] == [(row["i_node"], row["j_node"]) for row in rows]
    assert [m.rigid for m in frame.members] == [row["nonlinear"] == "剛域" for row in rows]
    micro = frame.members[4]
    # 11-6 section 1: 2700 wide (B6, normal to the plane) × 4500 high (W6, across the track), Ec 26.5 kN/mm2.
    width, height = (next(item["value"] for item in MODEL["section_1"]["dimensions"] if item["key"] == key)
                     for key in ("width", "height"))
    assert (micro.section.width.value * 1000, micro.section.depth.value * 1000) == (width, height)
    assert micro.material.modulus.value * 10 == 26.5  # 2.65 × 10^7 kN/m2


def test_11_7_node_springs_are_the_short_term_0500_springs():
    frame = seismic().frame
    springs = {item["key"]: item["value"] for item in MODEL["springs"]["node_springs"]}
    assert frame.support.node == 8
    assert frame.support.short_term.ks.value == springs["node8_horizontal"] == 8525475
    assert frame.support.short_term.kv.value == springs["node8_vertical"] == 25576488


def test_the_0620_frame_is_not_changed():
    _, _, transverse, result = chain()
    assert len(transverse.frame.nodes) == 6 and len(result.frame.nodes) == 8
    assert all(not m.rigid for m in transverse.frame.members if m.region is Region.COLUMN)
    assert all(m.region is not Region.GIRDER for m in transverse.frame.members)


def test_column_shorter_than_the_micro_member_stops_0720():
    with pytest.raises(InputError, match="H4"):
        seismic(pier(**{"下部構造/寸法/高さ/H4": 0.01}))

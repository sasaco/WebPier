"""0710 analysis model: Example2 10 pp.10-1 to 10-7 (frame with the column-base micro member)."""

import pytest

from reaction_support import pier
from seismic_longitudinal_support import S10, chain, seismic
from webpier.calc.frame import Direction, NodeRole, Region
from webpier.core.errors import InputError

MODEL = S10["model"]


def test_10_1_nodes_and_segment_lengths():
    frame = seismic().frame
    assert frame.direction is Direction.LONGITUDINAL
    assert [node.number for node in frame.nodes] == MODEL["nodes"]["node_numbers_top_to_bottom"]
    segments = MODEL["nodes"]["segment_lengths"]
    assert [(m.start, m.end) for m in frame.members] == [(s["from_node"], s["to_node"]) for s in segments]
    assert [m.height.value for m in frame.members] == [s["value"] for s in segments]  # 2.000 .. 1.350
    overall = {(o["from_node"], o["to_node"]): o["value"] for o in MODEL["nodes"]["overall_dimensions"]}
    y = {node.number: node.y.value for node in frame.nodes}
    assert y[1] - y[7] == overall[(1, 7)] == 10.3
    assert round(y[1] - y[4], 3) == overall[(1, 4)] and round(y[5] - y[7], 3) == overall[(5, 7)]


def test_10_1_micro_member_is_cut_from_the_column():
    # CONTEXT.md 柱下端の微小部材: 0.010 m is cut from H4 = 4.900, never added to it (4.890 + 0.010).
    frame = seismic().frame
    column = [m for m in frame.members if m.region in (Region.COLUMN, Region.COLUMN_BASE)]
    assert [(m.region, m.height.value) for m in column] == [(Region.COLUMN, 4.89), (Region.COLUMN_BASE, 0.01)]
    assert frame.node(NodeRole.MICRO_TOP).number == 4 and frame.node(NodeRole.FOOTING_TOP).number == 5
    assert frame.node(NodeRole.CAP_TOP).number == 1 and frame.node(NodeRole.FOOTING_CENTROID).number == 6


def test_10_5_only_the_micro_member_has_a_section():
    frame = seismic().frame
    rows = MODEL["elements"]["rows"]
    assert [m.number for m in frame.members] == [row["element"] for row in rows]
    assert [(m.start, m.end) for m in frame.members] == [(row["i_node"], row["j_node"]) for row in rows]
    assert [m.rigid for m in frame.members] == [row["nonlinear"] == "剛域" for row in rows]
    micro = frame.members[3]
    # 10-6 section 1: 4500 × 2700 mm (width normal to the plane, height along the track), Ec 26.5 kN/mm2.
    width, height = (next(item["value"] for item in MODEL["section_1"]["dimensions"] if item["key"] == key)
                      for key in ("width", "height"))
    assert (micro.section.width.value * 1000, micro.section.depth.value * 1000) == (width, height)
    assert micro.material.modulus.value * 10 == 26.5  # 2.65 × 10^7 kN/m2


def test_10_7_node_springs_are_the_short_term_0500_springs():
    # 10-7 prints the horizontal and vertical springs at node 7 = Ks, Kv of 0500 with ρ = 1.0 (short term).
    frame = seismic().frame
    springs = {item["key"]: item["value"] for item in MODEL["springs"]["node_springs"]}
    assert frame.support.node == 7
    assert frame.support.short_term.ks.value == springs["node7_horizontal"] == 8525475
    assert frame.support.short_term.kv.value == springs["node7_vertical"] == 25576488


def test_the_0610_frame_is_not_changed():
    _, _, longitudinal, result = chain()
    assert len(longitudinal.frame.nodes) == 6 and len(result.frame.nodes) == 7
    assert all(not m.rigid for m in longitudinal.frame.members if m.region is Region.COLUMN)


def test_column_shorter_than_the_micro_member_stops_0710():
    p = pier(**{"下部構造/寸法/高さ/H4": 0.01})
    with pytest.raises(InputError, match="H4"):
        seismic(p)

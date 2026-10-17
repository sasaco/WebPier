"""The model figure and the load diagrams draw the Frame: positions, labels and dimensions come from it.

Every expectation is taken from the Frame (node coordinates, member heights)
and the input, never from the drawing code: one isotropic scale maps each node
to its circle, every label is drawn once without overlapping another, and the
dimension texts are the printed member heights and node heights.
"""

from __future__ import annotations

import itertools
from collections import Counter
from dataclasses import replace

import pytest
from gridlayoutpdf import Circle, LayoutContext, LayoutOverflowError, Line, Polyline, Text, command_bounds, measure_block

from frame_report_cases import CASES, chain, pier_input, text
from webpier.calc.foundation import calculate_foundation
from webpier.calc.frame import Direction, NodeRole, Region, build_frame
from webpier.calc.materials import calculate_materials
from webpier.reporting.figures import (
    AxialGlyph, DistributedGlyph, FrameFigure, HorizontalDimension, LoadDiagram, PointGlyph,
    footing_dimensions, pier_outline,
)
from webpier.reporting.fonts import load_fonts
from webpier.reporting.styles import REPORT_STYLE, report_profile

FONTS = load_fonts()


def context() -> LayoutContext:
    return LayoutContext(FONTS, report_profile(), REPORT_STYLE)


def commands(block, width: float = 528):
    measured = measure_block(block, context(), width)
    return [command for part in measured.parts for command in part.commands]


def frames(case: str):
    pier, reaction, longitudinal, seismic = chain(case)
    return pier, reaction, {"0610": longitudinal.frame, "0710": seismic.frame}


def figure_for(case: str, stage: str, **options) -> FrameFigure:
    pier, reaction, by_stage = frames(case)
    frame = by_stage[stage]
    return FrameFigure(frame, pier_outline(pier, frame), **options)


def node_circles(drawn) -> list[Circle]:
    return [c for c in drawn if isinstance(c, Circle) and c.fill == (0, 0, 0)]


def texts(drawn, size: float | None = None, turned: bool | None = None) -> list[Text]:
    return [c for c in drawn if isinstance(c, Text) and (size is None or abs(c.style.size - size) < .01)
            and (turned is None or (c.quarter_turns == 1) == turned)]


@pytest.mark.parametrize("stage", ["0610", "0710"])
@pytest.mark.parametrize("case", list(CASES))
def test_nodes_are_drawn_at_one_isotropic_scale_of_their_coordinates(case: str, stage: str):
    pier, _, by_stage = frames(case)
    frame = by_stage[stage]
    drawn = commands(FrameFigure(frame, pier_outline(pier, frame)))
    circles = node_circles(drawn)
    assert len(circles) == len(frame.nodes)
    # Two nodes far apart define the transform; every node must follow it.
    top, base = frame.node(NodeRole.CAP_TOP), frame.node(NodeRole.FOOTING_BOTTOM)
    first, last = circles[top.number - 1], circles[base.number - 1]
    scale = (last.y - first.y) / (top.y.value - base.y.value)
    assert scale > 0
    for node, circle in zip(frame.nodes, circles, strict=True):
        assert circle.x == pytest.approx(first.x + (node.x.value - top.x.value) * scale, abs=1e-6)
        assert circle.y == pytest.approx(first.y - (node.y.value - top.y.value) * scale, abs=1e-6)
    # Members join their node circles; rigid members are drawn thicker than members with a section.
    member_lines = [c for c in drawn if isinstance(c, Line) and c.width in (2.0, .8) and not c.dash]
    assert len(member_lines) == len(frame.members)
    for member, line in zip(frame.members, member_lines, strict=True):
        a, b = circles[member.start - 1], circles[member.end - 1]
        assert (line.x1, line.y1, line.x2, line.y2) == pytest.approx((a.x, a.y, b.x, b.y))
        assert line.width == (2.0 if member.rigid else .8)


@pytest.mark.parametrize("stage", ["0610", "0710"])
@pytest.mark.parametrize("case", list(CASES))
def test_labels_and_dimension_texts_are_the_frame_values_drawn_once_without_overlap(case: str, stage: str):
    pier, _, by_stage = frames(case)
    frame = by_stage[stage]
    figure = FrameFigure(frame, pier_outline(pier, frame))
    drawn = commands(figure)
    upright = [c.text for c in texts(drawn, 9.9, turned=False) if c.style.font == "heading"]
    assert Counter(upright) == Counter(str(node.number) for node in frame.nodes)
    boxed = [c.text for c in texts(drawn, 8.0)]
    assert Counter(boxed) == Counter(str(member.number) for member in frame.members)
    top = max(frame.nodes, key=lambda node: node.y.value)
    expected = [text(m.height) for m in frame.members if m.height.value > 0]
    expected += [text(frame.pier_height), text(frame.node(NodeRole.FOOTING_TOP).y), text(top.y)]
    assert Counter(c.text for c in texts(drawn, turned=True)) == Counter(expected)
    assert figure.texts() == tuple(c.text for c in drawn if isinstance(c, Text))
    boxes = [command_bounds(c, FONTS) for c in drawn if isinstance(c, Text)]
    for a, b in itertools.combinations(boxes, 2):
        assert a.right <= b.x or b.right <= a.x or a.bottom <= b.y or b.bottom <= a.y


@pytest.mark.parametrize("case", list(CASES))
def test_each_vertical_dimension_spans_its_member_or_node_height(case: str):
    pier, _, by_stage = frames(case)
    frame = by_stage["0710"]
    drawn = commands(FrameFigure(frame, pier_outline(pier, frame)))
    circles = node_circles(drawn)
    scale = (circles[frame.node(NodeRole.FOOTING_BOTTOM).number - 1].y
             - circles[frame.node(NodeRole.CAP_TOP).number - 1].y) / frame.node(NodeRole.CAP_TOP).y.value
    vertical = [c for c in drawn if isinstance(c, Line) and c.width == .12 and c.x1 == c.x2 and abs(c.y2 - c.y1) > 0]
    spans = sorted(round(abs(c.y2 - c.y1) / scale, 6) for c in vertical)
    for member in frame.members:
        if member.height.value > 0 and member.height.value * scale >= 10:
            assert round(member.height.value, 6) in spans, member
    micro = next(m for m in frame.members if m.region is Region.COLUMN_BASE)
    assert micro.height.value == .01
    ring = [c for c in drawn if isinstance(c, Circle) and c.fill is None]
    a, b = circles[micro.start - 1], circles[micro.end - 1]
    assert [(c.x, c.y) for c in ring] == [pytest.approx(((a.x + b.x) / 2, (a.y + b.y) / 2))]


def test_outline_is_the_physical_shape_in_the_same_transform():
    pier, reaction, by_stage = frames("asymmetric")
    frame = by_stage["0610"]
    outline = pier_outline(pier, frame)
    s = pier.substructure
    footing = max(outline.polygons, key=lambda polygon: max(x for x, _ in polygon) - min(x for x, _ in polygon))
    width = sum(s.b[i].value for i in (7, 8, 9))
    assert min(x for x, _ in footing) == pytest.approx(-width / 2) and max(x for x, _ in footing) == pytest.approx(width / 2)
    axis = frame.node(NodeRole.CAP_TOP).x.value
    column = next(p for p in outline.polygons if {round(y, 6) for _, y in p} == {2.7, 7.6})
    assert sorted({round(x, 6) for x, _ in column}) == [round(axis - s.b[6].value / 2, 6), round(axis + s.b[6].value / 2, 6)]
    assert max(y for p in outline.polygons for _, y in p) == pytest.approx(frame.node(NodeRole.CAP_TOP).y.value)
    across = build_frame(pier, reaction.self_weight, calculate_foundation(pier), calculate_materials(pier),
                         Direction.TRANSVERSE)
    transverse = pier_outline(pier, across)
    assert max(x for p in transverse.polygons for x, _ in p) == pytest.approx(sum(s.w[i].value for i in (7, 8, 9)) / 2)
    beam = max(transverse.polygons, key=lambda p: max(y for _, y in p))
    assert max(x for x, _ in beam) - min(x for x, _ in beam) == pytest.approx(s.w[1].value)
    drawn = commands(FrameFigure(frame, outline))
    dashed = [c for c in drawn if isinstance(c, Line) and c.dash]
    assert len(dashed) == sum(len(polygon) for polygon in outline.polygons)
    pedestal_pier, _, pedestal = frames("pedestal")
    top = max(y for p in pier_outline(pedestal_pier, pedestal["0610"]).polygons for _, y in p)
    assert top == pytest.approx(pedestal["0610"].node(NodeRole.PEDESTAL_TOP).y.value)


def test_footing_dimensions_springs_and_bearings_are_drawn_from_their_printed_values():
    pier, reaction, by_stage = frames("asymmetric")
    frame = by_stage["0610"]
    horizontal = footing_dimensions(pier, frame, reaction.self_weight.footing_length)
    s = pier.substructure
    assert [(d.text, d.row) for d in horizontal] == [(text(s.b[7]), 0), (text(s.b[8]), 0), (text(s.b[9]), 0),
                                                    (text(reaction.self_weight.footing_length), 1)]
    figure = FrameFigure(frame, pier_outline(pier, frame), horizontal=horizontal, bearings=("M", "F"))
    drawn = commands(figure)
    upright = [c.text for c in texts(drawn, turned=False)]
    for d in horizontal:
        assert upright.count(d.text) == 1
    assert "Kv" not in upright and upright.count("K") == 3  # K and its 6.5 pt subscript are separate runs
    pieces = "".join(c.text for c in drawn if isinstance(c, Text) and c.style.font == "body")
    assert pieces == "KvKsKrMF"
    assert figure.texts() == tuple(c.text for c in drawn if isinstance(c, Text))


def test_a_figure_too_small_for_its_labels_is_a_layout_error():
    with pytest.raises((LayoutOverflowError, ValueError)):
        commands(figure_for("current", "0710", height=60))
    with pytest.raises(ValueError, match="footing bottom"):
        pier, _, by_stage = frames("current")
        frame = by_stage["0610"]
        moved = replace(frame, nodes=tuple(replace(n, y=replace(n.y, value=n.y.value + 1)) for n in frame.nodes))
        FrameFigure(moved, pier_outline(pier, frame)).texts()
    with pytest.raises(ValueError):
        HorizontalDimension(1.0, 1.0, "0.000", 0)


def _arrow_tips(drawn) -> list[tuple[float, float]]:
    return [(c.points[1].x, c.points[1].y) for c in drawn if isinstance(c, Polyline) and len(c.points) == 3]


@pytest.mark.parametrize("sign", [1, -1])
def test_load_glyphs_point_in_the_direction_of_their_sign(sign: int):
    _, _, by_stage = frames("current")
    frame = by_stage["0710"]
    top, centroid = frame.node(NodeRole.CAP_TOP), frame.node(NodeRole.FOOTING_CENTROID)
    glyphs = (PointGlyph(top.number, "N", sign, "N"), PointGlyph(top.number, "H", sign, "H"),
              PointGlyph(centroid.number, "P", sign, "P"))
    drawn = commands(LoadDiagram(frame, glyphs), 240)
    dots = node_circles(drawn)
    node = dots[top.number - 1]
    shafts = [c for c in drawn if isinstance(c, Line) and c.width == .8 and not c.dash][len(frame.members):]
    n_shaft, h_shaft, p_shaft = shafts
    # N: downward (+) ends at the node; upward (−) starts at it.
    assert (n_shaft.y2 > n_shaft.y1) == (sign > 0) and n_shaft.x1 == n_shaft.x2 == node.x
    # H: toward +x (→) for +, toward −x (←) for −, ending at the node.
    assert (h_shaft.x2 > h_shaft.x1) == (sign > 0)
    assert (h_shaft.x2, h_shaft.y2) == pytest.approx((node.x - sign * 1, node.y))
    assert (p_shaft.y2 > p_shaft.y1) == (sign > 0)
    assert [c.text for c in drawn if isinstance(c, Text)] == ["N", "H", "P"]


def test_moment_arc_turns_clockwise_for_a_positive_moment():
    _, _, by_stage = frames("current")
    frame = by_stage["0610"]
    top = frame.node(NodeRole.CAP_TOP).number
    for sign, clockwise in ((1, True), (-1, False)):
        drawn = commands(LoadDiagram(frame, (PointGlyph(top, "M", sign, "M"),)), 240)
        arc = next(c for c in drawn if isinstance(c, Polyline) and len(c.points) > 3)
        centre = node_circles(drawn)[top - 1]
        # In page coordinates (y down) a clockwise turn over the top runs from left to right.
        assert (arc.points[0].x < centre.x < arc.points[-1].x) == clockwise
        assert all(p.y <= centre.y + 1e-9 for p in arc.points)


def test_axial_and_distributed_glyphs_follow_their_members():
    _, _, by_stage = frames("pedestal")
    frame = by_stage["0710"]
    column_line = [m.number for m in frame.column_line]
    beam, haunch = (next(m for m in frame.members if m.region is region) for region in (Region.BEAM, Region.HAUNCH))
    glyphs = (AxialGlyph(tuple(column_line), "q"),
              DistributedGlyph(((beam.number, -2.0, -2.0), (haunch.number, -2.0, -1.0)),
                               ((beam.number, .5, "Hw1"), (haunch.number, 1.0, "Hw2"))))
    diagram = LoadDiagram(frame, glyphs)
    drawn = commands(diagram, 240)
    dashed = [c for c in drawn if isinstance(c, Line) and c.dash]
    assert len(dashed) == len(column_line)
    dots = node_circles(drawn)
    for member, line in zip(frame.column_line, dashed, strict=True):
        assert line.y1 == pytest.approx(dots[member.start - 1].y) and line.y2 == pytest.approx(dots[member.end - 1].y)
    outer = [c for c in drawn if isinstance(c, Line) and c.width == .5]
    beam_outer = outer[0]
    haunch_outer = outer[1]
    # The beam intensity is twice the haunch-bottom one: the outer edge is twice as far from the base line.
    base = dots[beam.start - 1].x + 6
    assert (beam_outer.x1 - base) == pytest.approx(2 * (haunch_outer.x2 - base))
    assert diagram.texts() == ("q", "Hw1", "Hw2")
    assert [c.text for c in drawn if isinstance(c, Text)] == ["q", "Hw1", "Hw2"]
    with pytest.raises(ValueError):
        PointGlyph(1, "X", 1, "X")
    with pytest.raises(ValueError):
        commands(LoadDiagram(frame, (PointGlyph(99, "N", 1, "N"),)), 240)


def test_the_figure_is_deterministic_and_independent_of_the_input_object():
    first = commands(figure_for("pedestal", "0610"))
    pier_input.cache_clear() if hasattr(pier_input, "cache_clear") else None
    assert commands(figure_for("pedestal", "0610")) == first


def test_the_pier_height_spans_the_beam_top_to_the_footing_top():
    pier, _, by_stage = frames("pedestal")
    frame = by_stage["0710"]
    drawn = commands(FrameFigure(frame, pier_outline(pier, frame)))
    circles = node_circles(drawn)
    top, footing = (circles[frame.node(role).number - 1].y for role in (NodeRole.CAP_TOP, NodeRole.FOOTING_TOP))
    lines = [c for c in drawn if isinstance(c, Line) and c.width == .12 and c.x1 == c.x2]
    assert any(c.y1 == pytest.approx(top) and c.y2 == pytest.approx(footing) for c in lines)
    assert text(frame.pier_height) == "7.600"



@pytest.mark.parametrize("stage", ["0620", "0720"])
@pytest.mark.parametrize("case", ["current", "curve", "pedestal", "asymmetric", "haunch_ground", "merged"])
def test_transverse_frames_draw_their_coordinates_labels_and_heights(case: str, stage: str):
    """Across the track: W sizes, the girder level above the seat (0720 node 1), the micro member."""
    from frame_report_cases import transverse_chain

    pier, _, transverse, seismic = transverse_chain(case)
    frame = transverse.frame if stage == "0620" else seismic.frame
    figure = FrameFigure(frame, pier_outline(pier, frame))
    drawn = commands(figure)
    circles = node_circles(drawn)
    top, base = frame.node(NodeRole.CAP_TOP), frame.node(NodeRole.FOOTING_BOTTOM)
    scale = (circles[base.number - 1].y - circles[top.number - 1].y) / (top.y.value - base.y.value)
    for node, circle in zip(frame.nodes, circles, strict=True):
        assert circle.x == pytest.approx(circles[top.number - 1].x + (node.x.value - top.x.value) * scale, abs=1e-6)
        assert circle.y == pytest.approx(circles[top.number - 1].y - (node.y.value - top.y.value) * scale, abs=1e-6)
    highest = max(frame.nodes, key=lambda node: node.y.value)
    expected = [text(m.height) for m in frame.members if m.height.value > 0]
    expected += [text(frame.pier_height), text(frame.node(NodeRole.FOOTING_TOP).y), text(highest.y)]
    assert Counter(c.text for c in texts(drawn, turned=True)) == Counter(expected)
    if stage == "0720":
        assert NodeRole.GIRDER_ORIGIN in highest.roles and highest.number == 1
    boxes = [command_bounds(c, FONTS) for c in drawn if isinstance(c, Text)]
    for a, b in itertools.combinations(boxes, 2):
        assert a.right <= b.x or b.right <= a.x or a.bottom <= b.y or b.bottom <= a.y
    width = sum(pier.substructure.w[i].value for i in (7, 8, 9))
    footing = next(p for p in pier_outline(pier, frame).polygons if min(y for _, y in p) == 0)
    assert max(x for x, _ in footing) - min(x for x, _ in footing) == pytest.approx(width)

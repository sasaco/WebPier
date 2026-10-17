"""Native point artwork and simple dynamic frame diagrams, with fixed text size."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
import math
from typing import Any

from gridlayoutpdf import (
    Arrow, Circle, Figure, Label, LayoutContext, LayoutOverflowError, Line, MeasuredBlock,
    Polyline, Rectangle, Text, command_bounds, measure_block,
)

from .styles import HEADING, grid_units

from ..frame_outline import TextExtent, build_outline, dimension_text, fit_frame, frame_dimensions


def figure(width: float, height: float, *items: Line | Polyline | Rectangle | Circle | Text | Arrow | Label,
           block_id: str = "") -> Figure:
    return Figure(grid_units(width), grid_units(height), *items, block_id=block_id)


@dataclass(frozen=True)
class Node:
    key: str
    x: float
    y: float

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key:
            raise ValueError("node key must be nonempty")
        for value in (self.x, self.y):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("node coordinates must be finite")


@dataclass(frozen=True)
class FrameDiagram:
    nodes: tuple[Node, ...]
    members: tuple[tuple[str, str], ...]
    width: float = 240
    height: float = 180
    block_id: str = "frame-diagram"

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        grid_units(self.width)
        grid_units(self.height)
        if not self.nodes or len({node.key for node in self.nodes}) != len(self.nodes):
            raise ValueError("frame nodes must have unique keys")
        if min(self.width, self.height) <= 48:
            raise ValueError("frame must leave 24 pt around the artwork")
        minimum_x, maximum_x = min(node.x for node in self.nodes), max(node.x for node in self.nodes)
        minimum_y, maximum_y = min(node.y for node in self.nodes), max(node.y for node in self.nodes)
        span_x, span_y = maximum_x - minimum_x, maximum_y - minimum_y
        if not math.isfinite(span_x + span_y):
            raise ValueError("frame coordinate range is not finite")
        scale = min((self.width - 48) / (span_x or 1), (self.height - 48) / (span_y or 1))
        positions = {node.key: ((self.width - span_x * scale) / 2 + (node.x - minimum_x) * scale,
                               (self.height - span_y * scale) / 2 + (maximum_y - node.y) * scale)
                     for node in self.nodes}
        commands: list[Line | Text | Rectangle] = []
        for start, end in self.members:
            if start not in positions or end not in positions:
                raise ValueError("member references an absent node")
            commands.append(Line(*positions[start], *positions[end], width=.48))
        label_bounds = []
        for node in self.nodes:
            x, y = positions[node.key]
            commands.append(Rectangle(x - .6, y - .6, 1.2, 1.2, stroke_width=.12))
            for dx, dy in ((4, -4), (4, 10), (-14, -4), (-14, 10)):
                command = Text(x + dx, y + dy, node.key, HEADING)
                bounds = command_bounds(command, context.fonts)
                if bounds.x < 0 or bounds.y < 0 or bounds.right > self.width or bounds.bottom > self.height:
                    continue
                if any(bounds.x < other.right + 1 and bounds.right + 1 > other.x
                       and bounds.y < other.bottom + 1 and bounds.bottom + 1 > other.y for other in label_bounds):
                    continue
                commands.append(command)
                label_bounds.append(bounds)
                break
            else:
                raise LayoutOverflowError(f"{self.block_id}: node label {node.key} has no readable position",
                                          block_id=self.block_id)
        return measure_block(figure(self.width, self.height, *commands, block_id=self.block_id),
                             context, available_width)


def frame_diagram(nodes: Sequence[Node], members: Sequence[tuple[str, str]], *,
                  width: float = 240, height: float = 180, block_id: str = "frame-diagram") -> FrameDiagram:
    return FrameDiagram(tuple(nodes), tuple(members), width, height, block_id)


def outline_segment(first: tuple[float, float], second: tuple[float, float]) -> list[Line]:
    """One dashed physical-outline edge (2 pt on, 2 pt off from its start)."""
    return [Line(*first, *second, .35, dash=(2, 2))] if first != second else []


def _white_backing(bounds: tuple[float, float, float, float]) -> Rectangle:
    """An opaque white mask, 1.5 pt beyond a label, painted without an outline."""
    left, top, right, bottom = bounds
    return Rectangle(left - 1.5, top - 1.5, right - left + 3, bottom - top + 3, fill=(1, 1, 1), stroke=False)


@dataclass(frozen=True)
class PhysicalFrame:
    """Current physical outline, graph, dimensions and all identifier labels."""

    geometry: Mapping[str, float]
    frame: Mapping[str, Any]
    direction: str
    width: float = 528
    height: float = 432
    block_id: str = "physical-frame"

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        grid_units(self.width)
        grid_units(self.height)
        outline = build_outline(self.geometry, self.direction)

        def metrics(text: str, size: float) -> TextExtent:
            measured = context.fonts.measure(text, replace(HEADING, size=size))
            box = measured.bounds
            return TextExtent(measured.width, box.x, box.y, box.right, box.bottom)

        layout = fit_frame(outline, self.frame["nodes"], (12, 12, self.width - 12, self.height - 12),
                           members=self.frame["members"], dimensions=frame_dimensions(self.frame),
                           measure_text=metrics, preferred_axis_x=212, dimension_label_gap=8)
        commands: list[Line | Rectangle | Circle | Text] = []
        for component in outline.components:
            points = tuple(layout.point(*point) for point in component.points)
            for first, second in zip(points, (*points[1:], points[0]), strict=True):
                commands.extend(outline_segment(first, second))
        for box in layout.annotation_bounds[:len(layout.node_labels)]:
            commands.append(_white_backing(box))
        nodes = {node["id"]: node for node in self.frame["nodes"]}
        for member in self.frame["members"]:
            first, second = nodes[member["node_i"]], nodes[member["node_j"]]
            commands.append(Line(*layout.point(first["x"], first["y"]), *layout.point(second["x"], second["y"]),
                                 width=1.6 if member["behavior"] == "rigid" else .8))
        for node in self.frame["nodes"]:
            commands.append(Circle(*layout.point(node["x"], node["y"]), 1.7, fill=(0, 0, 0), stroke=False))
            x, y = layout.node_labels[node["id"]]
            value = str(node["id"])
            commands.append(Text(x - metrics(value, 9.9).advance, y, value, HEADING))
        for member in self.frame["members"]:
            x, y = layout.member_labels[member["id"]]
            value = str(member["id"])
            extent = metrics(value, 8)
            half_width = max(3.5, (extent.right - extent.left) / 2 + 1.08)
            commands.append(Rectangle(x - half_width, y - 7, 2 * half_width, 14, stroke_width=.35, fill=(1, 1, 1)))
            commands.append(Text(x - (extent.left + extent.right) / 2, y + 3, value, replace(HEADING, size=8)))
        for dimension, label_y in zip(layout.dimensions, layout.dimension_label_ys, strict=True):
            first_y, second_y = layout.y(dimension.top), layout.y(dimension.bottom)
            x = layout.dimension_xs[dimension.column]
            for y in (first_y, second_y):
                commands.append(Line(layout.extension_x, y, x + 3, y, .12))
            commands.append(Line(x, first_y, x, second_y, .12))
            for y, sign in ((first_y, 1), (second_y, -1)):
                commands.extend((Line(x, y, x - 2, y + sign * 4, .12), Line(x, y, x + 2, y + sign * 4, .12)))
            midpoint = (first_y + second_y) / 2
            if abs(label_y - midpoint) > 1:
                commands.append(Line(x - 3, midpoint, x - 7, label_y, .12))
            value = dimension_text(dimension)
            extent = metrics(value, 9.9)
            commands.append(Text(x - 7, label_y + (extent.left + extent.right) / 2, value, HEADING, quarter_turns=1))
        return measure_block(figure(self.width, self.height, *commands, block_id=self.block_id), context, available_width)


def physical_frame(geometry: Mapping[str, float], frame: Mapping[str, Any], direction: str, *,
                   width: float = 528, height: float = 432, block_id: str = "physical-frame") -> PhysicalFrame:
    """Snapshot supplied physical/model geometry; do not recalculate any results."""
    return PhysicalFrame(deepcopy(dict(geometry)), deepcopy(dict(frame)), direction, width, height, block_id)

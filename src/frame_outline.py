"""Physical pier elevations in metres, centred on the analysis column axis."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Mapping, Sequence

from reportlab.pdfbase import pdfmetrics

from .frame_model import parapet_center
from .reaction_report_layout import format_value


Point = tuple[float, float]
Bounds = tuple[float, float, float, float]


@dataclass(frozen=True)
class TextExtent:
    """Advance and conservative top-origin glyph bounds supplied by a renderer."""

    advance: float
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class Component:
    name: str
    points: tuple[Point, ...]


@dataclass(frozen=True)
class Outline:
    components: tuple[Component, ...]
    bounds: Bounds


def build_outline(geometry: Mapping[str, float], direction: str) -> Outline:
    """Use the 0600 physical shape rules, including the H1 parapet.

    Zero-height haunches and beams are absent rather than thickened for display.
    Input dimensions are already validated by the existing input parser.
    """
    if direction not in ("b", "w"):
        raise ValueError("direction must be 'b' or 'w'")
    a1, _, a3, a4, a5, a6, a7, a8, a9 = (
        float(geometry[f"{direction}{i}"]) for i in range(1, 10)
    )
    h2, h3, h4, h5, h6 = (float(geometry[f"h{i}"]) for i in range(2, 7))
    width = a7 + a8 + a9
    footing_center = (a9 - a7) / 2
    beam_center = (a5 - a4) / 2
    footing_top = h6 + h5
    shaft_top = footing_top + h4
    haunch_top = shaft_top + h3
    beam_top = haunch_top + h2
    lower_haunch_width = a1 - a4 - a5
    parts: list[Component] = []

    def add(name: str, left: float, right: float, bottom: float,
            upper_left: float, upper_right: float, top: float) -> None:
        parts.append(Component(name, ((left, bottom), (right, bottom),
                                      (upper_right, top), (upper_left, top))))

    base_left, base_right = footing_center - width / 2, footing_center + width / 2
    add("footing_base", base_left, base_right, 0.0, base_left, base_right, h6)
    if h5:
        add("footing_taper", base_left, base_right, h6, -a8 / 2, a8 / 2, footing_top)
    add("shaft", -a6 / 2, a6 / 2, footing_top, -a6 / 2, a6 / 2, shaft_top)
    beam_left, beam_right = beam_center - a1 / 2, beam_center + a1 / 2
    if h3:
        add("haunch", -lower_haunch_width / 2, lower_haunch_width / 2,
            shaft_top, beam_left, beam_right, haunch_top)
    if h2:
        add("beam", beam_left, beam_right, haunch_top, beam_left, beam_right, beam_top)
    if geometry["h1"]:
        center = parapet_center(geometry, direction)
        add("parapet", center - a3 / 2, center + a3 / 2, beam_top,
            center - a3 / 2, center + a3 / 2, beam_top + geometry["h1"])
    xs, ys = zip(*(point for part in parts for point in part.points))
    return Outline(tuple(parts), (min(xs), min(ys), max(xs), max(ys)))


@dataclass(frozen=True)
class Dimension:
    name: str
    top: float
    bottom: float
    column: int = 0

    @property
    def value(self) -> float:
        return self.top - self.bottom


def frame_dimensions(frame: Mapping) -> tuple[Dimension, ...]:
    """Resolve dimensions by semantic roles, independently of ID/array order."""
    nodes = {node["id"]: node for node in frame["nodes"]}
    roles = frame["node_ids"]
    specifications = (
        ("H1", "parapet_top", "parapet_base", 0),
        ("H2", "cap_top", "h2_h3", 0),
        ("H3", "h2_h3", "h3_h4", 0),
        ("H4", "h3_h4", "footing_top", 0),
        ("", "footing_top", "footing_centroid", 0),
        ("hG", "footing_centroid", "footing_bottom", 0),
        ("", "cap_top", "footing_top", 1),
        ("", "footing_top", "footing_bottom", 1),
    )
    return tuple(Dimension(name, nodes[roles[a]]["y"], nodes[roles[b]]["y"], column)
                 for name, a, b, column in specifications if a in roles and b in roles
                 and nodes[roles[a]]["y"] > nodes[roles[b]]["y"])


def dimension_text(dimension: Dimension) -> str:
    return format_value(dimension.value, "0.000")


@dataclass(frozen=True)
class FrameLayout:
    """Isotropic transform and ID-keyed, top-origin annotation positions."""

    scale: float
    axis_x: float
    bottom: float
    extension_x: float
    dimension_xs: tuple[float, float]
    node_labels: Mapping[int, Point]
    member_labels: Mapping[int, Point]
    dimension_label_ys: tuple[float, ...]
    annotation_bounds: tuple[Bounds, ...]
    dimensions: tuple[Dimension, ...]

    def point(self, x: float, z: float) -> Point:
        return self.axis_x + x * self.scale, self.y(z)

    def y(self, z: float) -> float:
        return self.bottom - z * self.scale


def _spread(desired: Sequence[float], half_sizes: Sequence[float], gap: float,
            lower: float, upper: float) -> list[float]:
    """Fan labels while preserving physical order and their measured sizes."""
    if not desired:
        return []
    if sum(2 * radius for radius in half_sizes) + gap * (len(desired) - 1) > upper - lower:
        raise ValueError("fit box is too small for readable annotations")
    centres = []
    for index, (target, radius) in enumerate(zip(desired, half_sizes)):
        minimum = lower + radius if not index else centres[-1] + half_sizes[index - 1] + radius + gap
        centres.append(max(target, minimum))
    centres[-1] = min(centres[-1], upper - half_sizes[-1])
    for index in range(len(centres) - 2, -1, -1):
        centres[index] = min(centres[index], centres[index + 1] - half_sizes[index + 1] - half_sizes[index] - gap)
    return centres


def _dimension_label_layout(dimensions: Sequence[Dimension], dimension_xs: Point,
                            scale: float, bottom: float, font: str, font_size: float,
                            ascent: float, descent: float,
                            label_limits: Point,
                            measure_text: Callable[[str, float], TextExtent] | None = None,
                            gap: float = 4.0) -> tuple[list[float], list[Bounds]]:
    extents = ([measure_text(dimension_text(d), font_size) for d in dimensions]
               if measure_text is not None else None)
    widths = ([extent.right - extent.left for extent in extents] if extents is not None else
              [pdfmetrics.stringWidth(dimension_text(d), font, font_size) for d in dimensions])
    label_ys = [bottom - (d.top + d.bottom) * scale / 2 for d in dimensions]
    for column in (0, 1):
        indices = sorted((i for i, d in enumerate(dimensions) if d.column == column),
                         key=lambda i: label_ys[i])
        centres = _spread([label_ys[i] for i in indices], [widths[i] / 2 for i in indices],
                          gap, *label_limits)
        for i, centre in zip(indices, centres):
            label_ys[i] = centre
    bounds = []
    for index, (dimension, width, centre) in enumerate(zip(dimensions, widths, label_ys)):
        x = dimension_xs[dimension.column] - 7
        if extents is None:
            bounds.append((x - ascent, centre - width / 2, x - descent, centre + width / 2))
        else:
            extent = extents[index]
            baseline_y = centre + (extent.left + extent.right) / 2
            bounds.append((x + extent.top, baseline_y - extent.right,
                           x + extent.bottom, baseline_y - extent.left))
    return label_ys, bounds


def _place_annotation(preferred: Point, relative: Bounds, offsets: Sequence[Point],
                      occupied: list[Bounds], limits: Bounds) -> tuple[Point, Bounds]:
    left, top, right, bottom = limits
    for dx, dy in offsets:
        x, y = preferred[0] + dx, preferred[1] + dy
        bounds = (x + relative[0], y + relative[1], x + relative[2], y + relative[3])
        x0, y0, x1, y1 = bounds
        if x0 < left or x1 > right or y0 < top or y1 > bottom:
            continue
        if any(not (x1 + 3 <= a or c + 3 <= x0 or y1 + 3 <= b or d + 3 <= y0)
               for a, b, c, d in occupied):
            continue
        occupied.append(bounds)
        return (x, y), bounds
    raise ValueError("fit box is too small for readable annotations")


def fit_frame(outline: Outline, nodes: Sequence[Mapping], box: Bounds, *,
              members: Sequence[Mapping] | None = None,
              dimensions: Sequence[Dimension] | None = None,
              font: str = "Helvetica", font_size: float = 9.9,
              measure_text: Callable[[str, float], TextExtent] | None = None,
              preferred_axis_x: float = 260.0,
              dimension_label_gap: float = 4.0) -> FrameLayout:
    """Fit the physical shape, analysis nodes and readable labels into a box.

    The column axis prefers the original x=260 points. Actual asymmetric
    extents determine any necessary horizontal shift. Fixed text and dimension
    gutters are reserved before choosing one scale for both physical axes.
    """
    left, top, right, bottom_edge = box
    if not all(math.isfinite(value) for value in box) or right <= left or bottom_edge <= top:
        raise ValueError("fit box must have finite coordinates and positive size")
    if isinstance(dimension_label_gap, bool) or not math.isfinite(dimension_label_gap) or dimension_label_gap < 0:
        raise ValueError("dimension label gap must be finite and nonnegative")
    if measure_text is None:
        ascent, descent = pdfmetrics.getAscentDescent(font, font_size)
    else:
        reference_extent = measure_text("0123456789", font_size)
        ascent, descent = -reference_extent.top, -reference_extent.bottom
    by_id = {node["id"]: node for node in nodes}
    # The nodes-only form remains useful for callers fitting the original
    # four-node shape. Production reports always pass the explicit graph.
    if members is None:
        members = tuple({"id": i, "node_i": a, "node_j": b}
                        for i, (a, b) in enumerate(((1, 2), (2, 3), (3, 4)), 1))
    if dimensions is None:
        dimensions = tuple(Dimension("", by_id[a]["y"], by_id[b]["y"], column)
                           for a, b, column in ((1, 2, 1), (2, 4, 1), (2, 3, 0), (3, 4, 0)))
    dimensions = tuple(dimensions)
    node_widths = ([measure_text(str(node["id"]), font_size).advance for node in nodes]
                   if measure_text is not None else
                   [pdfmetrics.stringWidth(str(node["id"]), font, font_size) for node in nodes])
    left_gutter = max(48.0, max(node_widths) + 32)
    right_gutter = 64.0
    if right - left <= left_gutter + right_gutter:
        raise ValueError("fit box is too small for readable annotations")
    xmin, zmin, xmax, zmax = outline.bounds
    xmin = min(xmin, *(node["x"] for node in nodes))
    xmax = max(xmax, *(node["x"] for node in nodes))
    zmin = min(zmin, *(node["y"] for node in nodes))
    zmax = max(zmax, *(node["y"] for node in nodes))
    top_padding = max(8.0, ascent - 1)
    bottom_padding = max(8.0, 5 - descent)
    usable_height = bottom_edge - top - top_padding - bottom_padding
    if usable_height <= 0:
        raise ValueError("fit box is too small for readable annotations")
    scale_x = (right - left - right_gutter - left_gutter) / (xmax - xmin)
    scale = min(scale_x, usable_height / (zmax - zmin))
    axis_min = left + left_gutter - xmin * scale
    axis_max = right - xmax * scale - right_gutter
    axis_x = max(axis_min, min(preferred_axis_x, axis_max))
    bottom = bottom_edge - bottom_padding + zmin * scale
    physical_right = axis_x + xmax * scale
    extension_x = physical_right + 6
    dimension_xs = (physical_right + 28, physical_right + 60)
    # Keep the 1.5-point node text backing inside the same figure bounds.
    label_limits = (top + 2, bottom_edge - 2)
    dimension_label_ys, dimension_bounds = _dimension_label_layout(
        dimensions, dimension_xs, scale, bottom, font, font_size, ascent, descent, label_limits,
        measure_text, dimension_label_gap)

    # Keep each number beside its own node/member rather than in a remote
    # annotation lane. Nearby alternatives handle short members and coincident
    # elevations without needing leader lines.
    occupied = list(dimension_bounds)
    offsets = sorted(((dx * 14, dy * 18) for dx in range(-6, 7) for dy in range(-6, 7)),
                     key=lambda point: (point[0] ** 2 + point[1] ** 2, point[0] > 0, point[1]))
    annotation_limits = (left + 2, label_limits[0], right - 2, label_limits[1])

    node_labels, node_bounds = {}, {}
    for node in sorted(nodes, key=lambda node: (-node["y"], node["x"], node["id"])):
        x, y = axis_x + node["x"] * scale, bottom - node["y"] * scale
        if measure_text is None:
            width = pdfmetrics.stringWidth(str(node["id"]), font, font_size)
            relative = (-width, -ascent, 0, -descent)
        else:
            extent = measure_text(str(node["id"]), font_size)
            relative = (extent.left - extent.advance, extent.top,
                        extent.right - extent.advance, extent.bottom)
        node_labels[node["id"]], node_bounds[node["id"]] = _place_annotation(
            (x - 6, y + 3), relative, offsets, occupied, annotation_limits)
    member_labels = {}
    member_bounds = []
    for member in sorted(members, key=lambda member: member["id"]):
        a, b = by_id[member["node_i"]], by_id[member["node_j"]]
        midpoint = (axis_x + (a["x"] + b["x"]) * scale / 2,
                    bottom - (a["y"] + b["y"]) * scale / 2)
        half_width = (max(3.5, (measure_text(str(member["id"]), 8).right
                               - measure_text(str(member["id"]), 8).left) / 2 + 1.08)
                      if measure_text is not None else 3.5)
        member_labels[member["id"]], bounds = _place_annotation(
            (midpoint[0] + 8, midpoint[1]), (-half_width, -7, half_width, 7), offsets, occupied, annotation_limits)
        member_bounds.append(bounds)
    rectangles = [node_bounds[node["id"]] for node in nodes] + member_bounds + dimension_bounds
    return FrameLayout(scale, axis_x, bottom, extension_x, dimension_xs, node_labels,
                       member_labels, tuple(dimension_label_ys), tuple(rectangles), dimensions)

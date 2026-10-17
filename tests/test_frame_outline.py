"""Physical outlines use independent landmarks and shape equivalence classes."""

from copy import deepcopy
import importlib
import importlib.util
from itertools import product

import pytest
from reportlab.pdfbase import pdfmetrics


def outline_module():
    # A not-yet-created helper must fail an executing test, not collection.
    assert importlib.util.find_spec("src.frame_outline") is not None, "outline helper is missing"
    return importlib.import_module("src.frame_outline")


def geometry():
    result = dict(zip((f"b{i}" for i in range(1, 10)), (10, 2, 1, 1, 3, 4, 2, 6, 4)))
    result.update(zip((f"w{i}" for i in range(1, 10)), (14, 1, 2, 4, 2, 5, 5, 7, 1)))
    result.update(h1=0, h2=.5, h3=1, h4=8, h5=.75, h6=2, hG=17)
    return result


def polygons(outline):
    return {part.name: part.points for part in outline.components}


def test_asymmetric_physical_landmarks_are_column_centered():
    helper = outline_module()
    g = geometry()
    before = deepcopy(g)
    b = helper.build_outline(g, "b")
    assert polygons(b) == {
        "footing_base": ((-5, 0), (7, 0), (7, 2), (-5, 2)),
        "footing_taper": ((-5, 2), (7, 2), (3, 2.75), (-3, 2.75)),
        "shaft": ((-2, 2.75), (2, 2.75), (2, 10.75), (-2, 10.75)),
        "haunch": ((-3, 10.75), (3, 10.75), (6, 11.75), (-4, 11.75)),
        "beam": ((-4, 11.75), (6, 11.75), (6, 12.25), (-4, 12.25)),
    }
    assert b.bounds == (-5, 0, 7, 12.25)
    w = helper.build_outline(g, "w")
    assert polygons(w) == {
        "footing_base": ((-8.5, 0), (4.5, 0), (4.5, 2), (-8.5, 2)),
        "footing_taper": ((-8.5, 2), (4.5, 2), (3.5, 2.75), (-3.5, 2.75)),
        "shaft": ((-2.5, 2.75), (2.5, 2.75), (2.5, 10.75), (-2.5, 10.75)),
        "haunch": ((-4, 10.75), (4, 10.75), (6, 11.75), (-8, 11.75)),
        "beam": ((-8, 11.75), (6, 11.75), (6, 12.25), (-8, 12.25)),
    }
    assert w.bounds == (-8.5, 0, 6, 12.25)
    assert g == before


@pytest.mark.parametrize("prefix,topology", tuple(product(("b", "w"), product((False, True), repeat=3))))
def test_zero_height_topologies_omit_only_the_absent_components(prefix, topology):
    g = geometry()
    for key, present in zip(("h2", "h3", "h5"), topology):
        g[key] = .5 if present else 0
    outline = outline_module().build_outline(g, prefix)
    parts = polygons(outline)
    assert set(parts) == {"footing_base", "shaft"} | {
        name for name, present in zip(("beam", "haunch", "footing_taper"), topology) if present
    }
    assert all(max(y for _, y in points) > min(y for _, y in points) for points in parts.values())
    assert max(y for points in parts.values() for _, y in points) == 10 + .5 * sum(topology)


@pytest.mark.parametrize("prefix,beam_sides,footing_sides,shaft_width", tuple(product(
    ("b", "w"), ((0, 0), (0, 3), (3, 0), (1, 3), (3, 1)),
    ((0, 0), (0, 4), (4, 0), (2, 4), (4, 2)), (2, 6, 8),
)))
def test_width_regimes_outstands_and_mirror_invariant(prefix, beam_sides, footing_sides, shaft_width):
    helper = outline_module()
    g = geometry()
    g.update({f"{prefix}4": beam_sides[0], f"{prefix}5": beam_sides[1],
              f"{prefix}6": shaft_width, f"{prefix}7": footing_sides[0],
              f"{prefix}9": footing_sides[1]})
    outline = helper.build_outline(g, prefix)
    mirrored = deepcopy(g)
    for first, second in ((4, 5), (7, 9)):
        mirrored[f"{prefix}{first}"], mirrored[f"{prefix}{second}"] = g[f"{prefix}{second}"], g[f"{prefix}{first}"]
    other = helper.build_outline(mirrored, prefix)
    assert {part.name: {(-x, y) for x, y in part.points} for part in outline.components} == {
        part.name: set(part.points) for part in other.components
    }
    shaft = polygons(outline)["shaft"]
    assert shaft[0][0] == -shaft_width / 2
    assert shaft[1][0] == shaft_width / 2
    assert all(len(set(part.points)) >= 3 for part in outline.components)


@pytest.mark.parametrize("prefix,factor", tuple(product(("b", "w"), (1e-4, .25, 3, 1e4))))
def test_uniform_physical_scaling_and_excluded_centroid(prefix, factor):
    helper = outline_module()
    g = geometry()
    original = helper.build_outline(g, prefix)
    changed = {key: value * factor for key, value in g.items()}
    changed["hG"] = -999
    scaled = helper.build_outline(changed, prefix)
    for first, second in zip(original.components, scaled.components):
        assert first.name == second.name
        for (x, y), (xx, yy) in zip(first.points, second.points):
            assert xx == pytest.approx(x * factor)
            assert yy == pytest.approx(y * factor)
    g["h1"], g["hG"] = 0, 1234
    assert helper.build_outline(g, prefix) == original


@pytest.mark.parametrize("prefix,center,width", (("b", -1.5, 1), ("w", -6, 2)))
def test_h1_rectangle_uses_directional_offset_and_height_but_not_hg(prefix, center, width):
    g = geometry()
    g["h1"] = .4
    first = outline_module().build_outline(g, prefix)
    assert polygons(first)["parapet"] == (
        (center - width / 2, 12.25), (center + width / 2, 12.25),
        (center + width / 2, 12.65), (center - width / 2, 12.65))
    g["hG"] = 123456
    assert outline_module().build_outline(g, prefix) == first
    g["h1"] = 0
    assert "parapet" not in polygons(outline_module().build_outline(g, prefix))


@pytest.mark.parametrize("direction", ("", "longitudinal", "B", None, 1))
def test_invalid_direction_is_rejected_explicitly(direction):
    with pytest.raises(ValueError, match="direction"):
        outline_module().build_outline(geometry(), direction)


def fit_function():
    helper = outline_module()
    assert hasattr(helper, "fit_frame"), "frame fitting helper is missing"
    return helper.fit_frame


def frame_nodes(g):
    # hG is an analysis centroid, deliberately different from the physical H6.
    return tuple({"id": i, "x": 0, "y": value} for i, value in enumerate(
        (sum(g[f"h{j}"] for j in range(2, 7)), g["h5"] + g["h6"],
         (g["h5"] + g["h6"]) * .37, 0), 1))


def assert_inside(inner, outer):
    left, top, right, bottom = inner
    x0, y0, x1, y1 = outer
    assert x0 - 1e-8 <= left <= right <= x1 + 1e-8, (inner, outer)
    assert y0 - 1e-8 <= top <= bottom <= y1 + 1e-8, (inner, outer)


def assert_disjoint(rectangles):
    for i, (left, top, right, bottom) in enumerate(rectangles):
        for other in rectangles[i + 1:]:
            x0, y0, x1, y1 = other
            assert right <= x0 or x1 <= left or bottom <= y0 or y1 <= top, (
                (left, top, right, bottom), other)


def test_fit_preserves_physical_scale_and_model_node_heights():
    g = geometry()
    outline = outline_module().build_outline(g, "b")
    nodes = frame_nodes(g)
    layout = fit_function()(outline, nodes, (102, 232, 535, 676))
    assert layout.scale > 0
    assert layout.point(0, 0) == (layout.axis_x, layout.bottom)
    assert layout.point(2, 2) == pytest.approx((layout.axis_x + 2 * layout.scale,
                                             layout.bottom - 2 * layout.scale))
    assert layout.y(nodes[2]["y"]) != pytest.approx(layout.y(g["h6"]))
    assert layout.y(nodes[0]["y"]) == pytest.approx(layout.point(0, 12.25)[1])
    assert layout.y(nodes[-1]["y"]) == layout.bottom
    assert len(layout.node_labels) == 4 and len(layout.member_labels) == 3
    assert len(layout.dimension_label_ys) == 4


ASPECTS = ((100, 1), (1, 100), (1, .01), (1e-4, 1e-4), (1e4, 1e4))


@pytest.mark.parametrize("prefix,topology,eccentricity,shaft_ratio,aspect", tuple(product(
    ("b", "w"), product((False, True), repeat=3), (-1, 0, 1), (.5, 1, 3), ASPECTS,
)))
def test_shape_equivalence_matrix_fits_all_components_and_readable_annotations(
        prefix, topology, eccentricity, shaft_ratio, aspect):
    helper = outline_module()
    g = geometry()
    sides = {-1: (3, 1, 4, 2), 0: (2, 2, 3, 3), 1: (1, 3, 2, 4)}[eccentricity]
    for index, value in zip((4, 5, 7, 9), sides):
        g[f"{prefix}{index}"] = value
    g[f"{prefix}6"] = shaft_ratio * (g[f"{prefix}1"] - sum(sides[:2]))
    horizontal, vertical = aspect
    for key in g:
        g[key] *= horizontal if key.startswith(("b", "w")) else vertical
    for key, present in zip(("h2", "h3", "h5"), topology):
        if not present:
            g[key] = 0
    nodes = frame_nodes(g)
    before = deepcopy((g, nodes))
    outline = helper.build_outline(g, prefix)
    box = (102, 232, 535, 676) if prefix == "b" else (102, 200, 535, 610)
    layout = fit_function()(outline, nodes, box)
    assert layout.scale > 0
    for part in outline.components:
        for x, z in part.points:
            xx, yy = layout.point(x, z)
            assert_inside((xx, yy, xx, yy), box)
    for bounds in layout.annotation_bounds:
        assert_inside(bounds, box)
    assert_disjoint(layout.annotation_bounds)
    physical_right = max(layout.point(x, y)[0] for part in outline.components for x, y in part.points)
    assert physical_right + 5 <= layout.extension_x
    inner, outer = layout.dimension_xs
    assert layout.extension_x + 15 <= inner
    assert outer - inner == pytest.approx(32)
    assert outer + 3 <= box[2]
    for axis in (0, 1):
        first = layout.point(1, 1)[axis] - layout.point(0, 0)[axis]
        assert abs(first) == pytest.approx(layout.scale)
    for node in nodes:
        x, y = layout.point(node["x"], node["y"])
        tx, ty = layout.node_labels[node["id"]]
        assert abs(tx - x) <= 48 and abs(ty - y) <= 39
    for member_id, (a, b) in enumerate(((1, 2), (2, 3), (3, 4)), 1):
        midpoint = layout.y((nodes[a - 1]["y"] + nodes[b - 1]["y"]) / 2)
        tx, ty = layout.member_labels[member_id]
        assert abs(tx - layout.axis_x) <= 50 and abs(ty - midpoint) <= 54
    pairs = ((0, 1), (1, 3), (1, 2), (2, 3))
    lengths = [pdfmetrics.stringWidth(f'{nodes[a]["y"] - nodes[b]["y"]:.3f}', "Helvetica", 9.9)
               for a, b in pairs]
    for a, b in ((0, 1), (2, 3)):
        assert abs(layout.dimension_label_ys[b] - layout.dimension_label_ys[a]) >= (
            lengths[a] + lengths[b]) / 2 + 4 - 1e-8
    assert (g, nodes) == before


@pytest.mark.parametrize("font", ("Helvetica", "Times-Roman", "Courier"))
def test_annotation_bounds_use_fixed_font_metrics_and_nearby_clear_space(font):
    g = geometry()
    for key in g:
        if key.startswith(("b", "w")):
            g[key] *= 1000  # Compress the height so nearby labels need alternatives.
    nodes = frame_nodes(g)
    layout = fit_function()(outline_module().build_outline(g, "b"), nodes,
                            (102, 232, 535, 676), font=font, font_size=9.9)
    node_bounds = layout.annotation_bounds[:4]
    ascent, descent = pdfmetrics.getAscentDescent(font, 9.9)
    for node, (x, baseline), (left, top, right, bottom) in zip(nodes, layout.node_labels.values(), node_bounds):
        assert (left, top, right, bottom) == pytest.approx((
            x - pdfmetrics.stringWidth(str(node["id"]), font, 9.9), baseline - ascent,
            x, baseline - descent))
    assert_disjoint(layout.annotation_bounds)
    for node in nodes:
        x, y = layout.point(node["x"], node["y"])
        tx, ty = layout.node_labels[node["id"]]
        assert abs(tx - x) <= 48 and abs(ty - y) <= 39


@pytest.mark.parametrize("halfway,printed", (
    (9.9995, "10.000"), (99.9995, "100.000"), (9999.9995, "10000.000"),
))
def test_dimension_bounds_measure_the_report_rounding_at_integer_carry(halfway, printed):
    g = geometry()
    g.update(h2=0, h3=0, h4=1, h5=0, h6=halfway, b8=1e9)
    nodes = frame_nodes(g)
    layout = fit_function()(outline_module().build_outline(g, "b"), nodes, (102, 232, 535, 676))
    # Dimension pair (node2,node4) is exactly H6; the literal is an independent
    # Excel-style half-up carry oracle, not Python's binary f-string rounding.
    expected_width = pdfmetrics.stringWidth(printed, "Helvetica", 9.9)
    _, top, _, bottom = layout.annotation_bounds[8]
    assert bottom - top == pytest.approx(expected_width)
    first_width = pdfmetrics.stringWidth("1.000", "Helvetica", 9.9)
    assert layout.dimension_label_ys[1] - layout.dimension_label_ys[0] >= (
        first_width + expected_width) / 2 + 4 - 1e-8


@pytest.mark.parametrize("box", (
    (float("nan"), 232, 535, 676), (102, 232, float("inf"), 676),
    (102, 232, 102, 676), (102, 232, 535, 232), (500, 232, 100, 676),
    (102, 232, 150, 676), (102, 232, 535, 250),
))
def test_nonfinite_nonpositive_or_unreadably_small_fit_box_is_rejected(box):
    g = geometry()
    fit = fit_function()
    with pytest.raises(ValueError, match="box"):
        fit(outline_module().build_outline(g, "b"), frame_nodes(g), box)


@pytest.mark.parametrize("name,prefix,aspect", tuple(product(
    ("default", "parapet_asymmetric", "asymmetric_footing", "h2_zero", "h3_zero",
     "h2_h3_zero", "hg_zero", "hg_top", "parapet_centered", "parapet_tiny_eccentric"),
    ("b", "w"), ((1, 1), (100, .01), (.01, 100), (1e4, 1e4)),
)))
def test_explicit_graph_layout_handles_aliases_eccentricity_and_extreme_aspects(name, prefix, aspect):
    from test_frame_model import case_inputs
    from src.frame_outline import frame_dimensions

    g, _, expected = case_inputs(name, prefix)
    horizontal, vertical = aspect
    g = {key: value * (horizontal if key.startswith(("b", "w")) else vertical)
         for key, value in g.items()}
    frame = deepcopy(expected)
    for node in frame["nodes"]:
        node["x"] *= horizontal
        node["y"] *= vertical
    # Reverse both arrays to prove that physical order and IDs are independent.
    frame["nodes"].reverse()
    frame["members"].reverse()
    helper = outline_module()
    outline = helper.build_outline(g, prefix)
    box = (102, 200, 535, 610)
    layout = helper.fit_frame(outline, frame["nodes"], box, members=frame["members"],
                              dimensions=frame_dimensions(frame))
    assert set(layout.node_labels) == {node["id"] for node in frame["nodes"]}
    assert set(layout.member_labels) == {member["id"] for member in frame["members"]}
    for node in frame["nodes"]:
        x, y = layout.point(node["x"], node["y"])
        assert_inside((x, y, x, y), box)
    for component in outline.components:
        for x, y in component.points:
            xx, yy = layout.point(x, y)
            assert_inside((xx, yy, xx, yy), box)
    for bounds in layout.annotation_bounds:
        assert_inside(bounds, box)
    assert_disjoint(layout.annotation_bounds)
    assert layout.point(1, 1)[0] - layout.point(0, 0)[0] == pytest.approx(layout.scale)
    assert layout.point(0, 0)[1] - layout.point(1, 1)[1] == pytest.approx(layout.scale)


@pytest.mark.parametrize("prefix", ("b", "w"))
def test_parapet_and_eccentric_graph_mirror_together(prefix):
    from test_frame_model import case_inputs
    from src.frame_outline import frame_dimensions

    g, _, frame = case_inputs("parapet_asymmetric", prefix)
    mirrored = deepcopy(g)
    mirrored[f"{prefix}2"] = g[f"{prefix}1"] - g[f"{prefix}2"] - g[f"{prefix}3"]
    for a, b in ((4, 5), (7, 9)):
        mirrored[f"{prefix}{a}"], mirrored[f"{prefix}{b}"] = g[f"{prefix}{b}"], g[f"{prefix}{a}"]
    other_frame = deepcopy(frame)
    for node in other_frame["nodes"]:
        node["x"] = -node["x"]
    helper = outline_module()
    original, other = helper.build_outline(g, prefix), helper.build_outline(mirrored, prefix)
    for component, reflected in zip(original.components, other.components):
        assert component.name == reflected.name
        for expected, actual in zip(sorted((-x, y) for x, y in component.points), sorted(reflected.points)):
            assert actual == pytest.approx(expected)
    box = (102, 200, 535, 610)
    layout = helper.fit_frame(other, other_frame["nodes"], box, members=other_frame["members"],
                              dimensions=frame_dimensions(other_frame))
    for bounds in layout.annotation_bounds:
        assert_inside(bounds, box)
    assert_disjoint(layout.annotation_bounds)

"""The 0600 loading figure draws the moving-load result: positions come from the levers and the input.

Every expectation is taken from the result (levers, spacings, girder lengths) and
the input (L1, span, L2), never from the drawing code: one scale maps the bearings
and the axles along the girders, every label is drawn once without overlapping
another, and the labels are the figure's semantic record.
"""

from __future__ import annotations

import itertools

import pytest
from gridlayoutpdf import LayoutContext, Line, Polyline, Text, command_bounds, measure_block

from reaction_report_cases import case, input_document
from webpier.calc.moving_load import Girder
from webpier.calc.reaction import calculate_reaction
from webpier.inputs import parse_input
from webpier.reporting.fonts import load_fonts
from webpier.reporting.stages.reaction.figures import LoadingFigure, loading_figure
from webpier.reporting.styles import REPORT_STYLE, report_profile

FONTS = load_fonts()
LOADINGS = {"train": lambda result: result.train.loading,
            "lateral": lambda result: result.transverse.lateral_loading}


def drawn(result, pier, loading: str):
    spec = loading_figure(LOADINGS[loading](result), pier)
    measured = measure_block(LoadingFigure(spec.data, "figure"), LayoutContext(FONTS, report_profile(), REPORT_STYLE),
                             528)
    return spec, [command for part in measured.parts for command in part.commands]


def without_origin_overhang():
    document = input_document("current")
    document["上部構造"]["起点側"]["桁長"]["L1"] = 0.0
    pier = parse_input(document)
    return calculate_reaction(pier), pier


@pytest.mark.parametrize("loading", list(LOADINGS))
@pytest.mark.parametrize("name", ["current", "ea17"])
def test_bearings_and_axles_are_drawn_at_one_scale(name: str, loading: str):
    result, pier = case(name)
    _, commands = drawn(result, pier, loading)
    o, e = pier.spans.origin, pier.spans.end
    joint = o.l1.value + o.span.value + o.l2.value
    bearings = [o.l1.value, o.l1.value + o.span.value, joint + e.l1.value, joint + e.l1.value + e.span.value]
    axles = sorted(bearings[0] + axle.lever.value if axle.girder is Girder.ORIGIN else bearings[3] - axle.lever.value
                   for axle in LOADINGS[loading](result).axles)
    shoes = sorted(c.points[0].x for c in commands if isinstance(c, Polyline) and c.closed)
    shafts = sorted(c.x1 for c in commands if isinstance(c, Line) and c.x1 == c.x2 and c.width > .9)
    assert len(shoes) == 4 and len(shafts) == len(axles)
    scale = (shoes[3] - shoes[0]) / (bearings[3] - bearings[0])
    assert shoes == pytest.approx([shoes[0] + (b - bearings[0]) * scale for b in bearings])
    assert shafts == pytest.approx([shoes[0] + (x - bearings[0]) * scale for x in axles])


@pytest.mark.parametrize("loading", list(LOADINGS))
@pytest.mark.parametrize("name", ["current", "ea17", "no_overhang"])
def test_labels_are_the_record_and_never_overlap(name: str, loading: str):
    result, pier = without_origin_overhang() if name == "no_overhang" else case(name)
    spec, commands = drawn(result, pier, loading)
    texts = [c for c in commands if isinstance(c, Text)]
    assert tuple(c.text for c in texts) == spec.labels
    boxes = [command_bounds(c, FONTS) for c in texts]
    for a, b in itertools.combinations(boxes, 2):
        assert a.right <= b.x or b.right <= a.x or a.bottom <= b.y or b.bottom <= a.y


def test_the_example2_dimensions_and_no_zero_overhang():
    result, pier = case("current")
    # Example2 07 7-1: axles and the far bearings, L1/span/L2 of both girders, girder lengths.
    assert loading_figure(result.train.loading, pier).labels == (
        "0.575", "1.625", "12.800", "2.200", "2.800", "2.200", "7.425",
        "0.575", "18.850", "0.575", "0.375", "9.250", "0.375", "20.000", "10.000")
    # 7-14: the three axles of a car junction.
    assert loading_figure(result.transverse.lateral_loading, pier).labels[:5] == (
        "14.425", "2.200", "2.800", "2.200", "7.425")
    result, pier = without_origin_overhang()
    labels = loading_figure(result.train.loading, pier).labels
    assert "0.000" not in labels
    assert labels[-2:] == ("19.425", "10.000")  # 0 + 18.850 + 0.575

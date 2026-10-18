"""6.2 (1)-(6) Pier self weight per part: volumes, centroids, weights (and the exact haunch centroid).

桁受け is left out when its volume V is 0, and the following items close up
their numbers (decision 41).
"""

from __future__ import annotations

from ....calc.reaction.self_weight import Body, HaunchShape, SelfWeightResult
from ....core.printed import Printed
from ....inputs import PierInput
from .figures import outline_figure
from .manuscript import ITEM, SECTION, SUBSECTION, Manuscript, expr, sub
from .tables import volume_table

XL, XC = sub("x", "L"), sub("x", "C")


def pedestal_shown(sw: SelfWeightResult) -> bool:
    """桁受け is printed only when its volume is not 0 (decision 41)."""
    return sw.pedestal.volume.value != 0


def centroid(m: Manuscript, key: str, body: Body, *, heights: bool = True) -> None:
    """N = ΣV × γ, and the centroid ΣV·x / ΣV (a single prism keeps its own x), written in numbers."""
    m.start(key + ".totals")
    m.formula(key + ".weight", "N", None, (body.volume, "×", body.unit_weight), body.weight, gap=True)
    pairs = [(XL, body.moment_l, body.x_l), (XC, body.moment_c, body.x_c)]
    if heights:
        assert body.moment_y is not None and body.y is not None
        pairs.append(("y", body.moment_y, body.y))
    for index, (lhs, moment, position) in enumerate(pairs):
        name = f"{key}.centroid.{('x_l', 'x_c', 'y')[index]}"
        if len(body.rows) == 1 or body.volume.value == 0:
            m.value(name, lhs, position)
        else:
            m.formula(name, lhs, None, (moment, "/", body.volume), position)
    m.end()


def haunch(m: Manuscript, key: str, height: Printed, shape: HaunchShape, z: Printed) -> None:
    """The exact centroid of a haunch whose plan sides vary linearly (decision 22), written in numbers."""
    lb, lw, cb, cw = shape.lower_length, shape.lower_width, shape.length_change, shape.width_change
    # On the line (not stacked); the outer parentheses open so that the long expression wraps at its operators.
    top = (lb, "×", lw, "/", 2, "+", "(", lb, "×", cw, "+", lw, "×", cb, ")", "/", 3, "+", cb, "×", cw, "/", 4)
    bottom = (lb, "×", lw, "+", "(", lb, "×", cw, "+", lw, "×", cb, ")", "/", 2, "+", cb, "×", cw, "/", 3)
    m.equation(key + ".z", "z", expr(height, "×", "(", *top, ")", "/", "(", *bottom, ")", open_groups=True), z,
               gap=True)


def _pedestal(m: Manuscript, sw: SelfWeightResult, pier: PierInput, number: int) -> None:
    s = pier.substructure
    b, w, h = s.b, s.w, s.h
    row = sw.pedestal.rows[0]
    m.heading("weight.pedestal.heading", f"({number}) 桁受け", SUBSECTION)
    m.start("weight.pedestal.rows")
    m.formula("weight.pedestal.area", "A", None, (b[3], "×", w[3]), sw.pedestal_area)
    m.formula("weight.pedestal.volume", "V", None, (sw.pedestal_area, "×", h[1]), row.volume)
    for lhs, size, field in ((XL, b, "x_l"), (XC, w, "x_c")):
        m.formula(f"weight.pedestal.{field}", lhs, None,
                  ("(", 2, "×", size[2], "+", size[3], "−", size[1], "−", size[4], "+", size[5], ")", "/", 2),
                  getattr(row, field))
    m.formula("weight.pedestal.y", "y", None, (h[1], "/", 2), row.y)
    m.end()
    m.table("weight.pedestal.table", volume_table(sw.pedestal, ("桁受け",)), SUBSECTION)
    centroid(m, "weight.pedestal", sw.pedestal)


def _beam(m: Manuscript, sw: SelfWeightResult, pier: PierInput, number: int) -> None:
    s = pier.substructure
    b, w, h = s.b, s.w, s.h
    shape, prism, part = sw.beam_haunch_shape, sw.beam.rows[0], sw.beam.rows[1]
    a1, a2, b0, w0 = sub("A", "1"), sub("A", "2"), sub("b", "0"), sub("w", "0")
    m.heading("weight.beam.heading", f"({number}) はり", SUBSECTION)
    m.start("weight.beam.faces")
    m.formula("weight.beam.top", a1, None, (b[1], "×", w[1]), sw.beam_top_area)
    m.formula("weight.beam.b0", b0, None, (b[1], "−", b[4], "−", b[5]), shape.lower_length)
    m.formula("weight.beam.w0", w0, None, (w[1], "−", w[4], "−", w[5]), shape.lower_width)
    m.formula("weight.beam.db", "Δb", None, (b[1], "−", shape.lower_length), shape.length_change)
    m.formula("weight.beam.dw", "Δw", None, (w[1], "−", shape.lower_width), shape.width_change)
    m.formula("weight.beam.bottom", a2, None, (shape.lower_length, "×", shape.lower_width), sw.beam_bottom_area)
    m.end()
    m.start("weight.beam.prism")
    m.paragraph("weight.beam.prism.label", "はり", gap=True)
    m.formula("weight.beam.prism.volume", "V", None, (sw.beam_top_area, "×", h[2]), prism.volume)
    m.formula("weight.beam.prism.x_l", XL, None, ("(", b[5], "−", b[4], ")", "/", 2), prism.x_l)
    m.formula("weight.beam.prism.x_c", XC, None, ("(", w[5], "−", w[4], ")", "/", 2), prism.x_c)
    m.formula("weight.beam.prism.y", "y", None, ("−", h[2], "/", 2), prism.y)
    m.end()
    m.start("weight.beam.haunch")
    m.paragraph("weight.beam.haunch.label", "ハンチ部", gap=True)
    m.formula("weight.beam.haunch.volume", "V", None,
              (h[3], "/", 6, "×", "(", shape.lower_length, "×", w[1], "+", b[1], "×", shape.lower_width, "+", 2,
               "×", "(", sw.beam_top_area, "+", sw.beam_bottom_area, ")", ")"), part.volume, open_groups=True)
    m.end()
    m.start("weight.beam.z")
    haunch(m, "weight.beam", h[3], shape, sw.beam_haunch_centroid)
    m.end()
    m.start("weight.beam.haunch.position")
    for lhs, field in ((XL, "x_l"), (XC, "x_c")):
        name = f"weight.beam.haunch.{field}"
        if h[3].value == 0:
            m.value(name, lhs, getattr(part, field))
        else:
            m.formula(name, lhs, None, (getattr(prism, field), "×", sw.beam_haunch_centroid, "/", h[3]), getattr(part, field))
    m.formula("weight.beam.haunch.y", "y", None,
              ("−", "(", h[2], "+", h[3], "−", sw.beam_haunch_centroid, ")"), part.y)
    m.end()
    m.table("weight.beam.table", volume_table(sw.beam, ("はり", "ハンチ部")), SUBSECTION)
    centroid(m, "weight.beam", sw.beam)


def _column(m: Manuscript, sw: SelfWeightResult, pier: PierInput, number: int) -> None:
    s = pier.substructure
    b, w, h = s.b, s.w, s.h
    row = sw.column.rows[0]
    m.heading("weight.column.heading", f"({number}) 柱", SUBSECTION)
    m.start("weight.column.rows")
    m.formula("weight.column.area", "A", None, (b[6], "×", w[6]), sw.column_area)
    m.formula("weight.column.volume", "V", None, (sw.column_area, "×", h[4]), row.volume)
    m.formula("weight.column.x_l", XL, None, ("(", b[7], "−", b[9], ")", "/", 2), row.x_l)
    m.formula("weight.column.x_c", XC, None, ("(", w[7], "−", w[9], ")", "/", 2), row.x_c)
    m.formula("weight.column.y", "y", None, (h[4], "/", 2, "+", h[5], "+", h[6]), row.y)
    m.end()
    m.table("weight.column.table", volume_table(sw.column, ("柱",)), SUBSECTION)
    centroid(m, "weight.column", sw.column)


def _footing(m: Manuscript, sw: SelfWeightResult, pier: PierInput, number: int) -> None:
    s = pier.substructure
    b, w, h = s.b, s.w, s.h
    shape, part, prism = sw.footing_haunch_shape, sw.footing.rows[0], sw.footing.rows[1]
    a1, a2, b0, w0 = sub("A", "1"), sub("A", "2"), sub("b", "0"), sub("w", "0")
    m.heading("weight.footing.heading", f"({number}) フーチング", SUBSECTION)
    m.start("weight.footing.faces")
    m.formula("weight.footing.length", "B", None, (b[7], "+", b[8], "+", b[9]), sw.footing_length)
    m.formula("weight.footing.width", "W", None, (w[7], "+", w[8], "+", w[9]), sw.footing_width)
    m.formula("weight.footing.top", a1, None, (b[8], "×", w[8]), sw.footing_top_area)
    m.formula("weight.footing.bottom", a2, None, (sw.footing_length, "×", sw.footing_width), sw.footing_bottom_area)
    m.value("weight.footing.b0", b0, shape.lower_length)
    m.value("weight.footing.w0", w0, shape.lower_width)
    m.formula("weight.footing.db", "Δb", None, (b[8], "−", shape.lower_length), shape.length_change)
    m.formula("weight.footing.dw", "Δw", None, (w[8], "−", shape.lower_width), shape.width_change)
    m.end()
    m.start("weight.footing.haunch")
    m.paragraph("weight.footing.haunch.label", "ハンチ部", gap=True)
    m.formula("weight.footing.haunch.volume", "V", None,
              (h[5], "/", 6, "×", "(", sw.footing_length, "×", w[8], "+", b[8], "×", sw.footing_width, "+", 2,
               "×", "(", sw.footing_top_area, "+", sw.footing_bottom_area, ")", ")"), part.volume, open_groups=True)
    m.end()
    m.start("weight.footing.z")
    haunch(m, "weight.footing", h[5], shape, sw.footing_haunch_centroid)
    m.end()
    m.start("weight.footing.haunch.position")
    for lhs, field in ((XL, "x_l"), (XC, "x_c")):
        name = f"weight.footing.haunch.{field}"
        if h[5].value == 0:
            m.value(name, lhs, getattr(part, field))
        else:
            m.formula(name, lhs, None, (getattr(sw.column, field), "×", sw.footing_haunch_centroid, "/", h[5]), getattr(part, field))
    m.formula("weight.footing.haunch.y", "y", None, (h[6], "+", sw.footing_haunch_centroid), part.y)
    m.end()
    m.start("weight.footing.prism")
    m.paragraph("weight.footing.prism.label", "フーチング", gap=True)
    m.formula("weight.footing.prism.volume", "V", None, (sw.footing_bottom_area, "×", h[6]), prism.volume)
    m.value("weight.footing.prism.x_l", XL, prism.x_l)
    m.value("weight.footing.prism.x_c", XC, prism.x_c)
    m.formula("weight.footing.prism.y", "y", None, (h[6], "/", 2), prism.y)
    m.end()
    m.table("weight.footing.table", volume_table(sw.footing, ("ハンチ部", "フーチング")), SUBSECTION)
    centroid(m, "weight.footing", sw.footing)


def _overburden(m: Manuscript, sw: SelfWeightResult, pier: PierInput, number: int) -> None:
    s = pier.substructure
    b, h = s.b, s.h
    rows = sw.overburden.rows
    depth = sw.soil_depth_at_column
    m.heading("weight.soil.heading", f"({number}) 上載土", SUBSECTION)
    m.start("weight.soil.depth")
    m.formula("weight.soil.depth", "d", None,
              ("(", s.df1, "−", s.df2, ")", "/", sw.footing_length, "×", "(", b[9], "+", b[8], "/", 2, ")", "+",
               s.df2), depth)
    m.end()
    m.start("weight.soil.trapezoid")
    m.paragraph("weight.soil.trapezoid.label", "台形部", gap=True)
    m.formula("weight.soil.trapezoid.volume", "V", None,
              (sw.footing_bottom_area, "×", "(", s.df1, "+", s.df2, ")", "/", 2), rows[0].volume)
    if s.df1.value + s.df2.value == 0:
        m.value("weight.soil.trapezoid.x_l", XL, rows[0].x_l)
    else:
        m.formula("weight.soil.trapezoid.x_l", XL, None,
                  (sw.footing_length, "×", "(", s.df1, "+", 2, "×", s.df2, ")", "/", "(", 3, "×", "(", s.df1, "+",
                   s.df2, ")", ")", "−", sw.footing_length, "/", 2), rows[0].x_l)
    m.end()
    m.start("weight.soil.deductions")
    m.paragraph("weight.soil.column.label", "柱の控除", gap=True)
    m.formula("weight.soil.column.volume", "V", None, ("−", sw.column_area, "×", depth), rows[1].volume)
    m.paragraph("weight.soil.layer.label", "ハンチの層", gap=True)
    m.formula("weight.soil.layer.volume", "V", None, (sw.footing_bottom_area, "×", h[5]), rows[2].volume)
    m.paragraph("weight.soil.haunch.label", "フーチングのハンチ部の控除", gap=True)
    m.value("weight.soil.haunch.volume", "V", rows[3].volume)
    m.end()
    m.table("weight.soil.table", volume_table(sw.overburden, ("台形部", "柱控除", "ハンチの層", "ハンチ控除"),
                                              heights=False), SUBSECTION)
    centroid(m, "weight.soil", sw.overburden, heights=False)


def section(m: Manuscript, sw: SelfWeightResult, pier: PierInput) -> int:
    """(1) the shape, then each part; returns the number of the next item."""
    shown = pedestal_shown(sw)
    m.heading("weight.heading", "6.2 橋脚自重", SECTION)
    m.heading("weight.shape.heading", "(1) 橋脚の形状", SUBSECTION)
    m.figure("weight.shape.figure", outline_figure(pier, sw), ITEM)
    number = 2
    if shown:
        _pedestal(m, sw, pier, number)
        number += 1
    for part in (_beam, _column, _footing, _overburden):
        part(m, sw, pier, number)
        number += 1
    return number

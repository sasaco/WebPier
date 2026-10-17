"""6.2 (1)-(6) Pier self weight per part: volumes, centroids, weights (and the exact haunch centroid)."""

from __future__ import annotations

from gridlayoutpdf import Fraction, Row

from ....calc.reaction.self_weight import Body, HaunchShape, SelfWeightResult
from ....core.printed import Printed
from ....inputs import PierInput
from .figures import outline_figure
from .manuscript import (
    BODY, ITEM, SECTION, SUBSECTION, Manuscript, expr, symbols, sub,
)
from .tables import volume_table

XL, XC = sub("x", "L"), sub("x", "C")


def centroid(m: Manuscript, key: str, body: Body, *, heights: bool = True) -> None:
    """N = ΣV × γ, and the centroid ΣV·x / ΣV (a single prism keeps its own x)."""
    m.start(key + ".totals")
    m.formula(key + ".weight", "N", symbols("ΣV", "×", "γ"), (body.volume, "×", body.unit_weight), body.weight,
              gap=True)
    pairs = [(XL, body.moment_l, body.x_l), (XC, body.moment_c, body.x_c)]
    if heights:
        assert body.moment_y is not None and body.y is not None
        pairs.append(("y", body.moment_y, body.y))
    for index, (lhs, moment, position) in enumerate(pairs):
        name = f"{key}.centroid.{('x_l', 'x_c', 'y')[index]}"
        if len(body.rows) == 1 or body.volume.value == 0:
            m.value(name, lhs, position)
        else:
            m.formula(name, lhs, Row("ΣV・", lhs, "/ΣV", gap=0), (moment, "/", body.volume), position)
    if len(body.rows) > 1 and body.volume.value == 0:
        m.paragraph(key + ".centroid.note", "ΣV = 0 のため重心位置は 0 とする。")
    m.end()


def haunch(m: Manuscript, key: str, height_symbol: str, height: Printed, shape: HaunchShape, z: Printed) -> None:
    """The exact centroid of a haunch whose plan sides vary linearly (decision 22)."""
    m.paragraph(key + ".z.introduction",
                "ハンチの重心は、幅と奥行きが直線的に変わる立体の厳密な式で、下面からの高さ z を求める"
                "（相似な断面では錐台の式と一致する）。")
    b0, w0 = sub("b", "0"), sub("w", "0")
    numerator = symbols(b0, w0, "/", "2", "+", Row("(", b0, "Δw", "+", w0, "Δb", ")/3"), "+", "ΔbΔw/4")
    denominator = symbols(b0, w0, "+", Row("(", b0, "Δw", "+", w0, "Δb", ")/2"), "+", "ΔbΔw/3")
    m.math(key + ".z.symbolic", Row("z", "=", height_symbol, Fraction(numerator, denominator)), left=BODY)
    lb, lw, cb, cw = shape.lower_length, shape.lower_width, shape.length_change, shape.width_change
    # Written flat (not stacked) so that a long expression wraps at its operators.
    top = (lb, "×", lw, "/", 2, "+", "(", lb, "×", cw, "+", lw, "×", cb, ")", "/", 3, "+", cb, "×", cw, "/", 4)
    bottom = (lb, "×", lw, "+", "(", lb, "×", cw, "+", lw, "×", cb, ")", "/", 2, "+", cb, "×", cw, "/", 3)
    m.equation(key + ".z", "z", expr(height, "×", "(", *top, ")", "/", "(", *bottom, ")"), z)


def _pedestal(m: Manuscript, sw: SelfWeightResult, pier: PierInput) -> None:
    s = pier.substructure
    b, w, h = s.b, s.w, s.h
    row = sw.pedestal.rows[0]
    m.heading("weight.pedestal.heading", "(2) 桁受け", SUBSECTION)
    m.start("weight.pedestal.rows")
    m.formula("weight.pedestal.area", "A", symbols("B3", "×", "W3"), (b[3], "×", w[3]), sw.pedestal_area)
    m.formula("weight.pedestal.volume", "V", symbols("A", "×", "H1"), (sw.pedestal_area, "×", h[1]), row.volume)
    for lhs, size, name, field in ((XL, b, "B", "x_l"), (XC, w, "W", "x_c")):
        m.formula(f"weight.pedestal.{field}", lhs,
                  symbols("(", "2", "×", f"{name}2", "+", f"{name}3", "−", f"{name}1", "−", f"{name}4", "+",
                          f"{name}5", ")", "/", "2"),
                  ("(", 2, "×", size[2], "+", size[3], "−", size[1], "−", size[4], "+", size[5], ")", "/", 2),
                  getattr(row, field))
    m.formula("weight.pedestal.y", "y", symbols("H1", "/", "2"), (h[1], "/", 2), row.y)
    m.end()
    m.table("weight.pedestal.table", volume_table(sw.pedestal, ("桁受け",)), SUBSECTION)
    centroid(m, "weight.pedestal", sw.pedestal)


def _beam(m: Manuscript, sw: SelfWeightResult, pier: PierInput) -> None:
    s = pier.substructure
    b, w, h = s.b, s.w, s.h
    shape, prism, part = sw.beam_haunch_shape, sw.beam.rows[0], sw.beam.rows[1]
    a1, a2, b0, w0 = sub("A", "1"), sub("A", "2"), sub("b", "0"), sub("w", "0")
    m.heading("weight.beam.heading", "(3) はり", SUBSECTION)
    m.start("weight.beam.faces")
    m.formula("weight.beam.top", a1, symbols("B1", "×", "W1"), (b[1], "×", w[1]), sw.beam_top_area)
    m.formula("weight.beam.b0", b0, symbols("B1", "−", "B4", "−", "B5"), (b[1], "−", b[4], "−", b[5]),
              shape.lower_length)
    m.formula("weight.beam.w0", w0, symbols("W1", "−", "W4", "−", "W5"), (w[1], "−", w[4], "−", w[5]),
              shape.lower_width)
    m.formula("weight.beam.db", "Δb", symbols("B1", "−", b0), (b[1], "−", shape.lower_length), shape.length_change)
    m.formula("weight.beam.dw", "Δw", symbols("W1", "−", w0), (w[1], "−", shape.lower_width), shape.width_change)
    m.formula("weight.beam.bottom", a2, symbols(b0, "×", w0), (shape.lower_length, "×", shape.lower_width),
              sw.beam_bottom_area)
    m.end()
    m.start("weight.beam.prism")
    m.paragraph("weight.beam.prism.label", "はり（直方体部）", gap=True)
    m.formula("weight.beam.prism.volume", "V", symbols(a1, "×", "H2"), (sw.beam_top_area, "×", h[2]), prism.volume)
    m.formula("weight.beam.prism.x_l", XL, symbols("(", "B5", "−", "B4", ")", "/", "2"),
              ("(", b[5], "−", b[4], ")", "/", 2), prism.x_l)
    m.formula("weight.beam.prism.x_c", XC, symbols("(", "W5", "−", "W4", ")", "/", "2"),
              ("(", w[5], "−", w[4], ")", "/", 2), prism.x_c)
    m.formula("weight.beam.prism.y", "y", symbols("−", "H2", "/", "2"), ("−", h[2], "/", 2), prism.y)
    m.end()
    m.start("weight.beam.haunch")
    m.paragraph("weight.beam.haunch.label", "ハンチ部（高さ H3、下面 A2 から上面 A1 まで）", gap=True)
    m.formula("weight.beam.haunch.volume", "V",
              symbols("H3", "/", "6", "×", Row("(", b0, "W1", "+", "B1", w0, "+", "2", "(", a1, "+", a2, "))")),
              (h[3], "/", 6, "×", "(", shape.lower_length, "×", w[1], "+", b[1], "×", shape.lower_width, "+", 2,
               "×", "(", sw.beam_top_area, "+", sw.beam_bottom_area, ")", ")"), part.volume)
    m.end()
    m.start("weight.beam.z")
    haunch(m, "weight.beam", "H3", h[3], shape, sw.beam_haunch_centroid)
    m.end()
    m.start("weight.beam.haunch.position")
    for lhs, field in ((XL, "x_l"), (XC, "x_c")):
        name = f"weight.beam.haunch.{field}"
        if h[3].value == 0:
            m.value(name, lhs, getattr(part, field))
        else:
            m.formula(name, lhs, Row(lhs, "(はり)", "×", "z", "/", "H3"),
                      (getattr(prism, field), "×", sw.beam_haunch_centroid, "/", h[3]), getattr(part, field))
    m.formula("weight.beam.haunch.y", "y", symbols("−", "(", "H2", "+", "H3", "−", "z", ")"),
              ("−", "(", h[2], "+", h[3], "−", sw.beam_haunch_centroid, ")"), part.y)
    m.end()
    m.table("weight.beam.table", volume_table(sw.beam, ("はり", "ハンチ部")), SUBSECTION)
    centroid(m, "weight.beam", sw.beam)


def _column(m: Manuscript, sw: SelfWeightResult, pier: PierInput) -> None:
    s = pier.substructure
    b, w, h = s.b, s.w, s.h
    row = sw.column.rows[0]
    m.heading("weight.column.heading", "(4) 柱", SUBSECTION)
    m.start("weight.column.rows")
    m.formula("weight.column.area", "A", symbols("B6", "×", "W6"), (b[6], "×", w[6]), sw.column_area)
    m.formula("weight.column.volume", "V", symbols("A", "×", "H4"), (sw.column_area, "×", h[4]), row.volume)
    m.formula("weight.column.x_l", XL, symbols("(", "B7", "−", "B9", ")", "/", "2"),
              ("(", b[7], "−", b[9], ")", "/", 2), row.x_l)
    m.formula("weight.column.x_c", XC, symbols("(", "W7", "−", "W9", ")", "/", "2"),
              ("(", w[7], "−", w[9], ")", "/", 2), row.x_c)
    m.formula("weight.column.y", "y", symbols("H4", "/", "2", "+", "H5", "+", "H6"),
              (h[4], "/", 2, "+", h[5], "+", h[6]), row.y)
    m.end()
    m.table("weight.column.table", volume_table(sw.column, ("柱",)), SUBSECTION)
    centroid(m, "weight.column", sw.column)


def _footing(m: Manuscript, sw: SelfWeightResult, pier: PierInput) -> None:
    s = pier.substructure
    b, w, h = s.b, s.w, s.h
    shape, part, prism = sw.footing_haunch_shape, sw.footing.rows[0], sw.footing.rows[1]
    a1, a2, b0, w0 = sub("A", "1"), sub("A", "2"), sub("b", "0"), sub("w", "0")
    m.heading("weight.footing.heading", "(5) フーチング", SUBSECTION)
    m.start("weight.footing.faces")
    m.formula("weight.footing.length", "B", symbols("B7", "+", "B8", "+", "B9"), (b[7], "+", b[8], "+", b[9]),
              sw.footing_length)
    m.formula("weight.footing.width", "W", symbols("W7", "+", "W8", "+", "W9"), (w[7], "+", w[8], "+", w[9]),
              sw.footing_width)
    m.formula("weight.footing.top", a1, symbols("B8", "×", "W8"), (b[8], "×", w[8]), sw.footing_top_area)
    m.formula("weight.footing.bottom", a2, symbols("B", "×", "W"), (sw.footing_length, "×", sw.footing_width),
              sw.footing_bottom_area)
    m.value("weight.footing.b0", b0, shape.lower_length, symbolic="B")
    m.value("weight.footing.w0", w0, shape.lower_width, symbolic="W")
    m.formula("weight.footing.db", "Δb", symbols("B8", "−", b0), (b[8], "−", shape.lower_length), shape.length_change)
    m.formula("weight.footing.dw", "Δw", symbols("W8", "−", w0), (w[8], "−", shape.lower_width), shape.width_change)
    m.end()
    m.start("weight.footing.haunch")
    m.paragraph("weight.footing.haunch.label", "ハンチ部（高さ H5、下面 A2 から上面 A1 まで）", gap=True)
    m.formula("weight.footing.haunch.volume", "V",
              symbols("H5", "/", "6", "×", Row("(", "B", "W8", "+", "B8", "W", "+", "2", "(", a1, "+", a2, "))")),
              (h[5], "/", 6, "×", "(", sw.footing_length, "×", w[8], "+", b[8], "×", sw.footing_width, "+", 2,
               "×", "(", sw.footing_top_area, "+", sw.footing_bottom_area, ")", ")"), part.volume)
    m.end()
    m.start("weight.footing.z")
    haunch(m, "weight.footing", "H5", h[5], shape, sw.footing_haunch_centroid)
    m.end()
    m.start("weight.footing.haunch.position")
    for lhs, field in ((XL, "x_l"), (XC, "x_c")):
        name = f"weight.footing.haunch.{field}"
        if h[5].value == 0:
            m.value(name, lhs, getattr(part, field))
        else:
            m.formula(name, lhs, Row(lhs, "(柱)", "×", "z", "/", "H5"),
                      (getattr(sw.column, field), "×", sw.footing_haunch_centroid, "/", h[5]), getattr(part, field))
    m.formula("weight.footing.haunch.y", "y", symbols("H6", "+", "z"), (h[6], "+", sw.footing_haunch_centroid),
              part.y)
    m.end()
    m.start("weight.footing.prism")
    m.paragraph("weight.footing.prism.label", "フーチング（直方体部）", gap=True)
    m.formula("weight.footing.prism.volume", "V", symbols(a2, "×", "H6"), (sw.footing_bottom_area, "×", h[6]),
              prism.volume)
    m.value("weight.footing.prism.x_l", XL, prism.x_l)
    m.value("weight.footing.prism.x_c", XC, prism.x_c)
    m.formula("weight.footing.prism.y", "y", symbols("H6", "/", "2"), (h[6], "/", 2), prism.y)
    m.end()
    m.table("weight.footing.table", volume_table(sw.footing, ("ハンチ部", "フーチング")), SUBSECTION)
    centroid(m, "weight.footing", sw.footing)


def _overburden(m: Manuscript, sw: SelfWeightResult, pier: PierInput) -> None:
    s = pier.substructure
    b, h = s.b, s.h
    rows = sw.overburden.rows
    depth = sw.soil_depth_at_column
    m.heading("weight.soil.heading", "(6) 上載土", SUBSECTION)
    m.paragraph("weight.soil.introduction",
                "地表面はフーチング上面から起点側 df1、終点側 df2 の高さで直線とし、ハンチの層を含めて"
                "柱とフーチングのハンチを控除する。")
    m.start("weight.soil.depth")
    m.formula("weight.soil.depth", "d",
              symbols("(", "df1", "−", "df2", ")", "/", "B", "×", "(", "B9", "+", "B8", "/", "2", ")", "+", "df2"),
              ("(", s.df1, "−", s.df2, ")", "/", sw.footing_length, "×", "(", b[9], "+", b[8], "/", 2, ")", "+",
               s.df2), depth)
    m.end()
    a2 = sub("A", "2")
    m.start("weight.soil.trapezoid")
    m.paragraph("weight.soil.trapezoid.label", "台形部（フーチング上面から地表面まで）", gap=True)
    m.formula("weight.soil.trapezoid.volume", "V", symbols(a2, "×", "(", "df1", "+", "df2", ")", "/", "2"),
              (sw.footing_bottom_area, "×", "(", s.df1, "+", s.df2, ")", "/", 2), rows[0].volume)
    if s.df1.value + s.df2.value == 0:
        m.value("weight.soil.trapezoid.x_l", XL, rows[0].x_l)
    else:
        m.formula("weight.soil.trapezoid.x_l", XL,
                  symbols("B", "×", "(", "df1", "+", "2", "df2", ")", "/", "(", "3", "(", "df1", "+", "df2", ")",
                          ")", "−", "B", "/", "2"),
                  (sw.footing_length, "×", "(", s.df1, "+", 2, "×", s.df2, ")", "/", "(", 3, "×", "(", s.df1, "+",
                   s.df2, ")", ")", "−", sw.footing_length, "/", 2), rows[0].x_l)
    m.end()
    m.start("weight.soil.deductions")
    m.paragraph("weight.soil.column.label", "柱の控除（柱の位置の土被り d）", gap=True)
    m.formula("weight.soil.column.volume", "V", symbols("−", "A", "×", "d"), ("−", sw.column_area, "×", depth),
              rows[1].volume)
    m.paragraph("weight.soil.layer.label", "ハンチの層（フーチング平面全体、高さ H5）")
    m.formula("weight.soil.layer.volume", "V", symbols(a2, "×", "H5"), (sw.footing_bottom_area, "×", h[5]),
              rows[2].volume)
    m.paragraph("weight.soil.haunch.label", "フーチングのハンチ部の控除")
    m.value("weight.soil.haunch.volume", "V", rows[3].volume, symbolic=Row("−V", "(ハンチ部)", gap=0))
    m.end()
    m.table("weight.soil.table", volume_table(sw.overburden, ("台形部", "柱控除", "ハンチの層", "ハンチ控除"),
                                              heights=False), SUBSECTION)
    centroid(m, "weight.soil", sw.overburden, heights=False)


def section(m: Manuscript, sw: SelfWeightResult, pier: PierInput) -> None:
    m.heading("weight.heading", "6.2 橋脚自重", SECTION)
    m.paragraph("weight.introduction",
                "重心位置 xL は線路方向、xC は線路直角方向とする。桁受けとはりは柱の中心軸から、高さははり天端"
                "から上向きを正として測る。柱・フーチング・上載土はフーチング中心から、高さはフーチング下面から測る。")
    m.heading("weight.shape.heading", "(1) 橋脚の形状", SUBSECTION)
    m.figure("weight.shape.figure", outline_figure(pier, sw), ITEM)
    _pedestal(m, sw, pier)
    _beam(m, sw, pier)
    _column(m, sw, pier)
    _footing(m, sw, pier)
    _overburden(m, sw, pier)

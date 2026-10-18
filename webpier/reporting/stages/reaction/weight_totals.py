"""6.2 (7)-(9) Buoyancy at the three water levels, and the weights about the column bottom and the footing centre.

Without 桁受け (V = 0) the items are (6)-(8) and the pedestal rows are left out
of the totals; its weight is 0, so the sums of the printed rows do not change
(decision 41).
"""

from __future__ import annotations

from gridlayoutpdf import Row

from ....calc.reaction.self_weight import Aggregate, Buoyancy, Part, SelfWeightResult, WeightRow
from ....inputs import PierInput
from ...equations import Definition
from .manuscript import DETAIL, SUBSECTION, Manuscript, call, expr, join, sub, symbols
from .tables import PART_NAMES, aggregate_table, volume_table
from .weight_parts import XC, XL, centroid, pedestal_shown

LEVELS = (("high", "(a) 高水位", "hw1"), ("normal", "(b) 平水位", "hw2"), ("low", "(c) 低水位", "hw3"))
WATER_ROWS = ("フーチング", "柱", "斜面部", "矩形部")


def _level(m: Manuscript, key: str, title: str, symbol: str, water: Buoyancy, sw: SelfWeightResult,
           pier: PierInput) -> None:
    s = pier.substructure
    rows = water.body.rows
    hw, df_low, height, step = water.level, sw.soil_low, sw.footing_height, sw.soil_step
    bf, wf = sw.footing_length, sw.footing_width
    m.heading(key + ".heading", title, DETAIL)
    m.start(key + ".levels")
    m.value(key + ".level", symbol, hw)
    m.formula(key + ".rise", "h'", call("min", symbols(symbol, "−", "H", "−", sub("df", "min")), "Δdf"),
              (call("min", expr(hw, "−", height, "−", df_low), step),), water.rise)
    m.formula(key + ".submerged", "h''", call("max", "h'", "0"), (call("max", water.rise, 0),), water.submerged)
    if step.value == 0 or water.submerged.value == 0:
        m.value(key + ".wedge", "b'", water.wedge)
        m.paragraph(key + ".wedge.note", "斜面部の土は水没しない（h'' = 0 または Δdf = 0）。")
    else:
        m.formula(key + ".wedge", "b'", call("min", symbols("B", "h''", "/", "Δdf"), "B"),
                  (call("min", expr(bf, "×", water.submerged, "/", step), bf),), water.wedge)
    m.formula(key + ".rectangle", "b''", symbols("B", "−", "b'"), (bf, "−", water.wedge), water.rectangle)
    m.end()
    m.start(key + ".rows")
    m.paragraph(key + ".footing.label", "フーチング（低い側の地表面まで）", gap=True)
    m.formula(key + ".footing.volume", "V",
              symbols(sub("A", "2"), "×", call("max", "0", call("min", symbols(sub("df", "min"), "+", "H"), symbol))),
              (sw.footing_bottom_area, "×", call("max", 0, call("min", expr(df_low, "+", height), hw))),
              rows[0].volume)
    m.paragraph(key + ".column.label", "柱（地表面より上）", gap=True)
    m.formula(key + ".column.volume", "V",
              symbols("A", "×", call("max", symbols(symbol, "−", "d", "−", "H"), "0")),
              (sw.column_area, "×", call("max", expr(hw, "−", sw.soil_depth_at_column, "−", height), 0)),
              rows[1].volume)
    m.paragraph(key + ".wedge.label", "斜面部（水没した三角形部分の土）", gap=True)
    m.formula(key + ".wedge.volume", "V", symbols("b'", "×", "W", "×", "h''", "/", "2"),
              (water.wedge, "×", wf, "×", water.submerged, "/", 2), rows[2].volume)
    lower_end = s.df1.value > s.df2.value  # the soil is lower at the end side: the wedge lies there
    if lower_end:
        m.formula(key + ".wedge.x_l", XL, symbols("b''", "+", "b'", "/", "3", "−", "B", "/", "2"),
                  (water.rectangle, "+", water.wedge, "/", 3, "−", bf, "/", 2), rows[2].x_l)
    else:
        m.formula(key + ".wedge.x_l", XL, symbols("2", "b'", "/", "3", "−", "B", "/", "2"),
                  (2, "×", water.wedge, "/", 3, "−", bf, "/", 2), rows[2].x_l)
    m.paragraph(key + ".rectangle.label", "矩形部（水没した残りの幅の土）", gap=True)
    m.formula(key + ".rectangle.volume", "V", symbols("b''", "×", "W", "×", "h''"),
              (water.rectangle, "×", wf, "×", water.submerged), rows[3].volume)
    if lower_end:
        m.formula(key + ".rectangle.x_l", XL, symbols("b''", "/", "2", "−", "B", "/", "2"),
                  (water.rectangle, "/", 2, "−", bf, "/", 2), rows[3].x_l)
    else:
        m.formula(key + ".rectangle.x_l", XL, symbols("b'", "+", "b''", "/", "2", "−", "B", "/", "2"),
                  (water.wedge, "+", water.rectangle, "/", 2, "−", bf, "/", 2), rows[3].x_l)
    m.end()
    m.table(key + ".table", volume_table(water.body, WATER_ROWS, heights=False), SUBSECTION)
    centroid(m, key, water.body, heights=False)


def _buoyancy(m: Manuscript, sw: SelfWeightResult, pier: PierInput, number: int) -> None:
    s = pier.substructure
    m.heading("weight.water.heading", f"({number}) 浮力", SUBSECTION)
    m.paragraph("weight.water.introduction",
                "水位はフーチング下面からの高さとする。水中の構造物と土の体積に水の単位体積重量を負として乗じる。"
                "斜面部・矩形部は、低い側の地表面より上で水没した土である。")
    m.start("weight.water.common")
    m.formula("weight.water.height", "H", None, (s.h[5], "+", s.h[6]), sw.footing_height)
    m.formula("weight.water.low", sub("df", "min"), None, (call("min", s.df1, s.df2),), sw.soil_low)
    m.formula("weight.water.step", "Δdf", None, (call("max", s.df1, s.df2), "−", call("min", s.df1, s.df2)),
              sw.soil_step)
    m.definitions("weight.water.symbols", Definition("H", "フーチングの高さ"),
                  Definition(sub("df", "min"), "フーチング上面から低い側の地表面までの高さ"),
                  Definition("Δdf", "起点側と終点側の地表面の高さの差"))
    m.end()
    for name, title, symbol in LEVELS:
        _level(m, f"weight.water.{name}", title, symbol, getattr(sw, "buoyancy_" + name), sw, pier)


def _heights(m: Manuscript, key: str, total: Aggregate, sw: SelfWeightResult, pier: PierInput, *,
             footing_base: bool) -> None:
    """The x and y of the pedestal and the beam about the reference point, from their own tables."""
    h = pier.substructure.h
    values = (h[6], "+", h[5], "+", h[4], "+", h[3], "+", h[2]) if footing_base else (h[4], "+", h[3], "+", h[2])
    parts = ((Part.PEDESTAL, sw.pedestal), (Part.BEAM, sw.beam)) if pedestal_shown(sw) else ((Part.BEAM, sw.beam),)
    m.paragraph(key + ".heights.introduction",
                "・".join(PART_NAMES[part] for part, _ in parts) + "の位置は、"
                + ("各部の" if len(parts) > 1 else "") + "表の値（柱の中心軸からの x'、はり天端からの y'）"
                + ("に柱の位置と高さを加える。" if footing_base else "に柱下端からの高さを加える。"))
    for part, body in parts:
        row = next(item for item in total.rows if item.part is part)
        m.start(f"{key}.{part.value}")
        m.paragraph(f"{key}.{part.value}.label", PART_NAMES[part], gap=True)
        if footing_base:
            for lhs, field in ((XL, "x_l"), (XC, "x_c")):
                m.formula(f"{key}.{part.value}.{field}", lhs,
                          symbols(Row(lhs, "'", gap=0), "+", Row(lhs, "(柱)", gap=0)),
                          (getattr(body, field), "+", getattr(sw.column, field)), getattr(row, field))
        assert body.y is not None and row.y is not None
        m.formula(f"{key}.{part.value}.y", "y", None, (*values, "+", body.y), row.y)
        m.end()
    if not footing_base:
        column = total.rows[2]
        assert column.y is not None
        m.start(f"{key}.column")
        m.paragraph(f"{key}.column.label", "柱", gap=True)
        m.formula(f"{key}.column.y", "y", None, (h[4], "/", 2), column.y)
        m.end()


def _rows(total: Aggregate, sw: SelfWeightResult) -> tuple[WeightRow, ...]:
    """The printed rows: without 桁受け (V = 0, weight 0) its row is left out."""
    return tuple(row for row in total.rows if row.part is not Part.PEDESTAL or pedestal_shown(sw))


def _aggregate(m: Manuscript, key: str, total: Aggregate, sw: SelfWeightResult) -> None:
    rows = _rows(total, sw)
    m.start(key + ".totals")
    m.formula(key + ".weight", "N", "ΣN", join([row.weight for row in rows]), total.weight, gap=True)
    structure = [row.weight for row in rows if row.y is not None]
    m.formula(key + ".structure", "N'", "ΣN（高さを持つ部材）", join(structure), total.structure_weight)
    for lhs, moment, position, field in ((XL, total.moment_l, total.x_l, "x_l"), (XC, total.moment_c, total.x_c,
                                                                                    "x_c")):
        if total.weight.value == 0:
            m.value(f"{key}.{field}", lhs, position)
        else:
            m.formula(f"{key}.{field}", lhs, Row("ΣN・", lhs, "/N", gap=0), (moment, "/", total.weight), position)
    if total.structure_weight.value == 0:
        m.value(f"{key}.y", "y", total.y)
    else:
        m.formula(f"{key}.y", "y", Row("ΣN・y/N'", gap=0), (total.moment_y, "/", total.structure_weight), total.y)
    m.end()


def section(m: Manuscript, sw: SelfWeightResult, pier: PierInput, number: int) -> None:
    """Items *number* (buoyancy) to *number* + 2, after the parts of weight_parts."""
    _buoyancy(m, sw, pier, number)
    m.heading("weight.bottom.heading", f"({number + 1}) 柱下端における重量および重心位置", SUBSECTION)
    parts = "・".join(PART_NAMES[row.part] for row in _rows(sw.pier_bottom, sw))
    m.paragraph("weight.bottom.introduction", f"柱の中心軸と柱下端に対する{parts}の重量と重心位置。")
    _heights(m, "weight.bottom", sw.pier_bottom, sw, pier, footing_base=False)
    m.table("weight.bottom.table", aggregate_table(sw.pier_bottom, _rows(sw.pier_bottom, sw)), SUBSECTION)
    _aggregate(m, "weight.bottom", sw.pier_bottom, sw)
    m.heading("weight.centre.heading", f"({number + 2}) フーチング中心における重量および重心位置", SUBSECTION)
    m.paragraph("weight.centre.introduction",
                "フーチング中心とフーチング下面に対する重量と重心位置。重量 N と xL・xC は上載土を含み、"
                "重心高 y は上載土を含まない構造体だけの重量 N' で求める。")
    _heights(m, "weight.centre", sw.footing_centre, sw, pier, footing_base=True)
    m.table("weight.centre.table", aggregate_table(sw.footing_centre, _rows(sw.footing_centre, sw)), SUBSECTION)
    _aggregate(m, "weight.centre", sw.footing_centre, sw)

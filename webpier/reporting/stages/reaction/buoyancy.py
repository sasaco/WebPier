"""6.2 (3) Buoyancy at the three water levels: the submerged volume of each part, their sum and the weight.

The centroids of the buoyancy are of the calculation only (decision 79).
"""

from __future__ import annotations

from ....calc.reaction.self_weight import Buoyancy, SelfWeightResult
from ....inputs import PierInput
from .manuscript import DETAIL, SUBSECTION, Manuscript, call, expr, join, sub

LEVELS = (("high", "(a) 高水位", "hw1"), ("normal", "(b) 平水位", "hw2"), ("low", "(c) 低水位", "hw3"))


def _level(m: Manuscript, key: str, title: str, symbol: str, water: Buoyancy, sw: SelfWeightResult) -> None:
    rows, body = water.body.rows, water.body
    hw, df_low, height, step = water.level, sw.soil_low, sw.footing_height, sw.soil_step
    bf, wf = sw.footing_length, sw.footing_width
    m.heading(key + ".heading", title, DETAIL)
    m.start(key + ".levels")
    m.value(key + ".level", symbol, hw)
    m.formula(key + ".rise", "h'", None, (call("min", expr(hw, "−", height, "−", df_low), step),), water.rise)
    m.formula(key + ".submerged", "h''", None, (call("max", water.rise, 0),), water.submerged)
    if step.value == 0 or water.submerged.value == 0:
        m.value(key + ".wedge", "b'", water.wedge)
    else:
        m.formula(key + ".wedge", "b'", None, (call("min", expr(bf, "×", water.submerged, "/", step), bf),),
                  water.wedge)
    m.formula(key + ".rectangle", "b''", None, (bf, "−", water.wedge), water.rectangle)
    m.end()
    m.start(key + ".rows")
    m.paragraph(key + ".footing.label", "フーチング", gap=True)
    m.formula(key + ".footing.volume", "V", None,
              (sw.footing_bottom_area, "×", call("max", 0, call("min", expr(df_low, "+", height), hw))),
              rows[0].volume)
    m.paragraph(key + ".column.label", "柱", gap=True)
    m.formula(key + ".column.volume", "V", None,
              (sw.column_area, "×", call("max", expr(hw, "−", sw.soil_depth_at_column, "−", height), 0)),
              rows[1].volume)
    m.paragraph(key + ".wedge.label", "斜面部", gap=True)
    m.formula(key + ".wedge.volume", "V", None, (water.wedge, "×", wf, "×", water.submerged, "/", 2), rows[2].volume)
    m.paragraph(key + ".rectangle.label", "矩形部", gap=True)
    m.formula(key + ".rectangle.volume", "V", None, (water.rectangle, "×", wf, "×", water.submerged), rows[3].volume)
    m.end()
    m.start(key + ".totals")
    m.formula(key + ".volume", "V", None, join([row.volume for row in rows]), body.volume, gap=True)
    m.formula(key + ".weight", "N", None, (body.volume, "×", body.unit_weight), body.weight)
    m.end()


def section(m: Manuscript, sw: SelfWeightResult, pier: PierInput, number: int) -> None:
    """Item *number*: the buoyancy, after the parts of weight_parts."""
    s = pier.substructure
    m.heading("weight.water.heading", f"({number}) 浮力", SUBSECTION)
    m.start("weight.water.common")
    m.formula("weight.water.height", "H", None, (s.h[5], "+", s.h[6]), sw.footing_height)
    m.formula("weight.water.low", sub("df", "min"), None, (call("min", s.df1, s.df2),), sw.soil_low)
    m.formula("weight.water.step", "Δdf", None, (call("max", s.df1, s.df2), "−", call("min", s.df1, s.df2)),
              sw.soil_step)
    m.end()
    for name, title, symbol in LEVELS:
        _level(m, f"weight.water.{name}", title, symbol, getattr(sw, "buoyancy_" + name), sw)

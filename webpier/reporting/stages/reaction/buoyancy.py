"""6.2 (3) Buoyancy at the three water levels: the submerged volume of each part, their sum and the weight.

The centroids of the buoyancy are of the calculation only (decision 79). What is 0 is not printed (decision 86): the
slope's heights and widths of a level whose slope is not under water, a part above the water, a soil-surface step of 0.
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
    if water.submerged.value != 0:
        m.formula(key + ".rise", "h'", None, (call("min", expr(hw, "−", height, "−", df_low), step),), water.rise)
        m.formula(key + ".submerged", "h''", None, (call("max", water.rise, 0),), water.submerged)
        m.formula(key + ".wedge", "b'", None, (call("min", expr(bf, "×", water.submerged, "/", step), bf),),
                  water.wedge)
        m.formula(key + ".rectangle", "b''", None, (bf, "−", water.wedge), water.rectangle)
    m.end()
    parts = (
        ("footing", "フーチング", rows[0],
         (sw.footing_bottom_area, "×", call("max", 0, call("min", expr(df_low, "+", height), hw)))),
        ("column", "柱", rows[1],
         (sw.column_area, "×", call("max", expr(hw, "−", sw.soil_depth_at_column, "−", height), 0))),
        ("wedge", "斜面部", rows[2], (water.wedge, "×", wf, "×", water.submerged, "/", 2)),
        ("rectangle", "矩形部", rows[3], (water.rectangle, "×", wf, "×", water.submerged)),
    )
    shown = [part for part in parts if part[2].volume.value != 0]
    m.start(key + ".rows")
    for name, label, row, operands in shown:
        m.paragraph(f"{key}.{name}.label", label, gap=True)
        m.formula(f"{key}.{name}.volume", "V", None, operands, row.volume)
    m.end()
    m.start(key + ".totals")
    if len(shown) > 1:
        m.formula(key + ".volume", "V", None, join([part[2].volume for part in shown]), body.volume, gap=True)
        m.formula(key + ".weight", "N", None, (body.volume, "×", body.unit_weight), body.weight)
    elif shown:
        m.formula(key + ".weight", "N", None, (body.volume, "×", body.unit_weight), body.weight, gap=True)
    else:
        m.value(key + ".weight", "N", body.weight, gap=True)
    m.end()


def section(m: Manuscript, sw: SelfWeightResult, pier: PierInput, number: int) -> None:
    """Item *number*: the buoyancy, after the parts of weight_parts."""
    s = pier.substructure
    m.heading("weight.water.heading", f"({number}) 浮力", SUBSECTION)
    m.start("weight.water.common")
    m.formula("weight.water.height", "H", None, (s.h[5], "+", s.h[6]), sw.footing_height)
    if sw.soil_low.value != 0:
        m.formula("weight.water.low", sub("df", "min"), None, (call("min", s.df1, s.df2),), sw.soil_low)
    if sw.soil_step.value != 0:
        m.formula("weight.water.step", "Δdf", None, (call("max", s.df1, s.df2), "−", call("min", s.df1, s.df2)),
                  sw.soil_step)
    m.end()
    for name, title, symbol in LEVELS:
        _level(m, f"weight.water.{name}", title, symbol, getattr(sw, "buoyancy_" + name), sw)

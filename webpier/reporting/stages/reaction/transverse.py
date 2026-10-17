"""6.4.2 Transverse horizontal forces at the bearings on this pier: H, height y and M = H × y."""

from __future__ import annotations

from gridlayoutpdf import Fraction, Row

from ....calc.reaction import ReactionResult
from ....calc.reaction.transverse import (
    CENTRIFUGAL_DIVISOR, HALF, LATERAL_RATIO, SEISMIC_KH_GIRDER, SEISMIC_KH_TRAIN, WIND_WITH_TRAIN,
    WIND_WITHOUT_TRAIN, TransverseForce, TransverseSide,
)
from ....inputs import PierInput
from ...numbers import decimal_constant, printed
from .manuscript import (
    ITEM, SECTION, SUBSECTION, CellSpec, Manuscript, call, cells, expr, frac, join, sub, sup, symbols,
)
from .tables import header, summary
from .train import loading_lines

SIDES = (("origin", "1) 起点側（B支点）", "b"), ("end", "2) 終点側（C支点）", "c"))
GROUPS = (("ultimate", "安全性（破壊）・復旧性"), ("service", "使用性"), ("fatigue", "安全性（疲労破壊）"))


def _force(m: Manuscript, key: str, label: str, symbolic, numeric, force: TransverseForce) -> None:  # noqa: ANN001
    m.formula(key + ".force", Row("H", label, gap=0), symbolic, numeric, force.force)


def _moment(m: Manuscript, key: str, force: TransverseForce) -> None:
    m.formula(key + ".moment", "M", symbols("H", "×", "y"), (force.force, "×", force.height), force.moment)


def _centrifugal(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    m.heading("trans.centrifugal.heading", "(1) 遠心荷重", SUBSECTION)
    m.paragraph("trans.centrifugal.introduction",
                "単線の列車荷重に遠心荷重係数 αc = V²/(127R) を乗じ、レール面から車両の遠心重心高 hc の位置に"
                "作用させる（V：列車速度 km/h、R：曲線半径 m）。直線区間（R = 0）では αc = 0 とする。")
    for side, title, support in SIDES:
        span = getattr(pier.spans, side)
        values: TransverseSide = getattr(result.transverse, side)
        key = f"trans.centrifugal.{side}"
        m.heading(key + ".heading", title, ITEM)
        m.start(key + ".coefficient")
        if span.radius.value == 0:
            m.value(key + ".alpha", sub("α", "c"), values.centrifugal_coefficient)
            m.paragraph(key + ".straight", "直線区間のため遠心荷重は 0 となる。")
        else:
            m.formula(key + ".alpha", sub("α", "c"),
                      Fraction(sup("V", "2"), symbols(decimal_constant(CENTRIFUGAL_DIVISOR), "R")),
                      (frac(sup(printed(span.speed), "2"), expr(CENTRIFUGAL_DIVISOR, "×", span.radius)),),
                      values.centrifugal_coefficient)
        heights = span.heights
        m.formula(key + ".rail", "h", symbols("h1", "+", "h2", "+", "h3"),
                  (heights[1], "+", heights[2], "+", heights[3]), values.rail_height)
        m.formula(key + ".height", "y", symbols("h", "+", sub("h", "c")),
                  (values.rail_height, "+", pier.train.height_centrifugal), values.centrifugal_height)
        m.end()
        for group, label in GROUPS:
            force: TransverseForce = getattr(values, "centrifugal_" + group)
            load = getattr(getattr(getattr(result.train, group).single, support), "load")
            name = f"{key}.{group}"
            m.start(name)
            m.paragraph(name + ".label", label, gap=True)
            _force(m, name, "", symbols("L", "×", sub("α", "c")), (load, "×", values.centrifugal_coefficient), force)
            m.value(name + ".y", "y", force.height)
            _moment(m, name, force)
            m.end()


def _lateral(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    transverse = result.transverse
    m.heading("trans.lateral.heading", "(2) 車両横荷重", SUBSECTION)
    m.paragraph("trans.lateral.introduction",
                "1軌道当り次の集中移動荷重とし、レール面の高さで軌道に直角かつ水平に作用させる。"
                "連結部の3軸（軸距 a2、a1、a2）を RB + RC が最大となる位置に載荷する。")
    m.formula("trans.lateral.axle", sub("L", "F"), symbols(decimal_constant(LATERAL_RATIO), "×", "P"),
              (LATERAL_RATIO, "×", pier.train.axle_load), transverse.lateral_axle_load)
    loading_lines(m, "trans.lateral.loading", transverse.lateral_loading, pier, sub("L", "F"))
    for side, title, _ in SIDES:
        values: TransverseSide = getattr(transverse, side)
        force = values.vehicle_lateral
        key = f"trans.lateral.{side}"
        m.start(key)
        m.paragraph(key + ".label", title[3:], gap=True)
        m.value(key + ".force", "H", force.force, symbolic=sub("R", "B" if side == "origin" else "C"))
        m.value(key + ".y", "y", force.height, symbolic="h")
        _moment(m, key, force)
        m.end()


def _wind(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    m.heading("trans.wind.heading", "(3) 風荷重", SUBSECTION)
    m.paragraph("trans.wind.introduction",
                "受風高さ h の範囲に風圧 ω を作用させ、桁長 L の 1/2 を本橋脚の支承で受ける。作用位置は h/2 + h1。"
                f"列車があるときの受風高さは桁と軌道の上に車両の受風高 {printed(pier.train.height_wind)} m と"
                " h4 の大きい方をとる。")
    for side, title, _ in SIDES:
        span = getattr(pier.spans, side)
        heights = span.heights
        values: TransverseSide = getattr(result.transverse, side)
        length = getattr(result.longitudinal, side).length
        key = f"trans.wind.{side}"
        m.heading(key + ".heading", title, ITEM)
        for field, pressure, label, height, symbolic, numeric in (
                ("with_train", WIND_WITH_TRAIN, "列車荷重がある場合", values.wind_height_with_train,
                 symbols("h2", "+", "h3", "+", call("max", sub("h", "w"), "h4")),
                 (heights[2], "+", heights[3], "+", call("max", pier.train.height_wind, heights[4]))),
                ("without_train", WIND_WITHOUT_TRAIN, "列車荷重がない場合", values.wind_height_without_train,
                 symbols("h2", "+", "h3", "+", "h4"), (heights[2], "+", heights[3], "+", heights[4]))):
            force: TransverseForce = getattr(values, "wind_" + field)
            name = f"{key}.{field}"
            m.start(name)
            m.paragraph(name + ".label", f"{label}（ω = {printed(pressure)} kN/m²）", gap=True)
            m.formula(name + ".h", "h", symbolic, numeric, height)
            _force(m, name, "", symbols("ω", "×", "h", "×", "L", "×", decimal_constant(HALF)),
                   (pressure, "×", height, "×", length, "×", HALF), force)
            m.formula(name + ".y", "y", symbols("h", "×", decimal_constant(HALF), "+", "h1"),
                      (height, "×", HALF, "+", heights[1]), force.height)
            _moment(m, name, force)
            m.end()


def _seismic(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    m.heading("trans.seismic.heading", f"(4) 地震時慣性力（Kh = {decimal_constant(SEISMIC_KH_GIRDER)}）", SUBSECTION)
    m.paragraph("trans.seismic.introduction",
                "本橋脚の支点の D1 + D2 + S2 に設計水平震度を乗じ、入力した等価重心高 hs の位置に作用させる。")
    for side, title, _ in SIDES:
        loads = getattr(result.dead, side).pier
        force: TransverseForce = getattr(result.transverse, side).seismic_girder
        key = f"trans.seismic.{side}"
        m.start(key)
        m.paragraph(key + ".label", title[3:], gap=True)
        _force(m, key, "", symbols("(", "D1", "+", "D2", "+", "S2", ")", "×", "Kh"),
               ("(", *join((loads.d1, loads.d2, loads.snow2)), ")", "×", SEISMIC_KH_GIRDER), force)
        m.value(key + ".y", "y", force.height, symbolic=sub("h", "s"))
        _moment(m, key, force)
        m.end()
    m.heading("trans.train.heading", f"(5) 地震時列車荷重慣性力（Kh = {decimal_constant(SEISMIC_KH_TRAIN)}）",
              SUBSECTION)
    m.paragraph("trans.train.introduction",
                "地震時列車荷重（6.3）に設計水平震度を乗じ、レール面から車両の地震時重心高の位置に作用させる。")
    for side, title, _ in SIDES:
        values: TransverseSide = getattr(result.transverse, side)
        force = values.seismic_train
        key = f"trans.train.{side}"
        m.start(key)
        m.paragraph(key + ".label", title[3:], gap=True)
        _force(m, key, "", symbols("R", "×", "Kh"),
               (getattr(result.train.seismic, side), "×", SEISMIC_KH_TRAIN), force)
        m.formula(key + ".y", "y", symbols("h", "+", sub("h", "e")),
                  (values.rail_height, "+", pier.train.height_seismic), force.height)
        _moment(m, key, force)
        m.end()


ROWS = (("centrifugal_ultimate", "遠心荷重", "安全性・復旧性"), ("centrifugal_service", "遠心荷重", "使用性"),
        ("centrifugal_fatigue", "遠心荷重", "安全性（疲労）"), ("vehicle_lateral", "車両横荷重", ""),
        ("wind_with_train", "風荷重", "列車あり"), ("wind_without_train", "風荷重", "列車なし"),
        ("seismic_girder", "地震時", "1.0 EQ（桁）"), ("seismic_train", "地震時", "1.0 EQ（列車）"))


def _summary(m: Manuscript, result: ReactionResult) -> None:
    m.heading("trans.summary.heading", "(6) 支承に働く水平荷重のまとめ", SUBSECTION)
    head = ((CellSpec("荷重種別", colspan=2, rowspan=2, align="center"), CellSpec("起点側", colspan=3, align="center"),
             CellSpec("終点側", colspan=3, align="center")),
            header("H (kN)", "y (m)", "M (kN・m)", "H (kN)", "y (m)", "M (kN・m)"))
    body = []
    previous = None
    for field, group, label in ROWS:
        values = []
        for side in ("origin", "end"):
            force: TransverseForce = getattr(getattr(result.transverse, side), field)
            values += [force.force, force.height, force.moment]
        if not label:
            body.append((CellSpec(group, colspan=2, align="left"), *cells(*values)))
        else:
            span = sum(1 for _, other, text in ROWS if other == group and text)
            first = [CellSpec(group, rowspan=span, align="center")] if group != previous else []
            body.append((*first, *cells(label, *values)))
        previous = group
    m.table("trans.summary.table", summary((58.08, 87.12, 58.08, 50.88, 65.28, 58.08, 50.88, 65.28), head, body,
                                           (2, 3, 4, 5, 6, 7)), SECTION)


def section(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    m.heading("trans.heading", "6.4.2 線路直角方向に働く水平荷重", SECTION)
    m.paragraph("trans.introduction", "支承に働く水平荷重 H と、橋脚天端（支承の下面）からの作用位置 y、"
                "モーメント M = H × y を求める。")
    _centrifugal(m, result, pier)
    _lateral(m, result, pier)
    _wind(m, result, pier)
    _seismic(m, result, pier)
    _summary(m, result)

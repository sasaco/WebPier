"""6.4.1 Longitudinal horizontal forces: on each girder, then at its bearing on this pier."""

from __future__ import annotations

from gridlayoutpdf import Row

from ....calc.reaction import ReactionResult
from ....calc.reaction.dead import GirderDead
from ....calc.reaction.longitudinal import (
    ADHESION, AXLE_BRAKING, AXLE_STARTING, BEARING_LINES, DEFINITIONS, EA17_BRAKING, EA17_STARTING,
    FRICTION_SHARE, LONG_RAIL, LONG_RAIL_CAP, LONG_RAIL_SERVICE, SEISMIC_KH, BearingForce, BearingType,
    GirderForces, LongitudinalCase, SeismicBearing, SeismicForces,
)
from ....inputs import BrakingRule, PierInput
from ...numbers import decimal_constant, printed
from .manuscript import (
    DETAIL, INDENTED, ITEM, SECTION, SUBSECTION, CellSpec, Manuscript, call, cells, expr, join, sub, symbols,
)
from .tables import header, summary

WIDE_NOTE = 160.56  # labels inside a bearing derivation
RULES = {BrakingRule.AXLE: "軸重式", BrakingRule.EA17: "EA-17の規定式"}
BEARINGS = {BearingType.FIXED: "固定", BearingType.MOVABLE: "可動"}
# (check, label) of each combination; the combination itself is written from the calculator's definition.
CASES = {
    LongitudinalCase.SERVICE_LR08: ("使用性", "0.8 LR"),
    LongitudinalCase.SERVICE_LR10: ("使用性", "1.0 LR"),
    LongitudinalCase.SAFETY_LR10_B10: ("安全性（破壊）", "1.0 LR + 1.0 B"),
    LongitudinalCase.SAFETY_LR11_B10: ("安全性（破壊）", "1.1 LR + 1.0 B"),
    LongitudinalCase.SAFETY_LR10_B11: ("安全性（破壊）", "1.0 LR + 1.1 B"),
    LongitudinalCase.SAFETY_LR10: ("安全性（破壊）", "1.0 LR"),
    LongitudinalCase.RESTORABILITY_LR10_B10: ("復旧性", "1.0 LR + 1.0 B"),
    LongitudinalCase.RESTORABILITY_LR10: ("復旧性", "1.0 LR"),
}
SNOW = {"snow2": "S2", "snow10": "S10", "snow30": "S30"}
SIDES = (("origin", "起点側桁", "B", "A"), ("end", "終点側桁", "C", "D"))


def combination(case: LongitudinalCase) -> str:
    """The loads of a combination with their nominal factors, from the calculator's definition."""
    definition = DEFINITIONS[case]
    parts = [f"{decimal_constant(definition.d1)}D1", f"{decimal_constant(definition.d2)}D2"]
    if definition.live is not None:
        parts.append(f"{decimal_constant(definition.live)}(L+I)")
    parts.append(SNOW[definition.snow.value])
    rail = "LR(8 kN/m)" if definition.service_rail else "LR"
    parts.append(f"{decimal_constant(definition.lr_factor)}{rail}")
    if definition.brake is not None:
        parts.append(f"{decimal_constant(definition.brake)}B")
    return " + ".join(parts)


def _girder_forces(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    lon, loading = result.longitudinal, result.train.loading
    t = pier.train
    m.heading("long.girder.heading", "(1) 桁に働く水平荷重", SUBSECTION)
    m.heading("long.rail.heading", "1) ロングレール縦荷重", ITEM)
    m.paragraph("long.rail.introduction",
                f"1軌道当り {decimal_constant(LONG_RAIL)} kN/m"
                f"（使用性の 0.8 LR では {decimal_constant(LONG_RAIL_SERVICE)} kN/m）"
                f"を桁長 L に載荷し、1軌道当り {decimal_constant(LONG_RAIL_CAP)} kN を上限とする。n は軌道数（6.1）。")
    for key, name, _, _ in SIDES:
        forces: GirderForces = getattr(lon, key)
        m.start(f"long.rail.{key}")
        m.paragraph(f"long.rail.{key}.label", name)
        for field, per_metre, label in (("long_rail", LONG_RAIL, "LR"), ("long_rail_service", LONG_RAIL_SERVICE,
                                                                         "0.8 LR")):
            m.formula(f"long.rail.{key}.{field}", Row(sub("T", "LR"), f"({label})", gap=0),
                      symbols(call("min", symbols(decimal_constant(per_metre), "L"), decimal_constant(LONG_RAIL_CAP)),
                              "×", "n"),
                      (call("min", expr(per_metre, "×", forces.length), LONG_RAIL_CAP), "×", forces.track_total),
                      getattr(forces, field), medium=True)
        m.end()
    m.heading("long.brake.heading", "2) 制動荷重および始動荷重", ITEM)
    rule = lon.origin.braking_rule
    m.paragraph("long.brake.rule",
                f"車両 {t.vehicle} の制動荷重・始動荷重は{RULES[rule]}で求める（車両の選択による）。")
    if rule is BrakingRule.EA17:
        braking = Row(f"({decimal_constant(EA17_BRAKING[0])} + {decimal_constant(EA17_BRAKING[1])}/Lv)・ΣR")
        starting = Row(f"({decimal_constant(EA17_STARTING[0])} + {decimal_constant(EA17_STARTING[1])}/Lv)・ΣR")
        m.paragraph("long.brake.symbols", "ΣR は桁の両端の列車反力（1軌道、荷重修正係数なし）、Lv は1両の長さ。")
    else:
        braking = Row(f"({decimal_constant(AXLE_BRAKING[0])} + {decimal_constant(AXLE_BRAKING[1])}/Lv・L)・P")
        starting = Row(f"({decimal_constant(AXLE_STARTING[0])} + {decimal_constant(AXLE_STARTING[1])}/Lv・L)・P")
        m.paragraph("long.brake.symbols", "P は軸重、Lv は1両の長さ、L は桁長。")
    m.math("long.brake.braking.formula", Row("制動荷重：", braking, gap=0), left=INDENTED)
    m.math("long.brake.starting.formula", Row("始動荷重：", starting, gap=0), left=INDENTED)
    reactions = {"origin": (loading.ra, loading.rb), "end": (loading.rd, loading.rc)}
    for key, name, _, _ in SIDES:
        forces = getattr(lon, key)
        m.start(f"long.brake.{key}")
        m.paragraph(f"long.brake.{key}.label", name, gap=True)
        for field, (a, b), label in (("braking", EA17_BRAKING if rule is BrakingRule.EA17 else AXLE_BRAKING, "制動"),
                                     ("starting", EA17_STARTING if rule is BrakingRule.EA17 else AXLE_STARTING,
                                      "始動")):
            if rule is BrakingRule.EA17:
                numeric = ("(", a, "+", b, "/", t.car_length, ")", "×", "(", *join(reactions[key]), ")")
            else:
                numeric = ("(", a, "+", b, "/", t.car_length, "×", forces.length, ")", "×", t.axle_load)
            m.formula(f"long.brake.{key}.{field}", Row("T(", label, ")", gap=0), None, numeric, getattr(forces, field),
                      medium=True)
        m.formula(f"long.brake.{key}.adopted", "B", call("max", "T(制動)", "T(始動)"),
                  (call("max", forces.braking, forces.starting),), forces.braking_adopted, medium=True)
        m.end()
    m.heading("long.seismic.heading", f"3) 地震時慣性力（Kh = {decimal_constant(SEISMIC_KH)}）", ITEM)
    m.paragraph("long.seismic.introduction", "桁の両端の支点の D1 + D2 + S2 に設計水平震度を乗じる。")
    dead = {"origin": result.dead.origin, "end": result.dead.end}
    for key, name, near, far in SIDES:
        girder: GirderDead = dead[key]
        forces = getattr(lon, key)
        loads = (girder.far.d1, girder.pier.d1, girder.far.d2, girder.pier.d2, girder.far.snow2, girder.pier.snow2)
        m.formula(f"long.seismic.{key}", Row("T(", name, ")", gap=0), None,
                  ("(", *join(loads), ")", "×", SEISMIC_KH), forces.seismic_girder, medium=True)
    m.heading("long.train.heading", "4) 地震時列車荷重慣性力", ITEM)
    m.paragraph("long.train.introduction",
                f"車輪とレールの粘着係数 μ = {decimal_constant(ADHESION)} とし、桁の両端の地震時列車荷重に乗じる。")
    seismic = result.train.seismic
    for key, name, _, _ in SIDES:
        reaction = getattr(seismic, key)
        m.formula(f"long.train.{key}", Row("T(", name, ")", gap=0), None,
                  ("(", reaction, "+", reaction, ")", "×", ADHESION), getattr(lon, key).seismic_train, medium=True)


def _bearing(m: Manuscript, key: str, force: BearingForce, case: LongitudinalCase, side: str,
             result: ReactionResult, pier: PierInput) -> None:
    definition = DEFINITIONS[case]
    span = getattr(pier.spans, side)
    forces: GirderForces = getattr(result.longitudinal, side)
    girder: GirderDead = getattr(result.dead, side)
    loading, train = result.train.loading, result.train
    t = pier.train
    if force.brake_factor is not None:
        assert definition.brake is not None
        if definition.restorability and span.recovery_brake_coefficient is not None:
            m.value(key + ".brake", sub("γ", "B"), force.brake_factor, left=WIDE_NOTE, medium=True)
            m.paragraph(key + ".brake.note", "（入力した復旧性制動係数）", left=WIDE_NOTE)
        else:
            m.formula(key + ".brake", sub("γ", "B"), symbols("ρf", "×", decimal_constant(definition.brake)),
                      (t.factor_ultimate, "×", definition.brake), force.brake_factor, left=WIDE_NOTE, medium=True)
    if force.live_factor is not None:
        assert definition.live is not None
        rho = t.factor_service if definition.service_train else t.factor_ultimate
        m.formula(key + ".live", sub("γ", "L"), symbols("ρf", "×", decimal_constant(definition.live)),
                  (rho, "×", definition.live), force.live_factor, left=WIDE_NOTE, medium=True)
    rail = forces.long_rail_service if definition.service_rail else forces.long_rail
    numeric: list = [definition.lr_factor, "×", rail]
    symbolic: list = [decimal_constant(definition.lr_factor), "×", "LR"]
    if force.brake_factor is not None:
        numeric += ["+", force.brake_factor, "×", forces.braking_adopted]
        symbolic += ["+", sub("γ", "B"), "×", "B"]
    m.formula(key + ".applied", "T", symbols(*symbolic), numeric, force.applied, wide=True)
    movable = force.bearing is BearingType.MOVABLE
    loads = girder.pier if movable else girder.far
    reaction = (loading.rb if side == "origin" else loading.rc) if movable else (
        loading.ra if side == "origin" else loading.rd)
    impact_group = train.service if definition.service_train else train.ultimate
    impact = getattr(impact_group, side + "_impact").double
    snow_symbol = SNOW[definition.snow.value]
    vertical: list = [definition.d1, "×", loads.d1, "+", definition.d2, "×", loads.d2, "+",
                      getattr(loads, definition.snow.value)]
    vertical_symbols: list = [decimal_constant(definition.d1), "D1", "+", decimal_constant(definition.d2), "D2", "+",
                              snow_symbol]
    if force.live_factor is not None:
        vertical += ["+", force.live_factor, "×", reaction, "×", girder.track_total, "×", "(", 1, "+", impact, ")"]
        vertical_symbols += ["+", sub("γ", "L"), "R", "n", "(1", "+", "i)"]
    m.paragraph(key + ".vertical.label",
                "可動支承に働く鉛直荷重" + ("" if movable else "（他端の可動支承）"), left=WIDE_NOTE)
    m.formula(key + ".vertical", "Rm", symbols(*vertical_symbols), vertical, force.vertical, wide=True)
    m.paragraph(key + ".horizontal.label", ("可動" if movable else "固定") + "支承に働く水平荷重", left=WIDE_NOTE)
    m.formula(key + ".share", "T / n", None, (force.applied, "/", BEARING_LINES), force.share, wide=True)
    mu = span.mu
    if movable:
        assert force.friction is not None and force.friction_floor is not None
        m.formula(key + ".friction", "μ・Rm", None, (mu, "×", force.vertical), force.friction, wide=True)
        m.formula(key + ".floor", "μ・T / n", None, (mu, "×", force.share), force.friction_floor, wide=True)
        m.formula(key + ".force", "H", symbols(call("min", "T/n", call("max", "μ・Rm", "μ・T/n"))),
                  (call("min", force.share, call("max", force.friction, force.friction_floor)),), force.force,
                  wide=True)
    else:
        assert force.fixed_candidate is not None
        m.formula(key + ".candidate", "T − 1/2 μ・Rm", None,
                  (force.applied, "−", FRICTION_SHARE, "×", mu, "×", force.vertical), force.fixed_candidate, wide=True)
        m.formula(key + ".force", "H", symbols(call("max", "T − 1/2 μ・Rm", "T/n")),
                  (call("max", force.fixed_candidate, force.share),), force.force, wide=True)


def _cases(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    lon = result.longitudinal
    m.heading("long.bearing.heading", "(2) 支承に働く水平荷重", SUBSECTION)
    origin, end = (BEARINGS[lon.cases[0].origin.bearing], BEARINGS[lon.cases[0].end.bearing])
    m.paragraph("long.bearing.introduction",
                f"起点側桁の B支点は{origin}支承（μ = {printed(pier.spans.origin.mu)}）、"
                f"終点側桁の C支点は{end}支承（μ = {printed(pier.spans.end.mu)}）である。"
                f"各桁の支承線数は n = {decimal_constant(BEARING_LINES)} とし、"
                "可動支承の水平荷重は H = min(T/n, max(μ・Rm, μ・T/n))、固定支承の水平荷重は "
                "H = max(T − 1/2 μ・Rm, T/n) とする。Rm は可動支承の鉛直荷重、μ は支承の摩擦係数である。"
                "γL・γB は荷重修正係数 ρf と組合せの係数の積（小数2桁）である。")
    for number, case in enumerate(lon.cases, 1):
        definition_label = CASES[case.case]
        m.heading(f"long.case.{case.case.name.lower()}.heading",
                  f"({chr(ord('a') + number - 1)}) {definition_label[0]} {definition_label[1]}", DETAIL)
        m.paragraph(f"long.case.{case.case.name.lower()}.combination", f"[{combination(case.case)} の組合せ]",
                    keep=True)
        for side, name, support, _ in SIDES:
            key = f"long.case.{case.case.name.lower()}.{side}"
            m.start(key)
            m.paragraph(key + ".label", f"・{name}（{support}支点）", gap=True)
            _bearing(m, key, getattr(case, side), case.case, side, result, pier)
            m.end()
    for field, title in (("seismic_girder", "地震時慣性力（桁）"), ("seismic_train", "地震時列車荷重慣性力")):
        forces: SeismicForces = getattr(lon, field)
        m.heading(f"long.{field}.heading", f"({chr(ord('a') + len(lon.cases) + (field == 'seismic_train'))}) {title}",
                  DETAIL)
        for side, name, support, _ in SIDES:
            bearing: SeismicBearing = getattr(forces, side)
            key = f"long.{field}.{side}"
            m.start(key)
            m.paragraph(key + ".label", f"・{name}（{support}支点、{BEARINGS[bearing.bearing]}支承）", gap=True)
            m.value(key + ".applied", "T", bearing.applied, wide=True)
            if bearing.bearing is BearingType.MOVABLE:
                m.formula(key + ".force", "H", "T / n", (bearing.applied, "/", BEARING_LINES), bearing.force, wide=True)
            else:
                m.value(key + ".force", "H", bearing.force, symbolic="T", wide=True)
            m.end()


def _summary(m: Manuscript, result: ReactionResult) -> None:
    lon = result.longitudinal
    m.heading("long.summary.heading", "(3) 支承に働く水平荷重のまとめ", SUBSECTION)
    head = ((CellSpec("荷重種別", colspan=2, align="center"),
             *header(Row("起点桁 ", sub("H", "B"), gap=0), Row("終点桁 ", sub("H", "C"), gap=0), "合計")),)
    body = []
    previous = None
    groups: list[str] = [CASES[case.case][0] for case in lon.cases] + ["地震時", "地震時"]
    for index, case in enumerate(lon.cases):
        group = groups[index]
        span = groups.count(group) if group != previous else 0
        label = [CellSpec(group, rowspan=span, align="center")] if span else []
        body.append((*label, *cells(CASES[case.case][1], case.origin.force, case.end.force, case.total)))
        previous = group
    for index, (field, label) in enumerate((("seismic_girder", "1.0 EQ（桁）"), ("seismic_train", "1.0 EQ（列車）"))):
        forces = getattr(lon, field)
        first = [CellSpec("地震時", rowspan=2, align="center")] if index == 0 else []
        body.append((*first, *cells(label, forces.origin.force, forces.end.force, forces.total)))
    m.table("long.summary.table", summary((87.12, 116.16, 87.12, 87.12, 87.12), head, body, (2, 3, 4)), SUBSECTION)


def section(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    m.heading("long.heading", "6.4 水平荷重", SECTION)
    m.heading("long.direction.heading", "6.4.1 線路方向に働く水平荷重", SECTION)
    _girder_forces(m, result, pier)
    _cases(m, result, pier)
    _summary(m, result)


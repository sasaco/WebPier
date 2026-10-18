"""6.4.1 Longitudinal horizontal forces: on each girder, then at its bearing on this pier."""

from __future__ import annotations

from gridlayoutpdf import Row

from ....calc.reaction import ReactionResult
from ....calc.reaction.dead import GirderDead
from ....calc.reaction.longitudinal import (
    ADHESION, AXLE_BRAKING, AXLE_STARTING, BEARING_LINES, DEFINITIONS, EA17_BRAKING, EA17_STARTING,
    FRICTION_SHARE, LONG_RAIL, LONG_RAIL_CAP, LONG_RAIL_SERVICE, SEISMIC_KH, BearingForce, BearingType,
    CaseForces, GirderForces, LongitudinalCase, LongitudinalResult, SeismicBearing, SeismicForces,
)
from ....inputs import BrakingRule, PierInput
from ...equations import Definition
from ...numbers import decimal_constant, printed
from .manuscript import (
    CONCLUSION_EQUAL, DETAIL, FIXED_EQUAL, INDENTED, ITEM, MARK_EQUAL, PAIR_SECOND, SECTION, SUBSECTION,
    VERTICAL_EQUAL, WIDE_LHS, CellSpec, Manuscript, call, cells, expr, inline, join, ratio, sub, symbols,
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
MARKS = {"origin": "T1", "end": "T2"}  # the horizontal force on each girder in 6.4.1 (2) (07 7-5)
# 1) and 2) of 6.4.1 (2) (07 7-5 to 7-12): each heading and its (a), (b) with their combinations.
GROUPS = (
    ("ロングレール縦荷重", (
        ("使用性の照査におけるひび割れの検討", (LongitudinalCase.SERVICE_LR08,)),
        ("使用性の照査におけるひび割れの検討の必要性", (LongitudinalCase.SERVICE_LR10,)),
    )),
    ("ロングレール縦荷重＋制動荷重", (
        ("安全性（破壊）の照査", (LongitudinalCase.SAFETY_LR10_B10, LongitudinalCase.SAFETY_LR11_B10,
                              LongitudinalCase.SAFETY_LR10_B11, LongitudinalCase.SAFETY_LR10)),
        ("復旧性の照査", (LongitudinalCase.RESTORABILITY_LR10_B10, LongitudinalCase.RESTORABILITY_LR10)),
    )),
)
assert [case for _, details in GROUPS for _, cases in details for case in cases] == list(LongitudinalCase)


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
        m.paragraph(f"long.rail.{key}.label", name, gap=True)
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
        meanings = (Definition("ΣR", "桁の両端の列車反力（1軌道、荷重修正係数なし）"), Definition("Lv", "1両の長さ"))
    else:
        braking = Row(f"({decimal_constant(AXLE_BRAKING[0])} + {decimal_constant(AXLE_BRAKING[1])}/Lv・L)・P")
        starting = Row(f"({decimal_constant(AXLE_STARTING[0])} + {decimal_constant(AXLE_STARTING[1])}/Lv・L)・P")
        meanings = (Definition("P", "軸重"), Definition("Lv", "1両の長さ"), Definition("L", "桁長"))
    m.math("long.brake.braking.formula", Row("制動荷重：", braking, gap=0), left=INDENTED)
    m.math("long.brake.starting.formula", Row("始動荷重：", starting, gap=0), left=INDENTED)
    m.definitions("long.brake.symbols", *meanings)
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


def _factors(m: Manuscript, key: str, case: CaseForces, pier: PierInput) -> None:
    """γB and γL of a combination: ρf × the nominal factor, or the entered restorability braking factor."""
    definition = DEFINITIONS[case.case]
    t = pier.train
    entered = [(side, name) for side, name, _, _ in SIDES if definition.brake is not None
               and definition.restorability and getattr(pier.spans, side).recovery_brake_coefficient is not None]
    computed = [getattr(case, side).brake_factor for side, _, _, _ in SIDES
                if definition.brake is not None and side not in dict(entered)]
    if computed:
        assert definition.brake is not None
        m.formula(key + ".brake", sub("γ", "B"), symbols("ρf", "×", decimal_constant(definition.brake)),
                  (t.factor_ultimate, "×", definition.brake), computed[0], left=INDENTED, equal=MARK_EQUAL)
    if definition.live is not None:
        rho = t.factor_service if definition.service_train else t.factor_ultimate
        m.formula(key + ".live", sub("γ", "L"), symbols("ρf", "×", decimal_constant(definition.live)),
                  (rho, "×", definition.live), case.origin.live_factor, left=INDENTED, equal=MARK_EQUAL)
    for side, name in entered:
        m.math(f"{key}.{side}.brake", Row(f"{name}の ", sub("γ", "B"), " は入力した復旧性制動係数 "
                                          f"{printed(getattr(case, side).brake_factor)} とする。", gap=0),
               left=INDENTED)


def _bearing(m: Manuscript, key: str, force: BearingForce, case: LongitudinalCase, side: str, mark: str,
             result: ReactionResult, pier: PierInput) -> None:
    """※ T, the vertical load and the horizontal force candidates bracketed by the rule, ※ ∴ H (07 7-5)."""
    definition = DEFINITIONS[case]
    span = getattr(pier.spans, side)
    forces: GirderForces = getattr(result.longitudinal, side)
    girder: GirderDead = getattr(result.dead, side)
    loading, train = result.train.loading, result.train
    rail = forces.long_rail_service if definition.service_rail else forces.long_rail
    numeric: list = [definition.lr_factor, "×", rail]
    if force.brake_factor is not None:
        numeric += ["+", force.brake_factor, "×", forces.braking_adopted]
    m.formula(key + ".applied", f"※ {mark}", None, numeric, force.applied, left=INDENTED,
              equal=MARK_EQUAL, gap=True)
    movable = force.bearing is BearingType.MOVABLE
    loads = girder.pier if movable else girder.far
    reaction = (loading.rb if side == "origin" else loading.rc) if movable else (
        loading.ra if side == "origin" else loading.rd)
    impact_group = train.service if definition.service_train else train.ultimate
    impact = getattr(impact_group, side + "_impact").double
    vertical: list = [definition.d1, "×", loads.d1, "+", definition.d2, "×", loads.d2]
    vertical_symbols: list = [f"{decimal_constant(definition.d1)}D1", "+", f"{decimal_constant(definition.d2)}D2"]
    if force.live_factor is not None:
        # "× (1 + i)" is one term, so that a wrapped line begins with its operator, never with "(".
        vertical += ["+", force.live_factor, "×", reaction, "×", girder.track_total,
                     Row("×", " ", inline(expr("(", 1, "+", impact, ")")), gap=0)]
        vertical_symbols += ["+", Row(sub("γ", "L"), "・R・軌道数・(1 + i)", gap=0)]
    vertical += ["+", getattr(loads, definition.snow.value)]
    vertical_symbols += ["+", SNOW[definition.snow.value]]
    m.rule_start()
    m.paragraph(key + ".vertical.label",
                "可動支承に働く鉛直荷重" if movable else "他端の可動支承に働く鉛直荷重", left=WIDE_NOTE, gap=True)
    m.equation(key + ".vertical.symbols", "Rm", inline(symbols(*vertical_symbols)), left=WIDE_LHS,
               equal=VERTICAL_EQUAL, checked=False)
    m.formula(key + ".vertical", "", None, vertical, force.vertical, left=WIDE_LHS, equal=VERTICAL_EQUAL)
    m.paragraph(key + ".horizontal.label", ("可動" if movable else "固定") + "支承に働く水平荷重", left=WIDE_NOTE,
                gap=True)
    mu, equal = span.mu, None if movable else FIXED_EQUAL
    if not movable:
        assert force.fixed_candidate is not None
        m.formula(key + ".candidate", "T − 1/2μ・Rm", None,
                  (force.applied, "−", ratio(1, int(1 / FRICTION_SHARE)), "×", mu, "×", force.vertical),
                  force.fixed_candidate, wide=True, equal=equal)
    m.formula(key + ".share", "T / n", None, (ratio(force.applied, BEARING_LINES),), force.share, wide=True,
              equal=equal)
    if movable:
        assert force.friction is not None and force.friction_floor is not None
        m.formula(key + ".friction", "μ・Rm", None, (mu, "×", force.vertical), force.friction, wide=True)
        m.formula(key + ".floor", "μ・T / n", None, (mu, "×", force.share), force.friction_floor, wide=True)
    m.rule_end()
    m.value(key + ".force", "※ ∴ H", force.force, wide=True, left=INDENTED, equal=CONCLUSION_EQUAL, gap=True)


def _seismic(m: Manuscript, field: str, title: str, lon: LongitudinalResult) -> None:
    """07 7-13 3) 4): the girder's T, at a movable bearing T / n without the friction limit, at a fixed one T."""
    m.heading(f"long.{field}.heading", title, ITEM)
    forces: SeismicForces = getattr(lon, field)
    for side, _, _, _ in SIDES:
        bearing: SeismicBearing = getattr(forces, side)
        key = f"long.{field}.{side}"
        movable = bearing.bearing is BearingType.MOVABLE
        m.start(key)
        m.value(key + ".applied", f"※ {MARKS[side]}", bearing.applied, left=INDENTED, equal=MARK_EQUAL,
                gap=True)
        m.rule_start()
        m.paragraph(key + ".label", BEARINGS[bearing.bearing] + "支承に働く水平荷重", left=WIDE_NOTE, gap=True)
        if movable:
            m.formula(key + ".share", "T / n", None, (ratio(bearing.applied, BEARING_LINES),), bearing.force,
                      wide=True)
        else:
            m.value(key + ".share", "T", bearing.force, wide=True, equal=FIXED_EQUAL)
        m.rule_end()
        m.value(key + ".force", "※ ∴ H", bearing.force, wide=True, left=INDENTED, equal=CONCLUSION_EQUAL,
                gap=True)
        m.end()


def _cases(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    lon = result.longitudinal
    m.heading("long.bearing.heading", "(2) 支承に働く水平荷重", SUBSECTION)
    m.definitions("long.bearing.symbols", Definition("T1", "起点側桁に働く水平荷重"),
                  Definition("T2", "終点側桁に働く水平荷重"), Definition("Rm", "可動支承の鉛直荷重"),
                  Definition("R", "支点の列車反力（6.3）"), Definition("i", "衝撃係数（複線）"),
                  Definition("μ", "支承の摩擦係数"))
    for item, (title, details) in enumerate(GROUPS, 1):
        m.heading(f"long.item.{item}.heading", f"{item}) {title}", ITEM)
        for detail, (subtitle, cases) in enumerate(details):
            m.heading(f"long.item.{item}.{detail}.heading", f"({chr(ord('a') + detail)}) {subtitle}", DETAIL)
            for which in cases:
                case = lon.case(which)
                name = which.name.lower()
                for side, _, _, _ in SIDES:
                    key = f"long.case.{name}.{side}"
                    m.start(key)  # the combination and its factors stay with the first girder
                    if side == SIDES[0][0]:
                        m.pair(f"long.case.{name}.label", f"・{CASES[which][1]}",
                               f"[{combination(which)} の組合せ]", INDENTED, PAIR_SECOND, gap=True)
                        _factors(m, f"long.case.{name}", case, pier)
                    _bearing(m, key, getattr(case, side), which, side, MARKS[side], result, pier)
                    m.end()
    _seismic(m, "seismic_girder", f"{len(GROUPS) + 1}) 地震時慣性力", lon)
    _seismic(m, "seismic_train", f"{len(GROUPS) + 2}) 地震時列車荷重慣性力", lon)


def _summary(m: Manuscript, result: ReactionResult) -> None:
    lon = result.longitudinal
    m.heading("long.summary.heading", f"{len(GROUPS) + 3}) 支承に働く水平荷重のまとめ", ITEM)
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


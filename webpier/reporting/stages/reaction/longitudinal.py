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
from ....core.printed import Printed
from ....inputs import BrakingRule, PierInput
from ...numbers import decimal_constant, printed
from .manuscript import (
    CONCLUSION_EQUAL, DETAIL, FIXED_EQUAL, INDENTED, ITEM, MARK_EQUAL, PAIR_SECOND, SECTION, SUBSECTION,
    VERTICAL_EQUAL, WIDE_LHS, CellSpec, Manuscript, call, cells, expr, inline, join, ratio, sub, symbols,
)
from .tables import header, summary

WIDE_NOTE = 160.56  # labels inside a bearing derivation
BEARINGS = {BearingType.FIXED: "固定", BearingType.MOVABLE: "可動"}
# (check, long rail) of each combination; γB follows the long rail in its label, and the combination is written
# from the calculator's definition with the printed γL and γB (07 7-7: "1.0 LR + 1.23B  [1.1D1 + … の組合せ]").
CASES = {
    LongitudinalCase.SERVICE_LR08: ("使用性", "0.8 LR"),
    LongitudinalCase.SERVICE_LR10: ("使用性", "1.0 LR"),
    LongitudinalCase.SAFETY_LR10_B10: ("安全性（破壊）", "1.0 LR"),
    LongitudinalCase.SAFETY_LR11_B10: ("安全性（破壊）", "1.1 LR"),
    LongitudinalCase.SAFETY_LR10_B11: ("安全性（破壊）", "1.0 LR"),
    LongitudinalCase.SAFETY_LR10: ("安全性（破壊）", "1.0 LR"),
    LongitudinalCase.RESTORABILITY_LR10_B10: ("復旧性", "1.0 LR"),
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


def factors(case: CaseForces, pier: PierInput) -> tuple[Printed | None, Printed | None]:
    """γL and γB of a combination as printed (ρf × the nominal factor). γB is that of a girder whose braking
    factor is not the entered restorability one, or the entered one when both girders have it."""
    definition = DEFINITIONS[case.case]
    live = case.origin.live_factor if definition.live is not None else None
    if definition.brake is None:
        return live, None
    entered = {side for side, _, _, _ in SIDES
               if definition.restorability and getattr(pier.spans, side).recovery_brake_coefficient is not None}
    side = next((side for side, _, _, _ in SIDES if side not in entered), SIDES[0][0])
    return live, getattr(case, side).brake_factor


def label(case: CaseForces, pier: PierInput) -> str:
    """"1.0 LR + 1.23B": the long rail and γB."""
    _, brake = factors(case, pier)
    text = CASES[case.case][1]
    return text if brake is None else f"{text} + {printed(brake)}B"


def combination(case: CaseForces, pier: PierInput) -> str:
    """The loads of a combination: the nominal factors of the calculator's definition, γL and γB as printed."""
    definition = DEFINITIONS[case.case]
    live, brake = factors(case, pier)
    parts = [f"{decimal_constant(definition.d1)}D1", f"{decimal_constant(definition.d2)}D2"]
    if live is not None:
        parts.append(f"{printed(live)}(L+I)")
    parts.append(SNOW[definition.snow.value])
    rail = "LR(8 kN/m)" if definition.service_rail else "LR"
    parts.append(f"{decimal_constant(definition.lr_factor)}{rail}")
    if brake is not None:
        parts.append(f"{printed(brake)}B")
    return " + ".join(parts)


def _girder_forces(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    lon, loading = result.longitudinal, result.train.loading
    t = pier.train
    m.heading("long.girder.heading", "(1) 桁に働く水平荷重", SUBSECTION)
    m.heading("long.rail.heading", "1) ロングレール縦荷重", ITEM)
    # 07 7-4: (a) 10 kN/m for the necessity check, safety and restorability, (b) 8 kN/m for serviceability.
    for index, (field, per_metre, title) in enumerate((
            ("long_rail", LONG_RAIL, "使用性の照査におけるひび割れの検討の必要性 および 安全性（破壊）,復旧性の照査"),
            ("long_rail_service", LONG_RAIL_SERVICE, "使用性の照査"))):
        m.heading(f"long.rail.{field}.heading", f"({chr(ord('a') + index)}) {title}", DETAIL)
        m.start(f"long.rail.{field}")
        m.paragraph(f"long.rail.{field}.load", f"1 軌道当り {decimal_constant(per_metre)} kN/m を考える。",
                    left=INDENTED)
        for key, _, _, _ in SIDES:
            forces: GirderForces = getattr(lon, key)
            m.formula(f"long.rail.{field}.{key}", MARKS[key], None,
                      (call("min", expr(per_metre, "×", forces.length), LONG_RAIL_CAP), "×", forces.track_total),
                      getattr(forces, field))
        m.end()
    m.heading("long.brake.heading", "2) 制動荷重および始動荷重", ITEM)
    rule = lon.origin.braking_rule
    m.paragraph("long.brake.rule", "制動荷重および始動荷重の特性値は下式によって求める。")
    if rule is BrakingRule.EA17:
        braking = Row(f"({decimal_constant(EA17_BRAKING[0])} + {decimal_constant(EA17_BRAKING[1])}/Lv)・ΣR")
        starting = Row(f"({decimal_constant(EA17_STARTING[0])} + {decimal_constant(EA17_STARTING[1])}/Lv)・ΣR")
    else:
        braking = Row(f"({decimal_constant(AXLE_BRAKING[0])} + {decimal_constant(AXLE_BRAKING[1])}/Lv・L)・P")
        starting = Row(f"({decimal_constant(AXLE_STARTING[0])} + {decimal_constant(AXLE_STARTING[1])}/Lv・L)・P")
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
        m.formula(f"long.brake.{key}.adopted", "B", None, (call("max", forces.braking, forces.starting),),
                  forces.braking_adopted, medium=True)
        m.end()
    m.heading("long.seismic.heading", f"3) 地震時慣性力（Kh = {decimal_constant(SEISMIC_KH)}）", ITEM)
    m.equation("long.seismic.symbols", "T", inline(symbols("(", "D1", "+", "D2", "+", "S2", ")", "×", "Kh")),
               checked=False)
    dead = {"origin": result.dead.origin, "end": result.dead.end}
    for key, _, _, _ in SIDES:
        girder: GirderDead = dead[key]
        forces = getattr(lon, key)
        loads = (girder.far.d1, girder.pier.d1, girder.far.d2, girder.pier.d2, girder.far.snow2, girder.pier.snow2)
        m.formula(f"long.seismic.{key}", MARKS[key], None, ("(", *join(loads), ")", "×", SEISMIC_KH),
                  forces.seismic_girder)
    m.heading("long.train.heading", "4) 地震時列車荷重慣性力", ITEM)
    m.paragraph("long.train.introduction",
                f"線路方向の列車荷重慣性力は、車輪とレールとの粘着係数 μ = {decimal_constant(ADHESION)} とする。")
    seismic = result.train.seismic
    for key, _, _, _ in SIDES:
        reaction = getattr(seismic, key)
        m.formula(f"long.train.{key}", MARKS[key], None, ("(", reaction, "+", reaction, ")", "×", ADHESION),
                  getattr(lon, key).seismic_train)


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
        vertical_symbols += ["+", f"{printed(force.live_factor)}複線(L+I)"]
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
    for item, (title, details) in enumerate(GROUPS, 1):
        m.heading(f"long.item.{item}.heading", f"{item}) {title}", ITEM)
        for detail, (subtitle, cases) in enumerate(details):
            m.heading(f"long.item.{item}.{detail}.heading", f"({chr(ord('a') + detail)}) {subtitle}", DETAIL)
            for which in cases:
                case = lon.case(which)
                name = which.name.lower()
                for side, _, _, _ in SIDES:
                    key = f"long.case.{name}.{side}"
                    m.start(key)  # the combination stays with the first girder
                    if side == SIDES[0][0]:
                        m.pair(f"long.case.{name}.label", f"・{label(case, pier)}",
                               f"[{combination(case, pier)} の組合せ]", INDENTED, PAIR_SECOND, gap=True)
                    _bearing(m, key, getattr(case, side), which, side, MARKS[side], result, pier)
                    m.end()
    _seismic(m, "seismic_girder", f"{len(GROUPS) + 1}) 地震時慣性力", lon)
    _seismic(m, "seismic_train", f"{len(GROUPS) + 2}) 地震時列車荷重慣性力", lon)


def _summary(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
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
        group_cell = [CellSpec(group, rowspan=span, align="center")] if span else []
        body.append((*group_cell, *cells(label(case, pier), case.origin.force, case.end.force, case.total)))
        previous = group
    for index, (field, name) in enumerate((("seismic_girder", "1.0 EQ（桁）"), ("seismic_train", "1.0 EQ（列車）"))):
        forces = getattr(lon, field)
        first = [CellSpec("地震時", rowspan=2, align="center")] if index == 0 else []
        body.append((*first, *cells(name, forces.origin.force, forces.end.force, forces.total)))
    m.table("long.summary.table", summary((87.12, 116.16, 87.12, 87.12, 87.12), head, body, (2, 3, 4)), SUBSECTION)


def section(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    m.heading("long.heading", "6.4 水平荷重", SECTION)
    m.heading("long.direction.heading", "6.4.1 線路方向に働く水平荷重", SECTION)
    _girder_forces(m, result, pier)
    _cases(m, result, pier)
    _summary(m, result, pier)


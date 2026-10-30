"""13.1 (2) 水平荷重: the forces on the girders (Example2 13-15) and what each bearing on a cantilever takes along
the track in each case (decision 125), written as Example橋脚4 V-13 to V-25 writes them: for each case with bearing
forces (grouped by limit state) its loading and combination, then for each girder T (1橋梁当り, its terms γB × B and
the LR factor × LR, or Kh × the girder's dead load + the seismic train) and T / n (1支承当り); at a movable end each
bearing of the girder on a cantilever compares T / n with μ·Ni and takes the smaller (∴ H), at a fixed end H = T / n.
Mt = H × Y of each bearing and their sums are the bearing tables of 13.1 (4), so they are not repeated here.

``combination`` writes the combination of a case of 13.2 from its factors (the bearing tables of (4) use it too)."""

from __future__ import annotations

from gridlayoutpdf import Row

from ....calc.cantilever import CantileverResult
from ....calc.cantilever.bearings import BearingCase, BearingShare, GirderForce
from ....calc.cantilever.combinations import CaseResult, LimitState
from ....calc.cantilever.geometry import GIRDER_SIDES
from ....calc.moving_load import Girder
from ....calc.reaction import ReactionResult
from ....calc.reaction.longitudinal import ADHESION, LONG_RAIL, LONG_RAIL_SERVICE, BearingType
from ....core.printed import Printed
from ....inputs import PierInput
from ...numbers import decimal_constant
from ..reaction.manuscript import BODY, DETAIL, INDENTED, ITEM, SUBSECTION, Manuscript, call, sub

BEARINGS = {BearingType.FIXED: "固定", BearingType.MOVABLE: "可動"}
STATES = {LimitState.SAFETY: "(a) 安全性（破壊）", LimitState.SERVICEABILITY_DAMAGE: "(b) 使用性（損傷）",
          LimitState.RESTORABILITY_EQ: "(c) 復旧性（地震時）"}
CASE_EQUAL = 8  # the "=" of a case's lines: "∴ H" right-aligned before it, the terms of T before the result


def combination(case: CaseResult) -> str:
    """[1.1D1 + 1.2D2 + 1.35(L+I) + 1.0LR + 1.23B + S10 の組合せ], from the factors the case prints in 13.2."""
    factors = {part.column: part.factor for part in case.contributions}
    parts = [f"{factors[column]}{column}" for column in ("D1", "D2") if column in factors]
    if "L" in factors and factors.get("I") == factors["L"]:
        parts.append(f"{factors['L']}(L+I)")
    else:
        parts += [f"{factors[column]}{column}" for column in ("L", "I") if column in factors]
    parts += [f"{factors[column]}{column}" for column in ("LF", "W") if column in factors]
    if "LR+B" in factors:
        parts.append(factors["LR+B"].replace("+", " + "))
    if "EQ" in factors:
        parts.append(f"{factors['EQ']}EQ")
    if "S" in factors:
        assert case.definition.snow is not None
        parts.append(case.definition.snow.name)
    return "[" + " + ".join(parts) + " の組合せ]"


def _girder_forces(m: Manuscript, result: CantileverResult, reaction: ReactionResult, pier: PierInput) -> None:
    longitudinal = reaction.longitudinal
    m.heading("girder.heading", "1) 桁に働く水平荷重", ITEM)
    m.heading("girder.rail.heading", "(a) ロングレール縦荷重", DETAIL)
    m.heading("girder.rail.safety.heading", "a) 使用性の照査におけるひび割れの検討の必要性 および 安全性（破壊），復旧性の照査",
              INDENTED)
    m.paragraph("girder.rail.safety.text", f"1 軌道当り {decimal_constant(LONG_RAIL)} kN/m を考える．")
    for girder, forces in ((Girder.ORIGIN, longitudinal.origin), (Girder.END, longitudinal.end)):
        m.value(f"girder.rail.safety.{girder.name.lower()}", GIRDER_SIDES[girder], forces.long_rail,
                symbolic=sub("T", "L1" if girder is Girder.ORIGIN else "L2"), wide=True)
    m.heading("girder.rail.service.heading", "b) 使用性の照査", INDENTED)
    m.paragraph("girder.rail.service.text", f"1 軌道当り {decimal_constant(LONG_RAIL_SERVICE)} kN/m を考える．")
    for girder, forces in ((Girder.ORIGIN, longitudinal.origin), (Girder.END, longitudinal.end)):
        m.value(f"girder.rail.service.{girder.name.lower()}", GIRDER_SIDES[girder], forces.long_rail_service,
                symbolic=sub("T", "L1" if girder is Girder.ORIGIN else "L2"), wide=True)
    m.heading("girder.brake.heading", "(b) 制動荷重", DETAIL)
    m.paragraph("girder.brake.text", "安全性（破壊）の照査に対して：1軌道当り次式による．")
    for girder, forces in ((Girder.ORIGIN, longitudinal.origin), (Girder.END, longitudinal.end)):
        m.value(f"girder.brake.{girder.name.lower()}", GIRDER_SIDES[girder], forces.braking_adopted, symbolic="T",
                wide=True)
    response = result.longitudinal
    m.heading("girder.seismic.heading", "(c) 地震時死荷重", DETAIL)
    m.value("girder.seismic.kh", "最大応答震度", response.kh, symbolic="Kh", wide=True)
    m.paragraph("girder.seismic.kh.source", f"（線路方向 Case{response.adopted.case} {response.adopted.block}）")
    seismic = next(case for case in next(iter(result.sides.values())).bearings if case.combination is None)
    for girder, forces, devices in ((Girder.ORIGIN, longitudinal.origin, seismic.origin),
                                    (Girder.END, longitudinal.end, seismic.end)):
        assert devices.inertia is not None
        m.formula(f"girder.seismic.{girder.name.lower()}", GIRDER_SIDES[girder], "T",
                  (response.kh, "×", forces.seismic_girder), devices.inertia, wide=True)
    m.heading("girder.train.heading", "(d) 地震時列車荷重", DETAIL)
    m.value("girder.train.kh", "設計震度", Printed(float(ADHESION), 3, ""), symbolic="Kh", wide=True)
    for girder, forces in ((Girder.ORIGIN, longitudinal.origin), (Girder.END, longitudinal.end)):
        m.value(f"girder.train.{girder.name.lower()}", GIRDER_SIDES[girder], forces.seismic_train, symbolic="T",
                wide=True)


def _terms(force: GirderForce) -> list:
    found: list = []
    for by, value in force.terms:
        found += (["+"] if found else []) + ([value] if by is None else [by, "×", value])
    return found


def _movable(m: Manuscript, key: str, item: BearingShare, mu: Printed) -> None:
    """μ・Ni of a bearing and ∴ H = min(Ts, μ・Ni) (Example橋脚4 V-13: Ts = 415.0 / 2 = 207.5 < 3057.6 × 0.1 = 305.8,
    ∴ T1 = 207.5 kN)."""
    assert item.vertical is not None and item.cap is not None
    mark = f"Ｇ{item.bearing.bearing.number}"  # the bearing (Ｇ1桁) of the girder headed above
    m.formula(f"{key}.cap", Row("μ・", sub("N", mark), gap=0), None, (mu, "×", item.vertical), item.cap,
              equal=CASE_EQUAL)
    m.formula(f"{key}.adopted", Row("∴ ", sub("H", mark), gap=0), None, (call("min", item.share, item.cap),),
              item.force, equal=CASE_EQUAL)


def _case(m: Manuscript, key: str, number: int, cases: list[tuple[BearingCase, CaseResult]], pier: PierInput) -> None:
    bearing, combined = cases[0]
    m.start(key)
    loading = "" if bearing.loading is None else f"　{bearing.loading.value}"
    m.paragraph(f"{key}.label", f"・Case {number}{loading}", BODY, gap=True)
    m.paragraph(f"{key}.combination", combination(combined), INDENTED)
    for girder in Girder:
        force = bearing.origin if girder is Girder.ORIGIN else bearing.end
        shares = [item for case, _ in cases for item in case.bearings if item.bearing.girder is girder]
        if not shares:
            continue  # no bearing of this girder on a cantilever
        assert force.share is not None
        name = girder.name.lower()
        m.paragraph(f"{key}.{name}.label", f"＜{GIRDER_SIDES[girder]}（{BEARINGS[force.bearing]}支承）＞", INDENTED)
        m.formula(f"{key}.{name}.applied", "T", None, _terms(force), force.applied, equal=CASE_EQUAL)
        movable = force.bearing is BearingType.MOVABLE  # a fixed end: H = T / n, no cap (the sample's R = T / 4)
        m.formula(f"{key}.{name}.share", sub("T", "s") if movable else "H", None, (force.applied, "/", force.count),
                  force.share, equal=CASE_EQUAL)
        if movable:
            span = pier.spans.origin if girder is Girder.ORIGIN else pier.spans.end
            for item in shares:
                _movable(m, f"{key}.{name}.{item.bearing.bearing.number}", item, span.mu)
    m.end()


def _bearing_forces(m: Manuscript, result: CantileverResult, pier: PierInput) -> None:
    m.heading("bearing.heading", "2) シューに働く水平荷重", ITEM)
    m.paragraph("bearing.text", "桁の水平荷重 T を桁端の支承の数 n で等分し，可動の桁端は支承ごとに μ・Ni を上限とする．")
    sides = list(result.sides.values())
    previous = None
    for number in [case.number for case in sides[0].bearings]:
        cases = [(next(case for case in side.bearings if case.number == number),
                  next(case for case in side.cases if case.number == number)) for side in sides]
        state = cases[0][1].definition.state
        if state is not previous:
            m.heading(f"bearing.{state.name.lower()}.heading", STATES[state], DETAIL)
            previous = state
        _case(m, f"bearing.{number}", number, cases, pier)


def section(m: Manuscript, result: CantileverResult, reaction: ReactionResult, pier: PierInput) -> None:
    m.heading("horizontal.heading", "(2) 水平荷重", SUBSECTION)
    _girder_forces(m, result, reaction, pier)
    _bearing_forces(m, result, pier)

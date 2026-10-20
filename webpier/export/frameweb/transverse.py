"""The FrameWeb input of 0620 (transverse, non-seismic): Example2 09 pp.9-1 to 9-15.

The labels are those of the Example2 FrameWeb file (09_直角/frameWebForJS.json). Define 1-15 are those of 9-13:
Define 9 and 11 take the up or the down track, 13-15 either sign; on a curve the centrifugal load adds basic cases
18-20 and Define 16-17 (decision 33). The serviceability impact (9-6, ``Basis.SERVICE_IMPACT``) is three more load
cases (up, down, double) with their own Defines. The wind on the pier body is a load on part of each member, as the
calc gives it (decision 12). Combine names are the 9-14 performance item and remark, Pickup names those of 9-15.

FrameWeb takes the worse alternative of each Define on its own, so it also combines an up train with a down impact,
which the calc's variants exclude (``Combination.variants``): its envelope covers the calc's and more.
"""

from __future__ import annotations

from typing import Any

from ...calc.load_nature import SpringTerm
from ...calc.transverse import BasicAction, BasicCase, Basis, Component, DefineCase, TransverseResult
from . import cases
from .build import frameweb_document
from .longitudinal import LONGITUDINAL
from .profile import LONG_TERM, SHORT_TERM, Label, Profile
from .validate import validate_frameweb

_S = "　"  # the full-width space of the Example2 names
B = BasicCase

TRANSVERSE = Profile(
    loads={
        B.D1: Label("D1", "固定死荷重"),
        B.D2: Label("D2", "付加死荷重"),
        B.BUOYANCY_HIGH: Label("Wp1", f"浮力{_S}高水位"),
        B.BUOYANCY_NORMAL: Label("Wp2", f"浮力{_S}平水位"),
        B.BUOYANCY_LOW: Label("Wp3", f"浮力{_S}低水位"),
        B.SNOW2: Label("Ss2", f"雪荷重{_S}2年確率"),
        B.SNOW10: Label("Ss10", f"雪荷重{_S}10年確率"),
        B.SNOW30: Label("Ss30", f"雪荷重{_S}30年確率"),
        B.TRAIN_UP: Label("L1", f"列車荷重{_S}単線{_S}上り"),
        B.TRAIN_DOWN: Label("L2", f"列車荷重{_S}単線{_S}下り"),
        B.TRAIN_DOUBLE: Label("L3", f"列車荷重{_S}複線"),
        B.IMPACT_UP: Label("I1", f"衝撃荷重{_S}安全性・復旧性{_S}単線{_S}上り"),
        B.IMPACT_DOWN: Label("I2", f"衝撃荷重{_S}安全性・復旧性{_S}単線{_S}下り"),
        B.IMPACT_DOUBLE: Label("I3", f"衝撃荷重{_S}安全性・復旧性{_S}複線"),
        B.LATERAL: Label("Lf", "車両横荷重"),
        B.WIND_WITH_TRAIN: Label("W1", f"風荷重{_S}列車荷重がある場合"),
        B.WIND_WITHOUT_TRAIN: Label("W2", f"風荷重{_S}列車荷重がない場合"),
        B.CENTRIFUGAL_UP: Label("CF1", f"遠心荷重{_S}単線{_S}上り"),
        B.CENTRIFUGAL_DOWN: Label("CF2", f"遠心荷重{_S}単線{_S}下り"),
        B.CENTRIFUGAL_DOUBLE: Label("CF3", f"遠心荷重{_S}複線"),
    },
    auxiliary={
        (B.IMPACT_UP, Basis.SERVICE_IMPACT): Label("I1s", f"衝撃荷重{_S}使用性{_S}単線{_S}上り"),
        (B.IMPACT_DOWN, Basis.SERVICE_IMPACT): Label("I2s", f"衝撃荷重{_S}使用性{_S}単線{_S}下り"),
        (B.IMPACT_DOUBLE, Basis.SERVICE_IMPACT): Label("I3s", f"衝撃荷重{_S}使用性{_S}複線"),
    },
    combinations=dict(enumerate((
        "破壊 列車最大", "破壊 車横最大", "破壊 風最大", "破壊 雪最大", "ひび割れ 縁応力度", "ひび割れ 永久荷重",
        "ひび割れ 変動荷重", "損傷 列車最大", "損傷 雪最大", "地盤の安定 列車最大", "地盤の安定 車横最大",
        "地盤の安定 風最大", "地盤の安定 雪最大", "長期支持", "短期支持 低水位", "短期支持 高水位"), 1)),
    extractions=LONGITUDINAL.extractions,  # 9-15 prints the groups of 8-11
    springs={SpringTerm.LONG: LONG_TERM, SpringTerm.SHORT: SHORT_TERM},
    basic=Basis.BASIC,
)


def _load(action: BasicAction) -> cases.Load:
    return cases.Load(spring=action.spring, points=action.points, line_loads=action.line_loads,
                      member_loads=action.member_loads)


def _term(number: int, component: Component, define: DefineCase | None) -> cases.Term:
    """A component with its alternatives: every basic case of its Define case in every sign, one factor and basis."""
    alternatives = component.alternatives
    first = alternatives[0]
    loads = {a.case: _load(a.source) for a in alternatives}
    expected = [] if define is None else [(case, sign) for case in define.cases for sign in define.signs]
    if (define is None or [(a.case, a.sign) for a in alternatives] != expected
            or {(a.factor, a.basis) for a in alternatives} != {(first.factor, first.basis)}
            or any(_load(a.source) != loads[a.case] for a in alternatives)):
        raise ValueError(f"combination {number}: the alternatives of Define {component.define.value} are not its basic "
                         "cases in its signs with one factor and one action each")
    return cases.Term(define=define.number, basis=first.basis, factor=first.factor,
                      loads=tuple(loads[case] for case in define.cases))


def build_frameweb_transverse(result: TransverseResult) -> dict[str, Any]:
    """The FrameWeb input document of 0620; ``core.integrity.dump_json`` gives its bytes."""
    defines = {define.define: define for define in result.define_cases}
    source = cases.Source(
        basic=tuple((action.case, _load(action)) for action in result.basic_cases),
        groups=tuple(cases.Group(number=d.number, cases=d.cases, signs=d.signs) for d in result.define_cases),
        combinations=tuple(cases.Combination(number=c.number, terms=tuple(
            _term(c.number, k, defines.get(k.define)) for k in c.components)) for c in result.combinations),
        extractions=tuple((e.number, e.combinations) for e in result.extractions),
    )
    document = frameweb_document(result.frame, cases.assemble(source, TRANSVERSE))
    validate_frameweb(document)
    return document

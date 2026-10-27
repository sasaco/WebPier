"""The FrameWeb input of 0610 (longitudinal, non-seismic): Example2 08 pp.8-1 to 8-11.

The labels are those of the Example2 FrameWeb file (symbols with the nominal factors, 1.0LR+1.0B), except
basic cases 18 and 20, which carry the rail force only and are named as 8-9 prints them. The serviceability
impact (8-5, ``Basis.SERVICE_IMPACT``) is two more load cases. Combine names are the 8-10 performance item and
remark, Pickup names those of 8-11.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ...calc.longitudinal import BasicCase, Basis, Combination, Layout, LongitudinalResult, SpringTerm
from ...calc.longitudinal.actions import LAYOUT_DEPENDENT
from ...calc.longitudinal.combinations import EXTRACTION_NAMES
from .build import frameweb_document
from .cases import frameweb_cases
from .profile import LONG_TERM, SHORT_TERM, Label, Profile
from .validate import validate_frameweb

_S = "　"  # the full-width space of the Example2 names
B = BasicCase

_LOADS = {
    B.D1: Label("D1", "固定死荷重"),
    B.D2: Label("D2", "付加死荷重"),
    B.BUOYANCY_HIGH: Label("Wp1", f"浮力{_S}高水位"),
    B.BUOYANCY_NORMAL: Label("Wp2", f"浮力{_S}平水位"),
    B.BUOYANCY_LOW: Label("Wp3", f"浮力{_S}低水位"),
    B.SNOW2: Label("Ss2", f"雪荷重{_S}2年確率"),
    B.SNOW10: Label("Ss10", f"雪荷重{_S}10年確率"),
    B.SNOW30: Label("Ss30", f"雪荷重{_S}30年確率"),
    B.TRAIN_SINGLE: Label("L1", f"列車荷重{_S}単線"),
    B.TRAIN_DOUBLE: Label("L2", f"列車荷重{_S}複線"),
    B.IMPACT_SINGLE: Label("I1", f"衝撃荷重{_S}安全性・復旧性{_S}単線"),
    B.IMPACT_DOUBLE: Label("I2", f"衝撃荷重{_S}安全性・復旧性{_S}複線"),
    B.SERVICE_LR08: Label("0.8LR", f"ﾛﾝｸﾞﾚｰﾙ縦荷重{_S}使用性"),
    B.SERVICE_LR10: Label("1.0LR", f"ﾛﾝｸﾞﾚｰﾙ縦荷重{_S}使用性"),
    B.SAFETY_LR10_B: Label("1.0LR+1.0B", f"ﾛﾝｸﾞﾚｰﾙ+制動{_S}安全性"),
    B.SAFETY_LR11_B: Label("1.1LR+1.0B", f"ﾛﾝｸﾞﾚｰﾙ+制動{_S}安全性"),
    B.SAFETY_LR10_BMAX: Label("1.0LR+1.1B", f"ﾛﾝｸﾞﾚｰﾙ+制動{_S}安全性"),
    B.SAFETY_LR10: Label("1.0LR", f"ﾛﾝｸﾞﾚｰﾙ縦荷重{_S}安全性"),
    B.RESTORABILITY_LR10_B: Label("1.0LR+1.0B", f"ﾛﾝｸﾞﾚｰﾙ+制動{_S}復旧性"),
    B.RESTORABILITY_LR10: Label("1.0LR", f"ﾛﾝｸﾞﾚｰﾙ縦荷重{_S}復旧性"),
}
_AUXILIARY = {
    B.IMPACT_SINGLE: Label("I1s", f"衝撃荷重{_S}使用性{_S}単線"),
    B.IMPACT_DOUBLE: Label("I2s", f"衝撃荷重{_S}使用性{_S}複線"),
}
# 列車の配置 (decision 102): the symbol's suffix as the sample's L1-1, L1-2, L1-3 (Example橋脚4 表2.3.1) and the name's
# remark as its 備考 (両側の桁, 起点側の桁, 終点側の桁)
_PLACINGS = {Layout.BOTH: "1", Layout.ORIGIN: "2", Layout.END: "3"}
_CHECKS = ("破壊 列車最大", "破壊 制動最大", "破壊 ﾛﾝｸﾞ最大", "破壊 雪最大", "ひび割れ 縁応力度", "ひび割れ 永久荷重",
           "ひび割れ 変動荷重", "損傷 列車最大", "損傷 雪最大", "地盤の安定 列車最大", "地盤の安定 制動最大",
           "地盤の安定 ﾛﾝｸﾞ最大", "地盤の安定 雪最大", "長期支持", "短期支持 低水位", "短期支持 高水位")


def _placed(label: Label, layout: Layout | None) -> Label:
    if layout is None:
        return label
    return Label(f"{label.symbol}-{_PLACINGS[layout]}", f"{label.name}{_S}{layout.value}")


LONGITUDINAL = Profile(
    loads={(case, layout): _placed(label, layout) for case, label in _LOADS.items()
           for layout in ((*Layout, None) if case in LAYOUT_DEPENDENT else (None,))},
    auxiliary={((case, layout), Basis.SERVICE_IMPACT): _placed(label, layout) for case, label in _AUXILIARY.items()
               for layout in Layout},
    combinations={},  # by the result's combinations: build_frameweb
    extractions={group.value: name for group, name in EXTRACTION_NAMES.items()},
    springs={SpringTerm.LONG: LONG_TERM, SpringTerm.SHORT: SHORT_TERM},
    basic=Basis.BASIC,
)


def combination_name(combination: Combination) -> str:
    name = _CHECKS[combination.check.value - 1]
    return name if combination.layout is None else f"{name} {combination.layout.value}"


def longitudinal_profile(result: LongitudinalResult) -> Profile:
    """LONGITUDINAL with the names of the result's combinations (each check of the train for ①, ② and ③)."""
    return replace(LONGITUDINAL, combinations={c.number: combination_name(c) for c in result.combinations})


def build_frameweb(result: LongitudinalResult) -> dict[str, Any]:
    """The FrameWeb input document of 0610; ``core.integrity.dump_json`` gives its bytes."""
    document = frameweb_document(result.frame, frameweb_cases(result, longitudinal_profile(result)))
    validate_frameweb(document)
    return document

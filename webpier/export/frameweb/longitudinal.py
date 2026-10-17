"""The FrameWeb input of 0610 (longitudinal, non-seismic): Example2 08 pp.8-1 to 8-11.

The labels are those of the Example2 FrameWeb file (symbols with the nominal factors, 1.0LR+1.0B), except
basic cases 18 and 20, which carry the rail force only and are named as 8-9 prints them. The serviceability
impact (8-5, ``Basis.SERVICE_IMPACT``) is two more load cases. Combine names are the 8-10 performance item and
remark, Pickup names those of 8-11.
"""

from __future__ import annotations

from typing import Any

from ...calc.longitudinal import BasicCase, Basis, LongitudinalResult, SpringTerm
from .build import frameweb_document
from .cases import frameweb_cases
from .profile import LONG_TERM, SHORT_TERM, Label, Profile
from .validate import validate_frameweb

_S = "　"  # the full-width space of the Example2 names
B = BasicCase

LONGITUDINAL = Profile(
    loads={
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
    },
    auxiliary={
        (B.IMPACT_SINGLE, Basis.SERVICE_IMPACT): Label("I1s", f"衝撃荷重{_S}使用性{_S}単線"),
        (B.IMPACT_DOUBLE, Basis.SERVICE_IMPACT): Label("I2s", f"衝撃荷重{_S}使用性{_S}複線"),
    },
    combinations=dict(enumerate((
        "破壊 列車最大", "破壊 制動最大", "破壊 ﾛﾝｸﾞ最大", "破壊 雪最大", "ひび割れ 縁応力度", "ひび割れ 永久荷重",
        "ひび割れ 変動荷重", "損傷 列車最大", "損傷 雪最大", "地盤の安定 列車最大", "地盤の安定 制動最大",
        "地盤の安定 ﾛﾝｸﾞ最大", "地盤の安定 雪最大", "長期支持", "短期支持 低水位", "短期支持 高水位"), 1)),
    extractions=dict(enumerate((
        "安全性（破壊）", "永久＋変動", "永久作用", "変動作用", "復旧性（損傷）", "安全性（安定）", "長期支持性能",
        "短期支持性能"), 1)),
    springs={SpringTerm.LONG: LONG_TERM, SpringTerm.SHORT: SHORT_TERM},
    basic=Basis.BASIC,
)


def build_frameweb(result: LongitudinalResult) -> dict[str, Any]:
    """The FrameWeb input document of 0610; ``core.integrity.dump_json`` gives its bytes."""
    document = frameweb_document(result.frame, frameweb_cases(result, LONGITUDINAL))
    validate_frameweb(document)
    return document

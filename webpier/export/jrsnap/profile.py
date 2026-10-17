"""What differs between the directions of a JRSNAP 5.2-L03 NDU, and the settings both share.

The shared code reads the 0710 / 0720 result by its structure (frame, basic cases, combinations) and takes
everything direction-specific from a ``Profile``: the data name, which 方向別の鉄筋配置表 and hoop row is the
section, the control node, the displacement-increment settings, the input conditions, the footing plan and the
load titles. A direction is a profile, not a branch.

Sources of the fixed settings: the Example2 NDU files saved by JRSNAP (.claude/docs/Example橋脚2/10_線路(耐震)/
線路方向_朝里川温泉P1.ndu, 11_直角(耐震)/直角方向_朝里川温泉P1.ndu: DataInfo, SectSafe, the load titles) and the
JRSNAP 5.2-L03 manual as recorded in .claude/docs/research/webpier-longitudinal-ndu-field-map.md (the rigid
region 1000 m2 / 1000 m4 / 25 kN/mm2, p.144-145; Es = 200 kN/mm2; KR2 = 2 and the final slope 1/20 of the
direct-foundation rotational spring, p.155; GBVO = 1.3 added by 5.2).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ...calc.frame import NodeRole, Region
from ...calc.seismic_longitudinal import SeismicCase as LongitudinalCase
from ...calc.seismic_transverse import SeismicCase as TransverseCase
from ...core.printed import Precision, Printed

NATIVE_VERSION = "5.2.3.S.4"  # the header JRSNAP 5.2-L03 writes (its key is spelt Virsion)
TARGET_VERSION = "5.2-L03"
DISPLACEMENT = Precision(3, "m")

# DataInfo (Example2 NDU): load divisions, trials at intermediate and final steps, convergence factor FTM.
LOAD_DIVISIONS = 1000
TRIALS = 999
CONVERGENCE = Decimal("0.001")
RIGID_AREA, RIGID_INERTIA, RIGID_MODULUS = 1000, 1000, 25  # m2, m4, kN/mm2 (manual p.144-145 initial values)
STEEL_MODULUS = 200  # Es, kN/mm2
# SectSafe without the three input factors: GC, GR, GS, GB1, GB2, GB23, (GBC), (GBV), GBS, K, (GBVD), GBVO.
SAFETY_BEFORE = (Decimal("1.3"), 1, Decimal("1.05"), 1, 1, Decimal("1.15"))
SAFETY_GBS, SAFETY_K, SAFETY_GBVO = 0, Decimal("0.9"), Decimal("1.3")
SOIL_TYPE = 1  # FootInfo 砂質土系: c = 0, the bearing capacity from φ
SANDY_SOILS = ("砂質土", "砂礫")
ROTATION_KR2, ROTATION_KR3 = 2, 20  # FootInfo: KR2 and the reciprocal of the final slope ratio
SECTION_TITLE = "柱"
NONLINEAR_TITLE = "柱下端Mθ"  # at most 20 bytes (manual p.143)

REGION_TITLES = {
    Region.BEAM: "はり", Region.HAUNCH: "ハンチ", Region.COLUMN: "柱", Region.COLUMN_BASE: "柱下端",
    Region.FOOTING_UPPER: "フーチング上", Region.FOOTING_LOWER: "フーチング下", Region.PEDESTAL_ARM: "桁受け腕",
    Region.PEDESTAL: "桁受け", Region.GIRDER: "桁",
}


@dataclass(frozen=True)
class Analysis:
    """The displacement-increment analysis of DataInfo."""

    steps: int  # divisions of the target displacement
    limited_final_step: int  # last step of the limited incremental load (EQL)
    target: Printed  # target horizontal displacement of the control node, signed as the earthquake


@dataclass(frozen=True)
class Profile:
    data_name: str
    face: str  # the bending direction: its 方向別の鉄筋配置表 and its hoop row are the section
    control: frozenset[NodeRole]  # the roles of the control node; La runs from it to the footing top
    analysis: Analysis
    jrsnap: str  # attribute of PierInput.jrsnap (input key jrsnap_<jrsnap>)
    plan: tuple[str, str]  # FoundationResult attributes of FootInfo B (in the plane) and L
    case_titles: Mapping[Enum, str]
    seat_labels: Mapping[Enum, str]  # point loads at the bearing seat
    footing_labels: Mapping[Enum, str]  # point loads at the footing centroid
    member_labels: Mapping[Enum, str]


_L = LongitudinalCase
LONGITUDINAL = Profile(
    data_name="線路方向", face="線路", control=frozenset({NodeRole.CAP_TOP}),
    analysis=Analysis(steps=300, limited_final_step=200, target=DISPLACEMENT.exact(-0.3)),  # 10 NDU: ← 0.300 m
    jrsnap="longitudinal", plan=("b", "l"),
    case_titles={_L.D1: "固定死荷重", _L.D2: "付加死荷重", _L.BUOYANCY: "浮力", _L.SNOW: "雪荷重",
                 _L.TRAIN: "列車荷重（地震時）", _L.GIRDER_INERTIA: "地震時桁荷重慣性力",
                 _L.TRAIN_INERTIA: "地震時列車荷重慣性力", _L.SELF_INERTIA: "自重による地震時慣性力"},
    seat_labels={_L.D1: "上部工反力", _L.D2: "上部工反力", _L.SNOW: "雪荷重", _L.TRAIN: "列車荷重",
                 _L.GIRDER_INERTIA: "上部工慣性力", _L.TRAIN_INERTIA: "列車慣性力"},
    footing_labels={_L.D1: "フーチング自重", _L.D2: "上載土", _L.BUOYANCY: "浮力", _L.SELF_INERTIA: "フーチング慣性力"},
    member_labels={_L.D1: "柱自重", _L.SELF_INERTIA: "自重慣性力"},
)

_T = TransverseCase
TRANSVERSE = Profile(
    data_name="線路直角方向", face="直角", control=frozenset({NodeRole.GIRDER_ORIGIN, NodeRole.GIRDER_END}),
    analysis=Analysis(steps=350, limited_final_step=300, target=DISPLACEMENT.exact(0.35)),  # 11 NDU: → 0.350 m
    jrsnap="transverse", plan=("l", "b"),
    case_titles={_T.D1: "固定死荷重", _T.D2: "付加死荷重", _T.BUOYANCY: "浮力", _T.SNOW: "雪荷重",
                 _T.TRAIN_UP: "列車荷重（地震時・上り線）", _T.TRAIN_DOWN: "列車荷重（地震時・下り線）",
                 _T.GIRDER_INERTIA: "地震時桁荷重慣性力", _T.TRAIN_INERTIA: "列車荷重慣性力",
                 _T.SELF_INERTIA: "自重による地震時慣性力"},
    seat_labels={_T.D1: "上部工反力", _T.D2: "上部工反力", _T.SNOW: "雪荷重", _T.TRAIN_UP: "列車荷重",
                 _T.TRAIN_DOWN: "列車荷重", _T.GIRDER_INERTIA: "上部工慣性力", _T.TRAIN_INERTIA: "列車慣性力"},
    footing_labels={_T.D1: "フーチング自重", _T.D2: "上載土", _T.BUOYANCY: "浮力", _T.SELF_INERTIA: "フーチング慣性力"},
    member_labels={_T.D1: "柱自重", _T.SELF_INERTIA: "自重慣性力"},
)

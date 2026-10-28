"""What differs between the directions of a JRSNAP 5.2-L03 NDU, and the settings both share.

The shared code reads the 0710 / 0720 result by its structure (frame, basic cases, combinations) and takes
everything direction-specific from a ``Profile``: the data name, which 方向別の鉄筋配置表 and hoop row is the
section, the control node, the displacement-increment settings, the input conditions, the footing plan and the
load titles. A direction is a profile, not a branch. The analysis settings (steps, limited step, target
displacement) are inputs of each direction (decision 40), not profile values.

Sources of the fixed settings: the Example2 NDU files saved by JRSNAP (.claude/docs/Example橋脚2/10_線路(耐震)/
線路方向_朝里川温泉P1.ndu, 11_直角(耐震)/直角方向_朝里川温泉P1.ndu: DataInfo, SectSafe, the load titles) and the
JRSNAP 5.2-L03 manual (.claude/agents/jrsnap-operator/JRSNAP_Ver5.2-L03/JRSNAP_操作説明書.pdf, README JRSNAP; the rigid
region 1000 m2 / 1000 m4 / 25 kN/mm2, p.144-145; Es = 200 kN/mm2; KR2 = 2 and the final slope 1/20 of the
direct-foundation rotational spring, p.155; GBVO = 1.3 added by 5.2).
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from ...calc.frame import NodeRole, Region
from ...calc.seismic_longitudinal import EARTHQUAKE as TOWARD_ORIGIN
from ...calc.seismic_longitudinal import SeismicCase as LongitudinalCase
from ...calc.seismic_transverse import EARTHQUAKE as TOWARD_W9
from ...calc.seismic_transverse import SeismicCase as TransverseCase

NATIVE_VERSION = "5.2.3.S.4"  # the header JRSNAP 5.2-L03 writes (its key is spelt Virsion)
TARGET_VERSION = "5.2-L03"

# Solver numerical controls of DataInfo, not design inputs (Example2 NDU DataInfo 5, 10, 11, 20 = JRSNAP defaults):
LOAD_DIVISIONS = 1000  # divisions of the incremental load
TRIALS = 999  # stiffness-reduction trials at the intermediate and the final steps
CONVERGENCE = Decimal("0.001")  # convergence factor FTM of the stiffness reduction
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
# Decision 114: the column's M-θ is always of the 破壊形態 曲げ (no S on the AP card); La/d below 1.25 is a
# low-shear-span member, refused.
MIN_SHEAR_SPAN_RATIO = Decimal("1.25")

REGION_TITLES = {
    Region.BEAM: "はり", Region.HAUNCH: "ハンチ", Region.COLUMN: "柱", Region.COLUMN_BASE: "柱下端",
    Region.FOOTING_UPPER: "フーチング上", Region.FOOTING_LOWER: "フーチング下", Region.PEDESTAL_ARM: "桁受け腕",
    Region.PEDESTAL: "桁受け", Region.GIRDER: "桁", Region.FOOTING_BASE: "フーチング底面",
}


@dataclass(frozen=True)
class Profile:
    data_name: str
    face: str  # the bending direction: its 方向別の鉄筋配置表 and its hoop row are the section
    control: frozenset[NodeRole]  # the roles of the control node; La runs from it to the footing top
    earthquake: Decimal  # ±1: the direction of the earthquake in x (calc), and of the target displacement
    earthquake_text: str  # shown beside the target displacement in the editor
    jrsnap: str  # attribute of PierInput.jrsnap (input key jrsnap_<jrsnap>)
    plan: tuple[str, str]  # FoundationResult attributes of FootInfo B (in the plane) and L
    # by basic case: the train path's enums, a load model's ids (generic_profile)
    case_titles: Mapping[Hashable, str]
    seat_labels: Mapping[Hashable, str]  # point loads at the bearing seat
    footing_labels: Mapping[Hashable, str]  # point loads at the footing centroid
    member_labels: Mapping[Hashable, str]


_L = LongitudinalCase
LONGITUDINAL = Profile(
    data_name="線路方向", face="線路", control=frozenset({NodeRole.CAP_TOP}),
    earthquake=TOWARD_ORIGIN, earthquake_text="−x（←）",
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
    data_name="線路直角方向", face="直角", control=frozenset({NodeRole.CONTROL}),  # decision 65
    earthquake=TOWARD_W9, earthquake_text="+x（→）",
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


# The labels of the application's cases with a load model (decision 70), as the train path labels them.
_GENERIC_SEAT = {"D1": "上部工反力", "D2": "上部工反力"}
_GENERIC_FOOTING = {"D1": "フーチング自重", "D2": "上載土", "WP_NORMAL": "浮力", "EQ2": "フーチング慣性力"}
_GENERIC_MEMBER = {"D1": "柱自重", "EQ2": "自重慣性力"}


def generic_profile(base: Profile, seismic: Any) -> Profile:
    """*base* (LONGITUDINAL or TRANSVERSE) with the cases of a generic 0710 / 0720 (decision 70): titled and ordered
    as the load model declares them, its cases labelled by their names at the bearing seat."""
    cases = [case.id for case in seismic.basic_cases]
    application = set(_GENERIC_FOOTING) | set(_GENERIC_SEAT)
    return replace(
        base, case_titles={case.id: case.name for case in seismic.basic_cases},
        seat_labels={case.id: _GENERIC_SEAT.get(case.id, case.name) for case in seismic.basic_cases
                     if case.id in _GENERIC_SEAT or case.id not in application},
        footing_labels={case: label for case, label in _GENERIC_FOOTING.items() if case in cases},
        member_labels={case: label for case, label in _GENERIC_MEMBER.items() if case in cases})

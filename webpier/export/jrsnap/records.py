"""The NDU model laid out as JRSNAP 5.2-L03 records, in the order the native reader consumes them.

The record set and order are those JRSNAP 5.2-L03 saves (header 5.2.3.S.4; recorded in README JRSNAP and
confirmed against the Example2 NDU files for the shared records). The
inactive records are written with their native initial values: no pile, no slope ground, no linked foundation
check, no soil-analysis link, no displacement link, no section check (Sesf), display settings as initialised.
``Tisou=`` must be present even with TishouNum=0. A field is a number, BLANK (one space: not set), EMPTY (no
character, the inactive SesfPiIJ form), a bool, UNSET (the native "not set" single) or text.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Union

from ...core.printed import Printed
from .model import NduModel
from .profile import (
    CONVERGENCE, LOAD_DIVISIONS, NATIVE_VERSION, NONLINEAR_TITLE, RIGID_AREA, RIGID_INERTIA, RIGID_MODULUS,
    ROTATION_KR2, ROTATION_KR3, SECTION_TITLE, SOIL_TYPE, STEEL_MODULUS, TRIALS,
)


class Token(str):
    """A field written exactly as given, not as text to check."""


BLANK = Token(" ")
EMPTY = Token("")
UNSET = Token("-3.402823E+38")  # the native "not set" (−Single.MaxValue), as JRSNAP saves it
Field = Union[Printed, Decimal, int, bool, str]
Record = tuple[str, tuple[Field, ...] | None]  # None: a bare key line

TITLES = 20
COMBINATION_SLOTS = 15  # SNAPConb holds 15 case coefficients
# Native initial values of the inactive foundation-check resistance tables (JibanTeikouKeisuu1-3).
RESISTANCE = (Decimal("0.83"), 1, 1)
CONSTANT_RECORDS = {
    "ExOptLoad": (1, 1, 1),
    "ExOptDisp": (2, 2, 1, 0, 0, 1, 0, 0),
    "HendoCaseInfo": (0,) * 10,
    "TanbuShiji1": (0, 0),
    "GanmaA": (Decimal("1.2"), 1, 1, 1),
    "FontColor": (0, 0, 9, 12, 12, 13),
    "FontSize": (3,) * 6,
    "FontName": ("ＭＳ Ｐゴシック",),
    "LineColor": (0, 13, 10, 11, 12),
    "LineWidth": (0, 0, 0, 0, 10),
    "Sunpo": (Decimal("0.3"), Decimal("0.2")),
    "JointCircle": (Decimal("0.5"),),
    "Grid": (1, 1, 1, 1),
    "ErrInfo": (0,) * 11,
}


def _data_info(model: NduModel) -> tuple[Field, ...]:
    analysis, first = model.analysis, model.combinations[0]
    return (1, 1, analysis.steps, model.control, LOAD_DIVISIONS, analysis.limited_final_step, BLANK, BLANK, BLANK,
            TRIALS, TRIALS, 1, 1, 1, 1, 1, first.rho_m, first.alpha_f, analysis.target, CONVERGENCE, 0, 1, 0, 0, 0, 0)


def _frame(model: NduModel) -> Iterator[Record]:
    yield "JointOrg", (model.origin,)
    yield "JointNum", (len(model.joints),)
    for joint in model.joints:
        yield f"JointXY{joint.number}", (joint.x, joint.y, joint.number)
    yield "MemberNum", (len(model.elements),)
    for e in model.elements:
        yield f"MemberTitle{e.number}", (e.title,)
        yield f"MemberInfo{e.number}", (e.i, e.j, 1)
        yield f"MemberLeng{e.number}", (e.length,)
        yield f"MemberOkuyuki{e.number}", (1,)
        yield f"MemberDvid{e.number}-1", (e.length, 1)
        yield f"MemberShogen{e.number}", (1,)
    for e in model.elements:
        yield f"MemberKUI{e.number}", (0,)
    yield "KGNum", (0,)
    yield "ElementNum", (len(model.elements),)
    for e in model.elements:
        stiffness = (BLANK,) * 3 if e.nonlinear else (RIGID_AREA, RIGID_INERTIA, RIGID_MODULUS)
        yield f"ElementInfo{e.number}", (2 if e.nonlinear else 1, 0, 0, 0, e.i, e.j, int(e.nonlinear), 0,
                                         *stiffness, 0, 0, e.number)
    yield "HendoCaseInfo", CONSTANT_RECORDS["HendoCaseInfo"]
    yield "JibanCaseNum", (1,)
    for e in model.elements:
        yield f"JibanShogenInfo{e.number}", (BLANK,) * 7
    yield "TyakumokuNum", (0,)
    for e in model.elements:
        yield f"ElementTyakumokuNum{e.number}", (0, 0)
    yield "SHABUZAI_INFO", None
    for joint in model.joints:
        yield f"SHABUZAI_JointXY{joint.number}", (0, 0, False)
    for e in model.elements:
        yield f"ShabuzaiMeInfo{e.number}", (*(0,) * 9, False, False)
    yield "NonLinNum", (1, 1, 0)  # one automatic M-θ definition, for the one nonlinear element
    # The 4th field is the 破壊形態: 1 曲げ, 2 せん断 (the AP card's S; decision 66)
    yield "NonLinInfo1", (1, 1, 1, 2 if model.section.shear_failure else 1, 1, 1, 1, 1, 0, NONLINEAR_TITLE)


def _section(model: NduModel) -> Iterator[Record]:
    s = model.section
    yield "SectNum", (1,)
    yield "SectTitle1", (SECTION_TITLE,)
    yield "SectInfo1", (1, 1, 0, 1, s.width, s.height, 0, 0, 0, s.shear_span, UNSET, 0, 0, 0)
    yield "TanbuShiji1", CONSTANT_RECORDS["TanbuShiji1"]
    yield "SectConc1", (s.fck, 0, s.ec, 0, s.aggregate_max)
    yield "SectJikuNum1", (len(s.rows), *(s.main_layers,) * 4, 0)
    yield "SectJiku1", (s.yield_strength, STEEL_MODULUS, 0, 0, s.main_pitch, s.main_pitch, 0, 0, 0)
    for index, row in enumerate(s.rows, 1):
        yield f"SectRein1-{index}", (row.center, row.diameter, row.count)
    hoop = (s.shear.yield_strength, s.shear.diameter, s.shear.legs, s.shear.pitch)
    yield "SectSher1", (*hoop, 0, 0, *hoop)
    yield "SectSafe1", s.safety


def _supports(model: NduModel) -> Iterator[Record]:
    f = model.footing
    yield "SuppotNum", (len(model.springs) + 1,)
    yield "SuppotRow", (len(model.springs),)
    yield "SuppotAlf", (0, 0)
    yield "ShitenCaseNum", (0,)
    for index, spring in enumerate(model.springs, 1):
        yield f"SuppotInfo{index}", (BLANK, spring.node, spring.direction, spring.stiffness, *(BLANK,) * 9)
    yield "FootRow", (1,)
    yield "FootInfo1", (BLANK, f.node, SOIL_TYPE, f.b, f.l, f.kv, 0, f.depth, f.gamma1, f.gamma2, f.phi,
                        ROTATION_KR2, ROTATION_KR3, UNSET)
    yield "ChokuKisoNum", (0,)
    yield "G_intCHOKU_KISO_Link_Num", (0,)
    for index in range(1, len(model.springs) + 1):
        yield f"Suppot_ChokuKisoCaseNo{index}", (0,)
    yield "Foot_ChokuKisoCaseNo1", (0,)
    for e in model.elements:
        yield f"Member_BunpuBane{e.number}", (0,)
    for index, coefficient in enumerate(RESISTANCE, 1):
        yield f"JibanTeikouKeisuu{index}", (coefficient,) * 5


def _blank_zero(value: Printed) -> Field:
    return value if value.value else BLANK


def _loads(model: NduModel) -> Iterator[Record]:
    yield "LoadNum", (len(model.cases),)
    yield "MLoadNum", (sum(len(case.member_loads) for case in model.cases),)
    yield "JLoadNum", (sum(len(case.joint_loads) for case in model.cases),)
    member = joint = 0
    for case in model.cases:
        yield f"LoadTitle{case.number}", (case.title,)
        yield f"LoadCase{case.number}", (1, 1, 0)
        yield f"LoadAlph{case.number}", (1,)
        yield f"MLoadRow{case.number}", (len(case.member_loads),)
        for load in case.member_loads:
            member += 1
            yield f"MLoadInfo{member}", (case.number, BLANK, load.element, case.increment, load.kind, BLANK, BLANK,
                                         load.start, BLANK if load.end is None else load.end, BLANK, BLANK, load.label)
        yield f"JLoadRow{case.number}", (len(case.joint_loads),)
        for load in case.joint_loads:
            joint += 1
            # The zero row of a case without loads (decision 62) writes N = 0: a row of three blanks is no load.
            n = _blank_zero(load.n) if load.h.value or load.n.value or load.m.value else load.n
            yield f"JLoadInfo{joint}", (case.number, BLANK, load.node, case.increment, _blank_zero(load.h), n,
                                        _blank_zero(load.m), load.label)
    for key in ("ELoadNum", "ELoadRow", "DLoadNum", "DLoadRow"):
        yield key, (0,)
    yield "SNAPConbNum", (len(model.combinations),)
    for index, c in enumerate(model.combinations, 1):
        padding = (BLANK,) * (COMBINATION_SLOTS - len(c.coefficients))
        yield f"SNAPConb{index}", (c.rho_m, c.alpha_f, 0, 0, *c.coefficients, *padding, 0, 0)
    yield "ConbNum", (len(model.combinations),)
    for index, c in enumerate(model.combinations, 1):
        yield f"ConbAlpf{index}", c.coefficients


def _tail(model: NduModel) -> Iterator[Record]:
    for key in ("PickNum", "Conb2Num", "Pick2Num", "TishouNum"):
        yield key, (0,)
    yield "Tisou", (EMPTY,)
    yield "SesfNum", (0,)
    for e in model.elements:
        yield f"SesfPiIJ{e.number}", (0, 0, 0, 0, EMPTY, EMPTY)
    for key in ("SesfKihonNum", "SesfPiM", "SesfPiS"):
        yield key, (0,)
    yield "SesfPiBuzai", (0,) * 5
    for key in ("GanmaA", "FontColor", "FontSize", "FontName", "LineColor", "LineWidth", "Sunpo", "JointCircle",
                "Grid", "ErrInfo"):
        yield key, CONSTANT_RECORDS[key]


def records(model: NduModel) -> list[Record]:
    head: list[Record] = [("Virsion", (Token(NATIVE_VERSION),)), ("DataName", (model.profile.data_name,))]
    head += [(f"DataTitle{index}", (EMPTY,)) for index in range(1, TITLES + 1)]
    head += [("DataInfo", _data_info(model)), ("ExOptLoad", CONSTANT_RECORDS["ExOptLoad"]),
             ("ExOptDisp", CONSTANT_RECORDS["ExOptDisp"])]
    return [*head, *_frame(model), *_section(model), *_supports(model), *_loads(model), *_tail(model)]

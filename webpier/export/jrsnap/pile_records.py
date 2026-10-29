"""The NDU of a pile foundation laid out as JRSNAP 5.2-L03 records, in the order its reader consumes them (decision 93).

The records are those of ``records`` for the shared parts (the header, the loads, the display settings) and the ones of
the sample 01_サンプル(V53)：RC橋脚L for the members, the pile elements, their ground springs and the circular sections of
the piles (``pile-ndu-fields.md``). The link to a .sdc (SRenkei) is not written: its path would make the bytes depend on
where the file is put, and the springs it would let the screen recompute are in the model already (decision 93).
"""

from __future__ import annotations

from collections.abc import Iterator
from .pile_model import JointHeadSection, PileNduModel, PileSection, PipeSection
from .profile import RIGID_AREA, RIGID_INERTIA, RIGID_MODULUS, STEEL_MODULUS
from .records import BLANK, CONSTANT_RECORDS, RESISTANCE, UNSET, Record, head_records, loads_records, tail_records

YIELD_ANGLE = 45  # 着目降伏角度: the tension side at 45°


def pile_section_records(number: int, s: PileSection) -> Iterator[Record]:
    """SectTitle … SectSafe of section *number*, a circle with one ring of main bars and hoops."""
    yield f"SectTitle{number}", (s.title,)
    # 表2-28: the radius, the 内周半径, …, the 作用軸力 (blank: the axial force of the analysis)
    yield f"SectInfo{number}", (1, 2, 0, 1, s.radius, 0 if s.inner_radius is None else s.inner_radius, 0, 0, 0, 0,
                                UNSET if s.axial_force is None else s.axial_force, 0, 0, 0)
    yield f"TanbuShiji{number}", CONSTANT_RECORDS["TanbuShiji1"]
    yield f"SectConc{number}", (s.fck, s.construction, s.construction, 0, s.aggregate_max)
    yield f"SectJikuNum{number}", (1, 0, 0, 0, 0, 0)
    yield f"SectJiku{number}", (s.yield_strength, STEEL_MODULUS, 0, 0, 0, 0, YIELD_ANGLE, 0, 0)
    yield f"SectRein{number}-1", (s.center, s.diameter, s.count)
    hoop = (s.hoop_yield, s.hoop_diameter, s.hoop_legs, s.hoop_pitch)
    yield f"SectSher{number}", (*hoop, 0, 0, *hoop)
    yield f"SectSafe{number}", s.safety


def joint_section_records(number: int, s: JointHeadSection) -> Iterator[Record]:
    """SectTitle … SectSafe of the joint of a 鋼管ソイルセメント杭 (shape 501): the virtual RC circle (its radius, the pipe's
    thickness), the fill, the anchor bars and, after them, SectCFT with the yield strength and the modulus of the pipe
    (decision 122; JRSNAP_Input writes the NDT of shape 501 from these, not SectSher)."""
    yield f"SectTitle{number}", (s.title,)
    yield f"SectInfo{number}", (1, 501, 0, 1, s.radius, s.thickness, 0, 0, 0, 0, UNSET, 0, 0, 0)
    yield f"TanbuShiji{number}", CONSTANT_RECORDS["TanbuShiji1"]
    yield f"SectConc{number}", (s.fck, 0, 0, s.confined, s.aggregate_max)  # 表2-55: f'ck, fbck, Ec (JRSNAP's), 接合部圧縮強度
    yield f"SectJikuNum{number}", (1, 0, 0, 0, 0, 0)
    yield f"SectJiku{number}", (s.bar_yield, STEEL_MODULUS, 0, 0, 0, 0, YIELD_ANGLE, 0, 0)
    yield f"SectRein{number}-1", (s.center, s.bar_diameter, s.bar_count)
    yield f"SectCFT{number}", (0, s.pipe_yield, STEEL_MODULUS, 0, 0, 0, 0, 0)
    yield f"SectSher{number}", (0,) * 10
    yield f"SectSafe{number}", s.safety


def pipe_section_records(number: int, s: PipeSection) -> Iterator[Record]:
    """SectTitle … SectSafe of the pipe of a 鋼管ソイルセメント杭: shape 8 of the kind 鋼管杭 (SectInfo's third field 1), no bars,
    IntSectMpile (Tri-Linear) and SectMpile (f_syk and the factor 1.0 on the yield point of a pile; the rest JRSNAP's or 0)
    before SectSher (decision 122)."""
    yield f"SectTitle{number}", (s.title,)
    yield f"SectInfo{number}", (1, 8, 1, 1, s.diameter, s.thickness, 0, 0, 0, 0, UNSET, 0, 0, 0)
    yield f"TanbuShiji{number}", CONSTANT_RECORDS["TanbuShiji1"]
    yield f"SectConc{number}", (0,) * 5
    yield f"SectJikuNum{number}", (0,) * 6
    yield f"SectJiku{number}", (0,) * 9
    yield f"IntSectMpile{number}", (0, 0)
    yield f"SectMpile{number}", (0, 0, s.yield_strength, 0, 0, 0, 1, 0)
    yield f"SectSher{number}", (0,) * 10
    yield f"SectSafe{number}", s.safety


def _frame(model: PileNduModel) -> Iterator[Record]:
    yield "JointOrg", (model.origin,)
    yield "JointNum", (len(model.joints),)
    for joint in model.joints:
        yield f"JointXY{joint.number}", (joint.x, joint.y, joint.number)
    yield "MemberNum", (len(model.members),)
    for m in model.members:
        yield f"MemberTitle{m.number}", (m.title,)
        yield f"MemberInfo{m.number}", (m.i, m.j, len(m.divisions))
        yield f"MemberLeng{m.number}", (m.length,)
        yield f"MemberOkuyuki{m.number}", (m.depth_piles,)
        for index, (length, count) in enumerate(m.divisions, 1):
            yield f"MemberDvid{m.number}-{index}", (length, count)
        yield f"MemberShogen{m.number}", (int(m.nonlinear),)
    for m in model.members:
        yield f"MemberKUI{m.number}", (int(m.pile),)
    yield "KGNum", (len(model.piles),)
    for index, pile in enumerate(model.piles, 1):
        yield f"KGInfo{index}", (pile.member, pile.first, pile.last, 0)
    yield "ElementNum", (len(model.elements),)
    for e in model.elements:
        stiffness = (RIGID_AREA, RIGID_INERTIA, RIGID_MODULUS) if e.nonlinear == 0 else (BLANK,) * 3
        yield f"ElementInfo{e.number}", (e.kind, 0, 0, 0, e.i, e.j, e.nonlinear, 0, *stiffness, 0, 0, e.number)
    yield "HendoCaseInfo", CONSTANT_RECORDS["HendoCaseInfo"]
    yield "JibanCaseNum", (1,)
    for e in model.elements:
        g = e.ground
        yield f"JibanShogenInfo{e.number}", ((BLANK,) * 7 if g is None
                                             else (BLANK, g.horizontal, g.pressure_top, g.pressure_bottom, BLANK, BLANK, BLANK))
    yield "TyakumokuNum", (0,)
    for e in model.elements:
        yield f"ElementTyakumokuNum{e.number}", (0, 0)
    yield "SHABUZAI_INFO", None
    for joint in model.joints:
        yield f"SHABUZAI_JointXY{joint.number}", (0, 0, False)
    for m in model.members:
        yield f"ShabuzaiMeInfo{m.number}", (*(0,) * 9, False, False)
    yield "NonLinNum", (len(model.nonlinear), len(model.nonlinear), 0)
    for index, row in enumerate(model.nonlinear, 1):
        yield f"NonLinInfo{index}", (1, row.section, row.model, row.failure, 1, *row.ends, row.depth_piles, 0, row.title)


def _supports(model: PileNduModel) -> Iterator[Record]:
    yield "SuppotNum", (len(model.supports),)
    yield "SuppotRow", (len(model.supports),)
    yield "SuppotAlf", (0, 0)
    yield "ShitenCaseNum", (0,)
    for index, support in enumerate(model.supports, 1):
        yield f"SuppotInfo{index}", (BLANK, support.node, support.kind, *support.values)
    yield "FootRow", (0,)
    yield "ChokuKisoNum", (0,)
    yield "G_intCHOKU_KISO_Link_Num", (0,)
    for index in range(1, len(model.supports) + 1):
        yield f"Suppot_ChokuKisoCaseNo{index}", (0,)
    for m in model.members:
        yield f"Member_BunpuBane{m.number}", (0,)
    for index, coefficient in enumerate(RESISTANCE, 1):
        yield f"JibanTeikouKeisuu{index}", (coefficient,) * 5


def records(model: PileNduModel) -> list[Record]:
    sections: list[Record] = [("SectNum", (len(model.sections),))]
    for group in model.sections:
        sections += group
    return [*head_records(model), *_frame(model), *sections, *_supports(model), *loads_records(model),
            *tail_records(model)]

"""The JRSNAP sample 01_サンプル(V53)：RC橋脚L as a ``PileNduModel`` (decision 93), and its NDU as JRSNAP saved it.

The sample is a wall pier on 8 場所打ち杭 (φ1.0 m, L = 19 m) in three rows of 3, 2 and 3 piles, linked to the .sdc SOIL-JR 5.3
returned for its sample S (``tests/fixtures/soiljr/pile_s53.sdc``). The column, the footing and the loads of the model are
written out here from the NDU; the piles come from ``calc.pile_seismic`` and ``export.jrsnap.pile_build``, which is what is
tested. ``tests/fixtures/jrsnap/pile_s.ndu`` is the file; ``pile_s_springs.json`` has its spring rows.
"""

from decimal import Decimal
from pathlib import Path

from webpier.calc.pile_seismic import pile_row
from webpier.core.printed import LENGTH, Printed
from webpier.export.jrsnap import LONGITUDINAL
from webpier.export.jrsnap.model import Analysis, Combination, Joint, JointLoad, LoadCase
from webpier.export.jrsnap.pile_build import pile_row_parts
from webpier.export.jrsnap.pile_model import (
    COLUMN, M_THETA, RIGID, FrameElement, Member, NonLinear, PileNduModel, PileSection,
)
from webpier.export.jrsnap.pile_records import pile_section_records
from webpier.export.jrsnap.profile import SAFETY_BEFORE, SAFETY_GBS, SAFETY_GBVO, SAFETY_K
from webpier.export.jrsnap.records import UNSET
from webpier.export.soiljr.sdc_seismic import parse_seismic

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_NDU = FIXTURES / "jrsnap" / "pile_s.ndu"
SDC = FIXTURES / "soiljr" / "pile_s53.sdc"
TOP = LENGTH(1.307)  # the footing is 1.307 m from the centre line of its members to its base, where the ground begins


def printed(value: float, digits: int = 3, unit: str = "") -> Printed:
    return Printed(value, digits, unit)


def sample_records() -> list[tuple[str, str]]:
    """(key, right-hand side) of each line of the sample NDU, in file order."""
    lines = SAMPLE_NDU.read_bytes().decode("cp932").split("\r\n")[:-1]
    return [(line.partition("=")[0], line.partition("=")[2]) for line in lines]


def column_section() -> tuple:
    """SectTitle1 … SectSafe1 of the wall pier, as the sample has them (a shape the writer of the column does not know)."""
    return (("SectTitle1", ("壁式橋脚く体",)),
            ("SectInfo1", (4, 10, 0, 1, 900, 25, 0, 0, 0, 8000, UNSET, 0, 0, 0)),
            ("TanbuShiji1", (0, 0)),
            ("SectConc1", (Decimal("20.37"), 0, 25, 0, 25)),
            ("SectJikuNum1", (1, 0, 0, 0, 0, 0)),
            ("SectJiku1", (295, 200, 0, 0, 0, 0, 0, 0, 0)),
            ("SectRein1-1", (0, 0, 0)),
            ("SectCFT1", (1, 314, 200, 45, 16000, 480, Decimal("31.4"), 0)),
            ("SectSher1", (295, 0, 0, 0, 0, 0, 295, 0, 0, 0)),
            ("SectSafe1", (Decimal("1.3"), 1, Decimal("1.05"), 1, 1, 1, Decimal("1.3"), 0, 0, Decimal("0.9"), 0, 0)))


SAFETY = (*SAFETY_BEFORE, Decimal("1.3"), Decimal("1.1"), SAFETY_GBS, SAFETY_K, Decimal("1.2"), SAFETY_GBVO)


def pile_section(pitch: int, axial: Decimal | None = Decimal(210)) -> PileSection:
    return PileSection(
        title=f"杭(φ1000)：帯鉄筋ctc{pitch}", radius=printed(500, 0, "mm"),
        axial_force=None if axial is None else printed(float(axial), 0, "kN"), fck=printed(30, 0, "N/mm2"),
        construction=-3, aggregate_max=printed(25, 0, "mm"), yield_strength=printed(345, 0, "N/mm2"),
        center=printed(156, 0, "mm"), diameter=printed(32, 0, "mm"), count=20, hoop_yield=printed(345, 0, "N/mm2"),
        hoop_diameter=printed(19, 0, "mm"), hoop_legs=2, hoop_pitch=printed(pitch, 0, "mm"), safety=SAFETY)


def sample_model(axial: Decimal | None = Decimal(210)) -> PileNduModel:
    direction = parse_seismic(SDC.read_bytes()).direction("橋軸方向")
    diameter = LENGTH(1.0)
    joints = [Joint(1, printed(0), printed(-9.493)), Joint(2, printed(0), printed(-1.493)),
              Joint(3, printed(0), printed(-1.483)), Joint(4, printed(-3), printed(0)), Joint(5, printed(0), printed(0)),
              Joint(6, printed(3), printed(0))]
    members = [Member(1, "壁式橋脚く体", 1, 5, LENGTH(9.493), ((LENGTH(8), 1), (LENGTH(0.01), 1), (LENGTH(1.483), 1))),
               Member(2, "フーチング左", 4, 5, LENGTH(3), ((LENGTH(3), 1),)),
               Member(3, "フーチング右", 5, 6, LENGTH(3), ((LENGTH(3), 1),))]
    elements = [FrameElement(1, 1, 2, RIGID, 0), FrameElement(2, 2, 3, COLUMN, 1), FrameElement(3, 3, 5, RIGID, 0),
                FrameElement(4, 4, 5, RIGID, 0), FrameElement(5, 5, 6, RIGID, 0)]
    nonlinear = [NonLinear(section=1, model=M_THETA, failure=1, ends=(1, 1), depth_piles=1, title="壁式橋脚く体：要素番号　2")]
    piles, supports = [], []
    # +x is the push: the pile row on the right (x = +3) is the first column of the .sdc, the left one the third
    for number, (title, head, x, row) in enumerate((("杭（３本杭）", 4, -3, 3), ("杭（２本杭）", 5, 0, 2),
                                                   ("杭（３本杭）", 6, 3, 1)), 4):
        parts = pile_row_parts(
            pile_row(direction, row, diameter), member=number, head_joint=head, first_joint=len(joints) + 1,
            x=printed(x), top=TOP, rigid=TOP, first_element=len(elements) + 1, first_nonlinear=len(nonlinear) + 1,
            section=lambda depth: 2 if depth.value < 2.0 else 3, zone=LENGTH(2.0), title=title)
        joints += parts.joints
        members.append(parts.member)
        elements += parts.elements
        nonlinear += parts.nonlinear
        piles.append(parts.pile)
        supports += parts.supports
    sections = tuple(tuple(pile_section_records(n, pile_section(pitch, axial))) for n, pitch in ((2, 100), (3, 200)))
    load = JointLoad(node=1, h=printed(0), n=printed(5762.4, 1), m=printed(0), label="上部工反力")
    case = LoadCase(1, "固定死荷重", 0, (), (load,))
    combination = Combination(rho_m=printed(1, 1), alpha_f=printed(1, 1), coefficients=(1,))
    return PileNduModel(
        profile=LONGITUDINAL, analysis=Analysis(steps=200, limited_final_step=200, target=LENGTH(0.6),
                                                max_seismic=printed(1, 2), load_divisions=1000), control=1, origin=5,
        joints=tuple(joints), members=tuple(members), elements=tuple(elements), nonlinear=tuple(nonlinear),
        sections=(column_section(), *sections), piles=tuple(piles), supports=tuple(supports), cases=(case,),
        combinations=(combination,), shear_span=printed(8000, 0, "mm"))

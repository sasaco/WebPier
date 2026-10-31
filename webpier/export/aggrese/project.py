"""The Aggre-SE project of a 0711 / 0721 analysis (decision 49, CONTEXT.md 耐震照査の入力).

Aggre-SE (structural-mcp ``Batch``, Docu-SE) reads the JRSNAP results of each Case (the DB1 and the files of the same
name beside it) with the conditions of a project XML. Only the 耐震設計条件 are inputs; the other conditions are
WebPier's, those of the Example2 projects (.claude/docs/Example橋脚2/10_線路(耐震)/P1_線路.xml and 11_直角(耐震)/
P1_直角.xml), and the values that follow from the NDU are taken from its model:

- the direct foundation checked at the FootInfo joint (Aggre-SE's 直接基礎の照査位置 is a joint number);
- the shear span La of the one nonlinear (M-θ) member, in mm, as the NDU's section has it;
- the focus joint 0: Aggre-SE then uses the control joint stored in each DB1;
- the check items of each Case, by the 照査パターン (ρm, αf) of its combination (decision 76).

The project of a pile foundation (decision 94) differs in what it checks: the members are the column and the sections of the
piles (部材照査タイプ 杭), the reactions are taken at the head of each pile row and the displacement at the footing top, and
the limit values of the foundation's stability are SOIL-JR's, which the runner reads from the .sdr it is given (``--sdr``). The
check ⑧ 杭の段落し is made only for a pile with a cut-off (decision 98: its 段落し情報, ``AnchorBar``, with the 杭頭定着長
WebPier calculates), on the Cases its 照査パターン checks it; Aggre-SE calculates the capacity after the cut-off from the bars
it is given, so the NDU keeps the section of the head. A 鋼管ソイルセメント杭 with a cut-off of its pipe (decision 126) has
⑧ too: Aggre-SE reads the bars after the cut-off of a steel pipe pile (its elements 62 and 501) as the pipe below it, its
diameter, wall and yield strength. The Cases are those of the combinations of every NDU of the stage in turn: the NDU of the
forward push, then the one of the reversed push (decision 93).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
import re

from ...calc.detailing.pile import head_anchorage, section
from ...calc.pile_body import STEEL_PIPE_STRENGTH
from ...core.errors import InputError
from ...core.printed import Printed
from ...inputs import PierInput
from ...inputs.choices import CAST_IN_PLACE_PILE, GROUND_CLASSES, LIQUEFACTION_INDEXES, REGIONS, STEEL_SOIL_CEMENT_PILE
from ...inputs.model import STEEL_JOINT_REDUCTION, STEEL_PIPE_EMBEDMENT_MM
from ..jrsnap.model import NduModel
from ..jrsnap.pile_model import COLUMN, PileNduModel

SECTION = "耐震設計条件"
_CASE = re.compile(r".*\(Case(\d+)_[^()]*\)\.db1", re.IGNORECASE)  # JRSNAP's <data>(Case<n>_ρm…_αf…_…).DB1

# Decision 76: the check items ①..⑨ of a Case by its 照査パターン (ρm, αf), whichever way it is pushed:
# ① 復旧性L2, ② 安全性L2, ③ 損傷レベル, ④ 破壊形態の検討, ⑤ せん断耐力, ⑥ L1, ⑦ 基礎の安定, ⑧ 杭の段落し,
# ⑨ 断面力ピックアップ. ③ all but (1.0, 2.0), ④ ρm 1.2, ⑤ none, ⑥ (1.0, 1.0), ⑦⑧⑨ αf 1.0.
CHECKS = {
    (Decimal("1.0"), Decimal("1.0")): (True, True, True, False, False, True, True, True, True),
    (Decimal("1.2"), Decimal("1.0")): (True, True, True, True, False, False, True, True, True),
    (Decimal("1.0"), Decimal("2.0")): (True, True, False, False, False, False, False, False, False),
    (Decimal("1.2"), Decimal("2.0")): (True, True, True, True, False, False, False, False, False),
}
Checks = tuple[bool, ...]


class ProjectError(ValueError):
    """The JRSNAP results cannot be named in the project (not the input's fault)."""


@dataclass(frozen=True)
class Project:
    """What the project XML takes from the input and the NDU; everything else is a fixed condition."""

    region: int  # index of REGIONS (A, B, C)
    ground_class: int  # index of GROUND_CLASSES (G0 .. G5)
    shear_span: Printed  # La of the nonlinear member, mm
    footing_joint: int  # FootInfo joint: the direct foundation that is checked; of piles, the footing top joint
    cases: tuple[Checks, ...]  # the check items ①..⑨ of each combination of the NDU, one DB1 each
    pile_rows: tuple["PileRow", ...] = ()  # a pile foundation: where the reaction of each pile row is taken
    pile_sections: int = 0  # a pile foundation: the sections of the piles, each a member of the 杭 type
    liquefaction_cases: tuple[int, ...] = ()  # the indexes (from 0) of the Cases for the liquefaction (decision 95)
    liquefaction_index: int = 0  # 液状化指数: the index of choices.LIQUEFACTION_INDEXES (_rbEkijo)
    # the 着目点 (_AtPoint): 0, the control joint of each DB1; the NDU's control joint with the Cases of the 応答変位法, whose load
    # increment keeps none in its DB1 (decision 97; the inertia Cases have the same one)
    focus_joint: int = 0
    anchor_bar: "AnchorBar | None" = None  # a pile with a cut-off: ⑧ 杭の段落し (decision 98)

    @property
    def piled(self) -> bool:
        return bool(self.pile_rows)


@dataclass(frozen=True)
class PileRow:
    """The reaction Aggre-SE takes at the head of a pile row: its joint and the piles of the row in the depth."""

    head: int
    piles: int


@dataclass(frozen=True)
class AnchorBar:
    """The 段落し情報 of Aggre-SE's ⑧ 杭の段落し (clsPileAnchorBar): of a 場所打ち杭 (decision 98), the elements of each pile
    row, the bars after the cut-off and the lengths (mm) and rules of 鉄筋.杭.cutoff, with the 杭頭定着長 of the calculation;
    of a 鋼管ソイルセメント杭 (decision 126), the pipe below the cut-off in the same places (D1 its diameter, n1 its wall, D2 its
    yield strength) and the lengths of its 段落し. None is an item Aggre-SE does not read for it: its initial value."""

    rows: tuple[tuple[int, int, int], ...]  # (first element, last element, piles in the depth) of each pile row
    main_diameter: Decimal  # D1: 段落し後の軸方向鉄筋径; of a pipe 杭径 (the outer diameter less the corrosion)
    main_count: int  # n1; of a pipe 厚 (the wall less the corrosion)
    hoop_diameter: Decimal  # D2: 段落し後の帯鉄筋径; of a pipe 強度 (fsy, N/mm2)
    hoop_sets: int | None  # Aw: 帯鉄筋組数
    hoop_pitch: Decimal | None  # Ss: 帯鉄筋間隔
    head_anchorage: Decimal  # PileHeadLength: 杭頭定着長; of a pipe 杭頭埋込長
    cutoff_length: Decimal | None  # ParagraphLength: 段落し長さ; of a pipe 上杭長 (None: Aggre-SE finds the cut-off)
    concrete_strength: Decimal | None  # ConcreteStrength: 定着部のコンクリート強度 (the footing's)
    joint_reduction: Decimal  # ReductionCoefficient: 継手低減係数
    cutoff_anchorage: Decimal | None  # PileMidLength: 段落し定着長
    margin: Decimal | None  # DesignMarginLength: 設計余裕長
    no_joint_head: Decimal  # DisabledFromPileHead
    no_joint_above: Decimal  # DisabledUpwardFromCutOffPoint; of a pipe 施工余裕長 低止まり
    no_joint_below: Decimal  # DisabledDownwardFromCutOffPoint; of a pipe 施工余裕長 高止まり
    margin_moment: Decimal | None  # MudCoefficient: 余裕率（曲げ）
    margin_shear: Decimal | None  # VudCoefficient: 余裕率（せん断）


_CUTOFF = "鉄筋.杭.cutoff"


def anchored(pier: PierInput) -> bool:
    """Whether the piles of *pier* have a cut-off, which Aggre-SE checks as ⑧: of a 場所打ち杭 its main bars after it are
    entered (decision 98), of a 鋼管ソイルセメント杭 its 段落し後の鋼管厚 (decision 126)."""
    foundation = pier.substructure.foundation
    if foundation == CAST_IN_PLACE_PILE:
        return pier.rebar.pile.cutoff.main_diameter is not None
    return foundation == STEEL_SOIL_CEMENT_PILE and pier.piles.steel_soil_cement.cutoff.entered


def _exact(item: Printed) -> Decimal:
    return Decimal(repr(item.value))


def _anchor_rows(model: PileNduModel) -> tuple[tuple[int, int, int], ...]:
    """The rows of ⑧: the first and last elements of each pile row and its piles in depth."""
    members = {member.number: member for member in model.members}
    return tuple((pile.first, pile.last, members[pile.member].depth_piles) for pile in model.piles)


def _steel_anchor_bar(model: PileNduModel, pier: PierInput) -> AnchorBar:
    """⑧ of a 鋼管ソイルセメント杭 cut off (decision 126): the parser checked every item and the whole millimetres."""
    pile = pier.piles.steel_soil_cement
    cutoff = pile.cutoff
    corrosion = _exact(pile.corrosion)
    return AnchorBar(
        rows=_anchor_rows(model),
        main_diameter=_exact(pile.steel_diameter) * 1000 - 2 * corrosion,
        main_count=int(_exact(cutoff.thickness) - corrosion),
        hoop_diameter=Decimal(repr(STEEL_PIPE_STRENGTH[cutoff.grade][0])), hoop_sets=None, hoop_pitch=None,
        head_anchorage=Decimal(STEEL_PIPE_EMBEDMENT_MM),
        cutoff_length=None if cutoff.upper_length is None else _exact(cutoff.upper_length), concrete_strength=None,
        joint_reduction=Decimal(repr(STEEL_JOINT_REDUCTION)), cutoff_anchorage=None, margin=None,
        no_joint_head=_exact(cutoff.no_joint_from_head), no_joint_above=_exact(cutoff.low_margin),
        no_joint_below=_exact(cutoff.high_margin), margin_moment=None, margin_shear=None)


def anchor_bar(model: PileNduModel, pier: PierInput) -> AnchorBar | None:
    """⑧ of the piles of *model* when they have a cut-off, else None; of a 場所打ち杭 a blank item it needs is an input error
    naming it (a 鋼管ソイルセメント杭's are checked by the parser)."""
    if not anchored(pier):
        return None
    if pier.substructure.foundation == STEEL_SOIL_CEMENT_PILE:
        return _steel_anchor_bar(model, pier)
    cutoff = pier.rebar.pile.cutoff

    def need(item, path: str) -> Decimal:
        if item is None:
            raise InputError(f"{_CUTOFF}.{path}: 杭の段落しの照査（Aggre-SE の ⑧）に必要です")
        return Decimal(repr(item.value)) if isinstance(item, Printed) else Decimal(item)

    length = head_anchorage(pier, section(pier)).length
    return AnchorBar(
        rows=_anchor_rows(model), main_diameter=need(cutoff.main_diameter, "main_bars.diameter_mm"),
        main_count=int(need(cutoff.main_count, "main_bars.count")),
        hoop_diameter=need(cutoff.hoop.diameter, "hoops.diameter_mm"), hoop_sets=int(need(cutoff.hoop.sets, "hoops.sets")),
        hoop_pitch=need(cutoff.hoop.pitch, "hoops.pitch_mm"), head_anchorage=Decimal(repr(length.value)),
        cutoff_length=need(cutoff.cutoff_length, "cutoff_length_mm"),
        concrete_strength=Decimal(repr(pier.materials.footing.value)),
        joint_reduction=need(cutoff.joint_reduction, "joint_reduction"),
        cutoff_anchorage=need(cutoff.cutoff_anchorage, "cutoff_anchorage_mm"), margin=need(cutoff.margin, "margin_mm"),
        no_joint_head=need(cutoff.no_joint_from_head, "no_joint.from_head_mm"),
        no_joint_above=need(cutoff.no_joint_above, "no_joint.above_mm"),
        no_joint_below=need(cutoff.no_joint_below, "no_joint.below_mm"),
        margin_moment=need(cutoff.margin_moment, "margin_ratio.moment"),
        margin_shear=need(cutoff.margin_shear, "margin_ratio.shear"))


def _choice(value: str | None, options: tuple[str, ...], key: str) -> int:
    if value is None:
        raise InputError(f"{SECTION}.{key}: 値が必要です（静的非線形解析の耐震照査の入力に使います）")
    return options.index(value)


PILE_ANCHOR_BAR = 7  # the index of ⑧ 杭の段落し in the check items
# the check items of a Case for the liquefaction (decision 95; the owner's sample R-7 checks ②③⑤⑦⑧⑨, and ⑧ is not made):
# ② 安全性L2, ③ 損傷レベル, ⑤ せん断耐力, ⑦ 基礎の安定, ⑨ 断面力ピックアップ
LIQUEFACTION_CHECKS: Checks = (False, True, True, False, True, False, True, False, True)
# the check items of a Case of the 応答変位法 (decision 97; the sample R-7 checks ①②③⑤⑦⑧⑨ and ⑧ is not made): Aggre-SE takes a
# Case of the load increment as one of L1 when it checks ⑥ L1 and as one of L2 otherwise (ExcelReportPickUpFile)
RESPONSE_CHECKS: dict[str, Checks] = {"L1": (False, False, True, False, True, True, True, False, True),
                                      "L2": (True, True, True, False, True, False, True, False, True)}


def _checks(model: NduModel | PileNduModel, *, without_anchor_bar: bool = False) -> tuple[Checks, ...]:
    """The check items of each combination of *model*; without ⑧ for piles with no cut-off (*without_anchor_bar*)."""
    found = []
    for number, combination in enumerate(model.combinations, 1):
        pattern = (Decimal(repr(combination.rho_m.value)), Decimal(repr(combination.alpha_f.value)))
        if pattern not in CHECKS:
            raise ValueError(f"組合せ {number} の照査パターン ρm={pattern[0]}・αf={pattern[1]} の照査項目がありません")
        checks = CHECKS[pattern]
        found.append(tuple(item and not (without_anchor_bar and index == PILE_ANCHOR_BAR)
                           for index, item in enumerate(checks)))
    return tuple(found)


def build_project(model: NduModel, pier: PierInput) -> Project:
    """The project of the NDU *model*; a blank 耐震設計条件 is an input error."""
    design = pier.seismic_design
    nonlinear = [element for element in model.elements if element.nonlinear]
    if len(nonlinear) != 1:  # the NDU has one M-θ member, the column base; Aggre-SE's member type 2 is it
        raise InputError(f"JRSNAP の非線形部材が{len(nonlinear)}個です（耐震照査の入力は1個だけに対応します）")
    return Project(region=_choice(design.region, REGIONS, "地域別"),
                   ground_class=_choice(design.ground_class, GROUND_CLASSES, "地盤区分"),
                   shear_span=model.section.shear_span, footing_joint=model.footing.node, cases=_checks(model))


def _rows(model: PileNduModel) -> tuple[PileRow, ...]:
    elements = {element.number: element for element in model.elements}
    members = {member.number: member for member in model.members}
    # the joint of the row on the footing base: the i end of its first element in the ground (of a 鋼管ソイルセメント杭, of the
    # M-θ of its joint, decision 122)
    return tuple(PileRow(elements[pile.first].i, members[pile.member].depth_piles) for pile in model.piles)


def build_pile_project(models: Sequence[PileNduModel], pier: PierInput, *,
                       liquefied: Sequence[PileNduModel] = (),
                       response: Sequence[tuple[str, PileNduModel]] = ()) -> Project:
    """The project of the piles of the NDU *models* of a stage (the forward NDU, then the reversed one); a blank 耐震設計条件
    is an input error. Every NDU has the frame, the piles and the sections of the first, and the Cases follow its combinations.
    The NDUs for the liquefaction (*liquefied*, decision 95) follow with one Case each, which Aggre-SE checks as a Case for the
    liquefaction; they need the 液状化指数. The NDUs of the 応答変位法 (*response*: the level, L1 or L2, and the NDU of each
    Case, decision 97) follow with one Case each, checked as a Case of its level."""
    design = pier.seismic_design
    first = models[0]
    # the one M-θ member outside the piles is the column base, Aggre-SE's member type 2; the M-θ of the joint of a
    # 鋼管ソイルセメント杭 is the head of a pile row (decision 122)
    columns = [element for element in first.elements if element.kind == COLUMN
               and not any(pile.first <= element.number <= pile.last for pile in first.piles)]
    if len(columns) != 1:
        raise InputError(f"JRSNAP の非線形部材（柱）が{len(columns)}個です（耐震照査の入力は1個だけに対応します）")
    rows = _rows(first)
    for other in (*models[1:], *liquefied, *(model for _, model in response)):
        if (_rows(other), len(other.sections)) != (rows, len(first.sections)):
            raise ValueError("向きの違う NDU の杭の列と断面が同じではありません")
    # ⑧ is of piles with a cut-off: a 場所打ち杭's (decision 98) or a 鋼管ソイルセメント杭's (decision 126)
    anchor = anchor_bar(first, pier)
    ordinary = tuple(case for model in models for case in _checks(model, without_anchor_bar=anchor is None))
    index = _choice(design.liquefaction_index, LIQUEFACTION_INDEXES, "液状化指数") if liquefied else 0
    return Project(region=_choice(design.region, REGIONS, "地域別"),
                   ground_class=_choice(design.ground_class, GROUND_CLASSES, "地盤区分"), shear_span=first.shear_span,
                   footing_joint=columns[0].j, cases=ordinary + tuple(LIQUEFACTION_CHECKS for _ in liquefied)
                   + tuple(RESPONSE_CHECKS[level] for level, _ in response),
                   pile_rows=rows, pile_sections=len(first.sections) - 1,
                   liquefaction_cases=tuple(range(len(ordinary), len(ordinary) + len(liquefied))),
                   liquefaction_index=index, focus_joint=first.control if response else 0, anchor_bar=anchor)


def ndu_databases(folder: str, names: Iterable[str], groups: Sequence[tuple[str, int]]) -> tuple[str, ...]:
    """The DB1 of the Cases of each NDU in *groups* (its name without the extension, its Cases), among the result files *names*,
    in order, as a path from the XML (``folder/name``): JRSNAP names a file ``<NDU>(Case<n>_…).DB1`` and numbers the Cases of
    each NDU from 1."""
    names = list(names)
    return tuple(path for stem, cases in groups
                 for path in _by_case(folder, names, cases, re.compile(rf"{re.escape(stem)}\(Case(\d+)_[^()]*\)\.db1",
                                                                       re.IGNORECASE), f"{stem} の "))


def databases(folder: str, names: Iterable[str], cases: int) -> tuple[str, ...]:
    """The DB1 of each Case 1..*cases* among the result files *names*, as a path from the XML (``folder/name``)."""
    return _by_case(folder, names, cases, _CASE, "")


def _by_case(folder: str, names: Iterable[str], cases: int, pattern: re.Pattern[str], of: str) -> tuple[str, ...]:
    """The names matching *pattern* (its group 1 the Case) of Cases 1..*cases*, in order, as ``folder/name``; *of* names
    the NDU in the errors."""
    found: dict[int, str] = {}
    for name in names:
        if match := pattern.fullmatch(name):
            case = int(match[1])
            if case in found:
                raise ProjectError(f"{of}Case{case} の DB1 が2つあります: {found[case]}, {name}")
            found[case] = name
    if sorted(found) != list(range(1, cases + 1)):
        raise ProjectError(f"JRSNAP の結果に {of}Case1〜{cases} の DB1 がそろっていません（{sorted(found.values())!r}）")
    return tuple(f"{folder}/{found[case]}" for case in range(1, cases + 1))

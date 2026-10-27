"""0400 照査の前提 (§4, decision 73, ADR-0012): the detailing of the beam, the column and the footing.

WebPier lays out every page, after the sample 0400 (.claude/docs/Example橋脚/output/0400_照査の前提.pdf: its wording,
its formulas and its tables) and, for what the sample has not, Example2 06_照査の前提 6.3〜6.8:

- 4.1 配筋要領: (1) 梁, (2) 柱, (3) フーチング, each with its figure when one is given (``figures``: the 配筋図 is drawn
  elsewhere and put here as it is). A column whose 方向別の鉄筋配置表 is hand-made has no figure: (2) prints its two
  tables, with the 引張鉄筋 rows named (decision 111).
- 4.2 躯体の構造細目: (1) 線路方向, (2) 線路直角方向. The items of the whole section (1) (a) and 3) are printed in (1)
  only; the items are numbered in order in each direction.
- 4.3 梁の構造細目 and 4.4 フーチングの構造細目 ((1) 線路方向, (2) 線路直角方向).

The checks that use section forces (Mcrd, 0.008Ac, the maximum reinforcement, σc) print only the section of the check
that has them (ADR-0012), whether that is made or not (``references``): 0611 / 0621 n.10 and n.7, 0810 / 0820 the
section after their seismic restorability and their durability, 0910 the section after its restorability and its
durability. 9) prints its value and its sign without a judgement. Every number is a Printed value of the calc result (ADR-0003).

Not reproduced from the sample (ADR-0001): the #REF! of its (2), its duplicated pages, its b = 1140 of 6), the
footing's N'd of the column and the column's limits of the clear spacing in the footing, the "小判形" sentence of its
7) (the column here is rectangular) and the garbled f'cd line of 9).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document, Equation, KeepWithNext, PageBreak, PdfFigure, PreferKeepTogether, Row
from pypdf import PdfReader

from ...calc.detailing import DetailingResult
from ...calc.detailing.beam import BeamDetailing, SkinBars
from ...calc.column_rebar import DirectionTable
from ...calc.detailing.column import ColumnDetailing, ColumnDirection
from ...calc.detailing.common import (BarGroup, Bound, CapacityRatio, ClearSpacing, DuctilityLimit, ShearRatio,
                                      SteelRatio, StirrupSpacing)
from ...calc.detailing.footing import FootingDetailing, FootingDirection
from ...calc.detailing.pile import SPAN_FACTOR, SPAN_LIMIT, HoopRatio, PileDetailing
from ...calc.detailing.steel_pile import CLEAR_LEAST as STEEL_CLEAR_LEAST
from ...calc.detailing.steel_pile import DIAMETER_RANGE as STEEL_DIAMETER_RANGE
from ...calc.detailing.steel_pile import FILL_INEFFECTIVE as STEEL_FILL_INEFFECTIVE
from ...calc.detailing.steel_pile import FOOTING_HOOP_UPPER
from ...calc.detailing.steel_pile import Joint as SteelJoint
from ...calc.detailing.steel_pile import PC_RANGE as STEEL_PC_RANGE
from ...calc.detailing.steel_pile import RIB_GAP_LEAST as STEEL_RIB_GAP_LEAST
from ...calc.detailing.steel_pile import RIB_SPACINGS as STEEL_RIB_SPACINGS
from ...calc.detailing.steel_pile import TIP_RIBS as STEEL_TIP_RIBS
from ...calc.detailing.steel_pile import SteelPileDetailing, SteelPipe
from ...core.printed import Printed
from ...inputs.outputs import FootingParts
from ..document import blank, heading, indent_to, is_blank, math_line, paragraph, report, spacer
from ..equations import Definition, definitions, equation_group, terms
from ..styles import columns_pt, rows_for
from . import cantilever_check, column_check, footing_check
from .frame_report import (Definitions, FigureSpec, Labelled, Span, TableSpec, Unit, plain, sub, sup, table_block,
                           value)

PREFIX = "0400/"
FIGURES = ("beam", "column", "footing", "pile")  # the 配筋図 of 4.1, by name (the pile: decisions 98 and 99)
# A 配筋図 fills the body width from column 4 (as the sample Example橋脚2 6.1 nearly does) and as many rows as its page
# needs at that width, at most FIGURE_ROWS (a taller one is narrower).
FIGURE_LEFT, FIGURE_COLUMNS, FIGURE_ROWS = 4, 26, 30
LEVELS = (0, 1, 2, 3, 4)
BODY, INDENT = 4, 5
# The formula columns: a symbol's "=" on the boundary before column 8, a result's "=" before 24, the result ending at
# 27, its unit from 28; the bound lists (the spacing of the shear reinforcement) take their words from column 5 and
# their "=" before column 15, the result's before 23.
SYMBOL = (INDENT, 8, 24, 27, 28)
BOUND_LIST = (INDENT, 15, 23, 26, 27)
COLON = 9  # "ここに、" lists
ITEM_COLON = 17  # the lines of 5) (軸方向鉄筋ピッチ : 150.0 mm)
TAG_COLUMNS = {".shear.heading": 14}  # a heading whose tag does not fit from column 18
CLEAR_WIDTHS = (7, 8, 10)  # 部材 | あき(mm) | 備考
TABLE_WIDTHS = (7, 4, 4, 8)  # the column's 方向別の鉄筋配置表 (decision 111): 芯位置 | 径 | 本数 | 区分
TABLE_FACES = {"線路": ("線路方向", "上面", "上側", "下側"), "直角": ("線路直角方向", "左面", "左側", "右側")}
FACE_WIDTHS = (3, 6, 4, 4, 6, 6)  # 10) 面 | 径−本数 | As | As/6 | 配力鉄筋 | 圧縮鉄筋
OK, NG = "OK", "NG"
DOTS = "・・・・・・"
MM2 = sup("mm", "2")
FACES = {"上": "上側", "下": "下側"}
DIRECTIONS = {"線路": "線路方向", "直角": "線路直角方向"}
# 4.2, 4.3 and 4.4 begin a page, and so does (2) 線路直角方向 of 4.2 and 4.4: it repeats the items of (1) 線路方向,
# to be read beside them. Headings alone before one (4.1 without its figures) stay on its page.
NEW_PAGES = frozenset({*(f"{PREFIX}{member}{direction}.heading" for member in ("column", "beam", "footing")
                         for direction in ("", ".直角") if member != "beam" or not direction), f"{PREFIX}pile.heading"})


@dataclass(frozen=True)
class References:
    """The sections a check that uses section forces is printed in, by member (and direction)."""

    column: Mapping[str, tuple[str, str]]  # direction → (最小鉄筋量及び最大鉄筋量, 耐久性の照査)
    beam: tuple[str, str]
    # None: the footing check has neither section (decision 110: no footing, or its seismic part alone)
    footing: Mapping[str, tuple[str, str] | tuple[None, None]]


def references(appearance: bool, footing: FootingParts = FootingParts(frames=True, seismic=True)) -> References:
    """The sections 0400 refers to, as (最小鉄筋量及び最大鉄筋量, 耐久性の照査), numbered by the reports that print them
    (decision 73): 0611 / 0621 n.10 and n.7 (column_check), 0810 / 0820 by the parts of the footing the outputs choose
    (footing_check.chapters, decision 110; none without its frame part), 0910's following the appearance check of the
    input (cantilever_check.Numbering)."""
    columns = {"線路": column_check.LONGITUDINAL, "直角": column_check.TRANSVERSE}
    footings = dict(zip(("線路", "直角"), footing_check.chapters(footing.frames, footing.seismic)))
    beam = cantilever_check.Numbering.with_appearance(appearance)
    return References(
        column={direction: (f"{chapter.number}.{column_check.REBAR_AMOUNT_SECTION}",
                            f"{chapter.number}.{column_check.DURABILITY_SECTION}") for direction, chapter in columns.items()},
        beam=(f"{cantilever_check.CHAPTER}.{beam.rebar_amount}", f"{cantilever_check.CHAPTER}.{beam.durability}"),
        footing={direction: (chapter.section(footing_check.REBAR_AMOUNT_GROUP),
                             chapter.section(footing_check.DURABILITY_GROUP)) if footing.frames else (None, None)
                 for direction, chapter in footings.items()})


class _Manuscript:
    """The units of the report under the prefix 0400/."""

    def __init__(self) -> None:
        self.units: list[Unit] = []

    def add(self, key: str, item: Any, kind: str, *, left: int = BODY, keep: bool = False) -> None:
        self.units.append(Unit(PREFIX + key, item, kind, left, keep))

    def heading(self, key: str, text: str, level: int, tag: str | None = None) -> None:
        self.add(key, text if tag is None else (text, tag), "heading", left=LEVELS[level])

    def paragraph(self, key: str, text: str, *, left: int = BODY, keep: bool = False) -> None:
        self.add(key, text, "paragraph", left=left, keep=keep)

    def line(self, key: str, item: Any, *, left: int = INDENT, keep: bool = False) -> None:
        self.add(key, item, "line", left=left, keep=keep)

    def equation(self, key: str, label: str, lhs: Any, rhs: Any, result: Any = None, unit: Any = None, *,
                 anchors: tuple[int, ...] = SYMBOL) -> None:
        item = Equation(lhs, rhs) if result is None else Equation(lhs, rhs, result=result, unit=unit)
        self.add(key, Labelled(label, item), "equation" if anchors == SYMBOL else "bounds")

    def definitions(self, key: str, *items: Definition) -> None:
        self.add(key, Definitions(items, COLON), "definitions")

    def items(self, key: str, *items: Definition) -> None:
        self.add(key, Definitions(items, ITEM_COLON), "items")

    def table(self, key: str, spec: TableSpec, title: str | None = None) -> None:
        if title is not None:
            self.paragraph(f"{key}.title", title, left=spec.left, keep=True)
        self.add(key, spec, "table", left=spec.left)

    def figure(self, key: str, spec: FigureSpec) -> None:
        self.add(key, spec, "figure", left=spec.left)


class _Numbers:
    """1), 2), … in the order printed."""

    def __init__(self) -> None:
        self.next = 0

    def __call__(self, text: str) -> str:
        self.next += 1
        return f"{self.next}) {text}"


# --- printed pieces -----------------------------------------------------------------------------------------------


def _mm(number: Printed) -> Row:
    return Row(value(number), " mm", gap=0)


def _mm2(number: Printed) -> Row:
    return Row(value(number), " ", MM2, gap=0)


def _percent(number: Printed) -> str:
    return f"{value(number)} %"


def _judgement(ok: bool) -> str:
    return OK if ok else NG


def _satisfied(ok: bool) -> str:
    return "満足する。" if ok else "満足しない。"


def _bar(diameter: Printed) -> str:
    return f"D{value(diameter)}"


def _group(group: BarGroup) -> str:
    return f"{_bar(group.diameter)} − {value(group.count)} 本"


def _reference(m: _Manuscript, key: str, section: str | None, title: str) -> None:
    if section is None:  # the footing check without its frame part (decision 110)
        m.paragraph(key, f"照査は、フーチングの断面照査で地震時以外の照査を行うときに「{title}」で確かめる。")
        return
    m.paragraph(key, f"照査は「{section} {title}」に示す。")


def _check(m: _Manuscript, key: str, number: Printed, limit: Printed, ok: bool) -> None:
    """"= 0.919 % ＞ 0.15 % ・・・・・・ OK" under its formula (a lower limit)."""
    relation = "＜" if not ok else "＞" if number.value > limit.value else "≧"
    m.equation(key, "", "", terms(_text(number), relation, _text(limit), DOTS, _judgement(ok)))


def _text(number: Printed) -> str:
    return _percent(number) if number.unit == "%" else value(number)


# --- 1) 主鉄筋の最小鉄筋量 (a), 3) ------------------------------------------------------------------------------


def _ratio(m: _Manuscript, key: str, amount: SteelRatio, lines: Sequence[tuple[str, BarGroup]]) -> None:
    m.heading(f"{key}.heading", "(a) コンクリートの収縮や温度によるひび割れを有害でない程度に抑える", 4)
    m.paragraph(f"{key}.text", "軸方向鉄筋は、コンクリート部材のいかなる断面に対してもコンクリートの全断面積の0.15%以上に"
                               "なるように配置する。")
    m.line(f"{key}.formula", "Pc = As / (b・h)")
    m.definitions(f"{key}.symbols",
                  Definition("As", Row(f"軸方向鉄筋の量 (= ", _mm2(amount.area), f")（{amount.grade}）", gap=0)),
                  *(Definition("", Row(f"{name} {_group(group)} (= ", _mm2(group.area), ")", gap=0))
                    for name, group in lines),
                  Definition("b", Row("部材の幅 (= ", _mm(amount.width), ")", gap=0)),
                  Definition("h", Row("部材の高さ (= ", _mm(amount.depth), ")", gap=0)),
                  Definition("A", Row("断面積 (= ", _mm2(amount.section), ")", gap=0)))
    m.equation(f"{key}.pc", "", "Pc", terms(value(amount.area), "/", value(amount.section), "×", "100"))
    _check(m, f"{key}.check", amount.ratio, amount.minimum, amount.minimum_ok)
    m.paragraph(f"{key}.result", "以上の結果より、Pc＞0.15%となり満足する。" if amount.minimum_ok
                else "以上の結果より、Pc＜0.15%となり満足しない。")


def _maximum_ratio(m: _Manuscript, key: str, n: _Numbers, amount: SteelRatio) -> None:
    m.heading(f"{key}.heading", n("軸方向力の最大値から定まる最大鉄筋量"), 3, "【RC標準第Ⅲ編2.3.3.2】")
    m.paragraph(f"{key}.text", "軸方向の影響が支配的な部材は、施工特性を考慮して最大鉄筋量を定めることとする。一般には、"
                               "軸方向鉄筋比を6%以下とすればよい。")
    ok = bool(amount.maximum_ok)
    m.equation(f"{key}.check", "", "Pc", terms(_text(amount.ratio), "＜" if ok else "≧", _text(amount.maximum), DOTS,
                                               _judgement(ok)))
    m.paragraph(f"{key}.result", "以上の結果より、Pc＜6%となり満足する。" if ok
                else "以上の結果より、Pc≧6%となり満足しない。")


def _minimum(m: _Manuscript, key: str, n: _Numbers, section: str | None, ratio: Callable[[], None] | None) -> None:
    """1) with (a) when given, then (b) Mcrd and (c) 0.008Ac referred to *section*."""
    letters = iter("abc")
    m.heading(f"{key}.heading", n("主鉄筋の最小鉄筋量の検討"), 3, "【RC標準第Ⅲ編2.3.3.1】")
    if ratio is not None:
        next(letters)
        ratio()
    # The source of (b) and (c) closes their text (Example2 6.3 (2)): it does not fit beside the heading.
    m.heading(f"{key}.crack.heading", f"({next(letters)}) 曲げひび割れ発生と同時に部材が脆性的破壊することを防止", 4)
    m.paragraph(f"{key}.crack.text", "曲げモーメントの影響が支配的な部材については、設計曲げ降伏耐力Mydが設計曲げひび割れ"
                                     "耐力Mcrdを超えるように、引張鉄筋を配置する。【RC標準第Ⅲ編2.3.3.1(2)】")
    _reference(m, f"{key}.crack.reference", section, "最小鉄筋量及び最大鉄筋量")
    m.heading(f"{key}.axial.heading", f"({next(letters)}) 軸方向力の最大値から定まる最小鉄筋量", 4)
    m.paragraph(f"{key}.axial.text", "軸方向力が支配的な鉄筋コンクリートの場合、軸方向鉄筋量は、計算上必要とするコンクリート"
                                     "の全断面積0.8%以上とする。【RC標準第Ⅲ編2.3.3.1(3)】")
    _reference(m, f"{key}.axial.reference", section, "最小鉄筋量及び最大鉄筋量")


def _maximum(m: _Manuscript, key: str, n: _Numbers, section: str | None) -> None:
    m.heading(f"{key}.heading", n("主鉄筋の最大鉄筋量の検討"), 3, "【RC標準第Ⅲ編2.3.3.2】")
    m.paragraph(f"{key}.text", "断面破壊に対する引張鉄筋比Ptは、釣合鉄筋比Pbの75%以下としなければならない。")
    _reference(m, f"{key}.reference", section, "最小鉄筋量及び最大鉄筋量")


def _stress(m: _Manuscript, key: str, n: _Numbers, section: str | None) -> None:
    m.heading(f"{key}.heading", n("応力度の制限値"), 3, "【RC標準第Ⅲ編6.1 7.3】")
    m.paragraph(f"{key}.text", "コンクリートの圧縮応力度は、過度なクリープひずみや大きな圧縮応力による軸方向ひび割れ等を"
                               "生じないように制限することとする。一般には、永久作用によるコンクリートの曲げ圧縮応力度"
                               "σcを、設計圧縮強度f'cdの40%以下とすればよい。")
    _reference(m, f"{key}.reference", section, "耐久性の照査")


# --- 5) 鉄筋のあき --------------------------------------------------------------------------------------------------

_CLEAR_TEXT = ("コンクリートが鉄筋の周囲にゆきわたり、鉄筋が十分な付着を発揮できる寸法を確保できるように、軸方向鉄筋の"
               "水平のあきは、20mm以上、粗骨材の最大寸法の4/3以上かつ鉄筋の直径以上としなければならない。")
_COLUMN_CLEAR_TEXT = ("ただし、柱における軸方向鉄筋のあきは40mm以上、粗骨材の最大寸法の4/3以上かつ鉄筋の直径の1.5倍以上"
                      "としなければならない。")


def _clear_items(spacing: ClearSpacing, face: str = "") -> list[Definition]:
    items = []
    if spacing.pitch is not None:
        items.append(Definition(f"{face}軸方向鉄筋ピッチ", _mm(spacing.pitch)))
    if spacing.layer is not None:
        items.append(Definition(f"{face}1段目鉄筋と2段目鉄筋との間隔", _mm(spacing.layer)))
    items.append(Definition(f"{face}主鉄筋径", _bar(spacing.diameter)))
    for index, (centre, clear) in enumerate(((spacing.pitch, spacing.pitch_clear),
                                             (spacing.layer, spacing.layer_clear))):
        if centre is not None:
            first = index == 0 or spacing.pitch is None
            items.append(Definition(f"{face}軸方向鉄筋のあき" if first else "",
                                    Row(f"{value(centre)} − {value(spacing.diameter)} = ", _mm(clear), gap=0)))
    return items


def _clear_rows(member: str, spacing: ClearSpacing) -> list[tuple[Any, ...]]:
    clear = "－" if spacing.clear is None else value(spacing.clear)
    factor = "" if spacing.bar_factor.value == 1 else f" × {value(spacing.bar_factor)}"
    limits = (f"≧ {value(spacing.minimum)} mm",
              f"≧ {value(spacing.diameter)}{factor} = {value(spacing.bar_limit)} mm",
              f"≧ {value(spacing.aggregate_max)} × 4/3 = {value(spacing.aggregate_limit)} mm")
    first = (Span(member, rowspan=3), Span(f"軸方向鉄筋のあき {clear}", rowspan=3), Span(limits[0], align="left"))
    return [first, *((Span(limit, align="left"),) for limit in limits[1:])]


def _clear(m: _Manuscript, key: str, n: _Numbers, groups: Sequence[tuple[str, str, ClearSpacing]], *,
           column: bool) -> None:
    """5) for the groups (the words before each line, the member of the table, the spacing)."""
    m.heading(f"{key}.heading", n("鉄筋のあき"), 3, "【RC標準第Ⅲ編2.3.4】")
    m.paragraph(f"{key}.text", _CLEAR_TEXT)
    if column:
        m.paragraph(f"{key}.column", _COLUMN_CLEAR_TEXT)
    m.items(f"{key}.items", *(item for face, _, spacing in groups for item in _clear_items(spacing, face)))
    rows: list[tuple[Any, ...]] = [("部材", "あき(mm)", "備考")]
    for _, member, spacing in groups:
        rows += _clear_rows(member, spacing)
    m.table(f"{key}.table", TableSpec(CLEAR_WIDTHS, tuple(rows), (1,) * len(rows), left=BODY), "表．鉄筋のあき")
    ok = all(spacing.ok for _, _, spacing in groups)
    m.paragraph(f"{key}.result", "表より、鉄筋のあきは限界値以上となり満足する。" if ok
                else "表より、鉄筋のあきは限界値を下回り満足しない。")


# --- 6) 7) 8) 9) the shear reinforcement ---------------------------------------------------------------------------


def _shear(m: _Manuscript, key: str, n: _Numbers, shear: ShearRatio, rows: Sequence[str], name: str = "Ps") -> None:
    m.heading(f"{key}.heading", n("最小せん断補強鉄筋量の検討"), 3, "【RC標準第Ⅲ編2.3.3.1(4)】【耐震標準8.5】")
    m.paragraph(f"{key}.text", "コンクリートの収縮や温度勾配により斜めひび割れが発生して急激な破壊に至るのを防ぐために、"
                               "せん断補強鉄筋比として0.15%以上の帯鉄筋を配置する。")
    for index, text in enumerate(rows):
        m.line(f"{key}.bars.{index}", text)
    m.equation(f"{key}.ps", "", name, terms(value(shear.legs), "×", value(shear.unit_area), "/",
                                            "(", value(shear.width), "×", value(shear.pitch), ")", "×", "100"))
    _check(m, f"{key}.check", shear.ratio, shear.minimum, shear.ok)


_BOUNDS = {
    "three_quarters_d": "・有効高さの3/4", "fixed_400": "・400mm以下", "half_d": "・有効高さの1/2",
    "fixed_300": "・300mm以下", "compression_15": "・圧縮鉄筋の直径の15倍", "stirrup_48": "・帯鉄筋の直径の48倍",
    "quarter_d": "・有効高さの1/4", "main_8": "・圧縮・引張鉄筋の直径の8倍", "stirrup_24": "・帯鉄筋の直径の24倍",
    "main_12": "・軸方向鉄筋の直径の12倍", "half_short_side": "・断面の短辺寸法の1/2",
}


def _factor(item: Bound) -> str:
    return str(item.numerator) if item.denominator == 1 else f"{item.numerator}/{item.denominator}"


def _bounds(m: _Manuscript, key: str, spacing: StirrupSpacing, region: str, stirrup: str) -> None:
    for item in spacing.bounds:
        label = _BOUNDS[item.name].replace("帯鉄筋", stirrup)
        if item.base is None:
            m.line(f"{key}.{item.name}", label)
        else:
            m.equation(f"{key}.{item.name}", label, "", terms(value(item.base), "×", _factor(item)), value(item.value),
                       "mm", anchors=BOUND_LIST)
    verb = "より満足する。" if spacing.ok else "となり満足しない。"
    m.paragraph(f"{key}.result", f"{region}：上記最小間隔は{value(spacing.limit)}mmに対して計算上の配置間隔は"
                                 f"{value(spacing.pitch)}mm{verb}", left=INDENT)


_GENERAL_TEXT = (
    "最小鉄筋量に従いスターラップを配置する場合、コンクリートの収縮や温度差等によるひび割れを制御するために有効な間隔で"
    "配置することとする。一般には、有効高さの3/4以下かつ400mm以下とすれば良い。",
    "せん断補強鉄筋を計算上必要とする場合、スターラップは腹部コンクリートに発生する斜めひび割れと必ず交わるような間隔で"
    "配置することとする。一般には、有効高さの1/2以下かつ300mm以下とすればよい。",
    "圧縮鉄筋がある場合、スターラップは圧縮鉄筋の座屈を防止するために有効な間隔で配置することとする。一般には、圧縮鉄筋の"
    "直径の15倍以下かつスターラップの直径の48倍以下とすればよい。")
_CONFINEMENT_TEXT = (
    "せん断補強鉄筋を計算上必要とする場合、スターラップの間隔は、有効高さの1/4以下かつ300mm以下とする。かつ圧縮・引張"
    "鉄筋の直径の8倍、スターラップ・帯鉄筋の直径の24倍以下の間隔で配置する。なお、部材接合部及び柱下端から断面高さの"
    "2.0倍までの範囲とする。",
    "スターラップおよび帯鉄筋の部材軸方向の配置間隔は、軸方向鉄筋の直径の12倍以下で、かつ部材断面の短辺寸法の1/2以下"
    "とする。")


def _placement(m: _Manuscript, key: str, n: _Numbers, general: StirrupSpacing, confinement: StirrupSpacing | None,
               stirrup: str, lateral: Callable[[], None] | None = None) -> None:
    m.heading(f"{key}.heading", n("せん断補強鉄筋の配置"), 3, "【RC標準第Ⅲ編2.3.5.3 2.3.5.4】")
    m.paragraph(f"{key}.general.lead", "① 一般部", keep=True)
    for index, text in enumerate(_GENERAL_TEXT):
        m.paragraph(f"{key}.general.text.{index}", text, left=INDENT)
    _bounds(m, f"{key}.general", general, "一般部", stirrup)
    if confinement is not None:
        m.paragraph(f"{key}.confinement.lead", "② 塑性ヒンジ部（2D区間）", keep=True)
        for index, text in enumerate(_CONFINEMENT_TEXT):
            m.paragraph(f"{key}.confinement.text.{index}", text, left=INDENT)
        _bounds(m, f"{key}.confinement", confinement, "2D区間", stirrup)
    if lateral is not None:
        lateral()


def _lateral(m: _Manuscript, key: str, direction: ColumnDirection) -> None:
    lateral, hoops = direction.lateral, direction.hoops
    m.paragraph(f"{key}.lateral.lead", "③ 横方向の間隔", keep=True)
    m.paragraph(f"{key}.lateral.text", "長方形断面で帯鉄筋を用いる場合には、帯鉄筋の横方向の間隔は、帯鉄筋の直径の48倍以下"
                                       "とし、帯鉄筋の間隔がこれを超える場合には、中間帯鉄筋を配置する。", left=INDENT)
    m.equation(f"{key}.lateral.limit", "・帯鉄筋の直径の48倍", "", terms(value(hoops.diameter), "×", "48"),
               value(lateral.limit), "mm", anchors=BOUND_LIST)
    m.paragraph(f"{key}.lateral.need", f"よって、帯鉄筋の横方向の必要配置間隔は{value(lateral.limit)}mmとなる。",
                left=INDENT)
    sets = value(lateral.ties.intermediate_sets)
    m.paragraph(f"{key}.lateral.result", f"中間帯鉄筋を{sets}組配置し、帯鉄筋の横方向の間隔は最大"
                                         f"{value(lateral.ties.max_spacing)}mmとなり{_satisfied(lateral.ok)}",
                left=INDENT)


def _ductility(m: _Manuscript, key: str, n: _Numbers, ductility: DuctilityLimit, shear: ShearRatio,
               width: str) -> None:
    pw, kwo = sub("p", "w"), sub("k", "wo")
    m.heading(f"{key}.heading", n("帯鉄筋の靭性率における上限値の照査"), 3, "【RC標準第Ⅲ編5.2.3.3】")
    m.paragraph(f"{key}.text", "帯鉄筋の靭性率上限値は【RC標準[R5] 第Ⅲ編 5.2.3.3】より、", keep=True)
    m.line(f"{key}.formula", Row("0.021・", kwo, "・", pw, " ＋ 0.013 ≦ 0.04", gap=0))
    m.definitions(f"{key}.symbols",
                  Definition(pw, Row("帯鉄筋比 = ", sub("A", "w"), " / (", sub("b", "w"), "・", sub("s", "s"), ")",
                                     gap=0)),
                  Definition(kwo, f"帯鉄筋強度を考慮する係数 (= {value(ductility.kwo)})（{ductility.grade}）"))
    m.equation(f"{key}.pw", "", pw, terms(value(shear.area), "/", "(", width, "×", value(shear.pitch), ")", "×",
                                          "100"), value(ductility.pw), "%")
    m.line(f"{key}.check", f"{value(ductility.factor)} × {value(ductility.kwo)} × {value(ductility.pw)} ＋ "
                           f"{value(ductility.constant)} = {value(ductility.value)} {'≦' if ductility.ok else '＞'} "
                           f"{value(ductility.limit)}　{DOTS} {_judgement(ductility.ok)}")


def _capacity(m: _Manuscript, key: str, n: _Numbers, capacity: CapacityRatio, pw: Printed) -> None:
    m.heading(f"{key}.heading", n("帯鉄筋の設計せん断耐力の上限値の照査"), 3, "【RC標準第Ⅲ編7.7.2.1】")
    m.paragraph(f"{key}.text", "帯鉄筋のせん断耐力上限値は【RC標準[R5] 第Ⅲ編 7.2.2】より、", keep=True)
    m.line(f"{key}.formula", Row(sub("p", "w"), "・", sub("f", "wyd"), " / ", sub("f'", "cd"), " ≦ 0.1", gap=0))
    m.definitions(f"{key}.symbols",
                  Definition(sub("p", "w"), f"せん断補強鉄筋比 (= {_percent(pw)})"),
                  Definition(sub("A", "w"), Row("せん断補強鉄筋の総断面積 (", MM2, ")", gap=0)),
                  Definition(sub("b", "w"), "腹部の幅 (mm)"),
                  Definition(sub("s", "s"), "せん断補強鉄筋の配置間隔 (mm)"),
                  Definition(sub("f", "wyd"), Row("せん断補強鉄筋の設計引張降伏強度 (= ", value(capacity.fwyd), " N/mm",
                                                  sup("", "2"), ")", gap=0)),
                  Definition(sub("f'", "cd"), Row("コンクリートの設計圧縮強度 (", sub("f'", "cd"), " = ", sub("f'", "ck"),
                                                  " / ", sub("γ", "c"), ")", gap=0)),
                  Definition(sub("f'", "ck"), Row("コンクリートの設計基準強度 (= ", value(capacity.fck), " N/mm",
                                                  sup("", "2"), ")", gap=0)),
                  Definition(sub("γ", "c"), f"コンクリートの材料係数 (= {value(capacity.gamma_c)})"))
    relation = "＞" if capacity.above else "≦"
    m.line(f"{key}.value", f"{value(capacity.pw)} × {value(capacity.fwyd)} / ({value(capacity.fck)} / "
                           f"{value(capacity.gamma_c)}) = {value(capacity.value)} {relation} {value(capacity.limit)}")


# --- 4.1 (2) the column's tables in place of its 配筋図 (decision 111) ------------------------------------------------


def _column_tables(m: _Manuscript, tables: Sequence[DirectionTable]) -> None:
    m.paragraph("layout.column.tables.text", "柱は方向別の鉄筋配置表を手直ししているため、配筋図に代えて、計算に用いる"
                                             "鉄筋配置表を示す。引張鉄筋は、表の上から・下から引張鉄筋の段数の行とする。")
    for table in tables:
        name, face, upper, lower = TABLE_FACES[table.direction]
        rows: list[tuple[Any, ...]] = [(f"{face}からの芯位置(mm)", "径", "本数", "区分")]
        for index, row in enumerate(table.rows):
            kind = (f"引張鉄筋（{upper}）" if index < table.tension else
                    f"引張鉄筋（{lower}）" if index >= len(table.rows) - table.tension else "")
            rows.append((value(row.center), _bar(row.diameter), str(row.count), kind))
        m.table(f"layout.column.tables.{table.direction}", TableSpec(TABLE_WIDTHS, tuple(rows), (1,) * len(rows),
                                                                     numeric=frozenset({0, 2}), left=BODY),
                f"表．鉄筋配置表（{name}、引張鉄筋の段数 {table.tension}）")


# --- 4.2 the column -------------------------------------------------------------------------------------------------


def _column(m: _Manuscript, column: ColumnDetailing, refs: References) -> None:
    m.heading("column.heading", "4.2 躯体の構造細目", 1)
    amount = column.amount
    names = ["引張・圧縮鉄筋"] * column.main_count + ["側方鉄筋"] * (len(amount.groups) - column.main_count)
    for index, direction in enumerate(column.directions):
        key, n = f"column.{direction.direction}", _Numbers()
        first = index == 0
        section, durability = refs.column[direction.direction]
        m.heading(f"{key}.heading", f"({index + 1}) {DIRECTIONS[direction.direction]}", 2)
        _minimum(m, f"{key}.minimum", n, section,
                 (lambda: _ratio(m, f"{key}.minimum.ratio", amount, list(zip(names, amount.groups)))) if first
                 else None)
        _maximum(m, f"{key}.maximum", n, section)
        if first:
            _maximum_ratio(m, f"{key}.ratio", n, amount)
        _stress(m, f"{key}.stress", n, durability)
        _clear(m, f"{key}.clear", n, (("", "躯体", direction.spacing),), column=True)
        hoops, ties = direction.hoops, direction.lateral.ties
        bars = [f"外側帯鉄筋　{_bar(hoops.diameter)} − 1.0 組　ctc {value(hoops.pitch)}"]
        if ties.intermediate:
            bars.append(f"中間帯鉄筋　{_bar(hoops.diameter)} − {value(ties.intermediate_sets)} 組　ctc "
                        f"{value(hoops.pitch)}")
        _shear(m, f"{key}.shear", n, direction.shear, bars)
        _placement(m, f"{key}.placement", n, direction.general, direction.confinement, "帯鉄筋",
                   lambda: _lateral(m, f"{key}.placement", direction))
        _ductility(m, f"{key}.ductility", n, direction.ductility, direction.shear, value(direction.width))
        _capacity(m, f"{key}.capacity", n, direction.capacity, direction.shear.ratio)


# --- 4.3 the beam ---------------------------------------------------------------------------------------------------


def _skin(m: _Manuscript, key: str, label: str, bars: SkinBars, what: str) -> None:
    if bars.diameter is None:
        m.line(f"{key}.bars", f"・{label}　側方鉄筋なし")
    else:
        m.line(f"{key}.bars", f"・{label}　{_bar(bars.diameter)} @ {value(bars.pitch)}（{value(bars.count)} 本）を"
                              f"配置する。（{what}）" if bars.count.value != 1 else
               f"・{label}　{_bar(bars.diameter)} @ {value(bars.pitch)} を配置する。（{what}）")
    count = "0" if bars.unit_area is None else f"{value(bars.count)} × {value(bars.unit_area)}"
    m.line(f"{key}.ratio", f"{count} / ({value(bars.width)} × {value(bars.length)}) × 100 = {_percent(bars.ratio)} "
                           f"{'≧' if bars.ratio_ok else '＜'} {_percent(bars.minimum)}　{DOTS} "
                           f"{_judgement(bars.ratio_ok)}", left=INDENT + 1)


def _beam_ratio(m: _Manuscript, key: str, beam: BeamDetailing) -> None:
    groups = beam.amount.groups
    _ratio(m, key, beam.amount, [("上側鉄筋", groups[0]), ("下側鉄筋", groups[1])])


def _beam(m: _Manuscript, beam: BeamDetailing, refs: References) -> None:
    n = _Numbers()
    section, durability = refs.beam
    m.heading("beam.heading", "4.3 梁の構造細目", 1)
    _minimum(m, "beam.minimum", n, section, lambda: _beam_ratio(m, "beam.minimum.ratio", beam))
    _maximum(m, "beam.maximum", n, section)
    _stress(m, "beam.stress", n, durability)
    m.heading("beam.skin.heading", n("片持ち梁の用心鉄筋の配置"), 3, "【RC標準 13.3.4】")
    m.paragraph("beam.skin.deep.lead", "ディープビームの構造細目", keep=True)
    m.paragraph("beam.skin.deep.text", "はりの両側面には、鉛直および水平方向の格子状に、片面当りコンクリートの全断面積の"
                                       "0.08%以上の用心鉄筋を腹部幅の2倍以下かつ300mm以下の間隔で配置する。", left=INDENT)
    _skin(m, "beam.skin.horizontal", "水平方向", beam.horizontal, "側面鉄筋")
    _skin(m, "beam.skin.vertical", "鉛直方向", beam.vertical, "スターラップ")
    for key, name, bars in (("horizontal", "水平", beam.horizontal), ("vertical", "鉛直", beam.vertical)):
        if bars.pitch is not None:
            m.line(f"beam.skin.{key}.spacing",
                   f"・{name}方向の間隔 {value(bars.pitch)} mm {'≦' if bars.spacing_ok else '＞'} "
                   f"{value(bars.spacing_limit)} mm　{DOTS} {_judgement(bars.spacing_ok)}")
    corbel = beam.corbel
    m.paragraph("beam.skin.corbel.lead", "コーベルの構造細目", keep=True)
    m.paragraph("beam.skin.corbel.text", "コーベルの側面には、引張鉄筋の40%以上の用心鉄筋を、300mm以下の間隔で配置する。",
                left=INDENT)
    m.line("beam.skin.corbel.tension", Row("引張鉄筋量　As = ", _mm2(corbel.tension), gap=0))
    m.equation("beam.skin.corbel.required", "", "0.40・As", terms(value(corbel.factor), "×", value(corbel.tension)),
               value(corbel.required), MM2)
    provided = "0" if corbel.unit_area is None else \
        f"{value(corbel.count)} × {value(corbel.unit_area)} × 2"
    m.line("beam.skin.corbel.check", Row(f"両面　{provided} = ", _mm2(corbel.provided),
                                         f" {'＞' if corbel.ok else '＜'} ", _mm2(corbel.required),
                                         f"　{DOTS} {_judgement(corbel.ok)}", gap=0))
    compression = beam.compression
    m.heading("beam.compression.heading", n("片持ち梁の圧縮鉄筋"), 3)
    m.paragraph("beam.compression.text", "引張鉄筋の1/6以上を配置することを原則とする。")
    m.equation("beam.compression.required", "", "As / 6", terms(value(compression.tension), "/", "6"),
               value(compression.required), MM2)
    m.line("beam.compression.check", Row("As' = ", _mm2(compression.provided),
                                         f" {'≧' if compression.ok else '＜'} ", _mm2(compression.required),
                                         f"　{DOTS} {_judgement(compression.ok)}", gap=0))
    upper, lower = beam.spacings
    _clear(m, "beam.clear", n, (("上側 ", "梁（上側）", upper), ("下側 ", "梁（下側）", lower)), column=False)
    shear = beam.shear
    _shear(m, "beam.shear", n, shear, [f"スターラップ　{_bar(shear.diameter)} − {value(shear.legs)} 本　"
                                       f"ctc {value(shear.pitch)}"])
    _placement(m, "beam.placement", n, beam.general, beam.confinement, "スターラップ")


# --- 4.4 the footing ------------------------------------------------------------------------------------------------


def _face_table(direction: FootingDirection) -> TableSpec:
    rows: list[tuple[Any, ...]] = [("", "径－本数", "As\n(mm²)", "As/6\n(mm²)", "配置配力鉄筋\n＞As/6",
                                    "配置圧縮鉄筋\n＞As/6")]
    for face in direction.faces:
        rows.append((FACES[face.face], _group(face.bars), value(face.bars.area), value(face.required),
                     f"{value(face.distribution)} ({_judgement(face.distribution_ok)})",
                     f"{value(face.compression)} ({_judgement(face.compression_ok)})"))
    return TableSpec(FACE_WIDTHS, tuple(rows), (2, 1, 1), numeric=frozenset({2, 3, 4, 5}), left=1)


def _footing(m: _Manuscript, footing: FootingDetailing, refs: References) -> None:
    m.heading("footing.heading", "4.4 フーチングの構造細目", 1)
    for index, direction in enumerate(footing.directions):
        key, n = f"footing.{direction.direction}", _Numbers()
        section, durability = refs.footing[direction.direction]
        amount = direction.amount
        m.heading(f"{key}.heading", f"({index + 1}) {DIRECTIONS[direction.direction]}", 2)
        _minimum(m, f"{key}.minimum", n, section,
                 lambda: _ratio(m, f"{key}.minimum.ratio", amount,
                                [("上側鉄筋", amount.groups[0]), ("下側鉄筋", amount.groups[1])]))
        _maximum(m, f"{key}.maximum", n, section)
        _maximum_ratio(m, f"{key}.ratio", n, amount)
        _stress(m, f"{key}.stress", n, durability)
        upper, lower = direction.spacings
        _clear(m, f"{key}.clear", n, (("上側 ", "フーチング（上側）", upper), ("下側 ", "フーチング（下側）", lower)),
               column=False)
        shear = direction.shear
        _shear(m, f"{key}.shear", n, shear, [f"スターラップ　{_bar(shear.diameter)} − {value(shear.legs)} 本/m　"
                                             f"ctc {value(shear.pitch)}"])
        _placement(m, f"{key}.placement", n, direction.general, None, "スターラップ")
        _ductility(m, f"{key}.ductility", n, direction.ductility, shear, value(shear.width))
        _capacity(m, f"{key}.capacity", n, direction.capacity, shear.ratio)
        m.heading(f"{key}.faces.heading", n("配力鉄筋及び圧縮鉄筋"), 3, "【RC標準13.6.4】")
        m.paragraph(f"{key}.faces.distribution", "・配力鉄筋として、引張鉄筋の単位幅当りの断面積の1/6以上を単位幅当り"
                                                 "に対して配置する。")
        m.paragraph(f"{key}.faces.compression", "・圧縮鉄筋として、引張鉄筋の単位幅当りの断面積の1/6以上を単位幅当り"
                                                "に対して配置する。")
        m.table(f"{key}.faces.table", _face_table(direction))


# --- the document ---------------------------------------------------------------------------------------------------


# --- 4.5 the 場所打ち杭 (decision 98) -----------------------------------------------------------------------------------

# the sample 0440 (2.4), made by the sheet 杭の計算 of 照査の前提.xlsm; (1) is checked in 0711 / 0721 (minimum_bars)
PILE_MINIMUM_TITLE = "杭頭反力の最大値から定める最小鉄筋量"
PILE_MINIMUM_TAG = "【基礎標準 付属資料17 1.主鉄筋の配置】"
PILE_SEISMIC_REPORTS = ("0711_線路方向非線形解析", "0721_線路直角方向非線形解析")
_TOUGH = {True: "以上より、靭性の向上を考え帯鉄筋量は杭の側断面積の0.35％以上を配置する。",
          False: "以上より、靭性の向上は考えず帯鉄筋量は杭の側断面積の0.30％以上を配置する。"}


def _n_mm2(number: Printed) -> Row:
    return Row(value(number), " ", MM2, gap=0)


def pile_minimum_formula(m: _Manuscript, key: str) -> None:
    """The formula of (1) and its symbols, as the sample prints them before the values."""
    pv, fck, fsyd = sub("P", "vmax"), sub("f'", "ck"), sub("f", "syd")
    m.line(f"{key}.formula", Row("As ＝ 0.0104・", pv, " / (0.85・", fck, " ＋ 0.008・", fsyd, ")", gap=0))
    m.definitions(f"{key}.symbols", Definition(pv, "杭頭反力の最大値(kN)"),
                  Definition(fck, Row("コンクリートの設計圧縮強度(N/mm", sup("", "2"), ")", gap=0)),
                  Definition(fsyd, Row("鉄筋の降伏点強度(N/mm", sup("", "2"), ")", gap=0)))


def _relation(number: Printed, limit: Printed) -> str:
    return "＞" if number.value > limit.value else "≧" if number.value == limit.value else "＜"


def _pile_bending(m: _Manuscript, pile: PileDetailing) -> None:
    key, bending, found = "pile.bending", pile.bending, pile.section
    m.heading(f"{key}.heading", "(2) 曲げモーメントから定まる最小鉄筋量の検討", 2, PILE_MINIMUM_TAG)
    m.paragraph(f"{key}.text", "杭に作用する曲げモーメントに対しては、引張鉄筋比0.2％以上の鉄筋を配置する。"
                               "引張鉄筋は引張側1/4（90°）部分にある主鉄筋としてよい。"
                               "ただし、抵抗曲げモーメントが作用曲げモーメントの4/3以上あれば0.15％以上でよい。"
                               "また、引張鉄筋比は次式によって求める。")
    pt, ds = sub("p", "t"), sub("d", "s")
    m.line(f"{key}.formula", Row(pt, " ＝ 100・As／(b・d)", gap=0))
    m.definitions(f"{key}.symbols", Definition(pt, "引張鉄筋比(%)"),
                  Definition("As", Row("引張鉄筋の断面積(mm", sup("", "2"), ")　( ", value(found.bar_area), " × 1/4 ＝ ",
                                       _n_mm2(bending.tension_area), " )", gap=0)),
                  Definition("b", Row("＝ √2・R ＝ ", _mm(bending.width), gap=0)),
                  Definition("R", Row("半径(mm)　( ＝ ", _mm(found.radius), " )", gap=0)),
                  Definition("d", Row("＝ 2R－", ds, " ＝ ", _mm(bending.depth), gap=0)),
                  Definition(ds, Row("軸方向鉄筋の芯かぶり(mm)　( ＝ ", _mm(found.centre), " )", gap=0)))
    m.equation(f"{key}.pt", "", pt, terms("100", "×", value(bending.tension_area), "/", "(", value(bending.width), "×",
                                          value(bending.depth), ")"), value(bending.ratio), "%")
    m.line(f"{key}.check", f"{_percent(bending.ratio)} {_relation(bending.ratio, bending.minimum)} "
                           f"{_percent(bending.minimum)}")


def _pile_hoop(m: _Manuscript, key: str, title: str, ratio: HoopRatio) -> None:
    pw = sub("p", "w")
    m.paragraph(f"{key}.lead", title, keep=True)
    m.line(f"{key}.bars", f"帯鉄筋　{_bar(ratio.diameter)} －ctc {value(ratio.pitch)} mm")
    m.equation(f"{key}.pw", "", pw, terms(value(ratio.unit_area), "×", value(ratio.legs), "/", "(", value(ratio.width),
                                          "×", value(ratio.pitch), ")", "×", "100"), value(ratio.ratio), "%")
    m.line(f"{key}.check", f"{_percent(ratio.ratio)} {_relation(ratio.ratio, ratio.minimum)} {_percent(ratio.minimum)}")


def _pile_hoops(m: _Manuscript, pile: PileDetailing) -> None:
    key, hoops, found = "pile.hoops", pile.hoops, pile.section
    m.heading(f"{key}.heading", "(3) 最小帯鉄筋量の検討", 2, "【基礎標準 付属資料17 5.帯鉄筋】")
    m.paragraph(f"{key}.text", "杭頭から2D区間には0.30％以上の帯鉄筋を配置する。ただし、せん断スパン比が2.5以下の場合は"
                               "0.35％以上とする。2D区間を超えた第1段主鉄筋の範囲には0.20％以上配置する。")
    m.paragraph(f"{key}.span.lead", "・せん断スパン比", keep=True)
    both = len(hoops.spans) == 1
    for index, span in enumerate(hoops.spans):
        where = "" if both else f"（{'・'.join(span.directions)}）"
        m.line(f"{key}.span.{index}.beta", f"1／β ＝ {value(span.inverse_beta)} m{where}　「0500_杭基礎より」")
        m.line(f"{key}.span.{index}.formula", "L／d ＝ 1／(1.6・β・D)")
        m.equation(f"{key}.span.{index}.ratio", "", "L／d",
                   terms(value(span.inverse_beta), "/", "(", value(SPAN_FACTOR), "×", value(found.diameter_m), ")"),
                   value(span.ratio), "")
        m.line(f"{key}.span.{index}.check",
               f"{value(span.ratio)} {'≦' if span.tough else '＞'} {value(SPAN_LIMIT)}")
    m.paragraph(f"{key}.span.result", _TOUGH[hoops.tough])
    _pile_hoop(m, f"{key}.head", "・杭頭2D区間", hoops.head)
    for zone in hoops.lower:
        _pile_hoop(m, f"{key}.{zone.name}", f"・2D区間を超えた範囲（{zone.name}）", zone)


def _pile_anchorage(m: _Manuscript, pile: PileDetailing) -> None:
    key, item = "pile.anchorage", pile.anchorage
    ld, ab, kc, cb = sub("l", "d"), sub("α", "b"), sub("K", "c"), sub("c", "b")
    fsyd, fbod, at = sub("f", "syd"), sub("f", "bod"), sub("A", "t")
    m.heading(f"{key}.heading", "(4) 杭頭定着長", 2, "【RC標準第Ⅲ編2.3.7.3】")
    m.paragraph(f"{key}.text", "鉄筋の基本定着長ldは、次式により算定する。")
    m.line(f"{key}.formula", Row(ld, " ＝ ", ab, "・", fsyd, "／4", fbod, "・φ ≧ 20φ", gap=0))
    m.definitions(f"{key}.symbols", Definition(ld, "鉄筋の基本定着長（mm）"),
                  Definition(fsyd, Row("鉄筋の設計引張降伏強度（N/mm", sup("", "2"), "）", gap=0)),
                  Definition(fbod, Row("コンクリートの設計付着強度（N/mm", sup("", "2"), "）", gap=0)),
                  Definition("φ", "定着する鉄筋の直径（mm）"),
                  Definition(ab, Row("＝（0.75／", kc, "）＋ 0.2　ただし、0.5 ≦ ", ab, " ≦ 1.0", gap=0)),
                  Definition(kc, Row("＝（", cb, "／φ）＋｛15", at, "／（s・φ）｝", gap=0)),
                  Definition(cb, "定着する鉄筋のかぶりと、定着する鉄筋のあきの1/2のうち、"),
                  Definition("", "小さい方の値（mm）"),
                  Definition(at, "仮定される割裂破壊断面に垂直な横方向鉄筋の"),
                  Definition("", Row("断面積（mm", sup("", "2"), "）", gap=0)),
                  Definition("s", "横方向鉄筋の中心間隔（mm）"))
    pile_d, centre = value(pile.section.diameter), value(pile.section.centre)
    lines = [
        Row(fsyd, " ＝ ", value(item.fsyd), " N/mm", sup("", "2"), "　（γs ＝ 1.0）", gap=0),
        Row(fbod, " ＝ ", value(item.fbok), " ／ 1.3 ＝ ", value(item.fbod), " N/mm", sup("", "2"),
            f"　（フーチング f'ck ＝ {value(item.fck)} N/mm", sup("", "2"), "）", gap=0),
        f"φ ＝ {value(item.diameter)} mm",
        Row(sub("c", "b1"), f" ＝ {centre} － {value(item.diameter)} ／ 2 ＝ {value(item.clear_cover)} mm", gap=0),
        f"主鉄筋の中心間隔 ＝ π × ({pile_d} － 2 × {centre}) ／ {pile.section.bar_count} ＝ {value(item.pitch)} mm",
        Row(sub("c", "b2"), f" ＝ ({value(item.pitch)} － {value(item.diameter)}) ／ 2 ＝ {value(item.half_gap)} mm",
            gap=0),
        Row("∴ ", cb, f" ＝ {value(item.cb)} mm", gap=0),
        Row(at, f" ＝ {_bar(item.stirrup_diameter)} × {item.stirrup_sets} 組 ＝ ", _n_mm2(item.at),
            f"　（{item.stirrup_zone}）", gap=0),
        f"s ＝ {value(item.s)} mm"]
    for index, line in enumerate(lines):
        m.line(f"{key}.value.{index}", line)
    m.equation(f"{key}.kc", "", kc, terms(value(item.cb), "/", value(item.diameter), "+", "15", "×", value(item.at), "/",
                                          "(", value(item.s), "×", value(item.diameter), ")"), value(item.kc), "")
    m.equation(f"{key}.alpha", "", ab, terms("(", "0.75", "/", value(item.kc), ")", "+", "0.2"), value(item.alpha_raw), "")
    if item.alpha != item.alpha_raw:
        m.line(f"{key}.alpha.bound", Row("→ ", ab, f" ＝ {value(item.alpha)}", gap=0))
    m.equation(f"{key}.ld", "", ld, terms(value(item.alpha), "×", value(item.fsyd), "/", "(", "4", "×", value(item.fbod),
                                          ")", "×", value(item.diameter)), value(item.basic), "mm")
    m.line(f"{key}.least", f"{value(item.basic)} mm（{item.bars}φ） {'≧' if item.basic.value >= item.least.value else '＜'} "
                           f"20φ ＝ {value(item.least)} mm")
    m.paragraph(f"{key}.result", f"以上より、基本定着長は、ld＝{value(item.anchorage)}mmとし、杭頭定着長は、100mm単位に"
                                 f"切り上げて{value(item.length)}mmとする。")


def _pile(m: _Manuscript, pile: PileDetailing) -> None:
    m.heading("pile.heading", "4.5 杭の構造細目", 1)
    m.heading("pile.minimum.heading", f"(1) {PILE_MINIMUM_TITLE}", 2, PILE_MINIMUM_TAG)
    pile_minimum_formula(m, "pile.minimum")
    m.paragraph("pile.minimum.reference", "照査は" + "と".join(f"「{report} {PILE_MINIMUM_TITLE}」"
                                                             for report in PILE_SEISMIC_REPORTS) + "に示す。")
    _pile_bending(m, pile)
    _pile_hoops(m, pile)
    _pile_anchorage(m, pile)


# --- 4.5 the 鋼管ソイルセメント杭 (decision 99) -------------------------------------------------------------------------

# the sample Example橋脚4 II-18〜29 (1.2 杭に関する構造細目): its (a)→1), (i)→(a); its figures are the 配筋図 of 4.1
STEEL_SUMMARY_WIDTHS = (8, 9, 6, 2, 4)  # 項目 | 前提条件 | 設計値 | 判定 | 備考
SOIL_SUMMARY_WIDTHS = (3, 6, 7, 7, 2, 4)  # 項目 (2) | 前提条件 | 設計値 | 判定 | 備考
SEE = "配筋図参照"
STEEL_HOOP_UPPER = FOOTING_HOOP_UPPER[0]
_SATISFIES = {True: "上記条件を満足する。", False: "上記条件を満足しない。"}


def _mark(ok: bool) -> str:
    return "○" if ok else "×"


def _sat(ok: bool, lead: str = "") -> str:
    return lead + _SATISFIES[ok]


def _heights(rows: Sequence[tuple[Any, ...]]) -> tuple[int, ...]:
    """One grid row a table row, two when a cell of the row alone has two lines (a cell over several rows has their
    height)."""
    return tuple(1 + max((plain(cell.value if isinstance(cell, Span) else cell).count("\n") for cell in row
                          if not (isinstance(cell, Span) and cell.rowspan > 1)), default=0) for row in rows)


def _steel_pipe(m: _Manuscript, pile: SteelPileDetailing) -> None:
    pipe, n = pile.pipe, _Numbers()
    key = "steel.pipe"
    m.heading(f"{key}.heading", "(1) 鋼管杭", 2)
    low, high = (value(bound) for bound in STEEL_DIAMETER_RANGE)
    m.heading(f"{key}.diameter.heading", n("鋼管の径"), 3, "【杭体設計の手引き 1.3】")
    m.paragraph(f"{key}.diameter.text", f"一般に用いてよい鋼管杭径は、鋼管ソイルセメント杭に対し、{low}mm～{high}mmまでとする。")
    m.paragraph(f"{key}.diameter.result", _sat(pipe.diameter_ok, f"採用した杭径は{value(pipe.diameter)}mmのため、"))
    m.heading(f"{key}.thickness.heading", n("鋼管の肉厚"), 3, "【杭体設計の手引き 1.5】")
    made, effective = pipe.made, pipe.effective
    m.paragraph(f"{key}.made.text", "・鋼管杭の製造時の肉厚は、9mm以上かつ鋼管外径Dの1%以上とする。")
    m.items(f"{key}.made.items", Definition("鋼管外径 D", _mm(pipe.diameter)),
            Definition("鋼管の製造時の肉厚", _mm(made.value)))
    m.line(f"{key}.made.ratio", f"鋼管外径Dに対して　{value(made.value)} ／ {value(pipe.diameter)} ＝ {value(made.ratio)} "
                                f"{_relation(made.ratio, made.least_ratio).replace('＞', '≧')} {value(made.least_ratio)}")
    m.paragraph(f"{key}.made.result", _sat(made.ok, "となるため、"))
    m.paragraph(f"{key}.effective.text", "・地震時に鋼管杭が脆性的な破壊形態となることを回避するため、鋼管杭の有効肉厚（腐食代を"
                                         "考慮した肉厚）は、6mm以上かつ鋼管外径Dの1.25%以上とする。")
    m.items(f"{key}.effective.items", Definition("鋼管外径 D", _mm(pipe.diameter)),
            Definition("鋼管の有効肉厚 t", Row(_mm(effective.value), f"　（腐食代　{value(pipe.corrosion)} mm考慮）", gap=0)))
    m.line(f"{key}.effective.ratio",
           f"鋼管外径Dに対して　{value(effective.value)} ／ {value(pipe.diameter)} ＝ {value(effective.ratio)} "
           f"{_relation(effective.ratio, effective.least_ratio).replace('＞', '≧')} {value(effective.least_ratio)}")
    m.paragraph(f"{key}.effective.result", _sat(effective.ok, "となるため、"))
    m.heading(f"{key}.joint.heading", n("鋼管の継手"), 3, "【杭体設計の手引き 3】")
    for index, text in enumerate(_PIPE_JOINT_TEXT):
        m.paragraph(f"{key}.joint.{index}", text)
    _steel_tip(m, f"{key}.tip", n, pipe)
    m.heading(f"{key}.summary.heading", n("構造細目一覧"), 3)
    rows: list[tuple[Any, ...]] = [("項目", "前提条件", "設計値", "判定", "備考")]
    rows.append(("鋼管の径", f"{low}mm～{high}mm", f"D ＝ {value(pipe.diameter)} mm", _mark(pipe.diameter_ok), SEE))
    for name, item, symbol, least in (("鋼管の製造時の肉厚", made, "", "9mm以上"),
                                      ("鋼管の有効肉厚", effective, "t ＝ ", "6mm≦t")):
        ratio_text = "Dの1%以上" if item is made else "1.25%≦t/D"
        rows.append((Span(name, rowspan=2), least, f"{symbol}{value(item.value)} mm",
                     _mark(d_ok(item.value, item.least)), Span(SEE, rowspan=2)))
        rows.append((ratio_text, f"{'t/D ＝ ' if item is effective else ''}{value(item.percent)} %",
                     _mark(d_ok(item.ratio, item.least_ratio))))
    tip = pipe.tip
    rows.append(("ずれ止めの取付け長", "－" if tip.length is None else f"{value(tip.length)}mm",
                 "－" if tip.length is None else f"lspi ＝ {value(tip.length)} mm", _mark(tip.ok), SEE))
    rows.append(("鋼管の貫入長", f"{value(tip.penetration)}mm以上", f"lsp0 ＝ {value(tip.penetration)} mm", "○", SEE))
    rows.append(("余裕長", f"{value(tip.margin)}mm以上", f"le ＝ {value(tip.margin)} mm", "○", SEE))
    rows.append(("根入れ長", f"{value(tip.embedment)}mm以上", f"Df0 ＝ {value(tip.embedment)} mm", "○", SEE))
    m.table(f"{key}.summary.table", TableSpec(STEEL_SUMMARY_WIDTHS, tuple(rows), (1,) * len(rows), left=1),
            "表．構造細目一覧表")


_PIPE_JOINT_TEXT = (
    "鋼管杭の継手方法は、工場溶接継手、現場溶接継手、機械式継手によるものとする。",
    "素管を溶接して単管とする場合の工場溶接および付属品の取付けに使用する溶接材料は、素管および付属品の材料の引張強さ以上の"
    "ものとし、JIS A 5525による。また、厚さの異なる管を継ぐ場合は、原則としてあらかじめ工場で加工する。",
    "現場溶接の継手形状は、JIS A 5525 付属書Bに示される他、次の各項により行うものとする。",
    "①現場継手位置は、工場円周溶接部（断面変更位置）から2m以上離す。",
    "②現場継手位置の抵抗曲げモーメント（Mydw）は、継手位置の作用モーメント（Md）以上の強度を有するものとして降伏時の曲げ"
    "降伏耐力（Myd）に90%を乗じた値とする。",
    "鋼管の継手は、工場溶接継手および現場溶接継手を用いており、また溶接はJIS規格によるものとし、上記条件を満足する。",
)


def d_ok(number: Printed, least: Printed) -> bool:
    return number.value >= least.value


def _steel_tip(m: _Manuscript, key: str, n: _Numbers, pipe: SteelPipe) -> None:
    tip = pipe.tip
    m.heading(f"{key}.heading", n("杭先端部"), 3)
    m.heading(f"{key}.ribs.heading", "(a) ずれ止め取付け長", 4, "【杭体設計の手引き 1.11】")
    m.paragraph(f"{key}.ribs.text", "鋼管ソイルセメント杭は、鋼管とソイルセメント体の付着力により杭先端部の荷重を地盤へ伝達"
                                    "させる構造のため、鋼管外周面に突起を設ける他、杭先端部の内面へ突起（リブ）付鋼管やずれ止めを"
                                    "設置するものとする。ずれ止め設置の場合のずれ止めの配置を表に示す。")
    rows: list[tuple[Any, ...]] = [("鋼管外径\nD(mm)", "ずれ止め\n段数 n", "先端間隔\nl0(mm)", "ピッチ\nl(mm)",
                                    "取付長\nlspi(mm)")]
    for size, (steps, first, pitch, length) in STEEL_TIP_RIBS.items():
        rows.append((str(size), str(steps), str(first), str(pitch), str(length)))
    m.table(f"{key}.ribs.table", TableSpec((5, 5, 5, 5, 5), tuple(rows), (2,) + (1,) * (len(rows) - 1),
                                           numeric=frozenset({0, 1, 2, 3, 4}), left=BODY), "表．ずれ止めの配置")
    m.paragraph(f"{key}.ribs.note", "注）ずれ止めは、リング筋D13、SD295または平鋼t16×h32、SS400相当品以上を用いる。")
    if tip.length is None:
        m.paragraph(f"{key}.ribs.result", _sat(False, f"鋼管外径 {value(pipe.diameter)}mm は表の範囲外のため、"))
    else:
        m.paragraph(f"{key}.ribs.result", _sat(True, f"配筋図より、ずれ止めの取付け長lspiは{value(tip.length)}mmなので、"))
    for name, title, text, line, symbol, item in (
            ("penetration", "(b) 鋼管の貫入長", "杭先端部への鋼管の貫入長さは鋼管外径の1.5倍以上とする。",
             f"鋼管外径の1.5倍　：　{value(pipe.diameter)} × 1.5 ＝ {value(tip.penetration)} mm", "鋼管の貫入長lsp0",
             tip.penetration),
            ("margin", "(c) 余裕長", "杭先端から鋼管先端までの長さ（余裕長）はソイルセメント体径の0.5倍以上とする。",
             f"ソイルセメント体径の0.5倍　：　{value(pipe.soil_cement)} × 0.5 ＝ {value(tip.margin)} mm", "余裕長le",
             tip.margin),
            ("embedment", "(d) 根入れ長", "杭先端の最小根入れ長はソイルセメント体径以上とする。",
             f"ソイルセメント体径　：　{value(pipe.soil_cement)} mm", "根入れ長Df0", tip.embedment)):
        m.heading(f"{key}.{name}.heading", title, 4, "【杭体設計の手引き 1.11】")
        m.paragraph(f"{key}.{name}.text", text)
        m.line(f"{key}.{name}.value", line)
        m.paragraph(f"{key}.{name}.result", _sat(True, f"配筋図より、{symbol}は{value(item)}mmなので、"))


def _steel_joint(m: _Manuscript, pile: SteelPileDetailing) -> None:
    joint, pipe, n = pile.joint, pile.pipe, _Numbers()
    key = "steel.joint"
    phi, made = value(joint.bar_diameter), value(joint.made)
    m.heading(f"{key}.heading", "(2) 杭とフーチングの結合部", 2)
    m.heading(f"{key}.grade.heading", n("アンカー鉄筋の材質と鉄筋径"), 3, "【杭体設計の手引き 1.2, 1.10】")
    m.paragraph(f"{key}.grade.text", "アンカー鉄筋は、SD345またはSD390の異形鉄筋を標準とし、アンカー鉄筋径は19mm以上38mm"
                                     "以下とする。")
    m.paragraph(f"{key}.grade.result", _sat(joint.grade_ok and joint.size_ok,
                                            f"採用したアンカー鉄筋の材質は{joint.grade}であり、鉄筋径はD{phi}なので"))
    m.heading(f"{key}.cover.heading", n("かぶり"), 3, "【コンクリート構造編 3.3.2】")
    m.paragraph(f"{key}.cover.text", "一般に、かぶりは鋼材の直径以上とする。")
    m.paragraph(f"{key}.cover.lead", f"鋼管の厚さは {made}mm、アンカー鉄筋はD{phi}であるので、鋼管内側からアンカー鉄筋までの"
                                     "かぶりは、", keep=True)
    m.line(f"{key}.cover.value", f"{value(joint.centroid)} － {made} － {phi} ／ 2 ＝ {value(joint.cover)} mmである。")
    m.paragraph(f"{key}.cover.result", _sat(joint.cover_ok, f"アンカー鉄筋は D{phi} であるため、"))
    m.heading(f"{key}.clear.heading", n("鉄筋のあき"), 3, "【杭体設計の手引き 1.10】")
    m.paragraph(f"{key}.clear.text", "アンカー鉄筋のあきは、40mm以上、粗骨材の最大寸法の4/3以上かつ鉄筋の直径の1.5倍以上と"
                                     "しなければならない。")
    m.line(f"{key}.clear.pitch", f"軸方向鉄筋ピッチ ＝ π × ({value(pipe.diameter)} － 2 × {value(joint.centroid)}) ／ "
                                 f"{joint.bar_count} ＝ {value(joint.pitch)} mm")
    m.items(f"{key}.clear.items",
            Definition("軸方向鉄筋ピッチ", f"{value(joint.pitch)} mm"),
            Definition("アンカー鉄筋径", f"{phi} mm"),
            Definition("軸方向鉄筋のあき", f"{value(joint.pitch)} mm － {phi} mm ＝ {value(joint.clear)} mm"))
    limits = (f"≧ {value(STEEL_CLEAR_LEAST)} mm",
              f"≧ {value(joint.aggregate)} × 4/3 ＝ {value(joint.aggregate_limit)} mm",
              f"≧ {phi} × 1.5 ＝ {value(joint.bar_limit)} mm")
    rows = [("部材", "あき(mm)", "前提条件"),
            (Span("杭頭部", rowspan=3), Span(f"軸方向鉄筋のあき {value(joint.clear)}", rowspan=3),
             Span(limits[0], align="left")), *((Span(limit, align="left"),) for limit in limits[1:])]
    m.table(f"{key}.clear.table", TableSpec(CLEAR_WIDTHS, tuple(rows), (1,) * len(rows), left=BODY), "表．鉄筋のあき")
    m.paragraph(f"{key}.clear.result", _sat(joint.clear_ok, "よって、"))
    ribs = joint.ribs
    m.paragraph(f"{key}.gap.text", "アンカー鉄筋とずれ止めの間のあきは、15mm以上とする。")
    if ribs.thickness is None or joint.rib_gap is None:
        m.paragraph(f"{key}.gap.result", _sat(False, "ずれ止めを配置できないため、"))
    else:
        m.paragraph(f"{key}.gap.lead", f"ずれ止めの厚さは {value(ribs.thickness)}mmであるので、", keep=True)
        m.line(f"{key}.gap.value", f"あきは、{value(joint.centroid)} － {made} － {value(ribs.thickness)} － {phi} ／ 2 ＝ "
                                   f"{value(joint.rib_gap)} mmである。")
        m.paragraph(f"{key}.gap.result", _sat(joint.rib_gap_ok, "よって、"))
    pc = sub("p", "c")
    for name, title, text, bound, ok in (
            ("minimum", "最小鉄筋量", "アンカー鉄筋の最小鉄筋量は1%とする。", STEEL_PC_RANGE[0],
             d_ok(joint.pc, STEEL_PC_RANGE[0])),
            ("maximum", "最大鉄筋量", "アンカー鉄筋の最大鉄筋量は6%とする。", STEEL_PC_RANGE[1],
             joint.pc.value <= STEEL_PC_RANGE[1].value)):
        m.heading(f"{key}.{name}.heading", n(title), 3, "【杭体設計の手引き 1.10】")
        m.paragraph(f"{key}.{name}.text", text)
        m.paragraph(f"{key}.{name}.lead", "・軸方向鉄筋比pcの算出", keep=True)
        if name == "minimum":
            m.line(f"{key}.{name}.formula", Row(pc, " ＝ ", sub("A", "s"), "／(πD", sup("", "2"), "/4)", gap=0))
            m.definitions(f"{key}.{name}.symbols",
                          Definition(sub("A", "s"), Row("軸方向鉄筋の量　( ＝ ", _mm2(joint.bar_area), f" : D{phi} － "
                                                        f"{joint.bar_count} 本 )", gap=0)),
                          Definition("D", Row("杭径　( ＝ ", _mm(pipe.diameter), " )", gap=0)))
        m.equation(f"{key}.{name}.pc", "", pc, terms(value(joint.bar_area), "/", "(", "π", "×",
                                                     f"{value(pipe.diameter)}²", "/", "4", ")", "×", "100"),
                   value(joint.pc), "%")
        m.line(f"{key}.{name}.check", f"{value(joint.pc)} % {_relation(joint.pc, bound)} {value(bound)} %")
        m.paragraph(f"{key}.{name}.result", _sat(ok, "よって、"))
    _steel_anchorage(m, f"{key}.anchorage", n, joint)
    _steel_filling(m, f"{key}.filling", n, joint, pipe)
    _steel_hoops(m, f"{key}.hoops", n, joint, pipe)
    _steel_ribs(m, f"{key}.ribs", n, joint, pipe)
    _steel_joint_summary(m, f"{key}.summary", n, joint)


def _steel_anchorage(m: _Manuscript, key: str, n: _Numbers, joint: SteelJoint) -> None:
    item, phi = joint.anchorage, value(joint.bar_diameter)
    ld01, ld0, fsyd, fcd, fck = sub("l", "d01"), sub("l", "d0"), sub("f", "syd"), sub("f'", "cd"), sub("f'", "ck")
    k1, cs, ls, l1 = sub("k", "1"), sub("c", "s"), sub("l", "s"), sub("l", "1")
    m.heading(f"{key}.heading", n("アンカー鉄筋の定着"), 3)
    m.heading(f"{key}.basic.heading", "(a) フーチング内アンカー鉄筋の基本定着長の算定", 4, "【コンクリート構造編 2.3.7.3】")
    m.paragraph(f"{key}.basic.lead", "①マッシブなコンクリートに埋め込む鉄筋の基本定着長", keep=True)
    m.line(f"{key}.basic.formula", Row(ld01, " ＝ ", k1, "（0.7", fsyd, "／", fcd, " ＋ 11）φ", gap=0))
    m.definitions(f"{key}.basic.symbols",
                  Definition(ld01, "マッシブなコンクリートに埋め込む鉄筋の定着長"),
                  Definition(fsyd, Row("鉄筋の設計引張降伏強度　( ＝ ", value(item.fsyd), " N/mm", sup("", "2"), " )",
                                       gap=0)),
                  Definition(fcd, "コンクリートの設計圧縮強度"),
                  Definition(fck, Row("コンクリートの設計基準強度　( ＝ ", value(item.fck), " N/mm", sup("", "2"), " )",
                                      gap=0)),
                  Definition("γc", "材料係数　( ＝ 1.3 )"),
                  Definition("φ", f"定着する鉄筋の直径　( ＝ {phi} mm )"),
                  Definition(k1, "鉄筋間隔に関する係数"),
                  Definition(cs, f"鉄筋の中心間隔（≦10φ）　( ＝ {value(item.spacing)} mm ≦ {value(item.spacing_limit)} mm )"))
    m.equation(f"{key}.basic.fcd", "", fcd, terms(value(item.fck), "/", "1.3"), value(item.fcd), Row("N/mm", sup("", "2"), gap=0))
    m.equation(f"{key}.basic.k1", "", k1, terms("1", "+", "0.5", "×", phi, "/", value(item.spacing)), value(item.k1), "")
    m.equation(f"{key}.basic.ld01", "", ld01, terms(value(item.k1), "×", "(", "0.7", "×", value(item.fsyd), "/",
                                                    value(item.fcd), "+", "11", ")", "×", phi), value(item.ld01), "mm")
    m.paragraph(f"{key}.basic.hook", "なお、標準フックを設けるため基本定着長より10φ（φ：アンカー鉄筋径）減じる。ただし、"
                                     "基本定着長は、20φ以上とする。")
    least = item.reduced.value < item.least.value
    m.line(f"{key}.basic.ld0", Row(ld0, f" ＝ ", ld01, f" － 10φ ＝ {value(item.ld01)} － {value(item.hook)} ＝ "
                                   f"{value(item.reduced)} mm {'≦' if least else '≧'} 20φ（{value(item.least)} mm）",
                                   gap=0))
    m.paragraph(f"{key}.basic.result", "そのため、基本定着長は、20φとする。" if least
                else "そのため、基本定着長は、ld01－10φとする。")
    m.line(f"{key}.basic.value", Row(ld0, f" ＝ {value(item.ld0)} mm", gap=0))
    m.heading(f"{key}.footing.heading", "(b) フーチング内アンカー鉄筋の必要長 l1", 4,
              "【杭体設計の手引き 1.10】")
    m.paragraph(f"{key}.footing.text", "フーチング内アンカー鉄筋の必要長l1は、鋼管杭頭からフーチング内の定着が"
                                       "有効とならない範囲lsに、基本定着長を加えた長さとする。")
    m.line(f"{key}.footing.formula", Row(l1, " ＝ ", ld0, " ＋ ", ls, gap=0))
    m.definitions(f"{key}.footing.symbols", Definition(ld0, "鉄筋の基本定着長（mm）"),
                  Definition(ls, "鋼管杭頭からフーチング内の定着が有効とならない範囲（mm）"))
    m.line(f"{key}.footing.ls", f"軸方向鉄筋径の5φ　：　{phi} × 5 ＝ {value(item.ineffective)} mm")
    m.line(f"{key}.footing.l1", Row("よって、", l1, f" ＝ {value(item.ld0)} ＋ {value(item.ineffective)} ＝ "
                                    f"{value(item.sum)} mm → {value(item.l1)} mm", gap=0))


def _steel_filling(m: _Manuscript, key: str, n: _Numbers, joint: SteelJoint, pipe: SteelPipe) -> None:
    fill, phi = joint.filling, value(joint.bar_diameter)
    l2, ld, lc, lh = sub("l", "2"), sub("l'", "d"), sub("l", "c"), sub("l", "h")
    ab, fsyd, fbod = sub("α", "b"), sub("f", "syd"), sub("f", "bod")
    m.heading(f"{key}.pipe.heading", "(c) 鋼管内アンカー鉄筋の必要長 l2", 4, "【杭体設計の手引き 1.10】")
    m.paragraph(f"{key}.pipe.text", "鋼管内でのアンカー鉄筋の必要長l2は、鋼管内のアンカー鉄筋の定着が有効にならない"
                                    "範囲l''に鋼管内のアンカー鉄筋の基本定着長l'dを加えた長さとする。鋼管内の基本定着長l'dは、"
                                    "αb＝0.6として算定する。")
    m.line(f"{key}.pipe.formula", Row(l2, " ＝ l'' ＋ ", ld, "　　", ld, " ＝ ", ab, "・", fsyd, "／4", fbod, "・φ", gap=0))
    m.line(f"{key}.pipe.fbod", Row(fbod, f" ＝ {value(fill.fbok)} ／ 1.3 ＝ {value(fill.fbod)} N/mm", sup("", "2"),
                                   f"　（中詰めコンクリート f'ck ＝ {value(fill.fck)} N/mm", sup("", "2"), "）", gap=0))
    m.equation(f"{key}.pipe.ld", "", ld, terms("0.6", "×", value(joint.anchorage.fsyd), "/", "(", "4", "×",
                                               value(fill.fbod), ")", "×", phi), value(fill.anchorage), "mm")
    m.equation(f"{key}.pipe.l2", "", l2, terms(value(STEEL_FILL_INEFFECTIVE), "+", value(fill.anchorage)),
               value(fill.required), "mm")
    m.heading(f"{key}.heading", n("中詰めコンクリート長 lc"), 3, "【杭体設計の手引き 1.10】")
    m.paragraph(f"{key}.text", "中詰めコンクリートの長さlcは、鋼管径の1.5倍以上とし、鋼管内のアンカー鉄筋との定着が"
                               "可能な長さとする。また、アンカー鉄筋と中詰めコンクリート下端の間は、100mm以上とする。")
    m.line(f"{key}.formula", Row(lc, " ＝ max（1.5D，l'' ＋ ", ld, " ＋ ", lh, " ＋ 100）", gap=0))
    radius = format(fill.radius_factor, "f")
    m.definitions(f"{key}.symbols", Definition(lh, f"下端の半円形フックの半径　( ＝ {radius}φ ＋ φ ＝ "
                                                   f"{value(fill.hook)} mm )"))
    m.line(f"{key}.least", f"1.5D ＝ 1.5 × {value(pipe.diameter)} ＝ {value(fill.least)} mm")
    m.line(f"{key}.sum", Row("l'' ＋ ", ld, " ＋ ", lh, f" ＋ 100 ＝ {value(STEEL_FILL_INEFFECTIVE)} ＋ "
                             f"{value(fill.anchorage)} ＋ {value(fill.hook)} ＋ 100 ＝ {value(fill.sum)} mm", gap=0))
    larger = fill.sum if fill.sum.value >= fill.least.value else fill.least
    m.line(f"{key}.value", Row("よって、", lc, f" ＝ {value(larger)} mm → {value(fill.length)} mm", gap=0))


def _steel_hoops(m: _Manuscript, key: str, n: _Numbers, joint: SteelJoint, pipe: SteelPipe) -> None:
    hoops, inner, phi = joint.footing_hoops, joint.pipe_hoops, joint.bar_diameter
    m.heading(f"{key}.heading", n("帯鉄筋"), 3)
    m.heading(f"{key}.diameter.heading", "(a) 帯鉄筋径", 4, "【杭体設計の手引き 1.10】")
    band = next(name for most, name in (("16", "D16以下"), ("25", "D25以下"), ("inf", "D29以上"))
                if phi.value <= float(most))
    upper = "" if hoops.upper is None else (f"とし、鋼管外径が{value(STEEL_HOOP_UPPER)}mm以下の場合は、"
                                            f"D{value(hoops.upper)}以下")
    m.paragraph(f"{key}.diameter.text", f"フーチング内のアンカー鉄筋の帯鉄筋径は、アンカー鉄筋が{band}の場合は、"
                                        f"D{value(hoops.diameter)}以上{upper}とする。")
    m.items(f"{key}.diameter.items", Definition("・アンカー鉄筋径", f"D{value(phi)}"),
            Definition("・鋼管外径", f"{value(pipe.diameter)} mm"))
    bounds = f"D{value(hoops.diameter)}以上" + ("" if hoops.upper is None else f"、D{value(hoops.upper)}以下")
    m.paragraph(f"{key}.diameter.result", f"上記より、帯鉄筋径は、{bounds}となる。")
    m.paragraph(f"{key}.diameter.placed", f"配置した帯鉄筋径は、D{value(hoops.diameter)} なので、上記条件を満足する。")
    m.heading(f"{key}.pitch.heading", "(b) 帯鉄筋の配置間隔", 4, "【杭体設計の手引き 1.10】")
    m.paragraph(f"{key}.pitch.text", "フーチング内の帯鉄筋は、アンカー鉄筋の径に応じて表に示す配置間隔とする。")
    m.paragraph(f"{key}.pitch.pipe", "また、鋼管内の帯鉄筋は、アンカー鉄筋の鉄筋かごの組立て筋を兼ねて、アンカー鉄筋の内側に"
                                     "径10mm以上の鉄筋を200mm～300mm間隔で3本以上配置するものとする。")
    rows = [(Span("アンカー鉄筋径", colspan=2), "D25以下", "D29以上"),
            (Span("帯鉄筋間隔", rowspan=2), "フーチング下側鉄筋から3本程度", "100mm", "125mm"),
            ("それ以上", "150mm程度", "200mm"),
            ("組立筋間隔", "鋼管内", Span("200mm ～ 300mm", colspan=2))]
    m.table(f"{key}.pitch.table", TableSpec((5, 10, 5, 5), tuple(rows), (1,) * len(rows), left=BODY),
            "表．アンカー鉄筋定着部の帯鉄筋配置間隔")
    lc, lh = sub("l", "c"), sub("l", "h")
    m.line(f"{key}.pitch.formula", Row("鋼管内の帯鉄筋の範囲 ＝ ", lc, " － 100 － ", lh, " － l''", gap=0))
    m.line(f"{key}.pitch.range", f"＝ {value(joint.filling.length)} － 100 － {value(joint.filling.hook)} － 100 ＝ "
                                 f"{value(inner.range)} mm")
    m.line(f"{key}.pitch.inner", f"{value(inner.range)} ／ {inner.divisions} → ctc {value(inner.pitch)} mm"
                                 f"（D{value(inner.diameter)}－{inner.count}本）")
    m.paragraph(f"{key}.pitch.result", _sat(inner.ok, "配筋図より、"))


def _steel_ribs(m: _Manuscript, key: str, n: _Numbers, joint: SteelJoint, pipe: SteelPipe) -> None:
    ribs = joint.ribs
    m.heading(f"{key}.heading", n("ずれ止め"), 3)
    m.heading(f"{key}.shape.heading", "(a) ずれ止めの材質、形状および配置", 4, "【杭体設計の手引き 1.2, 1.10】")
    m.paragraph(f"{key}.grade.text", "・ずれ止めの材質は、SS400と同等以上の鋼材とする。")
    m.paragraph(f"{key}.grade.result", f"使用したずれ止めの材質は、{ribs.grade}なので、上記条件を満足する。")
    m.paragraph(f"{key}.thickness.text", "・ずれ止めの厚さt'は鋼管の有効肉厚以下とする。")
    if ribs.thickness is None or ribs.width is None or ribs.width_least is None or ribs.spacing is None \
            or ribs.bottom is None or ribs.bottom_least is None:
        m.paragraph(f"{key}.thickness.result", _sat(False, f"鋼管の有効肉厚が{value(ribs.effective)}mmのため、表の厚さの"
                                                           "ずれ止めを配置できず、"))
        return
    m.items(f"{key}.thickness.items",
            Definition("鋼管の有効肉厚 t", f"{value(ribs.effective)} mm　（腐食代　{value(pipe.corrosion)} mm考慮）"),
            Definition("ずれ止めの厚さ t'", f"{value(ribs.thickness)} mm ≦ t ＝ {value(ribs.effective)} mm"))
    m.paragraph(f"{key}.thickness.result", _sat(True, "よって、"))
    m.paragraph(f"{key}.width.text", "・ずれ止めの幅Bはずれ止めの厚さt'の2倍以上とする。")
    m.items(f"{key}.width.items",
            Definition("ずれ止めの厚さ t'の2倍", f"{value(ribs.thickness)} × 2 ＝ {value(ribs.width_least)} mm"),
            Definition("ずれ止めの幅 B", f"{value(ribs.width)} mm ≧ 2t' ＝ {value(ribs.width_least)} mm"))
    m.paragraph(f"{key}.width.result", _sat(True, "よって、"))
    m.paragraph(f"{key}.spacing.text", "・ずれ止めの間隔は、表を標準とする。")
    head = ("厚さ：t' (mm)", *(f"{low}～{high}" for low, high, _ in STEEL_RIB_SPACINGS))
    m.table(f"{key}.spacing.table", TableSpec((6, 4, 4, 4, 4), (head, ("間隔：lz (mm)", *(
        str(spacing) for _, _, spacing in STEEL_RIB_SPACINGS))), (1, 1), numeric=frozenset({1, 2, 3, 4}), left=BODY),
            "表．ずれ止めの間隔")
    lz, lz0 = sub("l", "z"), sub("l", "z0")
    m.line(f"{key}.spacing.value", Row(f"ずれ止めの厚さt'は、{value(ribs.thickness)} mm なので、", lz,
                                       f" ＝ {value(ribs.spacing)} mm", gap=0))
    m.paragraph(f"{key}.spacing.result", f"実際に配置したずれ止めの間隔は、{value(ribs.spacing)} mm なので、上記条件を満足する。")
    m.paragraph(f"{key}.position.text", "・最上段のずれ止めの取付中心位置は鋼管杭頭からD/4（D：鋼管外径）の位置とし、"
                                        "最下段のずれ止めの取付中心位置は中詰めコンクリートの下端からlz0（D/4あるいはlzの"
                                        "うち大きな値）以上離れた位置とする。")
    m.line(f"{key}.position.quarter", f"鋼管外径Dの1/4　：　{value(pipe.diameter)} ／ 4 ＝ {value(ribs.quarter)} mm")
    m.line(f"{key}.position.value", Row(lz0, f" ＝ max（{value(ribs.quarter)}，{value(ribs.spacing)}）＝ "
                                        f"{value(ribs.bottom_least)} mm", gap=0))
    m.paragraph(f"{key}.position.result", _sat(ribs.ok, f"最上段のずれ止めの取付中心位置は、鋼管杭頭から "
                                                        f"{value(ribs.quarter)} mm、最下段のずれ止めの取付中心位置は、"
                                                        f"中詰めコンクリート下端から {value(ribs.bottom)} mm なので、"))
    m.paragraph(f"{key}.steps.text", "・ずれ止めの段数は2段以上とする。")
    m.paragraph(f"{key}.steps.result", f"実際に配置したずれ止めは、{ribs.steps} 段なので、上記条件を満足する。")


def _steel_joint_summary(m: _Manuscript, key: str, n: _Numbers, joint: SteelJoint) -> None:
    ribs, item, fill, hoops, inner = joint.ribs, joint.anchorage, joint.filling, joint.footing_hoops, joint.pipe_hoops
    m.heading(f"{key}.heading", n("構造細目一覧"), 3)
    governing = max(((STEEL_CLEAR_LEAST, "40mm以上"), (joint.aggregate_limit, "4/3Dmax以上"),
                     (joint.bar_limit, "1.5φ以上")), key=lambda pair: pair[0].value)
    bounds = f"D{value(hoops.diameter)}以上" + ("" if hoops.upper is None else f", D{value(hoops.upper)}以下")
    rows: list[tuple[Any, ...]] = [
        ("項目", "前提条件", "設計値", "判定", "備考"),
        ("アンカー鉄筋：材質", "SD345,SD390", joint.grade, _mark(joint.grade_ok), SEE),
        ("アンカー鉄筋：径", "D19～D38", f"D{value(joint.bar_diameter)}", _mark(joint.size_ok), SEE),
        ("かぶり", f"c ＝ {value(joint.bar_diameter)} mm 以上", f"c ＝ {value(joint.cover)} mm", _mark(joint.cover_ok), SEE),
        ("鉄筋のあき（軸方向）", f"{value(governing[0])} mm 以上", f"{value(joint.clear)} mm", _mark(joint.clear_ok),
         governing[1]),
        ("鉄筋のあき（ずれ止め）", f"{value(STEEL_RIB_GAP_LEAST)} mm 以上",
         "－" if joint.rib_gap is None else f"{value(joint.rib_gap)} mm", _mark(joint.rib_gap_ok), SEE),
        ("最小鉄筋量", "pc＝1%以上", f"pc ＝ {value(joint.pc)} %", _mark(d_ok(joint.pc, STEEL_PC_RANGE[0])), ""),
        ("最大鉄筋量", "pc＝6%以下", f"pc ＝ {value(joint.pc)} %",
         _mark(joint.pc.value <= STEEL_PC_RANGE[1].value), ""),
        ("鉄筋の定着", f"l1 ＝ {value(item.l1)} mm 以上", f"l1 ＝ {value(item.l1)} mm", "○", SEE),
        ("中詰めコンクリート長さ", f"lc ＝ {value(fill.length)} mm 以上", f"lc ＝ {value(fill.length)} mm", "○", SEE),
        ("帯鉄筋径", bounds, f"D{value(hoops.diameter)}", "○", SEE),
        (Span("帯鉄筋の配置間隔", rowspan=3), f"フーチング下側鉄筋から\n3本程度：{value(hoops.lower_pitch)}mm",
         f"{value(hoops.lower_pitch)} mm", "○", Span(SEE, rowspan=3)),
        (f"それ以上：{value(hoops.upper_pitch)}mm程度", f"{value(hoops.upper_pitch)} mm", "○"),
        ("鋼管内：200mm～300mm", f"{value(inner.pitch)} mm", _mark(inner.ok)),
        ("ずれ止めの材質", "SS400と同等以上", ribs.grade, "○", SEE)]
    if ribs.thickness is None or ribs.width is None or ribs.width_least is None or ribs.spacing is None \
            or ribs.bottom is None or ribs.bottom_least is None:
        rows.append(("ずれ止めの厚さ", f"t ＝ {value(ribs.effective)} mm 以下", "－", "×", SEE))
    else:
        rows += [
            ("ずれ止めの厚さ", f"t ＝ {value(ribs.effective)} mm 以下", f"t' ＝ {value(ribs.thickness)} mm", "○", SEE),
            ("ずれ止めの幅", f"2t' ＝ {value(ribs.width_least)} mm 以上", f"B ＝ {value(ribs.width)} mm", "○", SEE),
            ("ずれ止めの間隔", f"lz ＝ {value(ribs.spacing)} mm", f"{value(ribs.spacing)} mm", "○", SEE),
            (Span("ずれ止めの取付中心位置", rowspan=2), f"杭頭から D/4 ＝ {value(ribs.quarter)} mm",
             f"{value(ribs.quarter)} mm", "○", Span(SEE, rowspan=2)),
            (f"下端から lz0 ＝ {value(ribs.bottom_least)} mm 以上", f"{value(ribs.bottom)} mm", _mark(ribs.ok)),
            ("ずれ止めの段数", "2段以上", f"{ribs.steps} 段", "○", SEE)]
    m.table(f"{key}.table", TableSpec(STEEL_SUMMARY_WIDTHS, tuple(rows), _heights(rows), left=1), "表．構造細目一覧表")


def _steel_soil_cement(m: _Manuscript, pile: SteelPileDetailing) -> None:
    soil, n, key = pile.soil_cement, _Numbers(), "steel.soil"
    dsp, dsc, tsp, tsc = sub("D", "sp"), sub("D", "sc"), sub("τ", "sp"), sub("τ", "sc")
    kn = Row("kN/m", sup("", "2"), gap=0)
    m.heading(f"{key}.heading", "(3) ソイルセメント", 2)
    m.heading(f"{key}.strength.heading", n("ソイルセメント体の一軸圧縮強度"), 3)
    m.heading(f"{key}.general.heading", "(a) 杭一般部のソイルセメント体の一軸圧縮強度", 4, "【杭体設計の手引き 1.8】")
    m.paragraph(f"{key}.general.text", "杭一般部では、ソイルセメント体と鋼管との付着力が地盤の周面摩擦力を上回る必要がある。")
    m.paragraph(f"{key}.general.lead", "・ソイルセメント体と鋼管との付着強度およびソイルセメント体と地盤との摩擦力の関係",
                keep=True)
    m.line(f"{key}.general.formula", Row("π・", dsp, "・", tsp, " ≧ π・", dsc, "・", tsc, "　【杭体設計の手引き 解(1.8-1)】",
                                         gap=0))
    m.definitions(f"{key}.general.symbols", Definition(dsp, "鋼管外径（m）"), Definition(dsc, "ソイルセメント体径（m）"),
                  Definition(tsp, Row("杭一般部のソイルセメント体と外面突起付き鋼管の付着強度（", kn, "）", gap=0)),
                  Definition(tsc, Row("杭一般部のソイルセメント体と地盤との周面最大摩擦力度（", kn, "）", gap=0)))
    m.paragraph(f"{key}.general.note", "なお、【杭体設計の手引き 1.8】より、基礎先行降伏とならない一般的な地盤条件においては"
                                       "表に示す一軸圧縮強度とすることで上記条件を満足する。")
    strengths = dict(soil.strengths)
    general = [("砂質土", strengths["杭一般部（砂質土）"]), ("粘性土", strengths["杭一般部（粘性土）"])]
    rows = [("杭の部位", "地盤", Row(sub("q", "u"), "（", kn, "）※材令28日強度", gap=0)),
            (Span("一般部", rowspan=2), general[0][0], value(general[0][1])), (general[1][0], value(general[1][1]))]
    m.table(f"{key}.general.table", TableSpec((5, 5, 12), tuple(rows), (1,) * len(rows), left=BODY),
            "表．杭一般部のソイルセメント体の一軸圧縮強度【杭体設計の手引き 解説表 1.8-1】")
    lspo, tspo, lspi, tspi = sub("l", "spo"), sub("τ", "spo"), sub("l", "spi"), sub("τ", "spi")
    asc, qd, lsc = sub("A", "sc"), sub("q", "d"), sub("l", "sc")
    m.heading(f"{key}.tip.heading", "(b) 杭先端部のソイルセメント体の一軸圧縮強度", 4, "【杭体設計の手引き 1.8】")
    m.paragraph(f"{key}.tip.text", "杭先端部では、杭先端部でのソイルセメント体と鋼管との付着力が地盤の極限支持力および地盤の"
                                   "周面摩擦力を上回る必要がある。")
    m.paragraph(f"{key}.tip.lead", "・ソイルセメント体と鋼管との付着強度および先端部の支持力（先端および周面）の関係", keep=True)
    m.line(f"{key}.tip.formula", Row("π・", dsp, "・（", lspo, "・", tspo, "＋", lspi, "・", tspi, "）≧ ", asc, "・", qd,
                                     "＋π・", dsc, "・", lsc, "・", tsc, gap=0))
    m.line(f"{key}.tip.source", "【杭体設計の手引き 解(1.8-2)】")
    m.definitions(f"{key}.tip.symbols", Definition(dsp, "鋼管外径（m）"), Definition(lspo, "杭先端部への鋼管の根入れ長（m）"),
                  Definition(tspo, Row("杭先端部の鋼管外面とソイルセメント体の付着強度（", kn, "）", gap=0)),
                  Definition(lspi, "杭先端部の鋼管の内面にずれ止めまたは突起を有する部分の長さ（m）"),
                  Definition(tspi, Row("杭先端部の鋼管内面とソイルセメント体の付着強度（", kn, "）", gap=0)),
                  Definition(asc, Row("ソイルセメント体外径を設計径とする断面積（m", sup("", "2"), "）", gap=0)),
                  Definition(qd, Row("先端地盤の極限支持力度（", kn, "）", gap=0)),
                  Definition(dsc, "ソイルセメント体径（m）"), Definition(lsc, "杭先端部の長さ（m）"),
                  Definition(tsc, Row("ソイルセメント体と地盤との周面最大摩擦力度（", kn, "）", gap=0)))
    m.paragraph(f"{key}.tip.note", "なお、【杭体設計の手引き 1.8】より、基礎先行降伏とならない一般的な地盤条件においては"
                                   "表に示す一軸圧縮強度とすることで上記条件を満足する。")
    rows = [("杭の部位", "地盤", Row(sub("q", "u"), "（", kn, "）※材令28日強度", gap=0)),
            ("先端部", "砂・砂礫", value(strengths["杭先端部（砂質土）"]))]
    m.table(f"{key}.tip.table", TableSpec((5, 5, 12), tuple(rows), (1, 1), left=BODY),
            "表．杭先端部のソイルセメント体の一軸圧縮強度【杭体設計の手引き 解説表 1.8-1】")
    m.heading(f"{key}.nominal.heading", n("ソイルセメント体の公称径"), 3, "【杭体設計の手引き 1.8】")
    m.paragraph(f"{key}.nominal.text", "ソイルセメント体の公称径は、鋼管外径よりも200mm大きい径を原則とする。")
    m.paragraph(f"{key}.nominal.result", _sat(soil.ok, f"採用したソイルセメント体の公称径は{value(soil.soil_cement)}mm、"
                                                       f"鋼管外径は{value(soil.steel)}mmのため、"))
    m.heading(f"{key}.summary.heading", n("前提条件一覧表"), 3)
    symbols = ("qu1-1", "qu1-2", "qu2")
    rows: list[tuple[Any, ...]] = [(Span("項目", colspan=2), "前提条件", "設計値", "判定", "備考")]
    for index, ((name, strength), symbol) in enumerate(zip(soil.strengths, symbols)):
        first = (Span("一軸\n圧縮\n強度", rowspan=3),) if index == 0 else ()
        remark = (Span(SEE, rowspan=3),) if index == 0 else ()
        rows.append((*first, name, Row(value(strength), " ", kn, " 以上", gap=0),
                     Row(f"{symbol} ＝ {value(strength)} ", kn, gap=0), "○", *remark))
    rows.append((Span("公称径", colspan=2), "Dsc ＝ Dsp ＋ 200mm",
                 f"Dsc ＝ {value(soil.soil_cement)}mm\nDsp ＝ {value(soil.steel)}mm", _mark(soil.ok), SEE))
    m.table(f"{key}.summary.table", TableSpec(SOIL_SUMMARY_WIDTHS, tuple(rows), _heights(rows), left=1),
            "表．前提条件一覧表")


def _steel_pile(m: _Manuscript, pile: SteelPileDetailing) -> None:
    m.heading("pile.heading", "4.5 杭の構造細目", 1)
    _steel_pipe(m, pile)
    _steel_joint(m, pile)
    _steel_soil_cement(m, pile)


def figure_specs(drawings: Mapping[str, tuple[bytes, bytes]]) -> dict[str, FigureSpec]:
    """The 配筋図 of 4.1 from their (PDF, PNG) by name (FIGURES): each page as vector artwork in a frame of the body
    width (GridLayoutPdf's PdfFigure), the PNG its picture in the grid Excel. The drawing is made elsewhere
    (export.drawing; the pipeline passes the bytes) and prints nothing WebPier reads back."""
    specs = {}
    for name, (pdf, png) in drawings.items():
        box = PdfReader(BytesIO(pdf)).pages[0].cropbox
        rows = min(rows_for(columns_pt(FIGURE_COLUMNS) * float(box.height) / float(box.width)), FIGURE_ROWS)
        figure = PdfFigure(FIGURE_COLUMNS, rows, pdf, preview=png, block_id=f"{PREFIX}layout.{name}.figure")
        specs[name] = FigureSpec(figure, (), left=FIGURE_LEFT)
    return specs


def content(result: DetailingResult, figures: Mapping[str, FigureSpec] | None = None) -> tuple[Unit, ...]:
    """The ordered manuscript, used by both the layout and the semantic tests. *figures* are the 配筋図 of 4.1 by
    name (FIGURES); a missing one leaves its heading alone."""
    figures = figures or {}
    if unknown := set(figures) - set(FIGURES):
        raise ValueError(f"配筋図の名前が不正です: {'・'.join(sorted(unknown))}")
    m = _Manuscript()
    refs = references(result.cantilever_appearance, result.footing_parts)
    m.heading("heading", "§4. 照査の前提", 0)
    m.heading("layout.heading", "4.1 配筋要領", 1)
    for index, (name, title) in enumerate(zip(FIGURES, ("梁", "柱", "フーチング", "杭"))):
        if name == "pile" and result.pile is None and result.steel_pile is None:
            continue
        m.heading(f"layout.{name}.heading", f"({index + 1}) {title}", 2)
        if name in figures:
            m.figure(f"layout.{name}", figures[name])
        elif name == "column" and result.column.tables is not None:
            _column_tables(m, result.column.tables)
    _column(m, result.column, refs)
    _beam(m, result.beam, refs)
    _footing(m, result.footing, refs)
    if result.pile is not None:
        _pile(m, result.pile)
    if result.steel_pile is not None:
        _steel_pile(m, result.steel_pile)
    return tuple(m.units)


def records(result: DetailingResult) -> list[dict[str, str]]:
    return [{"id": unit.key, "text": plain(unit.value)} for unit in content(result)]


_GROUPS = {"heading": "heading", "paragraph": "text", "line": "formula", "equation": "formula", "bounds": "formula",
           "definitions": "definitions", "items": "items", "table": "table", "figure": "figure"}


def _equations(run: Sequence[Unit], anchors: tuple[int, ...]) -> Any:
    left, first, second, right, unit = anchors
    result = run[0].value.equation.result is not None
    return equation_group(*(replace(piece.value.equation, label=piece.value.label, block_id=piece.key)
                            for piece in run), left=left, first_equal=first,
                          second_equal=second if result else None, result_right=right if result else None,
                          unit_start=unit if result else None, block_id=run[0].key,
                          label_columns=first - left - 1 if anchors == BOUND_LIST else None,
                          keep=(True,) * len(run))  # the formulas of a group stay on one page


def _titles(piece: Unit, following: Sequence[Unit]) -> bool:
    """A kept paragraph directly before a table is its title."""
    return bool(following) and following[0].kind == "table"


def _starts(piece: Unit) -> bool:
    """A heading or a lead (① 一般部, ディープビームの構造細目, …) begins a group that is laid out on one page: the page
    breaks only before one, so a formula stays with its text, its "ここに、" list and its judgement."""
    return piece.kind == "heading" or piece.key.endswith(".lead")


def _blocks(units: Sequence[Unit]) -> list:
    """One blank line around each heading, table and figure and between two groups of another kind (text, formulas,
    a "ここに、" list); a kept unit stays with the next without one, and a table's title with its table. Every unit
    stays on the page of the next unless that one begins a group (_starts)."""
    found: list = []
    index = 0
    previous: Unit | None = None
    while index < len(units):
        piece = units[index]
        index += 1
        group = _GROUPS[piece.kind]
        lead_in = piece.kind == "paragraph" and piece.keep and not _titles(piece, units[index:index + 1])
        if previous is not None and not previous.keep and (lead_in or group != _GROUPS[previous.kind] or group in (
                "heading", "table", "figure", "definitions", "items")):
            blank(found)
        if piece.key in NEW_PAGES and previous is not None and previous.kind != "heading":
            if found and is_blank(found[-1]):
                found.pop()
            found.append(PageBreak())
        if piece.kind == "heading":
            text, tag = piece.value if isinstance(piece.value, tuple) else (piece.value, None)
            column = next((value for suffix, value in TAG_COLUMNS.items() if piece.key.endswith(suffix)), None)
            found.append(heading(text, left=piece.left, tag=tag, block_id=piece.key,
                                 **({} if column is None else {"tag_column": column})))
            found.append(KeepWithNext(spacer()))
            previous = piece
            continue
        if piece.kind == "paragraph":
            block: Any = paragraph(piece.value, left=piece.left, block_id=piece.key)
        elif piece.kind == "line":
            block = math_line(piece.value, left=piece.left, block_id=piece.key)
        elif piece.kind in ("equation", "bounds"):
            run = [piece]
            shape = piece.value.equation.result is not None
            while (index < len(units) and units[index].kind == piece.kind
                   and (units[index].value.equation.result is not None) == shape):
                run.append(units[index])
                index += 1
            block = _equations(run, SYMBOL if piece.kind == "equation" else BOUND_LIST)
            piece = run[-1]
        elif piece.kind in ("definitions", "items"):
            items: Definitions = piece.value
            block = definitions(*items.items, left=BODY if piece.kind == "definitions" else INDENT,
                                colon=items.colon, label="ここに、" if piece.kind == "definitions" else "",
                                block_id=piece.key)
        elif piece.kind == "table":
            block = PreferKeepTogether(table_block(piece.value, piece.key))
        else:  # a figure
            block = indent_to(piece.value.block, piece.left)
        joined = piece.keep or (index < len(units) and not _starts(units[index]))
        found.append(KeepWithNext(block) if joined else block)
        previous = piece
    return found


def build_detailing(result: DetailingResult, figures: Mapping[str, FigureSpec] | None = None) -> Document:
    units = content(result, figures)
    if len({unit.key for unit in units}) != len(units):
        raise ValueError("帳票の単位に重複したキーがあります")
    return report(*_blocks(units))


def render_detailing(result: DetailingResult, path: str | Path,
                     figures: Mapping[str, FigureSpec] | None = None) -> Path:
    """Lay out completely, then atomically replace *path*; the same result gives the same bytes."""
    return build_detailing(result, figures).render(path, invariant=True)


def grid_documents(result: DetailingResult, figures: Mapping[str, FigureSpec] | None = None) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out (its grid Excel workbook): the whole report."""
    return (build_detailing(result, figures),)

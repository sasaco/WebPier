"""0500 直接基礎: the ground-spring report, authored as native GridLayoutPdf blocks.

Every number is a Printed value of the FoundationResult, of the EmbedmentResult
(Df and γ2, decision 40: printed where the procedure applies, None elsewhere) or
of the input it echoes, written at its digits by reporting.numbers. Nothing is calculated
here; the wording, the layout and the unit notation are this module's.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from gridlayoutpdf import (
    Block, Cell, CellLines, Document, Equation, FontRegistry, KeepWithNext, Literal, MathNode, Root, Row, Script,
    TermStop, as_math,
)

from ...calc.embedment import EmbedmentResult, surface_layer_thickness
from ...calc.foundation import SOIL_EQUATIONS, FoundationResult
from ...core.printed import LENGTH, Printed
from ...inputs import PierInput
from ..document import heading, indent_to, is_blank, math_line, paragraph, report, spacer
from ..equations import Definition, definitions, equation_group, script, terms
from ..numbers import constant, printed, unit
from ..styles import BODY, HEADING, PITCH_Y
from ..tables import CELL_PADDING, table
from .frame_report import BODY_LEFT, LEVELS

PREFIX = "0500/"
_REFERENCE = "【基礎標準 13.2.2.2】"
# The three equations of 基礎標準 13.2.2.2 as printed in Example2 04 p.4-1; 砂礫 uses the first.
_GENERAL_EQUATIONS = (("sand", "砂質土", "（砂質土）"),
                      ("alternating", "砂質土と粘性土の互層", "（砂質土，粘性土の互層）"),
                      ("clay", "粘性土", "（粘性土）"))
_TERMS = (("long_term", "長期"), ("short_term", "短期"))

# Body columns of the common grid, as the other reports: §5 from column 0, 5.1 from 1, (1) from 2, 1) from 3 and the
# body (paragraphs, "・長期" labels, equations) from 4.
CHAPTER, SECTION, ITEM, SUBITEM = LEVELS
# Equation anchors (first "=", result "=", result end, unit start; body columns, relations centred on the boundary
# before them). Every term takes whole grid columns of its own (term_columns="grid") from the column after the "=".
# A substitution's "=" stands before column 6, so that the longest one (kv, 13 columns) ends before its result's "="
# before column 21; the result ends at column 26 (Kr's 172,641,294 takes four columns) and the unit takes the three
# columns from 27 (kN・m/rad) to the body's right edge. A symbolic equation has its "=" in the same column (the
# reference's one column further left leaves a subscripted symbol such as γ2 too little room on the grid). A worded
# left side (表層の層厚) takes four columns before its "=".
_SUBSTITUTION = (6, 21, 26, 27)
_SYMBOLIC = (6, None, None, None)
_WORDED = (8, 22, 26, 27)
# A "ここに、" list: "ここに、" and the symbol from column 5, the "：" on the boundary before column 9 and the text from
# column 10; a value's "(=" before column 19, the value ending at column 23 and its unit from column 24.
_DEFINITIONS = {"left": 5, "colon": 9, "value_equal": 19, "value_right": 23, "unit_start": 24}
# The soil table spans the body's 30 columns: 層番, 層厚, 土質区分, Ｎ値, 湿潤, 水中, 内部摩擦角, 一軸圧縮強度, 変形係数.
# Each column holds its 10 pt header (一軸圧縮強度 takes five) and its widest value; a long name wraps.
_SOIL_LEFT = 0
_SOIL_WIDTHS = (3, 3, 3, 2, 3, 3, 4, 5, 4)


def sub(base: str | MathNode, suffix: str) -> Script:
    return script(base, subscript=suffix)


def power(base: str | MathNode, exponent: str) -> Script:
    return script(base, superscript=exponent)


def ratio(text: str) -> MathNode:
    """A rational constant such as "1/3", written inline as the reference prints it."""
    return Literal(text)


def plain(value: Any) -> str:
    """The text of an authored node, in reading order (the semantic record)."""
    if isinstance(value, str):
        return value
    if isinstance(value, TermStop):
        return ""
    if isinstance(value, Literal):
        return value.text
    if isinstance(value, Row):
        return "".join(plain(item) for item in value.items)
    if isinstance(value, Script):
        return (plain(value.base) + (plain(value.subscript) if value.subscript else "")
                + (plain(value.superscript) if value.superscript else ""))
    if isinstance(value, Root):
        return "√" + plain(value.body)
    if isinstance(value, Equation):
        text = plain(value.lhs) + value.relation + plain(value.rhs)
        if value.result is not None:
            text += value.result_relation + plain(value.result)
        return text + (plain(value.unit) if value.unit is not None else "")
    if isinstance(value, Definition):
        text = plain(value.symbol) + "：" + plain(value.text)
        if value.value is not None:
            text += "(=" + plain(value.value) + (plain(value.unit) if value.unit is not None else "") + ")"
        return text
    if isinstance(value, (tuple, list)):
        return "".join(plain(item) for item in value)
    raise TypeError(f"Unsupported foundation semantic node: {type(value).__name__}")


@dataclass(frozen=True)
class Unit:
    """One semantic unit of the manuscript: what is printed, how it is placed.

    *space* puts one blank line before the unit, between the reference's groups (the
    symbolic equations, a "ここに、" list, each "・長期"/"・短期" with its equation).
    The equations of one *family* share their term-column widths, so their numbers and
    operators stand in the same columns although a label or a blank line separates them.
    *lead* ("ここに、") opens a definition list.
    """

    key: str
    value: Any
    kind: str = "math"
    left: int = BODY_LEFT
    first_equal: int = _SUBSTITUTION[0]
    second_equal: int | None = None
    result_right: int | None = None
    unit_start: int | None = None
    space: bool = False
    family: str | None = None
    lead: str = ""

    @property
    def identifier(self) -> str:
        return PREFIX + self.key


def _optional(value: Printed | None, *, thousands: bool = False) -> str:
    return "" if value is None else printed(value, thousands=thousands)


def _with_unit(text: str, unit_base: str, unit_power: int) -> Row:
    """A definition's text with its unit in parentheses, e.g. "… (kN/m³)"."""
    return Row(text + " (", power(unit_base, str(unit_power)), ")", gap=0)


def content(result: FoundationResult, pier: PierInput, embedment: EmbedmentResult | None) -> tuple[Unit, ...]:
    """One ordered manuscript, used by both the layout and the semantic tests."""
    units: list[Unit] = []

    def add(key: str, value: Any, kind: str = "math", left: int = BODY_LEFT, **anchors: Any) -> None:
        units.append(Unit(key, value, kind, left, **anchors))

    def title(key: str, text: str, left: int, reference: bool = False) -> None:
        add(key, (text, _REFERENCE) if reference else text, "heading", left)

    def equation(key: str, lhs: MathNode, rhs: MathNode | str, value: str | None = None,
                 unit_text: MathNode | str | None = None, *, symbolic: bool = False, worded: bool = False,
                 family: str | None = None) -> None:
        first, second, right, start = _SYMBOLIC if symbolic else _WORDED if worded else _SUBSTITUTION
        add(key, Equation(lhs, rhs, result=value, unit=unit_text, block_id=PREFIX + key), "equation",
            first_equal=first, second_equal=second if value is not None else None,
            result_right=right if value is not None else None, unit_start=start if value is not None else None,
            family=family)

    def definition(key: str, symbol: str | MathNode, text: str | MathNode, *, first: bool = False,
                   value: str | None = None, unit_text: str | MathNode | None = None) -> None:
        add(key, Definition(symbol, text, value, unit_text), "definition", _DEFINITIONS["left"],
            space=first, lead="ここに、" if first else "")

    title("title", "§5. 地盤のモデル化", CHAPTER)
    title("soil.heading", "5.1 地盤の諸数値の設計用値のまとめ", SECTION)
    add("soil.introduction", "本橋脚の設計に用いる地盤の諸数値の設計用値を表 2.4.8 に示す.", "paragraph", BODY_LEFT)
    add("soil.caption", "地盤の諸数値の設計用値のまとめ", "caption", _SOIL_LEFT)
    add("soil.header", ("層番", ("層厚", "(m)"), "土質区分", "Ｎ値",
                        ("単位体積重量", "湿潤", "水中"),
                        ("内部摩擦角", "φd(°)"),
                        ("一軸圧縮強度", Row("qu(kN/m", power("", "2"), ")", gap=0)),
                        ("変形係数", Row("Ed(kN/m", power("", "2"), ")", gap=0))), "soil_header", _SOIL_LEFT)
    surface = surface_layer_thickness(pier, result.surface_thickness)
    for index, layer in enumerate(pier.soil.layers):
        # A blank 表層の層厚 is derived: the rest of Df below the layers above 支持層 (decision 64).
        thickness = surface if index == 0 else layer.thickness
        add(f"soil.row.{index}", (layer.name, _optional(thickness), layer.soil_type, _optional(layer.n_value),
                                  _optional(layer.unit_weight_wet), _optional(layer.unit_weight_submerged),
                                  _optional(layer.friction_angle), _optional(layer.compressive_strength),
                                  _optional(layer.deformation_modulus, thousands=True)), "soil_row", _SOIL_LEFT)
    sub_ = pier.substructure
    # The names of the input sheet (H6, H5, df1, df2) are not defined in the report: values only. With 表層
    # alone above the footing base its thickness is Df; otherwise the line is Df itself (decision 64).
    alone = pier.soil.surface.thickness is None and surface == result.surface_thickness
    equation("soil.surface", Literal("表層の層厚") if alone else sub("D", "f"),
             terms(printed(sub_.h[6]), "+", printed(sub_.h[5]), "+",
                   Row("min(", printed(sub_.df1), ", ", printed(sub_.df2), ")", gap=0)),
             printed(result.surface_thickness), unit(result.surface_thickness.unit), worded=alone)
    if embedment is not None:
        _embedment(embedment, add, equation, definition)
    add("bearing.heading", "支持層の支持力係数", "paragraph", BODY_LEFT, space=True)
    # Reference p1: Nγ = value, Nq = value and the case; the two lines are one group, so their terms share columns.
    for key, label in (("normal", "地震時を除く"), ("seismic", "地震時")):
        equation("bearing." + key, sub("N", "γ"),
                 Row(TermStop("right"), printed(result.n_gamma), TermStop("left"), ",",
                     TermStop("right"), sub("N", "q"), TermStop("center"), "=",
                     TermStop("right"), printed(result.n_q), TermStop("left"), label, gap=0),
                 symbolic=True)
    title("spring.heading", "5.2 地盤反力係数の算定", SECTION)
    title("vertical.heading", "(1) フーチング底面の鉛直地盤ばね定数", ITEM)
    title("kv.heading", "1) フーチング底面の鉛直地盤反力係数", SUBITEM, True)
    # Reference p1: the coefficient right-aligned, the product of symbols, then the soil.
    for key, soil, label in _GENERAL_EQUATIONS:
        coefficient, _, exponent = SOIL_EQUATIONS[soil]
        equation("kv." + key, sub("k", "v"),
                 Row(TermStop("right"), constant(coefficient), TermStop("left"),
                     Row(sub("ρ", "gk"), sub("E", "d"), power(sub("B", "v"), exponent)),
                     TermStop("left"), label, gap=0),
                 symbolic=True)
    modulus = result.deformation_modulus
    definition("kv.definition.kv", sub("k", "v"), _with_unit("フーチング底面の鉛直地盤反力係数", "kN/m", 3),
               first=True)
    definition("kv.definition.rho", sub("ρ", "gk"), "地盤反力係数に関する地盤修正係数")
    definition("kv.definition.Ed", sub("E", "d"), "地盤の変形係数", value=printed(modulus),
               unit_text=unit(modulus.unit))
    definition("kv.definition.Bv", sub("B", "v"), "フーチング底面の換算幅 (m)")
    definition("kv.definition.Av", sub("A", "v"), _with_unit("フーチング底面積", "m", 2))
    equation("kv.width", sub("B", "v"), terms(Root(sub("A", "v")), "=", Root(printed(result.area))),
             printed(result.width), unit(result.width.unit))
    equation("kv.area", sub("A", "v"), terms(printed(result.b), "×", printed(result.l)),
             printed(result.area), unit(result.area.unit))
    coefficient = printed(result.coefficient)
    # 決定18: the soil type and the coefficient/exponent of the equation used are printed.
    add("kv.soil_type", Row("支持層の土質区分：" + result.soil_type + "（", sub("k", "v"), " = ",
                            Row(coefficient, sub("ρ", "gk"), sub("E", "d"), power(sub("B", "v"), result.exponent_text)),
                            " を用いる）", gap=0),
        space=True)
    for term, label in _TERMS:
        springs = getattr(result, term)
        add("kv." + term + ".label", Row("・" + label + "（", sub("ρ", "gk"), " = ", printed(springs.rho), "）", gap=0),
            space=True)
        equation("kv." + term, sub("k", "v"),
                 terms(coefficient, "×", printed(springs.rho), "×", printed(modulus), "×",
                       power(printed(result.width), result.exponent_text)),
                 printed(springs.kv), unit(springs.kv.unit), family="kv")
    title("Kv.heading", "2) フーチング底面の鉛直地盤ばね定数", SUBITEM, True)
    equation("Kv.formula", sub("K", "v"), Row(sub("k", "v"), sub("A", "v")))
    definition("Kv.definition.Kv", sub("K", "v"), "フーチング底面の鉛直地盤ばね定数 (kN/m)", first=True)
    definition("Kv.definition.kv", sub("k", "v"), _with_unit("フーチング底面の鉛直地盤反力係数", "kN/m", 3))
    definition("Kv.definition.Av", sub("A", "v"), _with_unit("フーチング底面積", "m", 2))

    def springs(prefix: str, factor: str, other: Printed, field: str, suffix: str, family: str) -> None:
        for term, label in _TERMS:
            values = getattr(result, term)
            spring = getattr(values, field)
            add(prefix + "." + term + ".label", "・" + label, "paragraph", space=True)
            equation(prefix + "." + term, sub("K", suffix),
                     terms(printed(getattr(values, factor)), "×", printed(other)),
                     printed(spring, thousands=True), unit(spring.unit), family=family)

    springs("Kv", "kv", result.area, "Kv", "v", "Kv")
    title("shear.heading", "(2) フーチング底面のせん断地盤ばね定数", ITEM)
    title("ks.heading", "1) フーチング底面のせん断地盤反力係数", SUBITEM, True)
    equation("ks.formula", sub("k", "s"), Row("λ", sub("k", "v"), gap=0))
    definition("ks.definition.ks", sub("k", "s"), _with_unit("フーチング底面のせん断地盤反力係数", "kN/m", 3),
               first=True)
    definition("ks.definition.lambda", "λ", Row("換算係数（ = ", ratio(result.shear_ratio_text), " とする）", gap=0))
    for term, label in _TERMS:
        values = getattr(result, term)
        add("ks." + term + ".label", "・" + label, "paragraph", space=True)
        equation("ks." + term, sub("k", "s"), terms(ratio(result.shear_ratio_text), "×", printed(values.kv)),
                 printed(values.ks), unit(values.ks.unit), family="ks")
    title("Ks.heading", "2) フーチング底面のせん断地盤ばね定数", SUBITEM, True)
    equation("Ks.formula", sub("K", "s"), Row(sub("k", "s"), sub("A", "v")))
    definition("Ks.definition.Ks", sub("K", "s"), "フーチング底面のせん断地盤ばね定数 (kN/m)", first=True)
    definition("Ks.definition.ks", sub("k", "s"), _with_unit("フーチング底面のせん断地盤反力係数", "kN/m", 3))
    definition("Ks.definition.Av", sub("A", "v"), _with_unit("フーチング底面積", "m", 2))
    springs("Ks", "ks", result.area, "Ks", "s", "Ks")
    title("rotation.heading", "(3) フーチング底面の回転地盤ばね定数", ITEM, True)
    equation("Kr.formula", sub("K", "r"), Row(sub("k", "v"), sub("I", "v")))
    definition("Kr.definition.Kr", sub("K", "r"), "フーチング底面の回転地盤ばね定数 (kN・m/rad)", first=True)
    definition("Kr.definition.kv", sub("k", "v"), _with_unit("フーチング底面の鉛直地盤反力係数", "kN/m", 3))
    definition("Kr.definition.Iv", sub("I", "v"), _with_unit("フーチング底面の断面二次モーメント", "m", 4))
    for direction, label, first, cubed in (("longitudinal", "1) 線路方向", result.l, result.b),
                                          ("transverse", "2) 線路直角方向", result.b, result.l)):
        prefix = "Kr." + direction
        inertia: Printed = getattr(result, "inertia_" + direction)
        title(prefix + ".heading", label, SUBITEM)
        equation(prefix + ".inertia", sub("I", "v"), terms(printed(first), "×", power(printed(cubed), "3"), "/", "12"),
                 printed(inertia), unit(inertia.unit), family="Iv")
        springs(prefix, "kv", inertia, "Kr_" + direction, "r", "Kr")
    return tuple(units)


def _flush_left(rhs: Row) -> Row:
    """*rhs* with its terms from their columns' left edges instead of right-aligned: a term of symbols with
    subscripts is one rich-text cell in the grid Excel, which Excel draws narrower than the PDF (about 2 pt a
    subscript character); from the left edge it starts where the PDF's does."""
    return Row(*(TermStop("left", width=item.width) if isinstance(item, TermStop) and item.align == "right" else item
                 for item in rhs.items), gap=rhs.gap)


def _embedment(e: EmbedmentResult, add: Any, equation: Any, definition: Any) -> None:
    """γ2 of the cover, the FootInfo value of the JRSNAP direct foundation (Example2 08 p.8-28)."""
    depth, water, gamma2 = sub("D", "f"), sub("h", "w2"), sub("γ", "2")
    wet, submerged = sub("γ", "wet"), sub("γ", "sub")
    single = e.single
    if single is None:
        _embedment_layers(e, add, equation, definition)
        return
    add("embedment.heading", "有効根入れ深さと表層の平均有効単位重量", "paragraph", BODY_LEFT, space=True)
    # The bracket is two terms parted at its "+": a cell of the grid Excel holds few subscripts (see _flush_left).
    equation("embedment.formula", gamma2,
             Row(TermStop("left"), Row("((", depth, " − ", water, ") × ", wet, gap=0), TermStop("center"), "+",
                 TermStop("left"), Row(water, " × ", submerged, ")", gap=0), TermStop("center"), "/",
                 TermStop("left"), depth, gap=0),
             symbolic=True)
    equation("embedment.gamma2", gamma2,
             terms("(", "(", printed(e.depth), "−", printed(e.water), ")", "×", printed(single.unit_weight_wet), "+",
                   printed(e.water), "×", printed(single.unit_weight_submerged), ")", "/", printed(e.depth)),
             printed(e.unit_weight), unit(e.unit_weight.unit))
    definition("embedment.definition.Df", depth, "有効根入れ深さ（表層厚）", first=True,
               value=printed(e.depth), unit_text=unit(e.depth.unit))
    definition("embedment.definition.hw2", water, "基礎底面からの平水位", value=printed(e.water),
               unit_text=unit(e.water.unit))
    for key, symbol, label, value in (("wet", wet, "湿潤", single.unit_weight_wet),
                                      ("sub", submerged, "水中", single.unit_weight_submerged)):
        definition("embedment.definition." + key, symbol, f"{single.name}の{label}単位体積重量", value=printed(value),
                   unit_text=unit(value.unit))


def _embedment_layers(e: EmbedmentResult, add: Any, equation: Any, definition: Any) -> None:
    """γ2 of a cover of several layers (decision 64): each layer's part above and below hw2, from the ground."""
    depth, water, gamma2 = sub("D", "f"), sub("h", "w2"), sub("γ", "2")
    thickness, weight = sub("h", "i"), sub("γ", "i")
    add("embedment.heading", "有効根入れ深さと Df 区間の平均有効単位重量", "paragraph", BODY_LEFT, space=True)
    for layer in e.layers:
        add(f"embedment.layer.{layer.index}",
            f"・{layer.name}：厚さ {printed(layer.thickness)} m（基礎底面から {printed(layer.bottom)}〜"
            f"{printed(LENGTH.total((layer.bottom, layer.thickness)))} m）、γwet {printed(layer.unit_weight_wet)}・"
            f"γsub {printed(layer.unit_weight_submerged)} kN/m3", "paragraph")
    equation("embedment.formula", gamma2, _flush_left(terms("Σ", "(", thickness, "×", weight, ")", "/", depth)),
             symbolic=True)
    parts: list = []
    for segment in e.normal.segments:
        parts += [*(("+",) if parts else ()), printed(segment.thickness), "×", printed(segment.unit_weight)]
    equation("embedment.gamma2", gamma2, terms("(", *parts, ")", "/", printed(e.depth)),
             printed(e.unit_weight), unit(e.unit_weight.unit))
    definition("embedment.definition.Df", depth, "有効根入れ深さ", first=True,
               value=printed(e.depth), unit_text=unit(e.depth.unit))
    definition("embedment.definition.hw2", water, "基礎底面からの平水位", value=printed(e.water),
               unit_text=unit(e.water.unit))
    definition("embedment.definition.hi", thickness, "各層の平水位より上・下の部分の厚さ (m)")
    definition("embedment.definition.gi", weight, "その部分の単位体積重量（平水位より上は湿潤、下は水中）")


def semantic_records(result: FoundationResult, pier: PierInput,
                     embedment: EmbedmentResult | None) -> list[dict[str, str]]:
    return [{"id": item.identifier, "text": item.lead + plain(item.value)}
            for item in content(result, pier, embedment)]


def _soil_cell(value: Any, *, rowspan: int = 1, colspan: int = 1, align: str = "center",
               wrap: bool = False) -> Cell:
    """A soil-table cell at 10 pt, one grid row a line: a header's lines ("層厚" over "(m)") one under the other."""
    lines = value if isinstance(value, tuple) else (value,)
    return Cell(CellLines(lines, style=HEADING, line_advance=PITCH_Y, inner_padding=CELL_PADDING, align=align,
                          wrap=wrap),
                rowspan=rowspan, colspan=colspan, align=align, padding=0)


def _soil_table(header: Unit, rows: list[Unit]) -> Block:
    values = header.value
    merged = [_soil_cell(value, rowspan=2) for value in values]
    authored: list[list[Cell]] = [[*merged[:4], _soil_cell(values[4][0], colspan=2), *merged[5:]],
                                  [_soil_cell(value) for value in values[4][1:]]]
    # The names (層番, 土質区分) wrap in their columns, never shrink: a wrapped row takes a grid row a line.
    authored.extend([_soil_cell(value, wrap=True) if column in (0, 2) else _soil_cell(value, align="right")
                     for column, value in enumerate(row.value)] for row in rows)
    return indent_to(table(_SOIL_WIDTHS, authored, row_heights=None, header_rows=2, block_id=PREFIX + "soil.table"),
                     _SOIL_LEFT)


def _shared_columns(units: tuple[Unit, ...], fonts: FontRegistry) -> dict[str, Unit]:
    """The equations of each family with every term as wide as the family's widest term in that place.

    A family's equations stand in groups of their own (a "・長期" label, a blank line or a heading parts them).
    A TermStop's width is a minimum, so the grid gives each place the same whole columns in every equation of
    the family, whatever its own digits. The widths are the font-measured terms, never a resized text.
    """
    def columns(rhs: Row) -> list[tuple[int, list[Any]]]:
        found: list[tuple[int, list[Any]]] = []
        for index, item in enumerate(rhs.items):
            if isinstance(item, TermStop):
                found.append((index, []))
            else:
                found[-1][1].append(item)
        return found

    widths: dict[tuple[str, int], float] = {}
    for item in units:
        if item.family is None:
            continue
        for column, (_, atoms) in enumerate(columns(item.value.rhs)):
            measured = sum(as_math(atom).measure(fonts, BODY).width for atom in atoms)
            key = (item.family, column)
            widths[key] = max(widths.get(key, 0.0), measured)
    shared = {}
    for item in units:
        if item.family is None:
            continue
        rhs: Row = item.value.rhs
        items = list(rhs.items)
        for column, (index, _) in enumerate(columns(rhs)):
            items[index] = TermStop(items[index].align, width=widths[(item.family, column)])
        shared[item.key] = replace(item, value=replace(item.value, rhs=Row(*items, gap=rhs.gap)))
    return shared


def _kept(item: Unit) -> bool:
    """A label stays with its equation; a direction's Kr subsection is kept on one page."""
    direction_continues = (item.key.startswith(("Kr.longitudinal.", "Kr.transverse."))
                           and not item.key.endswith("short_term"))
    return item.key.endswith(".label") or direction_continues


def _joins(item: Unit, following: Unit) -> bool:
    """*following* continues the equations of *item*: on the same columns, with no blank line between."""
    def columns(unit: Unit) -> tuple[Any, ...]:
        return unit.left, unit.first_equal, unit.second_equal, unit.result_right, unit.unit_start
    return (item.kind == following.kind == "equation" and not following.space
            and columns(item) == columns(following))


def build_foundation(result: FoundationResult, pier: PierInput, embedment: EmbedmentResult | None) -> Document:
    """The 0500 report as a GridLayoutPdf Document (lay out or render it)."""
    fonts = FontRegistry()
    units = content(result, pier, embedment)
    shared = _shared_columns(units, fonts)
    blocks: list[Block] = []

    def blank() -> None:
        """One blank line, never two; it stays with what it follows when that is kept with its next."""
        if blocks and not is_blank(blocks[-1]):
            blocks.append(KeepWithNext(spacer()) if isinstance(blocks[-1], KeepWithNext) else spacer())

    for index, item in enumerate(units):
        if item.kind == "soil_row" or (item.kind == "definition" and not item.lead
                                       and units[index - 1].kind == "definition"):
            continue
        if index and _joins(units[index - 1], item):
            continue
        item = shared.get(item.key, item)
        if item.space or item.kind in ("soil_header", "caption", "heading"):
            # Blank lines around the table; its caption stays directly above it (as the reference).
            if not (item.kind == "soil_header" and units[index - 1].kind == "caption"):
                blank()
        if item.kind == "soil_header":
            blocks.append(_soil_table(item, [row for row in units[index + 1:] if row.kind == "soil_row"]))
            blocks.append(spacer())
        elif item.kind == "heading":
            text, tag = item.value if isinstance(item.value, tuple) else (item.value, None)
            blocks.append(heading(text, left=item.left, tag=tag, block_id=item.identifier))
            blocks.append(KeepWithNext(spacer()))
        elif item.kind == "caption":
            blocks.append(paragraph(item.value, left=item.left, style=HEADING, align="center", block_id=item.identifier))
        elif item.kind == "paragraph":
            blocks.append(paragraph(item.value, left=item.left, block_id=item.identifier))
        elif item.kind == "equation":
            # Consecutive equations on the same columns are one group: their terms line up across lines.
            run = [item]
            for following in units[index + 1:]:
                if not _joins(run[-1], following):
                    break
                run.append(shared.get(following.key, following))
            blocks.append(equation_group(*(equation.value for equation in run), left=item.left,
                                         first_equal=item.first_equal, second_equal=item.second_equal,
                                         result_right=item.result_right, unit_start=item.unit_start,
                                         block_id=item.identifier, keep=tuple(_kept(equation) for equation in run)))
            item = run[-1]
        elif item.kind == "definition":
            # A "ここに、" list and the lines that follow it without a lead are one block.
            run = [item.value]
            for following in units[index + 1:]:
                if following.kind != "definition" or following.lead:
                    break
                run.append(following.value)
            blocks.append(definitions(*run, label=item.lead, block_id=item.identifier, **_DEFINITIONS))
        else:
            blocks.append(math_line(item.value, left=item.left, block_id=item.identifier))
        if _kept(item):
            blocks[-1] = KeepWithNext(blocks[-1])
    return report(*blocks)


def render_foundation(result: FoundationResult, pier: PierInput, embedment: EmbedmentResult | None,
                      path: str | Path) -> Path:
    """Lay out completely, then atomically replace *path*; the same input gives the same bytes.

    *embedment* is calc.embedment.applicable_embedment(pier, result): γ2 is printed when it is not None.
    """
    return build_foundation(result, pier, embedment).render(path, invariant=True)


def grid_documents(result: FoundationResult, pier: PierInput, embedment: EmbedmentResult | None) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out (its grid Excel workbook): the whole report."""
    return (build_foundation(result, pier, embedment),)

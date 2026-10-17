"""0500 直接基礎: the ground-spring report, authored as native GridLayoutPdf blocks.

Every number is a Printed value of the FoundationResult (or of the input it
echoes), written at its digits by reporting.numbers. Nothing is calculated
here; the wording, the layout and the unit notation are this module's.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from gridlayoutpdf import (
    Block, Cell, CellLines, Document, Equation, Fraction, Insets, KeepWithNext, Literal,
    MathNode, Operator, Root, Row, Script,
)

from ...calc.foundation import SOIL_EQUATIONS, FoundationResult
from ...core.printed import Printed
from ...inputs import PierInput
from ..document import heading, indent_to, paragraph, report, spacer
from ..equations import equation_group, script
from ..numbers import constant, printed, unit
from ..styles import BODY, HEADING
from ..tables import REACTION_CELL_PADDING, table

PREFIX = "0500/"
FOOTER = "5 - {page}"
_REFERENCE = "【基礎標準 13.2.2.2】"
# The three equations of 基礎標準 13.2.2.2 as printed in Example2 04 p.4-1; 砂礫 uses the first.
_GENERAL_EQUATIONS = (("sand", "砂質土", "（砂質土）"),
                      ("alternating", "砂質土と粘性土の互層", "（砂質土，粘性土の互層）"),
                      ("clay", "粘性土", "（粘性土）"))
_TERMS = (("long_term", "長期"), ("short_term", "短期"))


def sub(base: str | MathNode, suffix: str) -> Script:
    return script(base, subscript=suffix)


def power(base: str | MathNode, exponent: str) -> Script:
    return script(base, superscript=exponent)


def ratio(text: str) -> MathNode:
    """A rational constant written as "1/3" becomes a stacked fraction."""
    numerator, _, denominator = text.partition("/")
    return Fraction(numerator, denominator) if denominator else Literal(numerator)


def plain(value: Any) -> str:
    """The text of an authored node, in reading order (the semantic record)."""
    if isinstance(value, str):
        return value
    if isinstance(value, Literal):
        return value.text
    if isinstance(value, Row):
        return "".join(plain(item) for item in value.items)
    if isinstance(value, Script):
        return (plain(value.base) + (plain(value.subscript) if value.subscript else "")
                + (plain(value.superscript) if value.superscript else ""))
    if isinstance(value, Fraction):
        return plain(value.numerator) + "/" + plain(value.denominator)
    if isinstance(value, Root):
        return "√" + plain(value.body)
    if isinstance(value, Equation):
        text = plain(value.lhs) + value.relation + plain(value.rhs)
        if value.result is not None:
            text += value.result_relation + plain(value.result)
        return text + (plain(value.unit) if value.unit is not None else "")
    if isinstance(value, (tuple, list)):
        return "".join(plain(item) for item in value)
    raise TypeError(f"Unsupported foundation semantic node: {type(value).__name__}")


@dataclass(frozen=True)
class Unit:
    """One semantic unit of the manuscript: what is printed, how it is placed."""

    key: str
    value: Any
    kind: str = "math"
    left: float = 157.8
    first_equal: float = 184.44
    second_equal: float | None = None
    result_right: float | None = None
    unit_start: float | None = None

    @property
    def identifier(self) -> str:
        return PREFIX + self.key


def _optional(value: Printed | None, *, thousands: bool = False) -> str:
    return "" if value is None else printed(value, thousands=thousands)


def content(result: FoundationResult, pier: PierInput) -> tuple[Unit, ...]:
    """One ordered manuscript, used by both the layout and the semantic tests."""
    units: list[Unit] = []

    def add(key: str, value: Any, kind: str = "math", left: float = 157.8, **anchors: Any) -> None:
        units.append(Unit(key, value, kind, left, **anchors))

    def title(key: str, text: str, left: float, reference: bool = False) -> None:
        add(key, (text, _REFERENCE) if reference else text, "heading", left)

    def equation(key: str, lhs: MathNode, rhs: MathNode | str, value: str | None = None,
                 unit_text: MathNode | str | None = None, *, symbolic: bool = False, left: float | None = None) -> None:
        add(key, Equation(lhs, rhs, result=value, unit=unit_text, block_id=PREFIX + key), "equation",
            left if left is not None else 143.28 if symbolic else 152.04,
            first_equal=169.92 if symbolic else 184.44,
            second_equal=460.32 if value is not None else None,
            result_right=525.96 if value is not None else None,
            unit_start=530.4 if value is not None else None)

    def definition(key: str, base: str, suffix: str, text: str, *, first: bool = False,
                   unit_power: int | None = None, unit_base: str = "kN/m") -> None:
        parts: list[str | MathNode] = ["ここに、" if first else "", sub(base, suffix), "：" + text]
        if unit_power is not None:
            parts.extend(("(", power(unit_base, str(unit_power)), ")"))
        add(key, Row(*parts, gap=0))

    title("title", "§5. 地盤のモデル化", 93.96)
    title("soil.heading", "5.1 地盤の諸数値の設計用値のまとめ", 108.48)
    add("soil.introduction", "本橋脚の設計に用いる地盤の諸数値の設計用値を表 2.4.8 に示す.", "paragraph", 123)
    add("soil.caption", "地盤の諸数値の設計用値のまとめ", "caption", 76.92)
    add("soil.header", ("層番", ("層厚", "(m)"), "土質区分", "Ｎ値",
                        ("単位体積重量", "湿潤", "水中"),
                        ("内部摩擦角", "φd(°)"),
                        ("一軸圧縮強度", Row("qu(kN/m", power("", "2"), ")", gap=0)),
                        ("変形係数", Row("Ed(kN/m", power("", "2"), ")", gap=0))), "soil_header", 76.92)
    for index, layer in enumerate(pier.soil.layers):
        # 表層の層厚 is not entered: it is the derived embedment of the footing base.
        thickness = result.surface_thickness if index == 0 else layer.thickness
        add(f"soil.row.{index}", (layer.name, _optional(thickness), layer.soil_type, _optional(layer.n_value),
                                  _optional(layer.unit_weight_wet), _optional(layer.unit_weight_submerged),
                                  _optional(layer.friction_angle), _optional(layer.compressive_strength),
                                  _optional(layer.deformation_modulus, thousands=True)), "soil_row", 76.92)
    sub_ = pier.substructure
    equation("soil.surface", Literal("表層の層厚"),
             f"H6+H5+min(df1, df2) = {printed(sub_.h[6])}+{printed(sub_.h[5])}"
             f"+min({printed(sub_.df1)}, {printed(sub_.df2)})",
             printed(result.surface_thickness), unit(result.surface_thickness.unit), left=123)
    add("bearing.heading", "支持層の支持力係数", "paragraph", 123)
    for key, label in (("normal", "地震時を除く"), ("seismic", "地震時")):
        add("bearing." + key, Row(sub("N", "γ"), "=", printed(result.n_gamma), ",",
                                   sub("N", "q"), "=", printed(result.n_q), label), left=143.28)
    title("spring.heading", "5.2 地盤反力係数の算定", 108.48)
    title("vertical.heading", "(1) フーチング底面の鉛直地盤ばね定数", 123)
    title("kv.heading", "1) フーチング底面の鉛直地盤反力係数", 137.52, True)
    for key, soil, label in _GENERAL_EQUATIONS:
        coefficient, _, exponent = SOIL_EQUATIONS[soil]
        equation("kv." + key, sub("k", "v"), Row(constant(coefficient), sub("ρ", "gk"), sub("E", "d"),
                                                   power(sub("B", "v"), exponent), label), symbolic=True)
    definition("kv.definition.kv", "k", "v", "フーチング底面の鉛直地盤反力係数 ", first=True, unit_power=3)
    definition("kv.definition.rho", "ρ", "gk", "地盤反力係数に関する地盤修正係数")
    modulus = result.deformation_modulus
    add("kv.definition.Ed", Row(sub("E", "d"), "：地盤の変形係数(=", printed(modulus), unit(modulus.unit), ")", gap=0))
    definition("kv.definition.Bv", "B", "v", "フーチング底面の換算幅 (m)")
    equation("kv.width", sub("B", "v"), Row(Root(sub("A", "v")), "(=", Root(printed(result.area))),
             printed(result.width), Row(unit(result.width.unit), ")", gap=0))
    add("kv.area", Row(sub("A", "v"), "：フーチング底面積(=", printed(result.b), Operator("×"), printed(result.l),
                       "=", printed(result.area), unit(result.area.unit), ")", gap=0))
    coefficient = printed(result.coefficient)
    # 決定18: the soil type and the coefficient/exponent of the equation used are printed.
    add("kv.soil_type", Row("支持層の土質区分：" + result.soil_type + "（", sub("k", "v"), "=", coefficient,
                            sub("ρ", "gk"), sub("E", "d"), power(sub("B", "v"), result.exponent_text), "を用いる）"),
        left=152.04)
    for term, label in _TERMS:
        springs = getattr(result, term)
        add("kv." + term + ".label", Row("・" + label + " ( ", sub("ρ", "gk"), "=", printed(springs.rho), ")", gap=0),
            left=152.04)
        equation("kv." + term, sub("k", "v"),
                 Row(coefficient, Operator("×"), printed(springs.rho), Operator("×"), printed(modulus),
                     Operator("×"), power(printed(result.width), result.exponent_text)),
                 printed(springs.kv), unit(springs.kv.unit))
    title("Kv.heading", "2) フーチング底面の鉛直地盤ばね定数", 137.52, True)
    equation("Kv.formula", sub("K", "v"), Row(sub("k", "v"), sub("A", "v")))
    definition("Kv.definition.Kv", "K", "v", "フーチング底面の鉛直地盤ばね定数 (kN/m)", first=True)
    definition("Kv.definition.kv", "k", "v", "フーチング底面の鉛直地盤反力係数 ", unit_power=3)
    definition("Kv.definition.Av", "A", "v", "フーチング底面積 ", unit_power=2, unit_base="m")

    def springs(prefix: str, factor: str, other: Printed, field: str, suffix: str) -> None:
        for term, label in _TERMS:
            values = getattr(result, term)
            spring = getattr(values, field)
            add(prefix + "." + term + ".label", "・" + label, "paragraph", 152.04)
            equation(prefix + "." + term, sub("K", suffix),
                     Row(printed(getattr(values, factor)), Operator("×"), printed(other)),
                     printed(spring, thousands=True), unit(spring.unit))

    springs("Kv", "kv", result.area, "Kv", "v")
    title("shear.heading", "(2) フーチング底面のせん断地盤ばね定数", 123)
    title("ks.heading", "1) フーチング底面のせん断地盤反力係数", 137.52, True)
    equation("ks.formula", sub("k", "s"), Row("λ", sub("k", "v"), gap=0))
    definition("ks.definition.ks", "k", "s", "フーチング底面のせん断地盤反力係数 ", first=True, unit_power=3)
    add("ks.definition.lambda", Row("λ：換算係数（ =", ratio(result.shear_ratio_text), "とする）"))
    for term, label in _TERMS:
        values = getattr(result, term)
        add("ks." + term + ".label", "・" + label, "paragraph", 152.04)
        equation("ks." + term, sub("k", "s"), Row(ratio(result.shear_ratio_text), Operator("×"), printed(values.kv)),
                 printed(values.ks), unit(values.ks.unit))
    title("Ks.heading", "2) フーチング底面のせん断地盤ばね定数", 137.52, True)
    equation("Ks.formula", sub("K", "s"), Row(sub("k", "s"), sub("A", "v")))
    definition("Ks.definition.Ks", "K", "s", "フーチング底面のせん断地盤ばね定数 (kN/m)", first=True)
    definition("Ks.definition.ks", "k", "s", "フーチング底面のせん断地盤反力係数 ", unit_power=3)
    definition("Ks.definition.Av", "A", "v", "フーチング底面積 ", unit_power=2, unit_base="m")
    springs("Ks", "ks", result.area, "Ks", "s")
    title("rotation.heading", "(3) フーチング底面の回転地盤ばね定数", 123, True)
    equation("Kr.formula", sub("K", "r"), Row(sub("k", "v"), sub("I", "v")))
    definition("Kr.definition.Kr", "K", "r", "フーチング底面の回転地盤ばね定数 (kN・m/rad)", first=True)
    definition("Kr.definition.kv", "k", "v", "フーチング底面の鉛直地盤反力係数", unit_power=3)
    definition("Kr.definition.Iv", "I", "v", "フーチング底面の断面二次モーメント", unit_power=4, unit_base="m")
    for direction, label, first, cubed in (("longitudinal", "1) 線路方向", result.l, result.b),
                                          ("transverse", "2) 線路直角方向", result.b, result.l)):
        prefix = "Kr." + direction
        inertia: Printed = getattr(result, "inertia_" + direction)
        title(prefix + ".heading", label, 137.52)
        equation(prefix + ".inertia", sub("I", "v"),
                 Fraction(Row(printed(first), Operator("×"), power(printed(cubed), "3")), "12"),
                 printed(inertia), unit(inertia.unit))
        springs(prefix, "kv", inertia, "Kr_" + direction, "r")
    return tuple(units)


def semantic_records(result: FoundationResult, pier: PierInput) -> list[dict[str, str]]:
    return [{"id": item.identifier, "text": plain(item.value)} for item in content(result, pier)]


def _soil_name(text: str) -> CellLines:
    """Native font-measured wrapping, preserving the standard one-line row height."""
    return CellLines((text,), style=HEADING, line_advance=14.28, min_height=14.28,
                     inner_padding=Insets(1.08, 1.08, 1.08, 1.08), align="center", wrap=True)


def _soil_table(header: Unit, rows: list[Unit]) -> Block:
    values = header.value

    def merged(value: Any, *, compressive: bool = False) -> Cell:
        lines = value if isinstance(value, tuple) else (value,)
        # The reference p1 caption 一軸圧縮強度 is measured at 8.9 pt; its unit stays 9.9.
        # This is that one measured role, not automatic shrinking to fit a column.
        line_styles = (replace(HEADING, size=8.9), HEADING) if compressive else None
        return Cell(CellLines(lines, style=HEADING, line_styles=line_styles, line_advance=12.0, min_height=28.56,
                              inner_padding=Insets(1.08, 1.08, 1.08, 1.08), align="center"),
                    rowspan=2, align="center", padding=0)

    def standard(value: str, *, colspan: int = 1, align: str = "center") -> Cell:
        # Values end at the clearance measured in the reference soil table (0500 p1, as 0600's tables).
        return Cell(CellLines((value,), style=HEADING, min_height=14.28,
                              inner_padding=REACTION_CELL_PADDING, align=align),
                    colspan=colspan, align=align, padding=0)

    authored: list[list[Cell]] = [[merged(values[0]), merged(values[1]), merged(values[2]), merged(values[3]),
                                  standard(values[4][0], colspan=2),
                                  merged(values[5]), merged(values[6], compressive=True), merged(values[7])],
                                 [standard(value) for value in values[4][1:]]]
    authored.extend([Cell(_soil_name(value), align="center", padding=0) if column in (0, 2)
                     else standard(value, align="right")
                     for column, value in enumerate(row.value)] for row in rows)
    widths = (44.4, 58.08, 58.08, 43.56, 58.08, 58.08, 58.08, 58.08, 58.08)
    return indent_to(table(widths, authored, row_heights=None, header_rows=2, block_id=PREFIX + "soil.table"), 76.92)


def build_foundation(result: FoundationResult, pier: PierInput) -> Document:
    """The 0500 report as a GridLayoutPdf Document (lay out or render it)."""
    units = content(result, pier)
    blocks: list[Block] = []
    for index, item in enumerate(units):
        if item.kind == "soil_row":
            continue
        if item.kind == "soil_header":
            blocks.append(_soil_table(item, [row for row in units[index + 1:] if row.kind == "soil_row"]))
            blocks.append(spacer())
        elif item.kind == "heading":
            if blocks:
                blocks.append(spacer())
            text = " ".join(item.value) if isinstance(item.value, tuple) else item.value
            blocks.append(heading(text, left=item.left, block_id=item.identifier))
            blocks.append(KeepWithNext(spacer()))
        elif item.kind == "caption":
            blocks.append(paragraph(item.value, left=item.left, style=HEADING, align="center", block_id=item.identifier))
        elif item.kind == "paragraph":
            blocks.append(paragraph(item.value, left=item.left, block_id=item.identifier))
        elif item.kind == "equation":
            blocks.append(equation_group(item.value, left=item.left, first_equal=item.first_equal,
                                         second_equal=item.second_equal, result_right=item.result_right,
                                         unit_start=item.unit_start, block_id=item.identifier))
        else:
            blocks.append(indent_to(CellLines((item.value,), style=BODY, min_height=14.28,
                                              block_id=item.identifier), item.left))
        # A label stays with its equation; a direction's Kr subsection is kept on one page.
        direction_continues = (item.key.startswith(("Kr.longitudinal.", "Kr.transverse."))
                               and not item.key.endswith("short_term"))
        if item.key.endswith(".label") or direction_continues:
            blocks[-1] = KeepWithNext(blocks[-1])
    return report(*blocks, footer=FOOTER)


def render_foundation(result: FoundationResult, pier: PierInput, path: str | Path) -> Path:
    """Lay out completely, then atomically replace *path*; the same input gives the same bytes."""
    return build_foundation(result, pier).render(path, invariant=True)

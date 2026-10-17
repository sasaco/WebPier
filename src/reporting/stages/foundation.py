"""0500 foundation report authored as semantic native GridLayoutPdf blocks.

Only formatting happens here. All displayed engineering values come from the
existing result, including its Double values rather than the Single handoff.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction as Rational
from pathlib import Path
from typing import Any

from gridlayoutpdf import (
    Block, Cell, CellLines, Document, Equation, Fraction, Insets, KeepWithNext, Literal,
    MathNode, Operator, Root, Row, Script, render_pdf,
)

from ..document import heading, indent_to, paragraph, report, spacer
from ..equations import equation_group, script
from ..formatting import number
from ..styles import BODY, HEADING
from ..tables import table


def sub(base: str, suffix: str) -> Script:
    return script(base, subscript=suffix)


def power(base: str | MathNode, exponent: str) -> Script:
    return script(base, superscript=exponent)


def fraction(value: float) -> MathNode:
    ratio = Rational(value).limit_denominator(1000)
    return Literal(str(ratio.numerator)) if ratio.denominator == 1 else Fraction(str(ratio.numerator), str(ratio.denominator))


def plain(value: Any) -> str:
    """Serialize the same authored nodes that are passed to the native layout."""
    if isinstance(value, str):
        return value
    if isinstance(value, Literal):
        return value.text
    if isinstance(value, Row):
        return "".join(plain(item) for item in value.items)
    if isinstance(value, Script):
        return plain(value.base) + (plain(value.subscript) if value.subscript else "") + (plain(value.superscript) if value.superscript else "")
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
        return "0500/" + self.key


_SOIL_FIELDS = (
    ("name", None, False), ("thickness", 3, False), ("soil_type", None, False),
    ("n_value", None, False), ("unit_weight_wet", 1, False),
    ("unit_weight_submerged", 1, False), ("friction_angle", None, False),
    ("compressive_strength", None, False), ("deformation_modulus", None, True),
)
_REFERENCE = "【基礎標準 13.2.2.2】"


def content(result: dict[str, Any]) -> tuple[Unit, ...]:
    """One ordered manuscript used by both layout and the semantic audit."""
    foundation, model = result["foundation"], result["model"]
    modulus = result["support_layer"]["deformation_modulus"]
    units: list[Unit] = []

    def add(key: str, value: Any, kind: str = "math", left: float = 157.8, **anchors: Any) -> None:
        units.append(Unit(key, value, kind, left, **anchors))

    def title(key: str, text: str, left: float, reference: bool = False) -> None:
        add(key, (text, _REFERENCE) if reference else text, "heading", left)

    def equation(key: str, lhs: MathNode, rhs: MathNode | str, value: str | None = None,
                 unit: MathNode | str | None = None, *, symbolic: bool = False) -> None:
        add(key, Equation(lhs, rhs, result=value, unit=unit, block_id="0500/" + key), "equation",
            143.28 if symbolic else 152.04, first_equal=169.92 if symbolic else 184.44,
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
    for index, layer in enumerate(result["layers"]):
        values = tuple(str(layer.get(field) or "") if field in ("name", "soil_type")
                       else number(layer.get(field), digits, comma=comma) for field, digits, comma in _SOIL_FIELDS)
        add(f"soil.row.{index}", values, "soil_row", 76.92)
    add("bearing.heading", "支持層の支持力係数", "paragraph", 123)
    for key, label in (("normal", "地震時を除く"), ("seismic", "地震時")):
        add("bearing." + key, Row(sub("N", "γ"), "=", number(model["bearing_n_gamma"]), ",",
                                   sub("N", "q"), "=", number(model["bearing_n_q"]), label), left=143.28)
    title("spring.heading", "5.2 地盤反力係数の算定", 108.48)
    title("vertical.heading", "(1) フーチング底面の鉛直地盤ばね定数", 123)
    title("kv.heading", "1) フーチング底面の鉛直地盤反力係数", 137.52, True)
    for key, coefficient, exponent, label in (("sand", "6.9", "-1/2", "（砂質土）"),
                                              ("alternating", "5.1", "-3/4", "（砂質土，粘性土の互層）"),
                                              ("clay", "3.8", "-1", "（粘性土）")):
        equation("kv." + key, sub("k", "v"), Row(coefficient, sub("ρ", "gk"), sub("E", "d"),
                                                   power(sub("B", "v"), exponent), label), symbolic=True)
    definition("kv.definition.kv", "k", "v", "フーチング底面の鉛直地盤反力係数 ", first=True, unit_power=3)
    definition("kv.definition.rho", "ρ", "gk", "地盤反力係数に関する地盤修正係数")
    add("kv.definition.Ed", Row(sub("E", "d"), "：地盤の変形係数(=", number(modulus), power("kN/m", "2"), ")", gap=0))
    definition("kv.definition.Bv", "B", "v", "フーチング底面の換算幅 (m)")
    equation("kv.width", sub("B", "v"), Row(Root(sub("A", "v")), "(=", Root(number(foundation["area"], 3))),
             number(foundation["equivalent_width"], 3), "m)")
    add("kv.area", Row(sub("A", "v"), "：フーチング底面積(=", number(foundation["B"], 3), Operator("×"),
                       number(foundation["L"], 3), "=", number(foundation["area"], 3), power("m", "2"), ")", gap=0))
    exponent = str(Rational(model["exponent"]).limit_denominator(1000))
    for term, label in (("long_term", "長期"), ("short_term", "短期")):
        add("kv." + term + ".label", Row("・" + label + " ( ", sub("ρ", "gk"), "=", number(model["rho_" + term], 1), ")", gap=0), left=152.04)
        equation("kv." + term, sub("k", "v"), Row(number(model["coefficient"]), Operator("×"), number(model["rho_" + term], 1),
                  Operator("×"), number(modulus), Operator("×"), power(number(foundation["equivalent_width"], 3), exponent)),
                 number(result[term]["kv"], 0), power("kN/m", "3"))
    title("Kv.heading", "2) フーチング底面の鉛直地盤ばね定数", 137.52, True)
    equation("Kv.formula", sub("K", "v"), Row(sub("k", "v"), sub("A", "v")))
    definition("Kv.definition.Kv", "K", "v", "フーチング底面の鉛直地盤ばね定数 (kN/m)", first=True)
    definition("Kv.definition.kv", "k", "v", "フーチング底面の鉛直地盤反力係数 ", unit_power=3)
    definition("Kv.definition.Av", "A", "v", "フーチング底面積 ", unit_power=2, unit_base="m")

    def springs(prefix: str, factor: str, area: float, field: str, suffix: str,
                unit: str = "kN/m", *, area_digits: int = 3) -> None:
        for term, label in (("long_term", "長期"), ("short_term", "短期")):
            add(prefix + "." + term + ".label", "・" + label, "paragraph", 152.04)
            equation(prefix + "." + term, sub("K", suffix), Row(number(result[term][factor], 0), Operator("×"), number(area, area_digits)),
                     number(result[term][field], 0, comma=True), unit)

    springs("Kv", "kv", foundation["area"], "Kv", "v")
    title("shear.heading", "(2) フーチング底面のせん断地盤ばね定数", 123)
    title("ks.heading", "1) フーチング底面のせん断地盤反力係数", 137.52, True)
    equation("ks.formula", sub("k", "s"), Row("λ", sub("k", "v"), gap=0))
    definition("ks.definition.ks", "k", "s", "フーチング底面のせん断地盤反力係数 ", first=True, unit_power=3)
    add("ks.definition.lambda", Row("λ：換算係数（ =", fraction(model["shear_ratio"]), "とする）"))
    for term, label in (("long_term", "長期"), ("short_term", "短期")):
        add("ks." + term + ".label", "・" + label, "paragraph", 152.04)
        equation("ks." + term, sub("k", "s"), Row(fraction(model["shear_ratio"]), Operator("×"), number(result[term]["kv"], 0)),
                 number(result[term]["ks"], 0), power("kN/m", "3"))
    title("Ks.heading", "2) フーチング底面のせん断地盤ばね定数", 137.52, True)
    equation("Ks.formula", sub("K", "s"), Row(sub("k", "s"), sub("A", "v")))
    definition("Ks.definition.Ks", "K", "s", "フーチング底面のせん断地盤ばね定数 (kN/m)", first=True)
    definition("Ks.definition.ks", "k", "s", "フーチング底面のせん断地盤反力係数 ", unit_power=3)
    definition("Ks.definition.Av", "A", "v", "フーチング底面積 ", unit_power=2, unit_base="m")
    springs("Ks", "ks", foundation["area"], "Ks", "s")
    title("rotation.heading", "(3) フーチング底面の回転地盤ばね定数", 123, True)
    equation("Kr.formula", sub("K", "r"), Row(sub("k", "v"), sub("I", "v")))
    definition("Kr.definition.Kr", "K", "r", "フーチング底面の回転地盤ばね定数 (kN・m/rad)", first=True)
    definition("Kr.definition.kv", "k", "v", "フーチング底面の鉛直地盤反力係数", unit_power=3)
    definition("Kr.definition.Iv", "I", "v", "フーチング底面の断面二次モーメント", unit_power=4, unit_base="m")
    for direction, label, first, cubed in (("longitudinal", "1) 線路方向", "L", "B"),
                                          ("transverse", "2) 線路直角方向", "B", "L")):
        prefix = "Kr." + direction
        inertia = foundation["inertia_" + direction]
        title(prefix + ".heading", label, 137.52)
        equation(prefix + ".inertia", sub("I", "v"), Fraction(Row(number(foundation[first], 3), Operator("×"),
                      power(number(foundation[cubed], 3), "3")), "12"), number(inertia, 6), power("m", "4"))
        springs(prefix, "kv", inertia, "Kr_" + direction, "r", "kN・m/rad", area_digits=6)
    return tuple(units)


def semantic_records(result: dict[str, Any]) -> list[dict[str, str]]:
    return [{"id": unit.identifier, "text": plain(unit.value)} for unit in content(result)]


def _soil_name(text: str) -> CellLines:
    """Native font-measured wrapping, preserving standard one-line row height."""
    return CellLines((text,), style=HEADING, line_advance=14.28, min_height=14.28,
                     inner_padding=Insets(1.08, 1.08, 1.08, 1.08), align="center", wrap=True)


def _soil_table(header: Unit, rows: list[Unit]) -> Block:
    values = header.value

    def merged(value: Any, *, source_role: str = "standard") -> Cell:
        lines = value if isinstance(value, tuple) else (value,)
        # The original p1 caption is explicitly 8.9 pt; its unit remains 9.9.
        # This measured role is not automatic shrinking to fit a column.
        line_styles = (replace(HEADING, size=8.9), HEADING) if source_role == "compressive_strength" else None
        return Cell(CellLines(lines, style=HEADING, line_styles=line_styles, line_advance=12.0, min_height=28.56,
                              inner_padding=Insets(1.08, 1.08, 1.08, 1.08), align="center"),
                    rowspan=2, align="center", padding=0)

    def standard(value: str, *, colspan: int = 1, align: str = "center") -> Cell:
        return Cell(CellLines((value,), style=HEADING, min_height=14.28,
                              inner_padding=Insets(1.08, 1.08, 1.08, 1.08), align=align),
                    colspan=colspan, align=align, padding=0)

    authored: list[list[Cell]] = [[merged(values[0]), merged(values[1]), merged(values[2]), merged(values[3]),
                                  standard(values[4][0], colspan=2),
                                  merged(values[5]), merged(values[6], source_role="compressive_strength"), merged(values[7])],
                                 [standard(value) for value in values[4][1:]]]
    authored.extend([Cell(_soil_name(value), align="center", padding=0) if column in (0, 2)
                     else standard(value, align="right")
                     for column, value in enumerate(row.value)] for row in rows)
    widths = (44.4, 58.08, 58.08, 43.56, 58.08, 58.08, 58.08, 58.08, 58.08)
    return indent_to(table(widths, authored, row_heights=None, header_rows=2, block_id="0500/soil.table"), 76.92)


def build_report(result: dict[str, Any]) -> Document:
    units = content(result)
    blocks: list[Block] = []
    for index, unit in enumerate(units):
        if unit.kind == "soil_row":
            continue
        if unit.kind == "soil_header":
            blocks.append(_soil_table(unit, [item for item in units[index + 1:] if item.kind == "soil_row"]))
            blocks.append(spacer())
        elif unit.kind == "heading":
            if blocks:
                blocks.append(spacer())
            if isinstance(unit.value, tuple):
                # Both are native headings; allow the citation to wrap naturally.
                blocks.append(heading(" ".join(unit.value), left=unit.left, block_id=unit.identifier))
            else:
                blocks.append(heading(unit.value, left=unit.left, block_id=unit.identifier))
            blocks.append(KeepWithNext(spacer()))
        elif unit.kind == "caption":
            blocks.append(paragraph(unit.value, left=unit.left, style=HEADING, align="center", block_id=unit.identifier))
        elif unit.kind == "paragraph":
            blocks.append(paragraph(unit.value, left=unit.left, block_id=unit.identifier))
        elif unit.kind == "equation":
            blocks.append(equation_group(unit.value, left=unit.left, first_equal=unit.first_equal,
                                         second_equal=unit.second_equal, result_right=unit.result_right,
                                         unit_start=unit.unit_start, block_id=unit.identifier))
        else:
            blocks.append(indent_to(CellLines((unit.value,), style=BODY, min_height=14.28,
                                              block_id=unit.identifier), unit.left))
        direction_continues = unit.key.startswith(("Kr.longitudinal.", "Kr.transverse.")) and not unit.key.endswith("short_term")
        if unit.key.endswith(".label") or direction_continues:
            blocks[-1] = KeepWithNext(blocks[-1])
    return report(*blocks, footer="5 - {page}")


def render(result: dict[str, Any], output_path: str | Path) -> None:
    document = build_report(result)
    pages = document.layout()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    render_pdf(pages, path, document.fonts, invariant=True)

"""0600 semantic manuscript: values, formulas, tables and physical diagrams.

Worksheet addresses identify existing display values, never paper positions.
All vertical placement is measured by the native GridLayoutPdf flow engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path
import re
from typing import Any, Iterable, Sequence

from gridlayoutpdf import (
    Block, BreakHint, Cell, CellLines, Document, Equation, Fraction, Insets, KeepWithNext,
    LayoutContext, Literal, MathBlock, MathNode, MeasuredBlock, Operator, PreferKeepTogether,
    Row, Script, render_pdf,
)

from ...reaction_inputs import SNOW_LOAD_CASES
from ...reaction_math import VBA_SINGLE_MAX
from ...reaction_report_layout import format_value
from ...reaction_report_values import build_display_values, load_content
from ..document import heading, indent_to, paragraph, report, spacer
from ..equations import equation_group, script
from ..styles import BODY, HEADING
from ..tables import cell, math_cell, table
from .foundation import plain as _foundation_plain


def plain(value: Any) -> str:
    if isinstance(value, BreakHint):
        return ""
    if isinstance(value, Row):
        return "".join(plain(part) for part in value.items)
    if isinstance(value, Script):
        return plain(value.base) + (plain(value.subscript) if value.subscript else "") + (plain(value.superscript) if value.superscript else "")
    if isinstance(value, Fraction):
        return plain(value.numerator) + "/" + plain(value.denominator)
    if isinstance(value, Equation):
        return (plain(value.lhs) + value.relation + plain(value.rhs)
                + (value.result_relation + plain(value.result) if value.result is not None else "")
                + (plain(value.unit) if value.unit is not None else ""))
    if isinstance(value, (tuple, list)):
        return "".join(plain(part) for part in value)
    return _foundation_plain(value)


@dataclass(frozen=True)
class Unit:
    key: str
    value: Any
    kind: str = "math"
    sources: tuple[str, ...] = ()
    widths: tuple[float, ...] = ()
    header_rows: int = 0
    style_role: str = "body"

    @property
    def identifier(self) -> str:
        return "0600/" + self.key


def _column(address: str) -> int:
    result = 0
    for char in re.match(r"[A-Z]+", address)[0]:
        result = result * 26 + ord(char) - 64
    return result


def _number(value: float, decimals: int = 2, *, significant: int | None = None) -> str:
    text = format(value, f".{significant}g" if significant is not None else f".{decimals}f")
    return text if len(text) <= 14 else format(value, ".6g")


def _snow(value: float) -> str:
    with localcontext() as context:
        context.prec = max(context.prec, Decimal(str(value)).adjusted() + 3)
        if abs(value) > VBA_SINGLE_MAX:
            return format(Decimal(format(value, ".15g")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), ".1f")
        return format_value(value, "0.0")


def rich(text: str, *, breaks: bool = False) -> MathNode:
    """Keep each signed factor atomic; allow wrapping only at operators."""
    pieces: list[MathNode] = []
    for token in re.split(r"([A-Za-z]+_\{[^}]+\}|[＋×＝−]|\s/\s)", text):
        if not token:
            continue
        match = re.fullmatch(r"([A-Za-z]+)_\{([^}]+)\}", token)
        if match:
            pieces.append(script(match[1], subscript=match[2]))
        elif token.strip() in ("＋", "×", "＝", "−", "/"):
            if breaks and pieces and token.strip() in ("＋", "×"):
                pieces.append(BreakHint("allowed"))
            pieces.append(Operator(token.strip()))
        else:
            pieces.append(Literal(token))
    return Row(*pieces, gap=0)


def _flow_row(values: Sequence[MathNode]) -> MathNode:
    parts: list[MathNode] = []

    def append(value: MathNode) -> None:
        if isinstance(value, Row):
            for item in value.items:
                append(item)
        else:
            if parts and isinstance(value, Operator) and value.text in ("＋", "×"):
                parts.append(BreakHint("allowed"))
            parts.append(value)

    for value in values:
        append(value)
    return Row(*parts, gap=0)


class Manuscript:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.data = load_content()
        self.values = build_display_values(result)
        # Pure string substitutions use exactly the current selected axle terms.
        for source, sheet, addresses in (("moving_train", "列車荷重", ("J34", "J36", "J38", "J40")),
                                          ("moving_lateral", "直角荷重", ("K87", "K94"))):
            formulas: dict[str, str] = {}
            moving = result[source]
            for side, index, outer in (("B", 1, "A"), ("C", 2, "D")):
                terms = [term for term in moving["contributions"] if term["side"] == side]
                if terms:
                    axle, span = terms[0]["axle_load"], terms[0]["span"]
                    distances = "＋".join(f"{term['distance']:.3f}" for term in terms)
                    formulas[side] = f"{axle:.2f}×({distances})/{span:.3f}"
                    formulas[outer] = f"{axle:.2f}×{len(terms)}-{moving['reactions'][index]:.2f}"
                else:
                    formulas[side] = formulas[outer] = "0"
            sides = ("A", "B", "C", "D") if source == "moving_train" else ("B", "C")
            self.values[sheet].update({address: formulas[side] for address, side in zip(addresses, sides)})
        self.values["死荷重"]["C5"] = "6.1 死荷重・雪荷重"
        self.units: list[Unit] = []

    def value(self, sheet: str, address: str) -> MathNode:
        spec = self.data["cells"][sheet].get(address)
        if spec is None:
            return Literal("")
        value = self.values.get(sheet, {}).get(address, spec.get("value", ""))
        if spec.get("blank_zero") and value == 0:
            return Literal("")
        text = format_value(value, spec["number_format"]).replace("\r", " ").replace("\n", " ").replace("\t", " ")
        if not isinstance(value, str) or value != spec.get("value"):
            return rich(text)
        runs = spec.get("runs") or [{"offset": 0, "role": spec["role"], "script": spec["script"]}]
        if runs[0]["offset"] > 0:
            runs = [{"offset": 0, "role": spec["role"], "script": spec["script"]}, *runs]
        pieces: list[MathNode] = []
        for index, run in enumerate(runs):
            end = runs[index + 1]["offset"] if index + 1 < len(runs) else len(text)
            part = text[run["offset"]:end]
            if not part:
                continue
            if run["script"] != "baseline":
                base = pieces.pop() if pieces else Literal("")
                pieces.append(script(base, **{"superscript" if run["script"] == "superscript" else "subscript": part}))
            else:
                pieces.append(Literal(part))
        return Row(*pieces, gap=0)

    def addresses(self, sheet: str, row: int) -> tuple[str, ...]:
        return tuple(sorted((address for address in self.data["cells"][sheet]
                             if int(re.sub("[A-Z]", "", address)) == row), key=_column))

    def add(self, key: str, value: Any, kind: str = "math", sources: Sequence[str] = (),
            widths: Sequence[float] = (), header_rows: int = 0) -> None:
        text = plain(value) if kind == "heading" else ""
        role = ("chapter" if key == "title" else "section" if re.match(r"\s*6\.", text)
                else "subsection" if text.startswith("(") else "subsubsection" if re.match(r"\d+\)", text) else "body")
        self.units.append(Unit(key, value, kind, tuple(sources), tuple(widths), header_rows, role))

    def cells(self, key: str, sheet: str, addresses: Sequence[str], kind: str = "math") -> None:
        self.add(key, Row(*(self.value(sheet, address) for address in addresses), gap=0), kind,
                 tuple(sheet + "!" + address for address in addresses))

    def row(self, key: str, sheet: str, number: int, kind: str = "math") -> None:
        self.cells(key, sheet, self.addresses(sheet, number), kind)

    def equation_row(self, key: str, sheet: str, number: int) -> None:
        addresses = self.addresses(sheet, number)
        values = [self.value(sheet, address) for address in addresses]
        equals = [index for index, value in enumerate(values) if plain(value) in ("＝", "=")]
        if not equals:
            self.row(key, sheet, number)
            return
        first, last = equals[0], equals[-1]
        rhs = _flow_row(values[first + 1:last if len(equals) > 1 else len(values)])
        equation = Equation(Row(*values[:first], gap=0), rhs, relation=plain(values[first]),
                            result=values[last + 1] if len(equals) > 1 else None,
                            result_relation=plain(values[last]),
                            unit=Row(*values[last + 2:], gap=0) if len(equals) > 1 else None)
        self.add(key, equation, "equation", tuple(sheet + "!" + address for address in addresses))

    def tab(self, key: str, sheet: str, rows: Iterable[int], columns: Sequence[str],
            widths: Sequence[float], header_rows: int = 1) -> None:
        addresses = [[column + str(row) for column in columns] for row in rows]
        self.add(key, tuple(tuple(self.value(sheet, address) for address in row) for row in addresses),
                 "table", tuple(sheet + "!" + address for row in addresses for address in row
                                if address in self.data["cells"][sheet]), widths, header_rows)

    def equation(self, key: str, symbol: str, expression: str, value: float | None,
                 unit: str = "kN", decimals: int = 2) -> None:
        if not expression and value is not None:
            self.add(key, Equation(rich(symbol), Row(_number(value, decimals), unit, gap=4.08), relation="＝"), "equation")
            return
        self.add(key, Equation(rich(symbol), rich(expression, breaks=True), relation="＝",
                              result=_number(value, decimals) if value is not None else None,
                              result_relation="＝", unit=unit if value is not None else None), "equation")


def _dead_snow(m: Manuscript) -> None:
    sheet = "死荷重"
    for key, address in (("title", "B3"), ("dead.heading", "C5"), ("dead.support.heading", "D7")):
        m.cells(key, sheet, (address,), "heading")
    m.cells("dead.unit", sheet, ("AF8",), "paragraph")
    m.tab("dead.support", sheet, (9, 10, 11, 12), ("E", "J", "N", "R", "V", "Z", "AD"),
          (130.68, 55.44, 55.44, 55.44, 55.44, 55.44, 55.44))
    rows = []
    for snow_key, label in SNOW_LOAD_CASES:
        values = [m.result["snow_loads"]["points" if len(point) == 1 else "girders"][point][snow_key]
                  for point in ("A", "B", "C", "D", "AB", "CD")]
        rows.append((label, *(_snow(value) for value in values)))
    m.add("dead.support.snow", tuple(rows), "table", widths=(130.68, *([55.44] * 6)))
    m.cells("dead.girders.heading", sheet, ("D15",), "heading")
    for side, heading_row, starts in (("B", 17, (19, 27)), ("C", 35, (37, 45))):
        m.cells(f"dead.{side}.heading", sheet, (f"E{heading_row}",), "heading")
        for group, header_row in enumerate(starts):
            columns = [index for index in range(5)
                       if m.result["dead_loads"]["slots"][side][group * 5 + index]["position"] is not None]
            if not columns:
                continue
            key = f"dead.{side}.{group}"
            m.cells(key + ".unit", sheet, (f"AA{header_row - 1}",), "paragraph")
            m.cells(key + ".caption", sheet, (f"M{header_row}",), "heading")
            cols = ["M", "P", "S", "V", "Y"]
            addresses = [[f"F{row}", f"J{row}", *(f"{cols[index]}{row}" for index in columns)]
                         for row in range(header_row + 1, header_row + 7)]
            values = [tuple(m.value(sheet, address) for address in row) for row in addresses]
            m.add(key + ".table", tuple(values), "table",
                  tuple(sheet + "!" + address for row in addresses for address in row if address in m.data["cells"][sheet]),
                  (112.2, 58.08, *([58.08] * len(columns))), 1)
            snow_rows = tuple((label, *(_snow(m.result["snow_loads"]["slots"][side][group * 5 + index][snow_key])
                                       for index in columns)) for snow_key, label in SNOW_LOAD_CASES)
            m.add(key + ".snow", snow_rows, "table", widths=(170.28, *([58.08] * len(columns))))


def _weights(m: Manuscript) -> None:
    sheet = "橋脚自重"
    m.row("weights.heading", sheet, 15, "heading")
    m.add("weights.overall.figure", ("overall", m.result), "figure")
    if m.result["weights"]["cells"]["X63"] != 0:
        m.row("weights.pedestal.heading", sheet, 61, "heading")
        for row in range(62, 68):
            m.equation_row(f"weights.pedestal.{row}", sheet, row)
        m.add("weights.pedestal.figure", ("pedestal", m.result), "figure")
    for key, head, areas, table_start, totals in (
        ("beam", 81, (83, 84), 86, range(92, 96)),
        ("column", 109, range(111, 117), None, ()),
        ("footing", 135, (137, 138), 140, range(146, 150)),
    ):
        m.row(f"weights.{key}.heading", sheet, head, "heading")
        for row in areas:
            m.equation_row(f"weights.{key}.{row}", sheet, row)
        if table_start:
            m.tab(f"weights.{key}.table", sheet, range(table_start, table_start + 5),
                  ("F", "J", "N", "Q", "U", "X", "AB", "AE"),
                  (76.2, 55.44, 43.56, 65.28, 43.56, 65.28, 43.56, 65.28), 2)
        for row in totals:
            m.equation_row(f"weights.{key}.{row}", sheet, row)
        m.add(f"weights.{key}.figure", (key, m.result), "figure")
    m.row("weights.soil.heading", sheet, 163, "heading")
    _volume_and_moment(m, "soil", 165, 173, 181)
    m.row("weights.water.heading", sheet, 199, "heading")
    for key, start in (("high", 201), ("normal", 235), ("low", 269)):
        m.row(f"weights.water.{key}.heading", sheet, start, "heading")
        _volume_and_moment(m, "water." + key, start + 2, start + 9, start + 16)
    for key, start, end in (("column_base", 304, 311), ("footing_center", 319, 328)):
        m.row(f"weights.{key}.heading", sheet, start, "heading")
        m.tab(f"weights.{key}.table", sheet, range(start + 2, end + 1),
              ("E", "I", "M", "P", "T", "W", "AA", "AD"),
              (76.2, 55.44, 43.56, 65.28, 43.56, 65.28, 43.56, 65.28), 2)
        for row in range(end + 2, end + 6):
            m.equation_row(f"weights.{key}.{row}", sheet, row)


def _volume_and_moment(m: Manuscript, key: str, volume: int, moment: int, totals: int) -> None:
    sheet = "橋脚自重"
    m.row(f"weights.{key}.volume.caption", sheet, volume, "heading")
    # Formula and result columns remain distinct semantic cells. The soil's
    # two-line product is explicitly kept within the same native table cell.
    values = [(m.value(sheet, f"F{volume + 1}"), m.value(sheet, f"K{volume + 1}"), m.value(sheet, f"Y{volume + 1}"))]
    source: list[str] = list(m.addresses(sheet, volume + 1))
    for row in range(volume + 2, moment - 1):
        addresses = m.addresses(sheet, row)
        middle = [address for address in addresses if address not in (f"F{row}", f"Y{row}")]
        values.append((m.value(sheet, f"F{row}"), Row(*(m.value(sheet, address) for address in middle), gap=0),
                       m.value(sheet, f"Y{row}")))
        source.extend(addresses)
    m.add(f"weights.{key}.volume", tuple(values), "table", [sheet + "!" + address for address in source],
          (102.96, 290.4, 65.28), 1)
    m.tab(f"weights.{key}.moments", sheet, range(moment, totals - 1 if key == "soil" else totals),
          ("F", "K", "O", "R", "V", "Y"), (102.96, 65.28, 65.28, 79.8, 65.28, 79.8), 2)
    for row in range(totals, totals + 3):
        m.equation_row(f"weights.{key}.{row}", sheet, row)
    m.add(f"weights.{key}.figure", (key, m.result), "figure")


def _train(m: Manuscript) -> None:
    sheet = "列車荷重"
    for row in (18, 20, 22):
        m.row(f"train.heading.{row}", sheet, row, "heading")
    m.add("train.moving.figure", ("moving_train", m.result), "figure")
    for row in (34, 36, 38, 40):
        m.equation_row(f"train.reaction.{row}", sheet, row)
    for row in (43, 47, 51):
        m.row(f"train.factor.heading.{row}", sheet, row, "paragraph")
        m.equation_row(f"train.factor.{row + 2}", sheet, row + 2)
    m.row("train.earthquake.heading", sheet, 55, "heading")
    for row in (57, 58):
        # This line has two equalities defining the two equal end reactions.
        m.row(f"train.earthquake.{row}", sheet, row)
    for row in (62, 64):
        m.row(f"impact.heading.{row}", sheet, row, "heading")
    m.row("impact.girder.unit", sheet, 65, "paragraph")
    m.tab("impact.girder.table", sheet, range(66, 88), ("E", "K", "R", "V", "Z", "AD"),
          (96.72, 120.96, 60.48, 60.48, 60.48, 60.48))
    m.row("impact.pier.heading", sheet, 90, "heading")
    m.row("impact.pier.introduction", sheet, 92, "paragraph")
    # Fraction structure comes from the symbolic formula, not old line paths.
    m.add("impact.pier.formula", Row(*(m.value(sheet, address) for address in ("G94", "H94", "I94", "J94", "K94", "L94", "M94")),
              Fraction(m.value(sheet, "O94"), m.value(sheet, "N95")), m.value(sheet, "S94"), m.value(sheet, "U95"), gap=0),
          sources=tuple(sheet + "!" + address for address in (*m.addresses(sheet, 94), *m.addresses(sheet, 95))))
    for row in range(97, 102):
        m.row(f"impact.pier.definition.{row}", sheet, row)
    m.row("impact.pier.unit", sheet, 103, "paragraph")
    m.tab("impact.pier.table", sheet, range(104, 117), ("G", "M", "T", "X", "AB"),
          (116.16, 145.2, 65.28, 65.28, 65.28))
    m.row("impact.foundation.heading", sheet, 119, "heading")
    for row in range(121, 126):
        m.row(f"impact.foundation.note.{row}", sheet, row, "paragraph")


def _transverse_cells(m: Manuscript) -> None:
    sheet = "直角荷重"
    m.row("centrifugal.heading", sheet, 16, "heading")
    m.row("centrifugal.subheading", sheet, 18, "heading")
    for side, start in (("B", 20), ("C", 45)):
        key = "centrifugal." + side
        m.row(key + ".heading", sheet, start, "heading")
        if m.result["input"]["spans"][side.lower()]["radius"] == 0:
            m.row(key + ".zero", sheet, start + 2, "paragraph")
        m.row(key + ".coefficient.note", sheet, start + 3, "paragraph")
        first, second = start + 5, start + 6
        numerator = Row(m.value(sheet, f"Q{first}"), m.value(sheet, f"S{first}"), gap=0)
        denominator = Row(*(m.value(sheet, f"{column}{second}") for column in ("P", "R", "S")), gap=0)
        m.add(key + ".coefficient", Equation(m.value(sheet, f"G{first}"),
              Row(Fraction(m.value(sheet, f"J{first}"), m.value(sheet, f"J{second}")),
                  m.value(sheet, f"N{first}"), Fraction(numerator, denominator), gap=4.08),
              relation="＝", result=m.value(sheet, f"W{first}"), result_relation="＝"), "equation",
              tuple(sheet + "!" + address for row in (first, second) for address in m.addresses(sheet, row)))
        m.row(key + ".height.caption", sheet, start + 8, "paragraph")
        m.equation_row(key + ".height", sheet, start + 10)
        for number, row in enumerate((start + 12, start + 16, start + 20)):
            m.row(key + f".force.{number}.heading", sheet, row, "paragraph")
            m.equation_row(key + f".force.{number}", sheet, row + 2)
    m.row("lateral.heading", sheet, 69, "heading")
    m.row("lateral.note", sheet, 71, "paragraph")
    m.equation_row("lateral.load", sheet, 73)
    m.add("lateral.moving.figure", ("moving_lateral", m.result), "figure")
    for side, start in (("B", 85), ("C", 92)):
        m.row(f"lateral.{side}.heading", sheet, start, "heading")
        m.equation_row(f"lateral.{side}.force", sheet, start + 2)
        m.equation_row(f"lateral.{side}.height", sheet, start + 4)
    m.row("wind.heading", sheet, 99, "heading")
    for key, heading_row, supports in (("loaded", 101, (106, 115)), ("empty", 124, (128, 137))):
        m.row(f"wind.{key}.heading", sheet, heading_row, "heading")
        m.equation_row(f"wind.{key}.pressure", sheet, heading_row + 2)
        if key == "loaded":
            m.row("wind.loaded.width", sheet, 104, "paragraph")
        for side, start in zip(("B", "C"), supports):
            m.row(f"wind.{key}.{side}.heading", sheet, start, "heading")
            for name, row in zip(("height", "force", "position"), (start + 2, start + 4, start + 6)):
                m.equation_row(f"wind.{key}.{side}.{name}", sheet, row)


_SNOW_SYMBOL = {"雪荷重_2年確率": "S_{2}", "雪荷重_10年確率": "S_{10}", "雪荷重_30年確率": "S_{30}"}


def _coefficient(value: float) -> str:
    return _number(value) if round(value, 2) == value else _number(value, significant=8)


def _unfactored(result: dict[str, Any], row: dict[str, Any], side: str) -> bool:
    return result["longitudinal_base"][side]["braking_rule"] == "EA-17" and row[side]["recovery_brake_override"]


def _brake_multiplier(result: dict[str, Any], row: dict[str, Any], side: str) -> str:
    detail = row[side]
    coefficient = _coefficient(detail["effective_brake_coefficient"])
    if result["longitudinal_base"][side]["braking_rule"] == "EA-17" and not detail["recovery_brake_override"]:
        rho = result["input"]["train"]["factors_ultimate"]
        return f"({coefficient} / {_number(rho, significant=8)})" if rho else "0"
    return coefficient


def _horizontal_terms(result: dict[str, Any], row: dict[str, Any], side: str) -> str:
    combination = row["combination"]
    terms = []
    if combination["lr_factor"]:
        terms.append(f"{combination['lr_factor']:.1f} L_{{R}}")
    if combination["brake_factor"]:
        symbol = "B_{0}" if _unfactored(result, row, side) else "B"
        terms.append(f"{_brake_multiplier(result, row, side)} {symbol}")
    return " ＋ ".join(terms)


def _condition(row: dict[str, Any]) -> str:
    return row["label"].split()[0]


def _vertical_symbol(combination: dict[str, Any]) -> str:
    terms = [f"{combination['d1_factor']:.1f} D_{{1}}", f"{combination['d2_factor']:.1f} D_{{2}}"]
    if combination["live_group"]:
        live = "(L＋I)" if combination["include_impact"] else "L"
        terms.append(f"{_coefficient(combination['effective_live_coefficient'])} {live}")
    terms.append(_SNOW_SYMBOL[combination["snow_key"]])
    return " ＋ ".join(terms)


def _longitudinal(m: Manuscript) -> None:
    result, vehicle = m.result, m.result["input"]["train"]
    m.add("longitudinal.heading", "6.3.1 線路方向に働く水平荷重", "heading")
    if vehicle.get("name"):
        m.add("longitudinal.vehicle", f"設計車両：{vehicle['name']}", "paragraph")
    m.add("longitudinal.girder.heading", "(1) 桁に働く水平荷重", "heading")
    m.add("longitudinal.rail.heading", "1) ロングレール縦荷重", "heading")
    for rate, description in ((10, "(a) ひび割れの検討および安全性・復旧性の照査"), (8, "(b) 使用性の照査")):
        m.add(f"longitudinal.rail.{rate}.heading", description, "paragraph")
        m.add(f"longitudinal.rail.{rate}.note", f"1 軌道当り　{rate} kN/m を考える。", "paragraph")
        for number, side in ((1, "B"), (2, "C")):
            base = result["longitudinal_base"][side]
            expression = f"{rate} × {_number(base['length'])} × {_number(base['track_total'], significant=6)}"
            if rate * base["length"] > 2000:
                expression = f"min({rate} × {_number(base['length'])}, 2000) × {_number(base['track_total'], significant=6)}"
            m.equation(f"longitudinal.rail.{rate}.{side}", f"T{number}", expression, base["LR" if rate == 10 else "LR_service"])
    m.add("longitudinal.brake.heading", "2) 制動荷重・始動荷重", "heading")
    m.add("longitudinal.brake.note", "制動荷重および始動荷重の特性値は下式によって求める。", "paragraph")
    ea = result["longitudinal_base"]["B"]["braking_rule"] == "EA-17"
    for key, label, constant, numerator in (("brake", "制動荷重", .27 if ea else .20, 1 if ea else .80),
                                             ("start", "始動荷重", .25 if ea else .19, .95 if ea else .76)):
        m.add("longitudinal." + key + ".formula", rich(f"{label} ：（{constant:.2f} ＋ {numerator:.2f} / L_{{v}}" + ("）・ΣR" if ea else "・L）・T")))
    for key, label, constant, numerator in (("brake", "(a) 制動荷重", .27 if ea else .20, 1 if ea else .80),
                                             ("start", "(b) 始動荷重", .25 if ea else .19, .95 if ea else .76)):
        m.add("longitudinal." + key + ".caption", label, "paragraph")
        for number, side in ((1, "B"), (2, "C")):
            base = result["longitudinal_base"][side]
            expression = (f"({constant:.2f} ＋ {numerator:.2f} / {_number(vehicle['length'])}) × {_number(base['train_reaction_total'])}" if ea else
                          f"({constant:.2f} ＋ {numerator:.2f} / {_number(vehicle['length'])} × {_number(base['length'])}) × {_number(vehicle['axle_load'])}")
            m.equation(f"longitudinal.{key}.{side}", f"T{number}", expression, base[key])
    m.add("longitudinal.brake.adopt", "制動荷重と始動荷重の大きい値を採用して設計する。", "paragraph")
    m.add("longitudinal.earthquake.heading", "3) 地震時慣性力荷重", "heading")
    m.add("longitudinal.earthquake.coefficient", rich("K_{h}＝1.00"))
    m.add("longitudinal.earthquake.formula", rich("T ＝ (D_{1} ＋ D_{2} ＋ S_{2}) × K_{h}"))
    for number, side, points in ((1, "B", ("A", "B")), (2, "C", ("C", "D"))):
        dead = [result["dead_loads"]["points"][point] for point in points]
        snow = [result["snow_loads"]["points"][point]["雪荷重_2年確率"] for point in points]
        expression = (f"({_number(dead[0]['D1'])} ＋ {_number(dead[1]['D1'])} ＋ {_number(dead[0]['D2'])} ＋ {_number(dead[1]['D2'])}"
                      f"＋ {_number(snow[0])} ＋ {_number(snow[1])}) × 1.00")
        m.equation(f"longitudinal.earthquake.{side}", f"T{number}", expression, result["longitudinal_base"][side]["earthquake_dead"])
    m.add("longitudinal.earthquake_train.heading", "4) 地震時列車荷重慣性力", "heading")
    m.add("longitudinal.earthquake_train.note", "線路方向の列車荷重慣性力は、車輪とレールとの粘着係数 μ＝0.20 とする。", "paragraph")
    for number, side in ((1, "B"), (2, "C")):
        load = result["train"]["earthquake"][f"R{side}"]
        m.equation(f"longitudinal.earthquake_train.{side}", f"T{number}", f"({_number(load)} ＋ {_number(load)}) × 0.20", result["longitudinal_base"][side]["earthquake_train"])
    rows = [*result["longitudinal"], *result.get("longitudinal_snow_cases", [])]
    for number, row in enumerate(rows, 1):
        if "combination" in row:
            _bearing_case(m, row, number)
        else:
            key = f"longitudinal.case.{number}"
            m.add(key + ".heading", f"(2) 支承に働く水平荷重  {row['case']}) {row['label']}", "heading")
            m.add(key + ".coefficient", rich("K_{h}＝1.00" if row["case"] == 9 else "μ＝0.20"))
            for index, side in ((1, "B"), (2, "C")):
                detail = row[side]
                m.add(key + f".{side}.caption", f"【{'起点側' if side == 'B' else '終点側'} {side}支点】 {detail['bearing']}支点", "paragraph")
                m.add(key + f".{side}.applied", rich(f"※ T{index} ＝ {_number(detail['applied'])} kN"))
                divisor = 2 if detail["bearing"] == "可動" else 1
                m.equation(key + f".{side}.force", "※ ∴ H", f"{_number(detail['applied'])} / {divisor}", detail["force"])
    m.add("longitudinal.summary.heading", "(3) 線路方向の支承水平荷重のまとめ", "heading")
    m.add("longitudinal.summary.unit", "単位：kN", "paragraph")
    values: list[tuple[Any, ...]] = [("No", "荷重組合せ", "B", "C", "合計")]
    for index, row in enumerate(rows, 1):
        if "combination" in row:
            b, c = (_horizontal_terms(result, row, side) for side in ("B", "C"))
            snow = _SNOW_SYMBOL[row["combination"]["snow_key"]]
            first = f"{_condition(row)}　{b}" if b == c else f"{_condition(row)}　B：{b}"
            second = f"{snow}（{row['combination']['snow_key'][4:]}）" if b == c else f"　　　 C：{c}　{snow}"
            label = (rich(first), rich(second))
        else:
            label = (rich(row["label"]),)
        values.append((str(index), label, _number(row["B"]["force"]), _number(row["C"]["force"]), _number(row["B"]["force"] + row["C"]["force"])))
    m.add("longitudinal.summary", tuple(values), "table", widths=(26.64, 232.32, 65.28, 65.28, 65.28), header_rows=1)


def _bearing_case(m: Manuscript, row: dict[str, Any], number: int) -> None:
    result, combination = m.result, row["combination"]
    key = f"longitudinal.case.{number}"
    m.add(key + ".heading", f"(2) 支承に働く水平荷重  {number}) {_condition(row)}", "heading")
    b, c = (_horizontal_terms(result, row, side) for side in ("B", "C"))
    m.add(key + ".horizontal", rich(f"・{b}" if b == c else f"・起点側：{b}　　終点側：{c}"))
    m.add(key + ".combination", rich(f"[ {_vertical_symbol(combination)} の組み合わせ ]"))
    for index, side in ((1, "B"), (2, "C")):
        base, detail = result["longitudinal_base"][side], row[side]
        prefix = key + "." + side
        m.add(prefix + ".caption", f"【{'起点側' if side == 'B' else '終点側'} {side}支点】 {detail['bearing']}支点", "heading")
        if combination["brake_factor"] and _unfactored(result, row, side):
            m.add(prefix + ".braking_base", rich(f"B_{{0}} ＝ {_number(detail['braking_base'])} kN （荷重修正前の制動荷重）"))
        terms = []
        if combination["lr_factor"]:
            terms.append(_number(base["LR_service"]) if combination["lr_factor"] == .8 else f"{combination['lr_factor']:.1f} × {_number(base['LR'])}")
        if combination["brake_factor"]:
            terms.append((" ＋ " if terms else "") + f"{_brake_multiplier(result, row, side)} × {_number(detail['braking_base'])}")
        if combination["lr_factor"] == .8 and not combination["brake_factor"]:
            m.add(prefix + ".applied", rich(f"※ T{index} ＝ {_number(detail['applied'])} kN"))
        else:
            m.equation(prefix + ".applied", f"※ T{index}", "".join(terms), detail["applied"])
        m.add(prefix + ".vertical.caption", f"{detail['bearing']}支承に働く鉛直荷重", "paragraph")
        m.add(prefix + ".vertical.formula", rich(f"R_{{m}} ＝ {_vertical_symbol(combination)}"))
        movable = detail["bearing"] == "可動"
        point = side if movable else ("A" if side == "B" else "D")
        dead = result["dead_loads"]["points"][point]
        snow = result["snow_loads"]["points"][point][combination["snow_key"]]
        expression = f"{combination['d1_factor']:.1f} × {_number(dead['D1'])} ＋ {combination['d2_factor']:.1f} × {_number(dead['D2'])}"
        if combination["live_group"]:
            live = result["train"]["girder"][combination["live_group"]][combination["live_track"]][f"R{point}"]
            coefficient = live["coefficient"] if combination["include_impact"] else 0
            raw = result["train"]["raw_reactions"][f"R{point}"]
            expression += (f"＋ {_coefficient(combination['effective_live_coefficient'])} × {_number(raw)}"
                           f" × {_number(base['track_total'], significant=6)} × (1 ＋ {_number(coefficient, 3)})")
        expression += f" ＋ {_number(snow)}"
        m.equation(prefix + ".vertical", "", expression, detail["local_vertical"] if movable else detail["remote_vertical"])
        m.add(prefix + ".horizontal.caption", f"{detail['bearing']}支承に働く水平荷重", "paragraph")
        candidates = (("T / n", f"{_number(detail['applied'])} / 2", detail["half_applied"]),
                      ("μ ・ R_{m}", f"{_number(detail['mu'], significant=6)} × {_number(detail['local_vertical'])}", detail["movable_friction"]),
                      ("μ ・ T / n", f"{_number(detail['mu'], significant=6)} × {_number(detail['half_applied'])}", detail["movable_floor"])) if movable else (
                      ("T − 1/2 μ ・ R_{m}", f"{_number(detail['applied'])} − 1/2 × {_number(detail['mu'], significant=6)} × {_number(detail['remote_vertical'])}", detail["fixed_candidate"]),
                      ("T / n", f"{_number(detail['applied'])} / 2", detail["half_applied"]))
        for item, (symbol, expression, value) in enumerate(candidates):
            m.equation(prefix + f".candidate.{item}", symbol, expression, value)
        m.add(prefix + ".adopted", rich(f"※ ∴ H ＝ {_number(detail['force'])} kN"))


def _transverse_earthquake(m: Manuscript) -> None:
    result, vehicle = m.result, m.result["input"]["train"]
    for key, index, title, coefficient in (("dead", 6, "(4) 地震時慣性力荷重", "1.00"),
                                           ("train", 7, "(5) 地震時列車荷重慣性力荷重", "0.30")):
        prefix = "transverse.earthquake." + key
        m.add(prefix + ".heading", title, "heading")
        m.add(prefix + ".coefficient", rich("設計水平震度　K_{h} ＝ " + coefficient))
        for side in ("B", "C"):
            detail, span = result["transverse"][index][side], result["input"]["spans"][side.lower()]
            name = prefix + "." + side
            m.add(name + ".heading", f"・{'起点側' if side == 'B' else '終点側'}", "heading")
            if key == "dead":
                dead = result["dead_loads"]["points"][side]
                snow = result["snow_loads"]["points"][side]["雪荷重_2年確率"]
                expression = f"{_number(dead['D1'])} ＋ {_number(dead['D2'])} ＋ {_number(snow)}"
            else:
                m.add(name + ".force.caption", "水平力", "paragraph")
                expression = f"{_number(result['train']['earthquake'][f'R{side}'])} × 0.30"
            m.equation(name + ".force", f"H_{{{side}}}", expression, detail["force"])
            m.add(name + ".height.caption", "作用位置", "paragraph")
            expression = "" if key == "dead" else (f"{_number(span['h1'], 3)} ＋ {_number(span['h2'], 3)}"
                           f" ＋ {_number(span['h3'], 3)} ＋ {_number(vehicle['height_seismic'], 3)}")
            m.equation(name + ".height", "h_{s}" if key == "dead" else "y_{1}", expression,
                       detail["height"], "m", 6 if key == "dead" else 3)
            m.add(name + ".moment.caption", "モーメント", "paragraph")
            m.equation(name + ".moment", "M" if key == "dead" else "M_{1}",
                       f"{_number(detail['force'])} × {_number(detail['height'], 6 if key == 'dead' else 3)}", detail["moment"], "kN・m")
    m.add("transverse.summary.heading", "(6) 支承に働く水平荷重のまとめ", "heading")
    m.add("transverse.summary.unit", "力 H：kN、作用高さ h：m", "paragraph")
    rows = [("ケース", "B H", "B h", "C H", "C h")]
    rows.extend((row["label"], _number(row["B"]["force"]), _number(row["B"]["height"], 3),
                 _number(row["C"]["force"]), _number(row["C"]["height"], 3)) for row in result["transverse"])
    m.add("transverse.summary", tuple(rows), "table", widths=(194.04, 65.28, 65.28, 65.28, 65.28), header_rows=1)


def content(result: dict[str, Any]) -> tuple[Unit, ...]:
    manuscript = Manuscript(result)
    _dead_snow(manuscript)
    _weights(manuscript)
    _train(manuscript)
    _longitudinal(manuscript)
    _transverse_cells(manuscript)
    _transverse_earthquake(manuscript)
    return tuple(manuscript.units)


def _dimension(value: float) -> str:
    return f"{0.0 if abs(value) < .0005 else value:.3f}"


def _soil_depth(geometry: dict[str, float]) -> float:
    return ((geometry["df1"] - geometry["df2"]) / (geometry["b7"] + geometry["b8"] + geometry["b9"])
            * (geometry["b9"] + geometry["b8"] / 2) + geometry["df2"])


def figure_labels(kind: str, result: dict[str, Any]) -> tuple[str, ...]:
    """Current physical dimensions, in the reviewed old figure meaning order."""
    if kind.startswith("moving_"):
        b, c = (result["input"]["spans"][key] for key in ("b", "c"))
        first = b["l1"] + b["span"] + b["l2"]
        total = first + c["l1"] + c["span"] + c["l2"]
        positions = sorted(position for position in result[kind]["positions"] if -.0001 <= position <= total + .0001)
        points = (0, *positions, total)
        intervals = [end - start for start, end in zip(points, points[1:]) if end - start >= .0001]
        return tuple(_dimension(value) for value in (*intervals, b["l1"], b["span"], b["l2"], c["l1"], c["span"], c["l2"], first, total - first))
    g = result["input"]["geometry"]
    labels = []
    for prefix, centroid in (("b", "xL"), ("w", "xC")):
        a, a2, a3, a4, a5, column, a7, a8, a9 = (g[f"{prefix}{index}"] for index in range(1, 10))
        total = a7 + a8 + a9
        if kind == "overall":
            labels.extend(("側 面 図" if prefix == "b" else "正 面 図", f"{a * 1000:.0f}", f"{column * 1000:.0f}"))
            if prefix == "w":
                labels.extend((f"{a4 * 1000:.0f}", f"{a5 * 1000:.0f}"))
            labels.extend((f"{(g['df1'] if prefix == 'b' else _soil_depth(g)) * 1000:.0f}",
                           *(f"{value * 1000:.0f}" for value in (a7, a8, a9)),
                           *(f"{g[f'h{index}'] * 1000:.0f}" for index in range(1, 7) if g[f"h{index}"] > 0)))
        elif kind == "beam":
            labels.extend((_dimension(a), centroid, *(_dimension(value) for value in (a4, (a - a4 - a5) / 2, (a - a4 - a5) / 2, a5))))
            if prefix == "w":
                labels.extend((_dimension(g["h2"]), _dimension(g["h3"])))
        elif kind == "pedestal":
            labels.extend(_dimension(value) for value in (a, a2, a3, max(0, a - a2 - a3), a / 2 - (a5 - a4) / 2, a / 2 + (a5 - a4) / 2))
            # The original labels a nonzero pedestal centroid displacement.
            component = result["weights"]["components"]["桁受け"]
            if abs(component[centroid] * (116 if prefix == "b" else 204) / max(a, .01)) > 5:
                labels.append(centroid)
            if prefix == "w":
                labels.append(_dimension(g["h1"]))
        else:
            if kind == "column":
                labels.append(_dimension(column))
            elif kind == "soil" or kind.startswith("water."):
                labels.extend(_dimension(value) for value in ((g["df1"], g["df2"]) if prefix == "b" else (_soil_depth(g),)))
                if kind.startswith("water."):
                    index = ("high", "normal", "low").index(kind.split(".")[1])
                    if prefix == "b":
                        labels.extend(_dimension(result["weights"]["cells"][f"{column}{220 + index * 34}"]) for column in ("G", "L"))
                    else:
                        labels.extend(("▽ 水位", _dimension(g[f"hw{index + 1}"])))
            labels.extend((centroid, *(_dimension(value) for value in (a7, a8, a9, total))))
            if prefix == "b" and (kind == "soil" or kind.startswith("water.")):
                labels.append(_dimension(g["h5"]))
                if kind.startswith("water."):
                    labels.append(_dimension(g["h6"]))
            if prefix == "w":
                if kind.startswith("water."):
                    labels.append(_dimension(g["h5"] + g["h6"]))
                elif kind in ("column", "footing"):
                    labels.extend((_dimension(g["h4"] if kind == "column" else g["h5"]),
                                   _dimension(g["h5"] + g["h6"] if kind == "column" else g["h6"]), "y"))
    return tuple(labels)


@dataclass(frozen=True)
class ReactionFigure:
    """Physical outlines and dimensions expressed with public native commands."""

    kind: str
    result: dict[str, Any]
    block_id: str

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        from gridlayoutpdf import Line, Polyline, Text, measure_block
        from ...frame_outline import build_outline
        from ..figures import figure

        commands: list[Any] = []
        labels = figure_labels(self.kind, self.result)
        width = min(available_width, 458.64)
        label_style = BODY

        def text(x: float, y: float, value: str, *, centered: bool = False) -> None:
            if centered:
                x -= context.fonts.measure(value, label_style).width / 2
            commands.append(Text(x, y, value, label_style))

        def arrow(x: float, y: float, dx: float, dy: float) -> None:
            commands.extend((Line(x, y, x + dx * 4 - dy * 2, y + dy * 4 + dx * 2, .12),
                             Line(x, y, x + dx * 4 + dy * 2, y + dy * 4 - dx * 2, .12)))

        if self.kind.startswith("moving_"):
            b, c = (self.result["input"]["spans"][key] for key in ("b", "c"))
            first = b["l1"] + b["span"] + b["l2"]
            total = first + c["l1"] + c["span"] + c["l2"]
            positions = sorted(position for position in self.result[self.kind]["positions"] if -.0001 <= position <= total + .0001)
            x = lambda value: 12 + value * (width - 24) / max(total, .01)
            tiers: list[float] = []
            placements = []
            points = (0, *positions, total)
            for start, end in zip(points, points[1:]):
                if end - start < .0001:
                    continue
                value = _dimension(end - start)
                center = (x(start) + x(end)) / 2
                half = context.fonts.measure(value, label_style).width / 2
                center = max(half + 1.08, min(width - half - 1.08, center))
                tier = next((index for index, right in enumerate(tiers) if center - half > right + 4.08), len(tiers))
                if tier == len(tiers):
                    tiers.append(0)
                tiers[tier] = center + half
                placements.append((x(start), x(end), center, value, tier))
            baseline = 48 + 18 * len(tiers)
            commands.append(Line(x(0), baseline, x(total), baseline, .48))
            for position in (b["l1"], b["l1"] + b["span"], first + c["l1"], first + c["l1"] + c["span"]):
                xx = x(position)
                commands.append(Polyline(((xx, baseline), (xx - 3, baseline + 6), (xx + 3, baseline + 6), (xx, baseline)), .48))
            for position in positions:
                xx = x(position)
                commands.append(Line(xx, baseline - 24, xx, baseline, .48))
                arrow(xx, baseline, 0, -1)
            for start, end, center, value, tier in placements:
                y = 12 + tier * 18
                commands.extend((Line(start, y + 4, end, y + 4, .12),
                                 Line(start, y + 1, start, baseline - 26, .12),
                                 Line(end, y + 1, end, baseline - 26, .12)))
                arrow(start, y + 4, 1, 0)
                arrow(end, y + 4, -1, 0)
                text(center, y, value, centered=True)
            # Six independently labelled physical lengths use three staggered
            # baselines, so even zero overhangs cannot collide.
            starts = (0, b["l1"], b["l1"] + b["span"], first,
                      first + c["l1"], first + c["l1"] + c["span"], total)
            for index, (start, end, value) in enumerate(zip(starts, starts[1:], labels[-8:-2])):
                y = baseline + 24 + index % 3 * 18
                commands.extend((Line(x(start), baseline + 7, x(start), y + 4, .12),
                                 Line(x(end), baseline + 7, x(end), y + 4, .12), Line(x(start), y + 4, x(end), y + 4, .12)))
                center = (x(start) + x(end)) / 2
                half = context.fonts.measure(value, label_style).width / 2
                text(max(half + 1.08, min(width - half - 1.08, center)), y, value, centered=True)
            for start, end, value in ((0, first, labels[-2]), (first, total, labels[-1])):
                y = baseline + 90
                commands.append(Line(x(start), y + 4, x(end), y + 4, .12))
                text((x(start) + x(end)) / 2, y, value, centered=True)
            height = baseline + 108
        else:
            geometry = self.result["input"]["geometry"]
            # Side/front share physical axes. Component views select current
            # physical shapes; centroids come from the supplied Double results.
            names = {"beam": {"beam", "haunch"}, "pedestal": {"parapet"},
                     "column": {"shaft", "footing_base", "footing_taper"},
                     "footing": {"footing_base", "footing_taper"}}
            components = {"beam": "はり", "pedestal": "桁受け", "column": "柱", "footing": "フーチング", "soil": "上載土",
                          "water.high": "高水位", "water.normal": "平水位", "water.low": "低水位"}
            label_cursor = 0

            def label() -> str:
                nonlocal label_cursor
                value = labels[label_cursor]
                label_cursor += 1
                return value

            def horizontal(first: float, last: float, physical_y: float, dimension_y: float,
                           value: str, label_x: float | None = None) -> None:
                commands.extend((Line(first, physical_y, first, dimension_y + 3, .12),
                                 Line(last, physical_y, last, dimension_y + 3, .12),
                                 Line(first, dimension_y, last, dimension_y, .12)))
                arrow(first, dimension_y, 1, 0)
                arrow(last, dimension_y, -1, 0)
                center = (first + last) / 2 if label_x is None else label_x
                if label_x is not None and abs(center - (first + last) / 2) > 4:
                    commands.append(Line((first + last) / 2, dimension_y, center, dimension_y - 5, .12))
                text(center, dimension_y - 6, value, centered=True)

            def vertical(first: float, last: float, physical_x: float, dimension_x: float,
                         value: str, baseline: float | None = None, label_x: float | None = None) -> None:
                commands.extend((Line(physical_x, first, dimension_x + 2, first, .12),
                                 Line(physical_x, last, dimension_x + 2, last, .12),
                                 Line(dimension_x, first, dimension_x, last, .12)))
                arrow(dimension_x, min(first, last), 0, 1)
                arrow(dimension_x, max(first, last), 0, -1)
                baseline = (first + last) / 2 + 3 if baseline is None else baseline
                label_x = dimension_x + 12 if label_x is None else label_x
                commands.append(Line(dimension_x, (first + last) / 2, label_x, baseline + 2, .12))
                text(label_x, baseline, value, centered=True)

            for index, prefix in enumerate(("b", "w")):
                outline = build_outline(geometry, prefix)
                selected = [part for part in outline.components if self.kind not in names or part.name in names[self.kind]]
                xs, ys = zip(*(point for part in selected for point in part.points))
                if self.kind == "pedestal":
                    # Its dimensions run along the whole beam top, so the view
                    # spans the beam width, not only the (often tiny) pedestal.
                    beam = [point for part in outline.components if part.name == "beam" for point in part.points]
                    xs = (*xs, *(point[0] for point in beam))
                minimum_x, maximum_x, minimum_y, maximum_y = min(xs), max(xs), min(ys), max(ys)
                scale = min(132 / max(maximum_x - minimum_x, .01), 120 / max(maximum_y - minimum_y, .01))
                origin = 114 + index * 229.32
                x = lambda value: origin + (value - (minimum_x + maximum_x) / 2) * scale
                y = lambda value: 174 - (value - minimum_y) * scale
                for part in selected:
                    points = tuple((x(a), y(b)) for a, b in part.points)
                    commands.append(Polyline((*points, points[0]), .48))
                commands.append(Line(x(0), 42, x(0), 188, .12))
                a, a2, a3, a4, a5, column, a7, a8, a9 = (geometry[f"{prefix}{number}"] for number in range(1, 10))
                total = a7 + a8 + a9
                foot_center = (a9 - a7) / 2
                base_left, base_right = foot_center - total / 2, foot_center + total / 2
                beam_center = (a5 - a4) / 2
                beam_left, beam_right = beam_center - a / 2, beam_center + a / 2
                foot_top = geometry["h5"] + geometry["h6"]
                column_top = foot_top + geometry["h4"]
                beam_bottom = column_top + geometry["h3"]
                beam_top = beam_bottom + geometry["h2"]
                centroid_x = x(0)
                centroid_y = 114.0
                if self.kind != "overall":
                    component = self.result["weights"]["components"][components[self.kind]]
                    centroid_x = x(component["xL" if prefix == "b" else "xC"])
                    centroid_y = y(beam_top + component["hG"]) if self.kind in ("beam", "pedestal") else y((foot_top + column_top) / 2) if self.kind == "column" else y(component["hG"]) if self.kind == "footing" else 114.0
                    commands.extend((Line(centroid_x - 2, centroid_y, centroid_x + 2, centroid_y, .96),
                                     Line(centroid_x, centroid_y - 2, centroid_x, centroid_y + 2, .96)))
                if self.kind == "soil" or self.kind.startswith("water."):
                    depth = geometry["df1"] if prefix == "b" else _soil_depth(geometry)
                    ground = 174 - min(110, max(-10, (geometry["h5"] + geometry["h6"] + depth) * scale))
                    commands.append(Line(origin - 72, ground, origin + 72, ground, .48))
                    if self.kind.startswith("water."):
                        water = geometry["hw" + str(("high", "normal", "low").index(self.kind.split(".")[1]) + 1)]
                        water_y = 174 - min(142, max(-10, water * scale))
                        for start in range(-72, 72, 6):
                            commands.append(Line(origin + start, water_y, origin + start + 3, water_y, .12))
                if self.kind == "overall":
                    text(origin, 12, label(), centered=True)
                    horizontal(x(beam_left), x(beam_right), y(beam_top), 34, label(), origin)
                    horizontal(x(-column / 2), x(column / 2), y(column_top), 210, label(), origin)
                    if prefix == "w":
                        lower = (a - a4 - a5) / 2
                        horizontal(x(beam_left), x(-lower), y(column_top), 234, label(), origin - 45)
                        horizontal(x(lower), x(beam_right), y(column_top), 234, label(), origin + 45)
                    soil_y = y(foot_top + (geometry["df1"] if prefix == "b" else _soil_depth(geometry)))
                    vertical(soil_y, y(foot_top), x(base_left), origin - 80, label(), 144, origin - 95)
                    corners = (base_left, -a8 / 2, a8 / 2, base_right)
                    for number, (first, last) in enumerate(zip(corners, corners[1:])):
                        horizontal(x(first), x(last), y(foot_top), 264, label(), origin + (number - 1) * 48)
                    top = beam_top + geometry["h1"]
                    baseline = 48.0
                    for number in range(1, 7):
                        height = geometry[f"h{number}"]
                        if height > 0:
                            bottom = top - height
                            baseline = max(baseline, (y(top) + y(bottom)) / 2 + 3)
                            vertical(y(top), y(bottom), origin + 67, origin + 80, label(), baseline, origin + 96)
                            baseline += 14.28
                            top = bottom
                elif self.kind == "beam":
                    horizontal(x(beam_left), x(beam_right), y(beam_top), 34, label(), origin)
                    horizontal(x(0), centroid_x, centroid_y, 210, label(), origin)
                    lower = (a - a4 - a5) / 2
                    corners = (beam_left, -lower, 0, lower, beam_right)
                    for number, (first, last) in enumerate(zip(corners, corners[1:])):
                        horizontal(x(first), x(last), y(column_top), 246, label(), origin + (number - 1.5) * 38)
                    if prefix == "w":
                        vertical(y(beam_top), y(beam_bottom), x(beam_right), origin + 80, label(), 100, origin + 96)
                        vertical(y(beam_bottom), y(column_top), x(lower), origin + 80, label(), 158, origin + 96)
                elif self.kind == "pedestal":
                    pedestal_left = beam_left + a2
                    pedestal_right = pedestal_left + a3
                    commands.append(Line(x(beam_left), y(beam_top), x(beam_right), y(beam_top), .48))
                    horizontal(x(beam_left), x(beam_right), y(beam_top), 34, label(), origin)
                    for number, (first, last) in enumerate(zip((beam_left, pedestal_left, pedestal_right), (pedestal_left, pedestal_right, beam_right))):
                        horizontal(x(first), x(last), y(beam_top), 210, label(), origin + (number - 1) * 48)
                    for number, (first, last) in enumerate(((beam_left, 0), (0, beam_right))):
                        horizontal(x(first), x(last), y(beam_top), 246, label(), origin + (number - .5) * 78)
                    if abs(component["xL" if prefix == "b" else "xC"] * (116 if prefix == "b" else 204) / max(a, .01)) > 5:
                        horizontal(x(0), centroid_x, centroid_y, 282, label(), origin)
                    if prefix == "w":
                        vertical(y(beam_top + geometry["h1"]), y(beam_top), x(pedestal_right), origin + 80, label(), 114, origin + 96)
                else:
                    if self.kind == "column":
                        horizontal(x(-column / 2), x(column / 2), y(column_top), 34, label(), origin)
                    elif self.kind == "soil" or self.kind.startswith("water."):
                        if prefix == "b":
                            vertical(ground, y(foot_top), x(base_left), origin - 80, label(), 104, origin - 95)
                            vertical(ground, y(foot_top), x(base_right), origin + 80, label(), 104, origin + 96)
                        else:
                            vertical(ground, y(foot_top), x(base_left), origin - 80, label(), 104, origin - 95)
                        if self.kind.startswith("water."):
                            water_index = ("high", "normal", "low").index(self.kind.split(".")[1])
                            if prefix == "b":
                                split = base_left + self.result["weights"]["cells"][f"G{220 + water_index * 34}"]
                                horizontal(x(base_left), x(split), y(foot_top), 34, label(), origin - 42)
                                horizontal(x(split), x(base_right), y(foot_top), 34, label(), origin + 42)
                            else:
                                text(origin - 60, max(14, water_y - 8), label())
                                vertical(water_y, y(0), x(base_right), origin + 80, label(), 70, origin + 96)
                    horizontal(x(0), centroid_x, centroid_y, 210, label(), origin)
                    corners = (base_left, -a8 / 2, a8 / 2, base_right)
                    for number, (first, last) in enumerate(zip(corners, corners[1:])):
                        horizontal(x(first), x(last), y(foot_top), 246, label(), origin + (number - 1) * 48)
                    horizontal(x(base_left), x(base_right), y(0), 282, label(), origin)
                    if prefix == "b" and (self.kind == "soil" or self.kind.startswith("water.")):
                        vertical(y(foot_top), y(geometry["h6"]), x(base_left), origin - 80, label(), 142, origin - 95)
                        if self.kind.startswith("water."):
                            vertical(y(geometry["h6"]), y(0), x(base_left), origin - 80, label(), 174, origin - 95)
                    if prefix == "w":
                        if self.kind.startswith("water."):
                            vertical(y(foot_top), y(0), x(base_right), origin + 80, label(), 154, origin + 96)
                        elif self.kind in ("column", "footing"):
                            first, last = (column_top, foot_top) if self.kind == "column" else (foot_top, geometry["h6"])
                            vertical(y(first), y(last), origin + 67, origin + 80, label(), 98, origin + 96)
                            vertical(y(foot_top if self.kind == "column" else geometry["h6"]), y(0), origin + 67, origin + 80, label(), 156, origin + 96)
                            vertical(centroid_y, y(0), centroid_x, origin - 80, label(), 146, origin - 95)
            if label_cursor != len(labels):
                raise ValueError("physical dimension annotation omitted")
            height = 300
        return measure_block(figure(width, height, *commands, block_id=self.block_id), context, available_width)


def _figure_block(unit: Unit) -> Block:
    kind, result = unit.value
    return indent_to(ReactionFigure(kind, result, unit.identifier), 93.96)


def semantic_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for unit in content(result):
        key = semantic_key(unit.key)
        text = "".join(figure_labels(unit.value[0], result)) if unit.kind == "figure" else plain(unit.value)
        if records and records[-1]["id"] == "0600/" + key:
            records[-1]["text"] += text
            records[-1]["unit_ids"].append(unit.identifier)
        else:
            records.append({"id": "0600/" + key, "text": text, "unit_ids": [unit.identifier]})
    return records


def semantic_key(key: str) -> str:
    if key.startswith("longitudinal.case."):
        return ".".join(key.split(".")[:3])
    if key.startswith("longitudinal.") and not key.startswith("longitudinal.summary"):
        return "longitudinal.introduction"
    if key.startswith("transverse.earthquake."):
        return "transverse.earthquake"
    return key + ".table" if key in ("longitudinal.summary", "transverse.summary") else key


def _table_block(unit: Unit) -> Block:
    rows = []
    for row_index, row in enumerate(unit.value):
        style = HEADING if row_index < unit.header_rows else BODY
        cells = []
        for value in row:
            if isinstance(value, tuple):
                cells.append(cell(CellLines(value, style=style, line_advance=14.28, min_height=14.28,
                                            inner_padding=Insets(1.08, 1.08, 1.08, 1.08))))
            elif re.search(r"[\u3040-\u30ff\u3400-\u9fff]", plain(value)):
                cells.append(cell(CellLines((plain(value),), style=style, line_advance=14.28, min_height=14.28,
                                            inner_padding=Insets(1.08, 1.08, 1.08, 1.08), wrap=True)))
            else:
                cells.append(Cell(CellLines((value,), style=style, min_height=14.28,
                                            inner_padding=Insets(1.08, 1.08, 1.08, 1.08)), align="right", padding=0))
        rows.append(cells)
    return indent_to(PreferKeepTogether(table(unit.widths, rows, row_heights=None, header_rows=unit.header_rows,
                                              block_id=unit.identifier)), 93.96)


def _keep_group(key: str) -> str:
    if key.startswith("weights."):
        pieces = key.split(".")
        return ".".join(pieces[:3] if len(pieces) > 2 and pieces[1] == "water" else pieces[:2])
    if key.startswith("dead."):
        pieces = key.split(".")
        if pieces[1] in ("B", "C"):
            return ".".join(pieces[:3]) if len(pieces) > 2 and pieces[2].isdigit() else key
        if pieces[1] == "support":
            return "dead.support"
    if key.startswith("longitudinal.case."):
        pieces = key.split(".")
        return ".".join(pieces[:4]) if len(pieces) > 3 and pieces[3] in ("B", "C") else ".".join(pieces[:3]) + ".header"
    if key.startswith("transverse.earthquake."):
        return ".".join(key.split(".")[:4])
    if key.startswith(("longitudinal.brake.", "longitudinal.start.")):
        return "longitudinal.brake.introduction" if key.endswith(("heading", "note", "formula")) else ".".join(key.split(".")[:2])
    return key


def build_report(result: dict[str, Any]) -> Document:
    blocks: list[Block] = []
    units = content(result)
    for index, unit in enumerate(units):
        start = len(blocks)
        if unit.kind == "heading":
            if blocks:
                blocks.append(spacer(7.2))
            left = {"chapter": 58.92, "section": 73.44, "subsection": 87.96, "subsubsection": 102.48, "body": 117}[unit.style_role]
            blocks.append(heading(plain(unit.value), left=left, block_id=unit.identifier))
        elif unit.kind == "paragraph":
            blocks.append(paragraph(plain(unit.value), left=117, block_id=unit.identifier))
        elif unit.kind == "table":
            blocks.extend((_table_block(unit), spacer(7.2)))
        elif unit.kind == "figure":
            blocks.append(_figure_block(unit))
        elif unit.kind == "equation":
            blocks.append(equation_group(unit.value, left=117, first_equal=276.72,
                                         second_equal=436.44 if unit.value.result is not None else None,
                                         result_right=516.48 if unit.value.result is not None else None,
                                         unit_start=523.68 if unit.value.result is not None else None,
                                         block_id=unit.identifier))
        else:
            blocks.append(indent_to(MathBlock(unit.value, style=BODY, block_id=unit.identifier), 117))
        if index + 1 < len(units):
            following = units[index + 1]
            if (_keep_group(unit.key) == _keep_group(following.key)
                    or unit.kind == "heading"
                    or unit.kind == "paragraph" and following.kind in ("math", "equation", "table")):
                for number in range(start, len(blocks)):
                    blocks[number] = KeepWithNext(blocks[number])
    return report(*blocks, footer="6 - {page}")


def render(result: dict[str, Any], output_path: str | Path) -> None:
    document = build_report(result)
    pages = document.layout()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    render_pdf(pages, path, document.fonts, invariant=True)

"""0710 native manuscript, preserving the calculated snapshot and display arithmetic."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext
import math
from pathlib import Path
from typing import Any

from gridlayoutpdf import (
    Block, Cell, CellLines, Document, Equation, Insets, KeepWithNext, LayoutContext,
    LayoutPart, Leading, Line, Literal, MeasuredBlock, Point,
    Polyline, Rectangle, Row, Script, Spacer, Text, measure_block, render_pdf,
)

from ...frame_outline import Dimension, FrameLayout, TextExtent, build_outline, dimension_text, fit_frame, frame_dimensions
from ..document import heading, indent_to, paragraph, report, spacer
from ..equations import equation_group, script
from ..figures import figure, outline_segment
from ..styles import BODY, BODY_LEADING, HEADING, grid_units
from ..tables import table


DIRECTIONS = {"down": "↓", "up": "↑", "left": "←", "right": "→"}
LOAD_TYPES = {"fixed": "固定", "incremental": "増分", "limited_incremental": "限定増分"}


def number(value: float, places: int = 2) -> str:
    if not math.isfinite(value):
        raise ValueError("地震時帳票: 表示値には有限の数値が必要です")
    return f"{value:.{places}f}"


def formula_factors(values: dict[str, tuple[float, int]], expected: float,
                    evaluate: Callable[[dict[str, Decimal]], Decimal], *, places: int = 2) -> dict[str, str]:
    """Retain the former Decimal check and add only necessary display digits."""
    target = Decimal(number(expected, places))
    with localcontext() as context:
        context.prec = 60
        for extra in range(13):
            formatted = {}
            for key, (value, minimum) in values.items():
                text = number(value, minimum + extra)
                while len(text.partition(".")[2]) > minimum and text.endswith("0"):
                    text = text[:-1]
                formatted[key] = text
            try:
                displayed = evaluate({key: Decimal(text) for key, text in formatted.items()})
                rounded = displayed.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
            except DecimalException:
                continue
            if rounded == target:
                return formatted
    raise ValueError("地震時帳票: 表示因子と計算結果を整合させる精度を確保できません")


def plain(value: Any) -> str:
    """Read the authored manuscript, including structured scripts and equations."""
    if isinstance(value, str):
        return value
    if isinstance(value, Literal):
        return value.text
    if isinstance(value, Row):
        return "".join(plain(item) for item in value.items)
    if isinstance(value, Script):
        return plain(value.base) + (plain(value.superscript) if value.superscript else "") + (plain(value.subscript) if value.subscript else "")
    if isinstance(value, Equation):
        return (plain(value.lhs) + " " + value.relation + " " + plain(value.rhs)
                + (" " + value.result_relation + " " + plain(value.result) if value.result is not None else "")
                + (plain(value.unit) if value.unit is not None else ""))
    if isinstance(value, (tuple, list)):
        return " ".join(plain(item) for item in value)
    raise TypeError(f"Unsupported seismic manuscript: {type(value).__name__}")


@dataclass(frozen=True)
class Unit:
    identifier: str
    value: Any
    kind: str = "paragraph"
    left: float = 117


@dataclass(frozen=True)
class Tagged:
    """Carry source ownership through the public layout trace, never expected text."""

    block: Block
    identifier: str
    kind: str
    keep: bool = False

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        child = measure_block(self.block, context, available_width)

        def parts(source: tuple[LayoutPart, ...]) -> tuple[LayoutPart, ...]:
            return tuple(replace(part, metadata={**part.metadata, "semantic_id": self.identifier,
                                                 "semantic_kind": self.kind,
                                                 "command_count": len(part.commands)}) for part in source)

        return replace(child, parts=parts(child.parts), prefix=parts(child.prefix), block_id=self.identifier,
                       keep_with_next=(child.keep_with_next or self.keep or self.kind == "caption"
                                       or self.identifier.endswith("actions.note")))


def heading_gap() -> Block:
    """One reference leading before a heading, retained with that heading."""
    return KeepWithNext(spacer())


def wrapped_cell(value: Any, align: str = "left", minimum: float = 14.28) -> CellLines:
    """Wrap authored text at its fixed font size before native row allocation."""
    return CellLines(value if isinstance(value, tuple) else (value,), style=BODY, line_advance=12.84,
                     min_height=minimum, inner_padding=Insets(1.08, 1.08, 1.08, 1.08), align=align, wrap=True)


@dataclass(frozen=True)
class AuthoredTable:
    units: tuple[Unit, ...]
    widths: tuple[float, ...]
    left: float = 87.96
    header_rows: int = 1
    numeric_columns: tuple[int, ...] = ()
    minimum: float = 14.28

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        rows = tuple(tuple(Cell(wrapped_cell(value, "right" if col in self.numeric_columns else "center" if row < self.header_rows else "left",
                                             self.minimum), padding=0,
                                align="center" if row < self.header_rows else "right" if col in self.numeric_columns else "left")
                           for col, value in enumerate(unit.value)) for row, unit in enumerate(self.units))
        child = measure_block(indent_to(table(self.widths, rows, row_heights=None, header_rows=self.header_rows,
                                              block_id=self.units[0].identifier + "/table"), self.left), context, available_width)

        def tagged(source: tuple[LayoutPart, ...]) -> tuple[LayoutPart, ...]:
            parts = []
            for part in source:
                indices = part.metadata["source_rows"]
                if len(indices) != 1:
                    raise ValueError("Seismic tables require independently auditable, unmerged rows")
                unit = self.units[indices[0]]
                parts.append(replace(part, metadata={**part.metadata, "semantic_id": unit.identifier,
                                                      "semantic_kind": "table", "command_count": len(part.commands)}))
            return tuple(parts)

        return replace(child, prefix=tagged(child.prefix), parts=tagged(child.parts), prefer_keep=True)


def seismic_dimensions(frame: dict[str, Any], transverse: bool = False) -> tuple[Dimension, ...]:
    nodes = {node["id"]: node for node in frame["nodes"]}
    roles = frame["node_ids"]
    micro_top, footing_top, cap_top = (nodes[roles[key]]["y"] for key in ("column_base_micro_top", "footing_top", "cap_top"))
    heights = sorted({nodes[level["node_id"]]["y"] for level in frame.get("upper_levels", {}).values()
                      if nodes[level["node_id"]]["y"] > cap_top}) if transverse else []
    dimensions = []
    for dimension in frame_dimensions(frame):
        if dimension.name == "H4":
            dimension = replace(dimension, bottom=micro_top)
        elif dimension.column == 1 and dimension.top == cap_top and dimension.bottom == footing_top:
            dimension = replace(dimension, top=heights[-1] if heights else cap_top, bottom=micro_top)
        dimensions.append(dimension)
    previous = cap_top
    for top in heights:
        dimensions.append(Dimension("上部形状", top, previous))
        previous = top
    dimensions.extend(Dimension("柱下端微小部材", micro_top, footing_top, column) for column in (0, 1))
    return tuple(dimensions)


def frame_units(result: dict[str, Any], stage: str) -> tuple[Unit, ...]:
    frame, geometry = result["frame"], result["input"]["geometry"]
    values = [("nodes", tuple(str(node["id"]) for node in frame["nodes"])),
              ("members", tuple(str(member["id"]) for member in frame["members"])),
              ("vertical_dimensions", tuple(dimension_text(d) for d in seismic_dimensions(frame, stage == "0720")))]
    if stage == "0710":
        symbols = []
        for side in ("b", "c"):
            bearing = result["input"]["spans"][side]["bearing"]
            if bearing not in ("可動", "固定"):
                raise ValueError(f"0710帳票: 支承種別を表示できません: {bearing}")
            symbols.append({"可動": "M", "固定": "F"}[bearing])
        values.append(("bearings", tuple(symbols)))
    else:
        values.append(("overall_height", number(max(n["y"] for n in frame["nodes"]) - min(n["y"] for n in frame["nodes"]), 3)))
    prefix = "b" if stage == "0710" else "w"
    dimensions = [geometry[f"{prefix}{i}"] for i in (7, 8, 9)]
    values.append(("horizontal_dimensions", tuple(number(value, 3) for value in (*dimensions, sum(dimensions)))))
    return tuple(Unit(stage + "/frame." + key, value, "figure") for key, value in values)


@dataclass(frozen=True)
class SeismicFrame:
    result: dict[str, Any]
    stage: str
    width: float = 528
    height: float = 570

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        frame, geometry = self.result["frame"], self.result["input"]["geometry"]
        direction = "b" if self.stage == "0710" else "w"
        outline = build_outline(geometry, direction)
        dimension_style = HEADING

        def metrics(text: str, size: float) -> TextExtent:
            measured = context.fonts.measure(text, replace(HEADING, size=size))
            box = measured.bounds
            return TextExtent(measured.width, box.x, box.y, box.right, box.bottom)

        layout = fit_frame(outline, frame["nodes"], (16, 28, self.width - (42 if self.stage == "0720" else 16), self.height - 70),
                           members=frame["members"], dimensions=seismic_dimensions(frame, self.stage == "0720"),
                           measure_text=metrics, preferred_axis_x=210, dimension_label_gap=8)
        layout = self._clear_labels(layout, frame, metrics)
        commands: list[Any] = []
        owners: list[str] = []

        def add(command: Any, key: str = "geometry") -> None:
            commands.append(command)
            owners.append(self.stage + "/frame." + key)

        for component in outline.components:
            points = tuple(layout.point(*point) for point in component.points)
            for first, second in zip(points, (*points[1:], points[0]), strict=True):
                for command in outline_segment(first, second):
                    add(command)
        nodes = {node["id"]: node for node in frame["nodes"]}
        for member in frame["members"]:
            a, b = nodes[member["node_i"]], nodes[member["node_j"]]
            add(Line(*layout.point(a["x"], a["y"]), *layout.point(b["x"], b["y"]),
                     1.6 if member["behavior"] == "rigid" else .8))
        for node in frame["nodes"]:
            x, y = layout.point(node["x"], node["y"])
            add(Rectangle(x - 1.2, y - 1.2, 2.4, 2.4, stroke_width=.48))
            tx, ty = layout.node_labels[node["id"]]
            value = str(node["id"])
            add(Text(tx - metrics(value, 9.9).advance, ty, value, HEADING), "nodes")
            if node["id"] in (frame["node_ids"]["column_base_micro_top"], frame["node_ids"]["footing_top"]):
                add(Line(tx + 2, ty - 3, x - 2, y, .12))
        for member in frame["members"]:
            x, y = layout.member_labels[member["id"]]
            value = str(member["id"])
            width = metrics(value, 8).advance
            add(Rectangle(x - width / 2 - 2, y - 7, width + 4, 14, stroke_width=.35))
            add(Text(x - width / 2, y + 3, value, replace(HEADING, size=8)), "members")

        def vertical(dimension: Dimension, x: float, label_y: float, key: str) -> None:
            a, b = layout.y(dimension.top), layout.y(dimension.bottom)
            for yy in (a, b):
                add(Line(layout.extension_x, yy, x + 3, yy, .12))
            add(Line(x, a, x, b, .12))
            for yy, sign in ((a, 1), (b, -1)):
                add(Line(x, yy, x - 2, yy + sign * 4, .12))
                add(Line(x, yy, x + 2, yy + sign * 4, .12))
            if abs(label_y - (a + b) / 2) > 1:
                add(Line(x - 3, (a + b) / 2, x - 7, label_y, .12))
            value = dimension_text(dimension)
            width = context.fonts.measure(value, dimension_style).width
            add(Text(x - 7, label_y + width / 2, value, dimension_style, quarter_turns=1), key)

        for dimension, label_y in zip(layout.dimensions, layout.dimension_label_ys, strict=True):
            vertical(dimension, layout.dimension_xs[dimension.column], label_y, "vertical_dimensions")
        if self.stage == "0720":
            top, bottom = max(n["y"] for n in nodes.values()), min(n["y"] for n in nodes.values())
            vertical(Dimension("全高", top, bottom), layout.dimension_xs[1] + 26,
                     (layout.y(top) + layout.y(bottom)) / 2, "overall_height")
        else:
            cap = next(part for part in reversed(outline.components) if part.name in ("beam", "haunch", "shaft"))
            cap_top = max(p[1] for p in cap.points)
            positions = [(layout.point(min(p[0] for p in cap.points), cap_top)[0] - 26, layout.y(cap_top) + 23),
                         (layout.point(max(p[0] for p in cap.points), cap_top)[0] + 26, layout.y(cap_top) + 23)]
            if positions[0][0] < 16 or positions[1][0] > layout.extension_x - 14:
                positions = [(50, 14), (115, 14)]
            symbols = next(unit.value for unit in frame_units(self.result, self.stage) if unit.identifier.endswith("bearings"))
            for symbol, (x, y) in zip(symbols, positions, strict=True):
                add(Polyline(tuple(Point(x + 7 * math.cos(i * math.tau / 32), y + 7 * math.sin(i * math.tau / 32))
                                   for i in range(32)), width=.3, closed=True))
                add(Text(x - context.fonts.measure(symbol, HEADING).width / 2, y + 3, symbol, HEADING), "bearings")
        a, b, c = (geometry[f"{direction}{i}"] for i in (7, 8, 9))
        xs = [layout.point(x, 0)[0] for x in (-b / 2 - a, -b / 2, b / 2, b / 2 + c)]
        values = (a, b, c)
        fit = all(xs[i + 1] - xs[i] >= context.fonts.measure(number(value, 3), dimension_style).width + 6
                  for i, value in enumerate(values))
        for x in (xs[0], xs[-1]):
            add(Line(x, layout.y(0) + 7, x, self.height - 18, .12))
        for index, value in enumerate((*values, a + b + c)):
            y = self.height - (44 if index < 3 else 19)
            left, right = (xs[index], xs[index + 1]) if index < 3 else (xs[0], xs[-1])
            if index < 3 and not fit:
                # Keep narrow physical segments true to scale and list their dimensions in order.
                add(Text(28 + index * 125, y - 4, number(value, 3), dimension_style), "horizontal_dimensions")
                continue
            add(Line(left, y, right, y, .12))
            for x, sign in ((left, 1), (right, -1)):
                add(Line(x, y - 7, x, y + 5, .12))
                add(Line(x, y, x + sign * 4, y - 2, .12))
                add(Line(x, y, x + sign * 4, y + 2, .12))
            text = number(value, 3)
            add(Text((left + right - context.fonts.measure(text, dimension_style).width) / 2,
                     y - 4, text, dimension_style), "horizontal_dimensions")
        child = measure_block(figure(self.width, self.height, *commands, block_id=self.stage + "/frame"), context, available_width)
        return replace(child, parts=tuple(replace(part, metadata={**part.metadata, "semantic_command_owners": tuple(owners),
                                                                 "semantic_kind": "figure", "command_count": len(part.commands),
                                                                 "physical_scale": layout.scale,
                                                                 "physical_axis_x": layout.axis_x,
                                                                 "physical_bottom": layout.bottom}) for part in child.parts))

    def _clear_labels(self, layout: FrameLayout, frame: dict[str, Any], metrics: Callable[[str, float], TextExtent]) -> FrameLayout:
        ys = list(layout.dimension_label_ys)
        widths = [metrics(dimension_text(d), 9.9).advance for d in layout.dimensions]
        extensions = {layout.y(h) for d in layout.dimensions for h in (d.top, d.bottom)}
        for index, dimension in enumerate(layout.dimensions):
            if dimension.name != "柱下端微小部材" and not (dimension.name == "上部形状" and dimension.value * layout.scale < widths[index] + 6):
                continue
            desired = layout.y(dimension.top) - widths[index] / 2 - 7
            selected = False
            candidates = sorted((30 + offset * 2 for offset in range(int((self.height - 100) / 2))),
                                key=lambda candidate: abs(candidate - desired))
            for candidate in candidates:
                top, bottom = candidate - widths[index] / 2, candidate + widths[index] / 2
                if top < 30 or bottom > self.height - 70:
                    continue
                if dimension.name == "柱下端微小部材" and bottom > layout.y(dimension.top) - 3:
                    continue
                if any(top - 3 <= yy <= bottom + 3 for yy in extensions):
                    continue
                if any(d.column == dimension.column and i != index and abs(candidate - ys[i]) < (widths[index] + widths[i]) / 2 + 4
                       for i, d in enumerate(layout.dimensions)):
                    continue
                ys[index] = candidate
                selected = True
                break
            if not selected:
                raise ValueError("地震時帳票: 短区間寸法の文字位置を確保できません")
        labels = dict(layout.node_labels)
        roles = frame["node_ids"]
        for node in frame["nodes"]:
            if node["id"] not in (roles["column_base_micro_top"], roles["footing_top"]):
                continue
            x, y = layout.point(node["x"], node["y"])
            labels[node["id"]] = (x - 24, y + (-8 if node["id"] == roles["column_base_micro_top"] else 16))
        return replace(layout, dimension_label_ys=tuple(ys), node_labels=labels)


def inertia_units(result: dict[str, Any], stage: str, ordinal: int) -> tuple[Unit, ...]:
    units = []

    def add(key: str, value: Any, kind: str = "paragraph", left: float = 117) -> None:
        units.append(Unit(stage + "/inertia." + key, value, kind, left))

    add("heading", f"({ordinal}) 自重による地震時慣性力", "heading", 87.96)
    add("kh", Row("設計水平震度  ", script("K", subscript="h"), " = ", number(result["inertia"]["Kh"]), gap=0), "math")
    formulas = result["formulas"]
    pedestal = formulas["pedestal"]
    if pedestal["value"] or pedestal["moment"]:
        add("pedestal_heading", "・桁受けに作用する水平力")
        factors = pedestal["factors"]
        force = formula_factors({k: (factors[k], 2) for k in ("weight", "Kh")}, pedestal["value"], lambda v: v["weight"] * v["Kh"])
        moment = formula_factors({"H": (pedestal["value"], 2), "height": (factors["height"], 3)}, pedestal["moment"], lambda v: v["H"] * v["height"])
        add("pedestal_force", Equation("H", Row(force["weight"], " × ", force["Kh"], gap=0), result=number(pedestal["value"]), unit=" kN"), "equation")
        add("pedestal_moment", Equation("M", Row(moment["H"], " × ", moment["height"], gap=0), result=number(pedestal["moment"]), unit=" kN・m"), "equation")
    add("body_heading", "・橋脚く体に作用する水平力")
    distinct = formulas["beam_bottom"]["value"] != formulas["column"]["value"]
    entries = [("beam", "はり上" if distinct else "はり", "1", "beam_top")]
    if distinct:
        entries.append(("beam_bottom", "はり下", "2", "beam_bottom"))
    entries.append(("column", "柱", "3", "column"))
    for key, label, suffix, field in entries:
        formula = formulas[field]
        factors = formula["factors"]
        shown = formula_factors({k: (factors[k], 1 if k == "unit_weight" else 2) for k in ("b", "w", "unit_weight", "Kh")},
                                formula["value"], lambda v: v["b"] * v["w"] * v["unit_weight"] * v["Kh"])
        keys = ("w", "b", "unit_weight", "Kh") if field == "column" else ("b", "w", "unit_weight", "Kh")
        lhs = Row(label, script("H", subscript="w" + suffix), gap=4.92)
        add(key, Equation(lhs, " × ".join(shown[k] for k in keys), result=number(formula["value"]), unit=" kN/m"), "equation")
    add("footing_heading", "・フーチング重心に作用する水平力")
    footing = formulas["footing"]
    factors, geometry = footing["factors"], footing["geometry"]
    rectangular = geometry["h5"] == 0 and math.isclose(geometry["b"] * geometry["w"] * geometry["h6"], factors["weight"] / factors["unit_weight"], rel_tol=0, abs_tol=1e-5)
    values = {k: (factors[k], 2 if k == "Kh" else 1) for k in ("unit_weight", "displaced_unit_weight", "Kh")}
    if rectangular:
        try:
            shown = formula_factors({**values, **{k: (geometry[k], 2) for k in ("b", "w", "h6")}}, footing["value"],
                                    lambda v: v["b"] * v["w"] * v["h6"] * (v["unit_weight"] - v["displaced_unit_weight"]) * v["Kh"])
        except ValueError:
            rectangular = False
    if rectangular:
        volume = " × ".join(shown[k] for k in ("b", "w", "h6"))
    else:
        shown = formula_factors({**values, "weight": (factors["weight"], 2)}, footing["value"],
                                lambda v: v["weight"] / v["unit_weight"] * (v["unit_weight"] - v["displaced_unit_weight"]) * v["Kh"])
        volume = f"{shown['weight']} / {shown['unit_weight']}"
    add("footing", Equation("H", f"{volume} × ( {shown['unit_weight']} - {shown['displaced_unit_weight']} ) × {shown['Kh']}",
                            result=number(footing["value"]), unit=" kN"), "equation")
    return tuple(units)


def case_units(result: dict[str, Any], stage: str, chapter: int) -> tuple[Unit, ...]:
    units = []

    def add(key: str, value: Any, kind: str = "table", left: float = 87.96) -> None:
        units.append(Unit(stage + "/" + key, value, kind, left))

    add("cases.heading", f"{chapter}.3 作用の組合せ", "heading", 73.44)
    add("cases.basic_caption", "基本Case", "caption")
    add("cases.header", ("Case", "記号", "作用方向", "荷重種別", "荷　重　名　称"))
    for case in result["basic_cases"]:
        label = case["label"]
        if case["symbol"] in ("EQ1", "EQL", "EQ2"):
            if stage == "0710":
                kh = result["horizontal"]["girder" if case["symbol"] == "EQ1" else "train"]["Kh"] if case["symbol"] != "EQ2" else result["inertia"]["Kh"]
            else:
                kh = result["seismic_conditions"]["girder_Kh" if case["symbol"] == "EQ1" else "train_Kh"] if case["symbol"] != "EQ2" else result["inertia"]["Kh"]
            label += f"（Kh={number(kh)}）"
        add("cases.row." + str(case["id"]), (str(case["id"]), case["symbol"], DIRECTIONS[case["direction"]], LOAD_TYPES[case["load_type"]], label))
    add("combination.caption", "組合せCase", "caption")
    add("combination.header", ("Case", (script("α", subscript="f"), script("ρ", subscript="m")), ("作用", "方向"), "荷重補正係数＋基本Case", ("地盤抵抗", "TYPE")))
    for combination in result["combinations"]:
        expression = " + ".join(str(case["id"]) if coefficient == 1 else f"{coefficient:g}×{case['id']}"
                                for case, coefficient in zip(result["basic_cases"], combination["coefficients"], strict=True)
                                if stage == "0710" or coefficient != 0)
        add("combination.row." + str(combination["id"]), (str(combination["id"]), (number(combination["alpha_f"], 1), number(combination["rho_m"], 1)),
                                                         DIRECTIONS[combination["direction"]], expression, str(combination["ground_resistance_type"])))
    return tuple(units)


def content(result: dict[str, Any]) -> tuple[Unit, ...]:
    units = []

    def add(key: str, value: Any, kind: str = "paragraph", left: float = 117) -> None:
        units.append(Unit("0710/" + key, value, kind, left))

    add("title", "§10. 線路方向の計算（地震時）", "heading", 58.92)
    add("model.heading", "10.1 検討モデル", "heading", 73.44)
    add("model.caption", "(1) 骨組図", "heading", 87.96)
    units.extend(frame_units(result, "0710"))
    add("model.unit", "単位：m", "right")
    add("actions.heading", "10.2 作用の計算", "heading", 73.44)
    add("actions.note", "下記以外の作用は、0610 線路方向荷重（地震時以外）と同様とする。")
    add("train.heading", "(1) 列車荷重", "heading", 87.96)
    add("train.track", "・単線載荷", "heading", 102.48)
    add("train.header", ("", "鉛直力 (kN)", "アーム (m)", "モーメント (kN・m)"), "table")
    train = result["vertical"]["train"]["earthquake"]
    for side, label in (("B", "起点側  RＢ"), ("C", "終点側  RＣ")):
        row = train[side]
        add("train.row." + side, (label, number(row["N"]), number(row["arm"], 3), number(row["M"])), "table")
    add("train.total", ("合計", number(train["N"]), "", number(train["M"])), "table")
    add("horizontal.heading", "(2) 水平荷重", "heading", 87.96)
    add("horizontal.subheading", "1) 支承に働く水平荷重のまとめ", "heading", 102.48)
    add("horizontal.header", ("荷　重　種　別", ("起点桁", "(kN)"), ("終点桁", "(kN)")), "table")
    add("horizontal.condition", ("地震時", "", ""), "table")
    for field, label in (("girder", "桁荷重"), ("train", "列車荷重")):
        values = result["horizontal"][field]
        add("horizontal." + field, (f"1.0 EＱ（{label}）", number(values["B"]), number(values["C"])), "table")
    units.extend(inertia_units(result, "0710", 3))
    units.extend(case_units(result, "0710", 10))
    return tuple(units)


def records(units: Sequence[Unit]) -> list[dict[str, str]]:
    result = []
    for unit in units:
        value = unit.value
        if unit.identifier.endswith("combination.header"):
            value = tuple(value[index] for index in (0, 3, 1, 2, 4))
        result.append({"id": unit.identifier, "text": plain(value)})
    return result


def semantic_records(result: dict[str, Any]) -> list[dict[str, str]]:
    return records(content(result))


def build_units(result: dict[str, Any], units: Sequence[Unit], stage: str) -> Document:
    if len({unit.identifier for unit in units}) != len(units):
        raise ValueError(f"{stage}帳票: duplicate semantic unit IDs in calculated snapshot")
    blocks: list[Block] = []
    index = 0
    while index < len(units):
        unit = units[index]
        if unit.kind == "figure":
            blocks.append(SeismicFrame(result, stage))
            while index < len(units) and units[index].kind == "figure":
                index += 1
            continue
        if unit.kind == "table":
            group = [unit]
            index += 1
            while index < len(units) and units[index].kind == "table":
                group.append(units[index])
                index += 1
            if "/cases." in unit.identifier:
                widths, numeric = (36, 48, 48, 60, 288), (0,)
            elif "/combination." in unit.identifier:
                widths, numeric = (36, 36, 36, 312, 60), ()
            elif "/horizontal." in unit.identifier:
                widths, numeric = (240, 120, 120), (1, 2)
            else:
                widths, numeric = ((84, 192, 72, 132) if stage == "0720" else (120, 120, 96, 144)), (1, 2, 3)
            blocks.append(AuthoredTable(tuple(group), widths, left=87.96, numeric_columns=numeric,
                                        minimum=12.84 if stage == "0720" else 14.28))
            blocks.append(spacer())
            continue
        if unit.kind == "heading":
            if blocks and not isinstance(blocks[-1], Spacer):
                blocks.append(heading_gap())
            block = heading(plain(unit.value), left=unit.left, block_id=unit.identifier)
        elif unit.kind == "equation":
            block = Leading(equation_group(unit.value, left=102.48, first_equal=184.44,
                                   second_equal=460.32 if unit.value.result is not None else None,
                                   result_right=525.96 if unit.value.result is not None else None,
                                   unit_start=530.4 if unit.value.result is not None else None, block_id=unit.identifier),
                            grid_units(14.4))
        elif unit.kind == "math":
            block = Leading(indent_to(CellLines((unit.value,), style=BODY, line_advance=14.28), unit.left),
                            grid_units(BODY_LEADING))
        else:
            block = paragraph(plain(unit.value), left=unit.left, align="right" if unit.kind == "right" else "center" if unit.kind == "caption" else "left",
                              block_id=unit.identifier)
        # A "・" lead-in and its equations form one group, e.g. はり and 柱.
        following = units[index + 1] if index + 1 < len(units) else None
        # The Kh line introduces the first group, so it never ends a page alone.
        keep = ("/inertia." in unit.identifier and following is not None
                and (following.kind == "equation" and unit.kind in ("equation", "paragraph")
                     or unit.identifier.endswith("inertia.kh")))
        blocks.append(Tagged(block, unit.identifier, unit.kind, keep))
        index += 1
    return report(*blocks, footer=("10" if stage == "0710" else "11") + " - {page}")


def validate(result: dict[str, Any], stage: str, count: int) -> None:
    direction = "longitudinal" if stage == "0710" else "transverse"
    if result.get("schema_version") != 1 or result.get("stage") != stage or result.get("direction") != direction:
        raise ValueError(f"{stage}帳票: schema_version=1、stage={stage}の計算結果が必要です")
    if len(result["basic_cases"]) != count or len(result["combinations"]) != 1:
        raise ValueError(f"{stage}帳票: 基本{count}ケース・組合せ1ケースが必要です")
    if len(result["combinations"][0]["coefficients"]) != count:
        raise ValueError(f"{stage}帳票: 組合せ係数は{count}個必要です")


def build_report(result: dict[str, Any]) -> Document:
    validate(result, "0710", 8)
    return build_units(result, content(result), "0710")


def render(result: dict[str, Any], output_path: str | Path) -> None:
    document = build_report(result)
    pages = document.layout()
    render_pdf(pages, output_path, document.fonts, invariant=True)

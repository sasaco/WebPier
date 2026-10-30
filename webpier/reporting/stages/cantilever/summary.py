"""13.1 (3) 片持梁の自重 and (4) 荷重設計の集計 of one cantilever (Example2 13-23 to 13-29)."""

from __future__ import annotations

from ....calc.cantilever import CantileverResult, Side, SideResult
from ....calc.cantilever.actions import Action
from ....calc.reaction import ReactionResult
from ....calc.reaction.longitudinal import Snow
from ....core.printed import Printed
from ...numbers import printed
from ..reaction.manuscript import DETAIL, INDENTED, ITEM, SUBSECTION, CellSpec, Manuscript, TableSpec, cells
from ..reaction.tables import header
from .horizontal import combination

DASH = "－"
SNOW_TITLES = {Snow.S2: "(a) 2年確率", Snow.S10: "(b) 10年確率", Snow.S30: "(c) 30年確率"}
LOADING_LETTERS = {"ORIGIN_MAX": "(a)", "END_MAX": "(b)", "BOTH_MAX": "(c)"}


def _self_weight_table(side: SideResult) -> TableSpec:
    weight = side.geometry.self_weight
    gamma, b = printed(weight.unit_weight), printed(weight.rectangle.width)
    rect, haunch = weight.rectangle, weight.haunch
    rows = [header("", "算　式", "鉛直力\n(kN)", "アーム\n(m)", "モーメント\n(kN・m)"),
            (CellSpec("①", align="center"),
             CellSpec(f"{gamma} × {b} × {printed(rect.depth)} × {printed(rect.length)}", align="left"),
             *cells(rect.force, rect.arm, rect.moment)),
            (CellSpec("②", align="center"),
             CellSpec(f"{gamma} × {b} × {printed(haunch.depth)} × {printed(haunch.length)} × 1/2", align="left"),
             *cells(haunch.force, haunch.arm, haunch.moment)),
            (CellSpec("合計", align="center", colspan=2), *cells(weight.force), CellSpec(DASH, align="center"),
             *cells(weight.moment))]
    return TableSpec((2, 14, 4, 3, 4), tuple(rows), header_rows=1, numeric_columns=(2, 3, 4))


def _dash_or(value: Printed | None) -> CellSpec:
    return CellSpec(DASH, align="center") if value is None else CellSpec(printed(value), align="right")


def _action_table(action: Action) -> TableSpec:
    horizontal = any(row.h is not None for row in action.rows)
    arm = "Y\n(m)" if horizontal else "e\n(m)"
    rows = [(CellSpec("作用種別", colspan=2, align="center"), *header("N\n(kN)", "X\n(m)", "Md\n(kN・m)", "H\n(kN)", arm,
                                                                    "Mt\n(kN・m)"))]
    previous = None
    for row in action.rows:
        label = "" if row.label == previous else row.label
        previous = row.label
        n_cell = _blank(row.n) if horizontal else _dash_or(row.n)
        rows.append((CellSpec(label, align="left"), CellSpec(row.sublabel, align="left"), n_cell,
                     _blank(row.x) if horizontal else _dash_or(row.x) if row.n is not None else CellSpec("", align="center"),
                     _blank(row.md) if horizontal else _dash_or(row.md),
                     _blank(row.h), _dash_or(row.arm) if row.arm is not None else CellSpec("", align="center"),
                     _dash_or(row.mt)))
    if horizontal:
        total = (CellSpec("合計", colspan=2, align="right"), CellSpec(DASH, align="center"), CellSpec(DASH, align="center"),
                 CellSpec(DASH, align="center"), _dash_or(action.h), CellSpec(DASH, align="center"), _dash_or(action.mt))
    else:
        total = (CellSpec("合計", colspan=2, align="right"), _dash_or(action.n), CellSpec(DASH, align="center"),
                 _dash_or(action.md), CellSpec(DASH, align="center"), CellSpec(DASH, align="center"), _dash_or(action.mt))
    rows.append(total)
    return TableSpec((5, 5, 3, 3, 3, 3, 3, 3), tuple(rows), header_rows=1, numeric_columns=(2, 3, 4, 5, 6, 7))


def _blank(value: Printed | None) -> CellSpec:
    return CellSpec("", align="center") if value is None else CellSpec(printed(value), align="right")


def _title(action: Action, snow: bool) -> tuple[str, str | None]:
    """The heading of an action's table: the numbered item and, for a loading or a wind, its sub-item. Without snow,
    3) 雪荷重S is not printed and the items after it move up (decision 69)."""
    key = action.key

    def n(number: int) -> int:
        return number if snow or number < 3 else number - 1

    if key.kind in ("D1", "D2"):
        return ("1) 固定死荷重D1" if key.kind == "D1" else "2) 付加死荷重D2"), None
    if key.kind == "S":
        return "3) 雪荷重S", SNOW_TITLES[Snow[key.variant]]
    if key.kind == "L":
        return f"{n(4)}) 列車荷重L", ("(d) 地震時列車荷重" if key.variant == "地震時"
                                 else f"{LOADING_LETTERS[key.variant]} {action.title.split(' ', 1)[1]}")
    if key.kind == "I":
        group, loading = key.variant.split(":")
        return f"{n(5)}) 衝撃荷重I", f"{'(a) 安全性(破壊)' if group == 'ULTIMATE' else '(b) 使用性'}　{LOADING_LETTERS[loading][1]}) " \
            f"{action.title.rsplit(' ', 1)[1]}"
    if key.kind == "LF":
        return f"{n(6)}) 車両横荷重LF", f"{LOADING_LETTERS[key.variant]} {action.title.split(' ', 1)[1]}"
    if key.kind == "W":
        return f"{n(7)}) 風荷重W", f"({'ab'[key.variant == 'WITHOUT_TRAIN']}) {action.title.split(' ', 1)[1]}"
    if key.kind == "EQ":
        return f"{n(8)}) 地震時直角方向EQ", None
    return action.title, None


def section(m: Manuscript, side: Side, side_name: str, result: SideResult, whole: CantileverResult,
            reaction: ReactionResult) -> None:
    key = side.name.lower()
    m.heading(f"{key}.weight.heading", f"(3) 片持梁の自重（{side_name}）", SUBSECTION)
    m.paragraph(f"{key}.weight.section", "設計断面：柱前面", gap=True)
    m.table(f"{key}.weight.table", _self_weight_table(result), SUBSECTION)
    m.heading(f"{key}.actions.heading", f"(4) 荷重設計の集計（{side_name}）", SUBSECTION)
    previous_title = None
    snow = any(action.key.kind == "S" for action in result.actions)
    bearing_number = 9 if snow else 8
    for action in result.actions:
        title, subtitle = _title(action, snow)
        action_key = f"{key}.actions.{action.key.kind}.{action.key.variant}".rstrip(".")
        if action.key.kind == "LRB":  # one table per case with bearing forces (decision 125), with its combination
            m.heading(f"{action_key}.heading", f"{bearing_number}) Case {action.key.variant} {action.title}", ITEM)
            case = next(item for item in result.cases if str(item.number) == action.key.variant)
            m.paragraph(f"{action_key}.combination", combination(case), INDENTED)
            bearing_number += 1
        else:
            if title != previous_title:
                m.heading(f"{action_key}.item", title, ITEM)
                previous_title = title
            if subtitle is not None:
                m.heading(f"{action_key}.heading", subtitle, DETAIL)
        m.table(f"{action_key}.table", _action_table(action), SUBSECTION)


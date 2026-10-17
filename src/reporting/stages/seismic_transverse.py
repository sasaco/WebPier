"""0720 native flowing report with every active bearing's substitution retained."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document, Equation, Row, render_pdf

from .seismic_longitudinal import (
    Unit, build_units, case_units, formula_factors, frame_units, inertia_units,
    number, records, validate,
)


def train_factors(row: dict[str, Any]) -> dict[str, str]:
    """Keep one printed source/rate pair valid for both force and moment."""
    values = {"source": (row["upstream_N"], 2), "rate": (row["factor"], 3), "arm": (row["arm"], 3)}
    target_force, target_moment = Decimal(number(row["N"])), Decimal(number(row["M"]))
    with localcontext() as context:
        context.prec = 60
        for extra in range(13):
            shown = {key: number(value, minimum + extra) for key, (value, minimum) in values.items()}
            if extra:
                shown = {key: value.rstrip("0").rstrip(".") for key, value in shown.items()}
            source, rate, arm = (Decimal(shown[key]) for key in ("source", "rate", "arm"))
            force = source * rate
            if (force.quantize(Decimal(".01"), rounding=ROUND_HALF_UP) == target_force
                    and (force * arm).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) == target_moment):
                return shown
    raise ValueError("0720帳票: 支承ごとの表示因子と計算結果を整合させる精度を確保できません")


def content(result: dict[str, Any]) -> tuple[Unit, ...]:
    units = []

    def add(key: str, value: Any, kind: str = "paragraph", left: float = 117) -> None:
        units.append(Unit("0720/" + key, value, kind, left))

    def equation(key: str, lhs: str, rhs: str, value: float | None = None, unit: str = "kN", places: int = 2) -> None:
        if value is None:
            add(key, Equation(lhs, Row(rhs, " " + unit, gap=0)), "equation")
        else:
            add(key, Equation(lhs, rhs, result=number(value, places), unit=" " + unit), "equation")

    add("title", "§11. 線路直角方向の計算（地震時）", "heading", 58.92)
    add("model.heading", "11.1 検討モデル", "heading", 73.44)
    add("model.caption", "(1) 骨組図", "heading", 87.96)
    units.extend(frame_units(result, "0720"))
    levels = result["frame"]["upper_levels"]
    add("model.upper_levels", "上部形状高（h1＋h2）：" + "、".join(f"{side} {number(levels[side]['height'], 3)} m" for side in ("B", "C")))
    add("model.unit", "単位：m", "right")
    add("actions.heading", "11.2 作用の計算（1）", "heading", 73.44)
    add("actions.note", "下記以外の作用は、0620 線路直角方向荷重（地震時以外）と同様とする。")
    add("train.heading", "(5) 列車荷重", "heading", 87.96)
    for track, label in (("up", "上り"), ("down", "下り")):
        action = result["vertical"]["train"][track]
        add(f"train.{track}.caption", f"・{label}線載荷", "heading", 102.48)
        add(f"train.{track}.header", ("", "鉛直力 (kN)", "アーム (m)", "モーメント (kN・m)"), "table")
        for row in action["rows"]:
            if not row["active"] and row["raw_N"] == 0:
                continue
            shown = train_factors(row)
            side = "起点側" if row["side"] == "B" else "終点側"
            substitution = Row(shown["source"], " × ", shown["rate"], " = ", number(row["N"]), gap=0)
            add(f"train.{track}.row.{row['side']}.{row['bearing']}",
                (f"{side} G{row['bearing']}", substitution, shown["arm"], number(row["M"])), "table")
        add(f"train.{track}.total", ("", "Σ " + number(action["table_totals"]["N"]), "", "Σ " + number(action["table_totals"]["M"])), "table")
    add("train.rounding_note", "Mは丸め前鉛直力×アーム、合計Mは各行表示値の和とする。")
    add("girder.heading", "(6) 地震時桁荷重慣性力", "heading", 87.96)
    add("girder.definition", "・起終点側の等価作用（橋脚天端）")
    action = result["horizontal"]["girder"]
    for row in action["rows"]:
        values = row["formula"]["factors"]
        force = formula_factors({key: (values[key], 2) for key in ("D1", "D2", "S2", "Kh")},
                                row["H"], lambda f: (f["D1"] + f["D2"] + f["S2"]) * f["Kh"])
        moment = formula_factors({"H": (row["H"], 2), "height": (row["height"], 3)}, row["M"], lambda f: f["H"] * f["height"])
        equation(f"girder.{row['side']}.force", f"{row['side']}  H", f"( {force['D1']} + {force['D2']} + {force['S2']} ) × {force['Kh']}", row["H"])
        equation(f"girder.{row['side']}.moment", "M", f"{moment['H']} × {moment['height']}", row["M"], "kN・m")
    equation("girder.total_force", "合計   H", number(action["table_totals"]["H"]))
    equation("girder.total_moment", "M", number(action["table_totals"]["M"]), unit="kN・m")
    add("actions.continuation_heading", "11.2 作用の計算（2）", "heading", 73.44)
    add("train_horizontal.heading", "(7) 地震時列車荷重慣性力", "heading", 87.96)
    action = result["horizontal"]["train"]
    kh = action["rows"][0]["formula"]["factors"]["Kh"]
    add("train_horizontal.definition", f"・橋脚天端に作用する荷重（Kh={number(kh)} 適用済み）")
    for row in action["rows"]:
        values = row["formula"]["factors"]
        factors = formula_factors({"source": (values["earthquake_reaction"], 2), "Kh": (values["Kh"], 2)}, row["H"], lambda f: f["source"] * f["Kh"])
        height = formula_factors({key: (values[key], 3) for key in ("h1", "h2", "h3", "height_seismic")}, row["height"], lambda f: sum(f.values()), places=3)
        equation(f"train_horizontal.{row['side']}.force", f"{row['side']}  H", f"{factors['source']} × {factors['Kh']}", row["H"])
        equation(f"train_horizontal.{row['side']}.height", "h", " + ".join(height[key] for key in ("h1", "h2", "h3", "height_seismic")), row["height"], "m", 3)
    totals = action["table_totals"]
    equation("train_horizontal.total_force", "水平力   H", " + ".join(number(row["H"]) for row in action["rows"]), totals["H"])
    factors = formula_factors({key: (value, 3 if key.startswith("h") else 2)
                              for i, row in enumerate(action["rows"]) for key, value in ((f"H{i}", row["H"]), (f"h{i}", row["height"]))},
                             totals["M"], lambda f: sum(f[f"H{i}"] * f[f"h{i}"] for i in range(len(action["rows"]))))
    expression = " + ".join(f"{factors[f'H{i}']} × {factors[f'h{i}']}" for i in range(len(action["rows"])))
    equation("train_horizontal.total_moment", "モーメント   M", expression, totals["M"], "kN・m")
    units.extend(inertia_units(result, "0720", 8))
    units.extend(case_units(result, "0720", 11))
    return tuple(units)


def semantic_records(result: dict[str, Any]) -> list[dict[str, str]]:
    return records(content(result))


def build_report(result: dict[str, Any]) -> Document:
    validate(result, "0720", 9)
    return build_units(result, content(result), "0720")


def render(result: dict[str, Any], output_path: str | Path) -> None:
    document = build_report(result)
    pages = document.layout()
    render_pdf(pages, output_path, document.fonts, invariant=True)

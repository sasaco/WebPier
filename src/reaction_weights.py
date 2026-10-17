"""0600 dead loads, component weights, soil and buoyancy from typed inputs.

Cell addresses preserve the calculation's provenance. All formulas below are
ordinary Python mathematics; workbook files and cached values are not read.
"""

from __future__ import annotations

from dataclasses import asdict
from decimal import DecimalException
import math
from typing import Any

from .inputs import InputError
from .reaction_inputs import ReactionGeometry, ReactionInput, SNOW_LOAD_CASES
from .reaction_math import excel_round


def _finite(value: Any, context: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _finite(item, f"{context}.{key}")
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _finite(item, f"{context}[{index}]")
    elif isinstance(value, (int, float)) and not math.isfinite(value):
        raise InputError(f"{context}: 計算結果が有限ではありません")


def calculate_dead(inputs: ReactionInput) -> dict[str, Any]:
    """Sum B/C bearing records and retain the validated A/D dead-load inputs."""
    cells: dict[str, float | None] = {}
    points: dict[str, dict[str, float]] = {}
    slots: dict[str, list[dict[str, Any]]] = {}
    factors: dict[str, tuple[float, ...]] = {}
    for side, rows, start in (("B", inputs.dead.b, 20), ("C", inputs.dead.c, 38)):
        slots[side] = []
        for index, row in enumerate(rows):
            column = ("M", "P", "S", "V", "Y")[index % 5]
            offset = start + (index // 5) * 8
            double_factor = row.factors[0] + row.factors[1]
            slots[side].append({**asdict(row), "double_factor": double_factor})
            cells[f"{column}{offset + 1}"] = row.d1
            cells[f"{column}{offset + 2}"] = row.d2
            cells[f"{column}{offset + 3}"] = row.factors[0]
            cells[f"{column}{offset + 4}"] = row.factors[1]
            cells[f"{column}{offset + 5}"] = double_factor
        d1, d2 = sum(row.d1 for row in rows), sum(row.d2 for row in rows)
        points[side] = {"D1": d1, "D2": d2, "total": d1 + d2}
        factors[side] = tuple(row.factors[0] + row.factors[1] for row in rows)
    for side, end in (("A", inputs.dead.a), ("D", inputs.dead.d)):
        points[side] = {"D1": end.d1, "D2": end.d2, "total": end.d1 + end.d2}
    girders = {
        "AB": {key: points["A"][key] + points["B"][key] for key in points["A"]},
        "CD": {key: points["C"][key] + points["D"][key] for key in points["C"]},
    }
    for point, column in (("A", "J"), ("B", "N"), ("C", "R"), ("D", "V")):
        for row, key in ((10, "D1"), (11, "D2"), (12, "total")):
            cells[f"{column}{row}"] = points[point][key]
    for girder, column in (("AB", "Z"), ("CD", "AD")):
        for row, key in ((10, "D1"), (11, "D2"), (12, "total")):
            cells[f"{column}{row}"] = girders[girder][key]
    result = {"points": points, "girders": girders, "slots": slots,
              "double_track_factors": factors,
              "track_totals": {side: sum(values) for side, values in factors.items()},
              "cells": cells}
    _finite(result, "死荷重")
    return result


def calculate_snow(inputs: ReactionInput) -> dict[str, Any]:
    """Aggregate each independent snow case without creating Excel cells."""
    points: dict[str, dict[str, float]] = {}
    slots: dict[str, list[dict[str, float]]] = {}
    for side, side_name, rows in (("B", "起点側", inputs.snow.b), ("C", "終点側", inputs.snow.c)):
        slots[side] = [dict(zip((key for key, _ in SNOW_LOAD_CASES), row)) for row in rows]
        points[side] = {}
        for key, _ in SNOW_LOAD_CASES:
            total = 0.0
            for index, slot in enumerate(slots[side]):
                total += slot[key]
                if not math.isfinite(total):
                    path = f"上部工反力.{side_name}.{side}支点.支承[{index}].{key}"
                    raise InputError(f"{path}: 雪荷重の明細合計が有限ではありません")
            points[side][key] = total
    for side, fallback_side, values in (("A", "B", inputs.snow.a), ("D", "C", inputs.snow.d)):
        points[side] = {
            key: points[fallback_side][key] if value is None else value
            for (key, _), value in zip(SNOW_LOAD_CASES, values)
        }
    girders: dict[str, dict[str, float]] = {}
    for name, first, second, side_name, end in (
        ("AB", "A", "B", "起点側", "A"), ("CD", "C", "D", "終点側", "D"),
    ):
        girders[name] = {}
        for key, _ in SNOW_LOAD_CASES:
            value = points[first][key] + points[second][key]
            if not math.isfinite(value):
                path = f"上部工反力.{side_name}.{end}支点.合計.{key}"
                raise InputError(f"{path}: 雪荷重の{name}主桁合計が有限ではありません")
            girders[name][key] = value
    return {"points": points, "girders": girders, "slots": slots}


def _area(b: float, w: float, label: str, *, required: bool = True) -> float:
    raw = b * w
    result = excel_round(raw, 3)
    if result <= 0 and (required or raw != 0):
        raise InputError(f"{label}: 小数3桁に丸めた面積は正値が必要です")
    return result


def _volume_row(cells: dict[str, float], row: int, volume: float,
                xl: float, xc: float, height: float) -> None:
    for column, value in zip(("J", "N", "Q", "U", "X", "AB", "AE"),
                             (volume, xl, volume * xl, xc, volume * xc, height, volume * height)):
        cells[f"{column}{row}"] = value


def _soil_row(cells: dict[str, float], row: int, volume: float, xl: float, xc: float) -> None:
    for column, value in zip(("K", "O", "R", "V", "Y"), (volume, xl, volume * xl, xc, volume * xc)):
        cells[f"{column}{row}"] = value


def _weight_row(cells: dict[str, float], row: int, weight: float,
                xl: float, xc: float, height: float) -> None:
    for column, value in zip(("I", "M", "P", "T", "W", "AA", "AD"),
                             (weight, xl, weight * xl, xc, weight * xc, height, weight * height)):
        cells[f"{column}{row}"] = value


def _centroids(total: float, moments: tuple[float, ...], warnings: list[str],
               label: str, *, rounding: bool = True) -> tuple[float, ...]:
    if total == 0:
        if any(moment != 0 for moment in moments):
            raise InputError(f"{label}: 合計量が0でモーメントが非ゼロです")
        warnings.append(f"{label}: ゼロ量の重心を0と定義しました（除算を行わない拡張）。")
        return tuple(0.0 for _ in moments)
    return tuple(excel_round(moment / total, 3) if rounding else moment / total for moment in moments)


def _volume_total(cells: dict[str, float], rows: tuple[int, ...], total_row: int,
                  output_row: int, gamma: float, warnings: list[str], label: str) -> dict[str, float]:
    for column in ("J", "Q", "X", "AE"):
        cells[f"{column}{total_row}"] = sum(cells[f"{column}{row}"] for row in rows)
    volume = cells[f"J{total_row}"]
    moments = tuple(cells[f"{column}{total_row}"] for column in ("Q", "X", "AE"))
    coordinates = _centroids(volume, moments, warnings, label)
    values = (excel_round(volume * gamma, 2), *coordinates)
    for row, value in enumerate(values, output_row):
        cells[f"X{row}"] = value
    return dict(zip(("N", "xL", "xC", "hG"), values))


def _soil_total(cells: dict[str, float], rows: tuple[int, ...], total_row: int,
                output_row: int, gamma: float, warnings: list[str], label: str,
                *, rounding: bool = True) -> dict[str, float]:
    for column in ("K", "R", "Y"):
        cells[f"{column}{total_row}"] = sum(cells[f"{column}{row}"] for row in rows)
    volume = cells[f"K{total_row}"]
    coordinates = _centroids(volume, (cells[f"R{total_row}"], cells[f"Y{total_row}"]),
                             warnings, label, rounding=rounding)
    values = (excel_round(volume * gamma, 2), *coordinates)
    for row, value in enumerate(values, output_row):
        cells[f"X{row}"] = value
    return dict(zip(("N", "xL", "xC"), values))


def _weight_total(cells: dict[str, float], rows: tuple[int, ...], total_row: int,
                  output_row: int, warnings: list[str], label: str) -> dict[str, float]:
    # The source omits the first (pedestal) row only from the transverse moment.
    for column in ("I", "P", "W", "AD"):
        included = rows[1:] if column == "W" else rows
        cells[f"{column}{total_row}"] = sum(cells[f"{column}{row}"] for row in included)
    weight = cells[f"I{total_row}"]
    moments = tuple(cells[f"{column}{total_row}"] for column in ("P", "W", "AD"))
    values = (weight, *_centroids(weight, moments, warnings, label))
    for row, value in enumerate(values, output_row):
        cells[f"X{row}"] = value
    return dict(zip(("N", "xL", "xC", "hG"), values))


def calculate_weights(geometry: ReactionGeometry) -> dict[str, Any]:
    """Compute the original double-precision weight worksheet expressions."""
    try:
        result = _calculate_weights(geometry)
        _finite(result, "橋脚自重")
        return result
    except InputError:
        raise
    except (ArithmeticError, DecimalException, ValueError) as exc:
        raise InputError(f"橋脚自重: 入力または計算結果が数値範囲を超えています（{exc}）") from exc


def _beam_weight(g: ReactionGeometry, cells: dict[str, float],
                 warnings: list[str]) -> dict[str, float]:
    """Combine the beam prism and haunch at the beam-top reference."""
    lower_b, lower_w = g.b1 - g.b4 - g.b5, g.w1 - g.w4 - g.w5
    a1 = _area(g.b1, g.w1, "はり上面")
    a2 = _area(lower_b, lower_w, "はり下面")
    cells.update(X83=a1, X84=a2)
    xl, xc = (g.b5 - g.b4) / 2, (g.w5 - g.w4) / 2
    _volume_row(cells, 88, a1 * g.h2, xl, xc, -g.h2 / 2)
    ratio = a1 / a2
    height = -(g.h3 / 4 * (1 + 2 * math.sqrt(ratio) + 3 * ratio)
               / (1 + math.sqrt(ratio) + ratio) + g.h2)
    haunch_volume = g.h3 / 6 * (lower_b * g.w1 + g.b1 * lower_w + 2 * (a1 + a2))
    if g.h3 == 0:
        hxl = hxc = 0.0
        warnings.append("H3=0: はりハンチのゼロ体積・ゼロモーメントを定義し、元式の0除算を回避しました。")
    else:
        hxl = xl / g.h3 * (g.h3 + height + g.h2)
        hxc = xc / g.h3 * (g.h3 + height + g.h2)
    _volume_row(cells, 89, haunch_volume, hxl, hxc, height)
    return _volume_total(cells, (88, 89), 90, 92, g.unit_weight_body, warnings, "はり")


def _reference_weights(g: ReactionGeometry, components: dict[str, dict[str, float]],
                       cells: dict[str, float], warnings: list[str]
                       ) -> tuple[dict[str, float], dict[str, float]]:
    """Aggregate components at the pier and footing reference levels."""
    pedestal, beam, column, footing, soil = (
        components[name] for name in ("桁受け", "はり", "柱", "フーチング", "上載土")
    )
    # Pier-bottom reference. The pedestal uses its volume, not its weight.
    top_height = g.h4 + g.h3 + g.h2
    _weight_row(cells, 308, cells["X63"], pedestal["xL"], pedestal["xC"], top_height + pedestal["hG"])
    _weight_row(cells, 309, beam["N"], beam["xL"], beam["xC"], top_height + beam["hG"])
    _weight_row(cells, 310, column["N"], 0, 0, g.h4 / 2)
    pier_bottom = _weight_total(cells, (308, 309, 310), 311, 313, warnings, "柱下端集計")
    if cells["X63"] != 0:
        warnings.append("元式I308=X63を保持し、柱下端集計の桁受けには重量ではなく体積を加算します。")

    # Footing-bottom reference. Soil is included in N, with zero height moment.
    top_height += g.h5 + g.h6
    _weight_row(cells, 323, pedestal["N"], pedestal["xL"] + column["xL"],
                pedestal["xC"] + column["xC"], pedestal["hG"] + top_height)
    _weight_row(cells, 324, beam["N"], beam["xL"] + column["xL"],
                beam["xC"] + column["xC"], beam["hG"] + top_height)
    _weight_row(cells, 325, column["N"], column["xL"], column["xC"], column["hG"])
    _weight_row(cells, 326, footing["N"], footing["xL"], footing["xC"], footing["hG"])
    _weight_row(cells, 327, soil["N"], soil["xL"], soil["xC"], 0)
    footing_center = _weight_total(cells, (323, 324, 325, 326, 327), 328, 330, warnings, "フーチング基準集計")
    if cells["W308"] != 0 or cells["W323"] != 0:
        warnings.append("元式W311・W328を保持し、両集計の直角方向モーメントから桁受けを除外します。")
    # The source displays '-' in these cells. Zero was used only internally
    # for the soil's contribution to the height-moment sum.
    del cells["AA327"], cells["AD327"]
    return pier_bottom, footing_center


def _calculate_weights(g: ReactionGeometry) -> dict[str, Any]:
    _finite(asdict(g), "下部構造")
    cells: dict[str, float] = {}
    warnings: list[str] = []
    components: dict[str, dict[str, float]] = {}
    for prefix, column, count in (("b", "E", 9), ("w", "M", 9), ("h", "U", 6)):
        for i in range(1, count + 1):
            cells[f"{column}{i + 3}"] = getattr(g, f"{prefix}{i}")
    for row, value in enumerate((g.df1, g.df2, g.hw1, g.hw2, g.hw3), 4):
        cells[f"AI{row}"] = value
    for row, value in enumerate((g.unit_weight_body, g.unit_weight_footing,
                                 g.unit_weight_soil, g.unit_weight_displaced_soil), 4):
        cells[f"AT{row}"] = value

    # Pedestal: the source retains geometric eccentricities even at zero volume.
    area = _area(g.b3, g.w3, "桁受け", required=False)
    volume = area * g.h1
    pedestal = dict(N=excel_round(volume * g.unit_weight_body, 2),
                    xL=(2 * g.b2 + g.b3 - g.b1 - g.b4 + g.b5) / 2,
                    xC=(2 * g.w2 + g.w3 - g.w1 - g.w4 + g.w5) / 2,
                    hG=g.h1 / 2)
    components["桁受け"] = pedestal
    for row, value in enumerate((area, volume, *pedestal.values()), 62):
        cells[f"X{row}"] = value

    components["はり"] = _beam_weight(g, cells, warnings)

    # Column.
    column_area = _area(g.b6, g.w6, "柱")
    column_volume = column_area * g.h4
    column = dict(N=excel_round(column_volume * g.unit_weight_body, 2),
                  xL=(g.b7 - g.b9) / 2, xC=(g.w7 - g.w9) / 2,
                  hG=g.h4 / 2 + g.h5 + g.h6)
    components["柱"] = column
    for row, value in enumerate((column_area, column_volume, *column.values()), 111):
        cells[f"X{row}"] = value

    # Footing haunch and lower prism.
    bf, wf = g.b7 + g.b8 + g.b9, g.w7 + g.w8 + g.w9
    a1, a2 = _area(g.b8, g.w8, "フーチング上面"), _area(bf, wf, "フーチング下面")
    cells.update(X137=a1, X138=a2)
    ratio = a1 / a2
    height = (g.h5 / 4 * (1 + 2 * math.sqrt(ratio) + 3 * ratio)
              / (1 + math.sqrt(ratio) + ratio) + g.h6)
    footing_haunch_volume = g.h5 / 6 * (bf * g.w8 + g.b8 * wf + 2 * (a1 + a2))
    hxl = 0 if g.h5 == 0 else -(bf / 2 - (g.b7 + g.b8 / 2)) / g.h5 * (height - g.h6)
    hxc = 0 if g.h5 == 0 else -(wf / 2 - (g.w7 + g.w8 / 2)) / g.h5 * (height - g.h6)
    _volume_row(cells, 142, footing_haunch_volume, hxl, hxc, height)
    _volume_row(cells, 143, a2 * g.h6, 0, 0, g.h6 / 2)
    footing = _volume_total(cells, (142, 143), 144, 146, g.unit_weight_footing, warnings, "フーチング")
    components["フーチング"] = footing

    # Signed soil volumes. O177 deliberately references the column's xC.
    soil_top = bf * (g.df1 + g.df2) * 0.5 * wf
    if g.df1 + g.df2 == 0:
        soil_xl = 0.0
        warnings.append("土かぶりdf1=df2=0: 上載土175行のゼロ体積モーメントを0と定義しました。")
    else:
        soil_xl = bf * (g.df1 + 2 * g.df2) / (3 * (g.df1 + g.df2)) - bf / 2
    soil_column_height = (g.df1 - g.df2) / bf * (g.b9 + g.b8 / 2) + g.df2
    _soil_row(cells, 175, soil_top, soil_xl, 0)
    _soil_row(cells, 176, -column_area * soil_column_height, column["xL"], column["xC"])
    _soil_row(cells, 177, bf * wf * g.h5, column["xC"], 0)
    _soil_row(cells, 178, -footing_haunch_volume, hxl, hxc)
    soil = _soil_total(cells, (175, 176, 177, 178), 179, 181, g.unit_weight_soil, warnings, "上載土")
    components["上載土"] = soil
    if cells["K177"] != 0 and column["xC"] != column["xL"]:
        warnings.append("元式O177=X115を保持し、上載土177行のxLには柱のxCを使用します。")

    # Three water levels, preserving the source's signed base volume and widths.
    base = g.h5 + g.h6
    for name, hw, offset in (("高水位", g.hw1, 0), ("平水位", g.hw2, 34), ("低水位", g.hw3, 68)):
        rise = min(hw - base - min(g.df1, g.df2), abs(g.df1 - g.df2))
        wedge = min(0 if g.df1 == g.df2 else bf * rise / abs(g.df1 - g.df2), bf)
        rectangle = bf - wedge
        volumes = (
            bf * wf * min(min(g.df1, g.df2) + base, hw),
            column_area * max(hw - soil_column_height - base, 0),
            wedge * wf * max(rise, 0) * 0.5,
            rectangle * wf * max(rise, 0),
        )
        wedge_xl = (rectangle + wedge / 3 if g.df1 > g.df2 else 2 * wedge / 3) - bf / 2
        rectangle_xl = (rectangle / 2 if g.df1 > g.df2 else wedge + rectangle / 2) - bf / 2
        for row, volume, xl, xc in zip(range(212 + offset, 216 + offset), volumes,
                                       (0, column["xL"], wedge_xl, rectangle_xl),
                                       (0, column["xC"], 0, 0)):
            _soil_row(cells, row, volume, xl, xc)
        cells[f"G{220 + offset}"] = rectangle
        cells[f"L{220 + offset}"] = wedge
        cells[f"R{222 + offset}"] = rise
        components[name] = _soil_total(cells, tuple(range(212 + offset, 216 + offset)),
                                       216 + offset, 217 + offset, -10, warnings, name, rounding=False)
        if hw < 0:
            warnings.append(f"{name}: 負水位{hw:g}を元式どおり扱い、負の基部体積を保持しました（0へ補正しません）。")

    pier_bottom, footing_center = _reference_weights(g, components, cells, warnings)
    return {"components": components, "pier_bottom": pier_bottom,
            "footing_center": footing_center, "cells": cells, "warnings": tuple(warnings)}

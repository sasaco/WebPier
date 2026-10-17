"""Optional reinforcement input and physical placement, independent of Tk.

The document's optional ``鉄筋`` object supports versions 1 and 2 with Japanese
member keys. Version 2 adds explicit column distributions and editing snapshots.
All reinforcement lengths are millimetres. Column coordinates start at the
upper-left corner: X is the cross direction and Y is the rail direction.
These checks validate input and placement, not structural adequacy.
"""

from __future__ import annotations

from copy import deepcopy
from bisect import bisect_left, bisect_right
import math
from typing import Any

from .editor_model import EditorError
from . import column_rebar


MEMBERS = ("梁", "柱", "フーチング")
DIRECTIONS = ("線路", "直角")
MAX_PREVIEW_BARS = 10000
ROW_FIELDS = ("main_rows", "side_rows", "band_rows", "manual_positions")
FIELD_LABELS = {
    "concrete_strength_mpa": "コンクリート強度", "pure_cover_mm": "純かぶり",
    "diameter_mm": "鉄筋径", "per_face_count": "片面本数", "count": "本数",
    "layer": "段", "layers": "段数", "columns": "列数", "sets": "組数",
    "stack_order": "重ね順", "center_mm": "芯かぶり", "clear_gap_mm": "段間のあき",
    "pitch_mm": "配置間隔", "start_mm": "開始位置", "end_mm": "終了位置",
    "width_pitch_mm": "幅方向の配置間隔", "distribution_width_mm": "配置幅",
    "column_pitch_mm": "列の芯間隔", "effective_legs": "有効脚数",
    "density_per_m": "幅方向の配置密度", "x_mm": "X座標", "y_mm": "Y座標",
    "face_direction": "面の方向", "direction": "方向", "face": "面",
    "bar_type": "主筋の形状", "cover_mode": "芯かぶりの決め方",
    "endpoints": "端部の鉄筋", "stirrup_position": "スターラップとの内外関係",
    "type": "横補強筋の種類", "material": "材質",
    "legs_mode": "有効脚数の決め方", "distribution_mode": "幅方向の指定方法",
}
ROW_LABELS = {"main_rows": "主筋", "side_rows": "側面筋", "band_rows": "横補強筋",
              "manual_positions": "指定位置"}
INTEGER_FIELDS = {"per_face_count", "count", "layer", "layers", "columns", "stack_order", "effective_legs"}
POSITIVE_FIELDS = {"diameter_mm", "pitch_mm", "width_pitch_mm", "density_per_m",
                   "column_pitch_mm", "layer", "layers", "columns", "stack_order", "concrete_strength_mpa"}
NUMERIC_FIELDS = set(FIELD_LABELS) - {
    "face_direction", "direction", "face", "bar_type", "cover_mode", "endpoints",
    "stirrup_position", "type", "material",
    "legs_mode", "distribution_mode",
}
ENUM_FIELDS = {
    "face_direction": DIRECTIONS, "direction": DIRECTIONS,
    "face": ("上", "下"), "bar_type": ("ループ筋", "直筋"),
    "cover_mode": ("自動", "指定"), "endpoints": ("含む", "含めない"),
    "stirrup_position": ("内側", "外側"), "type": ("外巻き", "内側"),
    "legs_mode": ("自動", "指定"), "distribution_mode": ("間隔", "密度"),
}


class GeometryIncomplete(EditorError):
    """A needed dimension is missing/null; other available cuts still validate."""


def _member_name(member: str) -> None:
    if member not in MEMBERS:
        raise EditorError("鉄筋の部材は梁・柱・フーチングから選んでください")


def _number(value: Any, label: str, *, positive: bool = False,
            integer: bool = False, nullable: bool = True) -> float | int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EditorError(f"{label}: 数値または空欄が必要です")
    try:
        finite = math.isfinite(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise EditorError(f"{label}: 有限の数値が必要です") from exc
    if not finite:
        raise EditorError(f"{label}: 有限の数値が必要です")
    if value < 0 or (positive and value == 0):
        condition = "0より大きい数値" if positive else "0以上の数値"
        raise EditorError(f"{label}: {condition}が必要です")
    if integer and int(value) != value:
        raise EditorError(f"{label}: 整数が必要です")
    return value


def _text(value: Any, label: str) -> None:
    if value is not None and not isinstance(value, str):
        raise EditorError(f"{label}: 文字列または空欄が必要です")


def _blank_main(member: str, **values: Any) -> dict:
    row = {"diameter_mm": None, "material": None, "cover_mode": "自動",
           "center_mm": None, "clear_gap_mm": None}
    if member == "柱":
        row.update(face_direction="線路", layer=1, per_face_count=None, endpoints="含む")
    elif member == "梁":
        row.update(face="上", bar_type="直筋", layer=1, count=None)
    else:
        row.update(direction="線路", face="上", pitch_mm=None, layers=1, stack_order=1)
    row.update(values)
    return row


def blank_member(member: str) -> dict:
    """Return a detached virtual form, without sample steel, strength or cover."""
    _member_name(member)
    if member == "柱":
        main = [_blank_main(member, face_direction=direction) for direction in DIRECTIONS]
    elif member == "梁":
        main = [_blank_main(member, face=face) for face in ("上", "下")]
    else:
        main = [_blank_main(member, direction=direction, face=face, stack_order=index + 1)
                for index, direction in enumerate(DIRECTIONS) for face in ("上", "下")]
    return {"materials": {"main": None, "transverse": None},
            "concrete_strength_mpa": None, "pure_cover_mm": None,
            "main_rows": main, "side_rows": [], "band_rows": [], "manual_positions": [],
            "position_mode": "基本"}


def blank_row(member: str, family: str) -> dict:
    """Virtual row defaults contain layout choices, never engineering values."""
    _member_name(member)
    if family == "main_rows":
        return _blank_main(member)
    if family == "side_rows":
        return {"diameter_mm": None, "material": None, "per_face_count": None, "columns": 1,
                "column_pitch_mm": None, "start_mm": None, "pitch_mm": None,
                "stirrup_position": "内側", "cover_mode": "自動", "center_mm": None}
    if family == "band_rows":
        row = {"type": "外巻き", "direction": "線路", "diameter_mm": None, "material": None,
               "sets": None, "pitch_mm": None, "start_mm": None, "end_mm": None,
               "legs_mode": "自動", "effective_legs": None}
        if member == "フーチング":
            row.update(distribution_mode="間隔", width_pitch_mm=None, density_per_m=None)
        return row
    if family == "manual_positions":
        return {"x_mm": None, "y_mm": None, "diameter_mm": None, "material": None}
    raise EditorError("配筋表の種類を確認してください")


def _root(document: dict) -> dict:
    if not isinstance(document, dict):
        raise EditorError("入力全体はオブジェクトが必要です")
    if "鉄筋" not in document:
        return {}
    root = document["鉄筋"]
    if not isinstance(root, dict):
        raise EditorError("鉄筋: オブジェクトが必要です")
    if "version" in root and (isinstance(root["version"], bool) or root["version"] not in (1, 2)):
        raise EditorError("鉄筋: 対応していない保存形式のバージョンです")
    column = root.get("柱")
    if root.get("version", 1) == 1 and isinstance(column, dict) and column_rebar.requires_v2(column):
        raise EditorError("鉄筋: 新しい柱入力には保存形式バージョン2が必要です")
    return root


def _merge(base: dict, supplied: dict) -> dict:
    result = deepcopy(base)
    for key, value in supplied.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _apply_changed_leaves(stored: dict, baseline: dict, candidate: dict) -> dict:
    """Retain missing virtual defaults while applying complete-form edits."""
    result = deepcopy(stored)
    for key, value in candidate.items():
        if key in baseline and value == baseline[key]:
            continue
        if isinstance(value, dict) and isinstance(baseline.get(key), dict):
            old = result.get(key, {})
            result[key] = _apply_changed_leaves(old if isinstance(old, dict) else {},
                                                baseline[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_member(document: dict, member: str) -> dict:
    """Read a detached virtual member without inserting missing document keys."""
    _member_name(member)
    root = _root(document)
    if member not in root:
        return blank_member(member)
    validate_member_shape(member, root[member])
    return _merge(blank_member(member), root[member])


def validate_member_shape(member: str, candidate: dict) -> None:
    """Validate containers before building widgets, leaving numeric repair open."""
    _member_name(member)
    if not isinstance(candidate, dict):
        raise EditorError(f"鉄筋 / {member}: オブジェクトが必要です")
    if "materials" in candidate and not isinstance(candidate["materials"], dict):
        raise EditorError(f"{member} / 材料: オブジェクトが必要です")
    for family in ROW_FIELDS:
        if family not in candidate:
            continue
        if not isinstance(candidate[family], list):
            raise EditorError(f"{member} / {ROW_LABELS[family]}: 行の配列が必要です")
        for index, row in enumerate(candidate[family]):
            if not isinstance(row, dict):
                raise EditorError(f"{member} / {ROW_LABELS[family]} [{index + 1}]: オブジェクトが必要です")
    if member == "柱":
        column_rebar.validate_shapes(candidate)


def validate_member(member: str, candidate: dict) -> None:
    """Accept incomplete blanks, reject malformed known values; keep extensions."""
    validate_member_shape(member, candidate)
    if candidate.get("position_mode", "基本") not in ("基本", "指定"):
        raise EditorError(f"{member} / 配置方法: 基本・指定から選んでください")
    materials = candidate.get("materials", {})
    if not isinstance(materials, dict):
        raise EditorError(f"{member} / 材料: オブジェクトが必要です")
    for key, label in (("main", "主筋材質"), ("transverse", "横補強筋材質")):
        _text(materials.get(key), f"{member} / {label}")
    for key in ("concrete_strength_mpa", "pure_cover_mm"):
        _number(candidate.get(key), f"{member} / {FIELD_LABELS[key]}", positive=key in POSITIVE_FIELDS)
    for family in ROW_FIELDS:
        rows = candidate.get(family, [])
        if not isinstance(rows, list):
            raise EditorError(f"{member} / {ROW_LABELS[family]}: 行の配列が必要です")
        for index, row in enumerate(rows):
            label = f"{member} / {ROW_LABELS[family]} [{index + 1}]"
            if not isinstance(row, dict):
                raise EditorError(f"{label}: オブジェクトが必要です")
            _validate_row_values(row, label)
            _validate_row_relationships(row, family, label)
    if member == "柱":
        column_rebar.validate_inputs(candidate)


def _validate_row_values(row: dict, label: str) -> None:
    for key in NUMERIC_FIELDS & row.keys():
        _number(row[key], f"{label} / {FIELD_LABELS[key]}",
                positive=key in POSITIVE_FIELDS, integer=key in INTEGER_FIELDS)
    for key, choices in ENUM_FIELDS.items():
        value = row.get(key)
        if value is not None and value not in choices:
            raise EditorError(f"{label} / {FIELD_LABELS[key]}: {'・'.join(choices)}から選んでください")
    _text(row.get("material"), f"{label} / 材質")


def _validate_row_relationships(row: dict, family: str, label: str) -> None:
    if family == "side_rows" and row.get("per_face_count") is not None and row["per_face_count"] > 0:
        if row.get("columns") is not None and row["columns"] > row["per_face_count"]:
            raise EditorError(f"{label} / 列数: 片面本数以下にしてください")
    if family == "band_rows" and row.get("legs_mode", "自動") == "自動":
        if all(row.get(key) is not None for key in ("diameter_mm", "sets", "pitch_mm")):
            if effective_legs(row) is None:
                raise EditorError(f"{label} / 有効脚数: 自動換算できません。有効脚数を指定してください")
    if row.get("start_mm") is not None and row.get("end_mm") is not None:
        if row["end_mm"] < row["start_mm"]:
            raise EditorError(f"{label} / 終了位置: 開始位置以上にしてください")


def effective_legs(row: dict) -> int | None:
    """Equivalent legs (1 set = 2 legs); width density is never a tie count."""
    if row.get("legs_mode", "自動") == "指定":
        value = row.get("effective_legs")
        return None if value is None else int(value)
    sets = row.get("sets")
    if sets is None:
        return None
    value = sets * 2
    if not math.isfinite(value) or int(value) != value:
        return None
    return int(value)


def patch_member(document: dict, member: str, candidate: dict) -> dict:
    """Copy-on-write patch from a COMPLETE member candidate, not sparse rows.

    Existing members apply changed leaves against load_member's virtual form,
    keeping unchanged missing/null defaults absent. Changed row lists are
    complete detached objects, including their unknown keys; replacing a list
    supports removal/reordering without transferring metadata by row index.
    A first patch of an absent member stores its complete candidate schema.
    The known column_hoops key can be explicitly removed to restore the legacy
    source; other omitted keys keep the established extension-preserving rules.
    """
    _member_name(member)
    root = _root(document)
    old = root.get(member, {})
    if not isinstance(old, dict):
        raise EditorError(f"鉄筋 / {member}: オブジェクトが必要です")
    validate_member(member, candidate)
    merged = (_apply_changed_leaves(old, load_member(document, member), candidate)
              if member in root else _merge(old, candidate))
    if member == "柱" and "column_hoops" in old and "column_hoops" not in candidate:
        merged.pop("column_hoops", None)
    if member == "柱" and "manual_basis" in candidate:
        # A new generation replaces its whole basis; recursive leaf merging
        # would retain the previous source (for example column_hoops).
        merged["manual_basis"] = deepcopy(candidate["manual_basis"])
    validate_member(member, merged)
    result = deepcopy(document)
    result.setdefault("鉄筋", {})["version"] = (2 if root.get("version") == 2
        or member == "柱" and column_rebar.requires_v2(merged) else 1)
    result["鉄筋"][member] = merged
    return result


def section_geometry(document: dict, member: str, direction: str = "線路") -> dict:
    """Read only needed raw dimensions in metres and return detached mm data."""
    _member_name(member)
    if direction not in DIRECTIONS:
        raise EditorError("断面の方向は線路・直角から選んでください")
    try:
        dimensions = document["下部構造"]["寸法"]
    except (KeyError, TypeError) as exc:
        raise GeometryIncomplete("下部構造 / 寸法: 断面図に必要な寸法を入力してください") from exc

    def dimension(group: str, key: str) -> float:
        try:
            value = dimensions[group][key]
        except (KeyError, TypeError) as exc:
            raise GeometryIncomplete(f"下部構造 / 寸法 / {key}: 寸法を入力してください") from exc
        if value is None:
            raise GeometryIncomplete(f"下部構造 / 寸法 / {key}: 寸法を入力してください")
        return float(_number(value, f"下部構造 / 寸法 / {key}", nullable=False)) * 1000

    def side(key: str) -> float:
        if key == "B9":
            try:
                raw = dimensions["側面"].get(key)
            except (KeyError, AttributeError, TypeError) as exc:
                raise GeometryIncomplete("下部構造 / 寸法 / B9: 寸法を入力してください") from exc
            if raw is None:
                return dimension("側面", "B7")
        return dimension("側面", key)

    if member == "柱":
        rail, cross = side("B6"), dimension("正面", "W6")
        result = {"width_mm": cross, "height_mm": rail, "rail_mm": rail, "cross_mm": cross}
        try:
            result["member_height_mm"] = dimension("高さ", "H4")
        except EditorError:
            pass  # H4 is optional for the independent cross-section preview.
    elif member == "梁":
        width = side("B1")
        h2, h3 = (dimension("高さ", key) for key in ("H2", "H3"))
        left, right = (side(key) for key in ("B4", "B5")) if h3 else (0.0, 0.0)
        lower_width = width - left - right
        if lower_width <= 0:
            raise EditorError("梁 / B1-B4-B5: ハンチ下幅は0より大きくしてください")
        result = {"width_mm": width, "height_mm": h2 + h3,
                  "haunch_mm": h3, "lower_width_mm": lower_width, "lower_left_mm": left}
    else:
        parts = ([side(f"B{i}") for i in (7, 8, 9)] if direction == "線路" else
                 [dimension("正面", f"W{i}") for i in (7, 8, 9)])
        h5, h6 = (dimension("高さ", key) for key in ("H5", "H6"))
        result = {"direction": direction, "width_mm": sum(parts), "height_mm": h5 + h6,
                  "top_width_mm": parts[1], "top_left_mm": parts[0], "taper_mm": h5}
    for key in ("width_mm", "height_mm"):
        _number(result[key], f"{member} / 断面寸法", positive=True, nullable=False)
    return result


def effective_center(member: dict, row: dict) -> float | None:
    """Resolve an explicit centre or a fully specified enclosing/layer build-up.

    The gap on layer N is the clear gap from layer N-1. A blank enclosing band,
    cover, earlier diameter, layer or gap leaves the derived value blank. Outer
    bands with differing zone diameters also leave it blank: this API has no
    selected elevation from which to choose one enclosing band.
    """
    return _center_resolver(member)(row)


def _center_resolver(member: dict):
    """Index predecessors once and resolve arbitrarily deep valid layer chains."""
    groups = {}
    for other in member.get("main_rows", []):
        for group_key in ("face_direction", "face"):
            key = (group_key, other.get(group_key),
                   None if group_key == "face_direction" else other.get("bar_type"),
                   other.get("layer", 1))
            groups.setdefault(key, []).append(other)
    centers, enclosing = {}, {}

    def resolve(row):
        trail = []
        while id(row) not in centers:
            if row.get("cover_mode", "自動") == "指定":
                value = row.get("center_mm")
                break
            if row.get("cover_mode", "自動") != "自動" or row.get("diameter_mm") is None:
                value = None
                break
            pure, layer = member.get("pure_cover_mm"), row.get("layer", 1)
            if pure is None or layer is None:
                value = None
                break
            # Integral JSON floats require exact subtraction even at 1e20.
            layer = int(layer)
            column = "face_direction" in row
            if column not in enclosing:
                enclosing[column] = _enclosing_diameter(member, column=column)
            diameter = row["diameter_mm"]
            if enclosing[column] is None:
                value = None
                break
            if layer == 1:
                value = pure + enclosing[column] + diameter / 2
                break
            group_key = "face_direction" if column else "face"
            key = (group_key, row.get(group_key), None if column else row.get("bar_type"), layer - 1)
            earlier = groups.get(key, [])
            if len(earlier) != 1 or earlier[0].get("diameter_mm") is None or row.get("clear_gap_mm") is None:
                value = None
                break
            trail.append((id(row), earlier[0]["diameter_mm"], row["clear_gap_mm"], diameter))
            row = earlier[0]
        else:
            value = centers[id(row)]
        centers[id(row)] = value
        for identity, previous_diameter, gap, diameter in reversed(trail):
            if value is not None:
                value = value + previous_diameter / 2 + gap + diameter / 2
            centers[identity] = value
        return value

    return resolve


def _effective_centers(member: dict) -> list[float | None]:
    resolve = _center_resolver(member)
    return [resolve(row) for row in member.get("main_rows", [])]


def _enclosing_diameter(member: dict, *, empty_is_absent: bool = False,
                        column: bool = False) -> float | None:
    if column and "column_hoops" in member:
        column_rebar.validate_hoops(member["column_hoops"])
        return member["column_hoops"].get("enclosing_diameter_mm")
    outside = [row for row in member.get("band_rows", []) if row.get("type") == "外巻き"]
    active = [row for row in outside if row.get("sets") != 0]
    if not active:
        return 0 if outside or empty_is_absent else None
    diameters = {row.get("diameter_mm") for row in active}
    return next(iter(diameters)) if len(diameters) == 1 and None not in diameters else None


def _face_positions(start: float, end: float, count: int, endpoints: str,
                    diameter: float, label: str) -> list[float]:
    if count == 1:
        return [(start + end) / 2]
    divisor = count - 1 if endpoints == "含む" else count + 1
    spacing = (end - start) / divisor
    if spacing < diameter - 1e-7:
        raise EditorError(f"{label}: 本数に対して鉄筋の配置間隔が不足しています")
    offset = 0 if endpoints == "含む" else 1
    positions = [start + (index + offset) * spacing for index in range(count)]
    if endpoints == "含む":
        positions[0], positions[-1] = start, end
    return positions


def _reject_overlapping_bars(bars: list[dict]) -> None:
    """Compare nearby discs after exact shared-corner deduplication.

    A cell is at least the maximum diameter, so an overlapping centre must lie
    in this cell or its eight neighbours. The preview cap bounds the index.
    """
    if not bars:
        return
    cell_size = max(bar["diameter_mm"] for bar in bars)
    cells: dict[tuple[int, int], list[dict]] = {}
    for bar in bars:
        cell = (math.floor(bar["x_mm"] / cell_size), math.floor(bar["y_mm"] / cell_size))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other in cells.get((cell[0] + dx, cell[1] + dy), []):
                    minimum = (bar["diameter_mm"] + other["diameter_mm"]) / 2
                    tolerance = max(1e-7, minimum * 1e-9)
                    distance = math.hypot(bar["x_mm"] - other["x_mm"],
                                          bar["y_mm"] - other["y_mm"])
                    if distance < minimum - tolerance:
                        indices = sorted(set(bar["row_indices"] + other["row_indices"]))
                        labels = "・".join(f"[{index + 1}]" for index in indices)
                        raise EditorError(f"鉄筋 {labels}: 鉄筋が重なっています。配置間隔を確認してください")
        cells.setdefault(cell, []).append(bar)


def column_bars(member: dict, geometry: dict) -> list[dict]:
    """Expand complete pairs; preview requests are limited to 10000 bars.

    The bound is checked before expanding each row, independently of save-time
    format validation. Identical physical corners count only once afterwards.
    """
    validate_member("柱", member)
    width = _number(geometry.get("cross_mm", geometry.get("width_mm")), "柱 / 直角幅",
                    positive=True, nullable=False)
    height = _number(geometry.get("rail_mm", geometry.get("height_mm")), "柱 / 線路幅",
                     positive=True, nullable=False)
    found: dict[tuple[float, float], dict] = {}
    requested_count = 0
    for index, (row, center) in enumerate(zip(member.get("main_rows", []), _effective_centers(member))):
        diameter, count = row.get("diameter_mm"), row.get("per_face_count")
        direction, endpoints = row.get("face_direction"), row.get("endpoints")
        if "distribution" in row:
            incomplete = bool(column_rebar.missing_fields(row, center))
        else:
            incomplete = None in (center, diameter, count, direction, endpoints)
        if incomplete or count == 0:
            continue
        label = f"柱 / 主筋 [{index + 1}]"
        requested_count += int(count) * 2
        if requested_count > MAX_PREVIEW_BARS:
            raise EditorError(f"{label}: 配筋図の鉄筋本数の上限は{MAX_PREVIEW_BARS}本です")
        normal_depth = height if direction == "線路" else width
        cover_depth = normal_depth if "distribution" in row else min(width, height)
        if center * 2 > cover_depth:
            raise EditorError(f"{label}: 芯かぶりが断面の半幅を超えています")
        across = width if direction == "線路" else height
        positions = (column_rebar.face_positions(row, across) if "distribution" in row else
                     _face_positions(center, across - center, int(count), endpoints, diameter, label))
        fixed = (center, height - center) if direction == "線路" else (center, width - center)
        if fixed[0] == fixed[1]:
            raise EditorError(f"{label}: 対向する面が同じ位置に重なっています")
        material = row.get("material") or member.get("materials", {}).get("main")
        for face in fixed:
            for position in positions:
                x, y = (position, face) if direction == "線路" else (face, position)
                radius = diameter / 2
                if min(x, y, width - x, height - y) < radius - 1e-7:
                    raise EditorError(f"{label}: 鉄筋が断面の外に配置されます")
                key = (x, y)
                if key in found:
                    existing = found[key]
                    if existing["diameter_mm"] != diameter or existing["material"] != material:
                        raise EditorError(f"{label}: 同じ位置に異なる径または材質の鉄筋が重なっています")
                    if direction in existing["face_directions"]:
                        raise EditorError(f"{label}: 同じ方向の鉄筋が同じ位置に重複しています")
                    existing["face_directions"].append(direction)
                    if index not in existing["row_indices"]:
                        existing["row_indices"].append(index)
                else:
                    found[key] = {"x_mm": x, "y_mm": y, "diameter_mm": diameter,
                                  "material": material, "row_indices": [index], "face_directions": [direction]}
    bars = list(found.values())
    _reject_overlapping_bars(bars)
    return bars


def column_layout(member: dict, geometry: dict) -> dict:
    """Return the detached automatic column placement for both direction views."""
    validate_member("柱", member)
    centers = _effective_centers(member)
    issues = []
    for index, (row, center) in enumerate(zip(member.get("main_rows", []), centers)):
        fields = column_rebar.missing_fields(row, center)
        if center is None and row.get("per_face_count") != 0 and row.get("cover_mode", "自動") == "自動":
            fields = [key for key in fields if key != "center_mm"]
            if member.get("pure_cover_mm") is None:
                fields.append("pure_cover_mm")
            if _enclosing_diameter(member, column=True) is None:
                fields.append("column_hoops.enclosing_diameter_mm" if "column_hoops" in member else "band_rows.diameter_mm")
            if row.get("layer", 1) is None:
                fields.append("layer")
            elif row.get("layer", 1) > 1:
                if row.get("clear_gap_mm") is None:
                    fields.append("clear_gap_mm")
                fields.append("previous_layer")
        if fields:
            names = {"distribution.pitch_mm": "配列ピッチ", "distribution.edge_center_mm": "端部芯距離",
                     "distribution.mode": "配列方法", "column_hoops.enclosing_diameter_mm": "外帯筋径",
                     "band_rows.diameter_mm": "外帯筋径", "previous_layer": "前段の芯位置・径"}
            message = f"主筋 [{index + 1}] 未入力: " + "・".join(names.get(key, FIELD_LABELS.get(key, key)) for key in fields)
            issues.append({"row_index": index, "fields": fields, "message": message})
    return {"bars": column_bars(member, geometry), "centers": centers,
            "issues": issues, "complete": not issues}


def column_detail_status(member: dict, geometry: dict) -> str:
    validate_member("柱", member)
    return column_rebar.detail_status(member, geometry)


def column_has_detail(member: dict) -> bool:
    validate_member("柱", member)
    return column_rebar.has_detail(member)


def _complete_column_layout(member: dict, geometry: dict) -> dict:
    layout = column_layout(member, geometry)
    if not layout["complete"]:
        raise EditorError("柱 / 自動配置が未完成です: " + " / ".join(issue["message"] for issue in layout["issues"]))
    return layout


def _validate_column_snapshot(candidate: dict, geometry: dict) -> None:
    validate_member("柱", candidate)
    for index, row in enumerate(candidate.get("manual_positions", [])):
        if any(row.get(key) is None for key in ("x_mm", "y_mm", "diameter_mm")):
            raise EditorError(f"柱 / 詳細位置 [{index + 1}]: X・Y・径をすべて入力してください")
    member_preview("柱", candidate, geometry)


def column_set_detail(member: dict, geometry: dict, positions: list[dict]) -> dict:
    """Validate a complete detached detail edit before replacing any state."""
    if member.get("position_mode", "基本") == "基本":
        _complete_column_layout(member, geometry)
    candidate = column_rebar.detail_candidate(member, geometry, positions)
    _validate_column_snapshot(candidate, geometry)
    return candidate


def column_edit_detail(member: dict, geometry: dict, index: int, changes: dict) -> dict:
    """The first actual edit copies the complete automatic physical layout."""
    positions = (deepcopy(_complete_column_layout(member, geometry)["bars"])
                 if member.get("position_mode", "基本") == "基本" else deepcopy(member.get("manual_positions", [])))
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(positions):
        raise EditorError("柱 / 詳細位置: 編集する鉄筋を選択してください")
    if not isinstance(changes, dict):
        raise EditorError("柱 / 詳細位置: 変更値はオブジェクトが必要です")
    positions[index].update(deepcopy(changes))
    return column_set_detail(member, geometry, positions)


def column_regeneration_preview(member: dict, geometry: dict) -> dict:
    """Generate a separate candidate, including when old detail is out of bounds."""
    layout = _complete_column_layout(member, geometry)
    automatic = deepcopy(member)
    automatic["position_mode"] = "基本"
    member_preview("柱", automatic, geometry)
    if member.get("position_mode", "基本") == "指定":
        old_bars = []
        for index, row in enumerate(member.get("manual_positions", [])):
            if any(row.get(key) is None for key in ("x_mm", "y_mm", "diameter_mm")):
                continue
            bar = _bar(member, row, "manual_positions", index, row["x_mm"], row["y_mm"])
            if "manual_basis" in member:
                bar["material"] = row.get("material")
            old_bars.append(bar)
    else:
        old_bars = deepcopy(layout["bars"])
    return {"candidate_bars": deepcopy(layout["bars"]),
            "basis": column_rebar.generation_basis(member, geometry),
            "source_token": column_rebar.source_token(member, geometry),
            "old_bars": old_bars}


def column_apply_regeneration(member: dict, geometry: dict, preview: dict,
                              *, to_auto: bool = False) -> dict:
    """Only apply the still-current complete candidate shown in the dialog."""
    if not isinstance(preview, dict) or preview.get("source_token") != column_rebar.source_token(member, geometry):
        raise EditorError("柱 / 再配置: 入力が変更されています。候補を再生成してください")
    fresh = column_regeneration_preview(member, geometry)
    if any(preview.get(key) != fresh[key] for key in ("candidate_bars", "basis", "old_bars")):
        raise EditorError("柱 / 再配置: 候補が変更されています。候補を再生成してください")
    candidate = column_rebar.apply_regeneration(member, fresh, to_auto=to_auto)
    if to_auto:
        member_preview("柱", candidate, geometry)
    else:
        _validate_column_snapshot(candidate, geometry)
    return candidate


def column_restore_detail(member: dict, geometry: dict) -> dict:
    if not column_has_detail(member):
        raise EditorError("柱 / 詳細位置: 退避した配置がありません")
    candidate = deepcopy(member)
    candidate["position_mode"] = "指定"
    _validate_column_snapshot(candidate, geometry)
    return candidate


def directional_rows(bars: list[dict], direction: str) -> list[dict]:
    """Aggregate physical bars by actual centre, diameter and material."""
    if direction not in DIRECTIONS:
        raise EditorError("配筋表の方向は線路・直角から選んでください")
    coordinate = "y_mm" if direction == "線路" else "x_mm"
    groups: dict[tuple[float, float, str | None], int] = {}
    for index, bar in enumerate(bars):
        label = f"鉄筋 [{index + 1}]"
        center = _number(bar.get(coordinate), f"{label} / 芯位置", nullable=False)
        diameter = _number(bar.get("diameter_mm"), f"{label} / 鉄筋径", positive=True, nullable=False)
        material = bar.get("material")
        _text(material, f"{label} / 材質")
        key = (round(center, 8), diameter, material)
        groups[key] = groups.get(key, 0) + 1
    return [{"center_mm": center, "diameter_mm": diameter, "count": count, "material": material}
            for (center, diameter, material), count in sorted(
                groups.items(), key=lambda item: (item[0][0], item[0][1], item[0][2] or ""))]


def section_outline(member: str, geometry: dict) -> list[tuple[float, float]]:
    """Physical section polygon, in mm and the same coordinates as the bars."""
    width, height = geometry["width_mm"], geometry["height_mm"]
    if member == "梁":
        shoulder = height - geometry["haunch_mm"]
        left = geometry["lower_left_mm"]
        right = left + geometry["lower_width_mm"]
        return [(0, 0), (width, 0), (width, shoulder), (right, height), (left, height), (0, shoulder)]
    if member == "フーチング":
        left, top, taper = (geometry[key] for key in ("top_left_mm", "top_width_mm", "taper_mm"))
        return [(left, 0), (left + top, 0), (width, taper), (width, height), (0, height), (0, taper)]
    return [(0, 0), (width, 0), (width, height), (0, height)]


def band_outline(member: str, candidate: dict, geometry: dict, row: dict) -> list:
    """Convex section offset to the explicitly entered outside-band centre."""
    pure, diameter = candidate.get("pure_cover_mm"), row.get("diameter_mm")
    if row.get("sets") == 0 or row.get("type") != "外巻き" or pure is None or diameter is None:
        return []
    inset = pure + diameter / 2
    _number(inset, f"{member} / 外巻きの芯位置", nullable=False)
    points = section_outline(member, geometry)
    edges = []
    for start, end in zip(points, points[1:] + points[:1]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length:
            normal = (-dy / length, dx / length)
            edges.append((normal[0], normal[1], normal[0] * start[0] + normal[1] * start[1] + inset))
    result = []
    for previous, current in zip(edges[-1:] + edges[:-1], edges):
        ax, ay, ac = previous
        bx, by, bc = current
        determinant = ax * by - ay * bx
        if abs(determinant) < 1e-12:
            continue
        result.append(((ac * by - ay * bc) / determinant, (ax * bc - ac * bx) / determinant))
    if not result or any(not math.isfinite(value) for point in result for value in point) or any(nx * x + ny * y < constant - 1e-6
                         for x, y in result for nx, ny, constant in edges):
        raise EditorError(f"{member} / 外巻き: 純かぶり・鉄筋径に対して断面内の配置幅が不足しています")
    return result


def _edge_span(member: str, geometry: dict, y: float) -> tuple[float, float]:
    width, height = geometry["width_mm"], geometry["height_mm"]
    if y < 0 or y > height:
        raise EditorError("鉄筋の芯位置が断面の外にあります")
    if member == "梁":
        haunch = geometry["haunch_mm"]
        if haunch and y > height - haunch:
            fraction = (y - (height - haunch)) / haunch
            left = geometry["lower_left_mm"] * fraction
            right = width + (geometry["lower_left_mm"] + geometry["lower_width_mm"] - width) * fraction
            return left, right
    elif member == "フーチング":
        taper = geometry["taper_mm"]
        if taper and y < taper:
            fraction = 1 - y / taper
            left = geometry["top_left_mm"] * fraction
            right = width + (geometry["top_left_mm"] + geometry["top_width_mm"] - width) * fraction
            return left, right
    return 0.0, width


def _safe_span(member: str, geometry: dict, y: float, diameter: float,
               cover: float) -> tuple[float, float]:
    radius = diameter / 2
    lower = _edge_span(member, geometry, y - radius)
    upper = _edge_span(member, geometry, y + radius)
    inset = max(radius, cover)
    left, right = max(lower[0], upper[0]) + inset, min(lower[1], upper[1]) - inset
    if right < left:
        raise EditorError("鉄筋の径・芯かぶりに対して断面内の配置幅が不足しています")
    return left, right


def _check_budget(count: int) -> None:
    if count > MAX_PREVIEW_BARS:
        raise EditorError(f"配筋図の鉄筋本数の上限は{MAX_PREVIEW_BARS}本です")


def _bar(member: dict, row: dict, family: str, index: int, x: float, y: float) -> dict:
    return {"x_mm": x, "y_mm": y, "diameter_mm": row["diameter_mm"],
            "material": row.get("material") or member.get("materials", {}).get("main"),
            "row_indices": [index], "family": family, "sources": [(family, index)]}


def _finish_bars(member: str, geometry: dict, bars: list[dict]) -> list[dict]:
    unique: dict[tuple[float, float], dict] = {}
    for bar in bars:
        x, y, diameter = bar["x_mm"], bar["y_mm"], bar["diameter_mm"]
        left, right = _safe_span(member, geometry, y, diameter, diameter / 2)
        if x < left - 1e-7 or x > right + 1e-7:
            raise EditorError("鉄筋の指定位置が断面の外にあります")
        key = (x, y)
        if key in unique:
            raise EditorError("同じ位置の鉄筋が重複しています。指定位置・段配置を確認してください")
        else:
            unique[key] = bar
    result = list(unique.values())
    _reject_overlapping_bars(result)
    return result


def _auto_warning(member: dict, row: dict) -> str:
    outer = {band.get("diameter_mm") for band in member.get("band_rows", [])
             if band.get("sets") != 0 and band.get("type") == "外巻き" and band.get("diameter_mm") is not None}
    if len(outer) > 1:
        return "自動算定不可：外帯筋径が区間で異なるため芯位置を指定"
    return "自動芯位置：純かぶり・外帯筋径・主筋径・前段の径とあきを入力してください"


def side_offsets(member: dict, row: dict) -> list[float] | None:
    """Shared side-column distances from each concrete face, after validation.

    None means the horizontal layout is incomplete; an empty list is an
    explicitly inactive zero count. Specified centres retain their raw value.
    """
    diameter, count = row.get("diameter_mm"), row.get("per_face_count")
    columns = row.get("columns", 1)
    if None in (diameter, count, columns):
        return None
    if count == 0:
        return []
    column_pitch = row.get("column_pitch_mm")
    if columns > 1 and column_pitch is None:
        return None
    center = row.get("center_mm") if row.get("cover_mode", "自動") == "指定" else None
    outside = row.get("stirrup_position", "内側") == "外側"
    if row.get("cover_mode", "自動") == "自動":
        pure, enclosing = member.get("pure_cover_mm"), _enclosing_diameter(member)
        if pure is not None and (outside or enclosing is not None):
            center = pure - diameter / 2 if outside else pure + enclosing + diameter / 2
    if center is None:
        return None
    _check_budget(min(int(columns), int(count)))
    sign = -1 if outside else 1
    return [center + sign * index * (column_pitch or 0)
            for index in range(min(int(columns), int(count)))]


def _beam_preview(member: dict, geometry: dict) -> tuple[list[dict], list, list, list[str]]:
    centers = _effective_centers(member)
    bars, warnings = _beam_main_bars(member, geometry, centers)
    _append_beam_side_bars(member, geometry, bars, warnings)
    return _finish_bars("梁", geometry, bars), [], centers, warnings


def _beam_main_bars(member: dict, geometry: dict,
                    centers: list[float | None]) -> tuple[list[dict], list[str]]:
    groups: dict[tuple[str, int], list[tuple[int, dict, float]]] = {}
    warnings = []
    for index, row in enumerate(member.get("main_rows", [])):
        center, diameter, count = centers[index], row.get("diameter_mm"), row.get("count")
        if diameter is not None and count is not None and center is None:
            warnings.append(_auto_warning(member, row))
        if None in (center, diameter, count, row.get("face")) or count == 0:
            continue
        layer = row.get("layer", 1)
        if layer is None:
            continue
        y = center if row["face"] == "上" else geometry["height_mm"] - center
        groups.setdefault((row["face"], layer), []).append((index, row, y))
    bars: list[dict] = []
    for entries in groups.values():
        count = sum(int(row["count"]) for _, row, _ in entries)
        _check_budget(len(bars) + count)
        spans = [_safe_span("梁", geometry, y, row["diameter_mm"], centers[index])
                 for index, row, y in entries]
        left, right = max(span[0] for span in spans), min(span[1] for span in spans)
        if right < left:
            raise EditorError("梁 / 同じ段の主筋: 共通する配置幅がありません")
        xs = [(left + right) / 2] if count == 1 else [left + (right - left) * i / (count - 1) for i in range(count)]
        remaining = [int(row["count"]) for _, row, _ in entries]
        assignment = []
        while len(assignment) < count:
            for slot in range(len(entries)):
                if remaining[slot]:
                    assignment.append(slot)
                    remaining[slot] -= 1
        for x, slot in zip(xs, assignment):
            index, row, y = entries[slot]
            bars.append(_bar(member, row, "main_rows", index, x, y))
    return bars, warnings


def _append_beam_side_bars(member: dict, geometry: dict, bars: list[dict],
                           warnings: list[str]) -> None:
    for index, row in enumerate(member.get("side_rows", [])):
        diameter, count = row.get("diameter_mm"), row.get("per_face_count")
        columns, start, pitch = row.get("columns", 1), row.get("start_mm"), row.get("pitch_mm")
        if None in (diameter, count, columns, start) or count == 0:
            continue
        column_pitch = row.get("column_pitch_mm")
        if columns > 1 and column_pitch is None:
            warnings.append("側面筋：2列目以降の列の芯間隔を入力してください")
            continue
        offsets = side_offsets(member, row)
        if offsets is None:
            warnings.append("側面筋：純かぶり・外帯筋径、または指定した芯かぶりを入力してください")
            continue
        _check_budget(len(bars) + int(count) * 2)
        for column, offset in enumerate(offsets):
            in_column = int(count) // int(columns) + (column < int(count) % int(columns))
            if in_column > 1 and pitch is None:
                warnings.append("側面筋：上下の芯間隔を入力してください")
                continue
            for level in range(in_column):
                y = start + level * (pitch or 0)
                left, right = _edge_span("梁", geometry, y)
                for x in (left + offset, right - offset):
                    bars.append(_bar(member, row, "side_rows", index, x, y))


def _footing_centers(member: dict, row: dict, visiting: tuple[int, ...] = ()) -> list[float]:
    diameter, layers = row.get("diameter_mm"), row.get("layers", 1)
    if diameter is None or layers is None:
        return []
    if id(row) in visiting:
        raise EditorError("フーチング / 重ね順: 循環しない順序を指定してください")
    center = row.get("center_mm")
    if row.get("cover_mode", "自動") == "自動":
        pure = member.get("pure_cover_mm")
        if pure is None:
            return []
        enclosing = _enclosing_diameter(member, empty_is_absent=True)
        if enclosing is None:
            return []
        center = pure + enclosing + diameter / 2
        order = row.get("stack_order", 1 if row.get("direction") == "線路" else 2)
        if order is None:
            return []
        for earlier in member.get("main_rows", []):
            earlier_order = earlier.get("stack_order", 1 if earlier.get("direction") == "線路" else 2)
            if earlier.get("face") == row.get("face") and earlier_order is not None and earlier_order < order:
                earlier_diameter = earlier.get("diameter_mm")
                actual = _footing_centers(member, earlier, (*visiting, id(row)))
                if earlier_diameter is None or not actual:
                    return []
                center = max(center, actual[-1] + earlier_diameter / 2 + diameter / 2)
    if center is None or layers > 1 and row.get("clear_gap_mm") is None:
        return []
    _check_budget(int(layers))
    return [center + index * (diameter + (row.get("clear_gap_mm") or 0)) for index in range(int(layers))]


def _footing_lateral_cover(member: dict, row: dict) -> tuple[float, str | None]:
    """Lateral cover is independent of the top/bottom vertical centre."""
    pure = member.get("pure_cover_mm")
    enclosing = _enclosing_diameter(member, empty_is_absent=True)
    radius = row["diameter_mm"] / 2
    if pure is None or enclosing is None:
        return radius, "横方向の純かぶりが未確定：コンクリート内に収まる範囲を表示しています（配置未確定）"
    return pure + enclosing + radius, None


def _footing_preview(member: dict, geometry: dict, direction: str) -> tuple[list, list, list, list[str]]:
    bars, lines, centers, warnings = [], [], [], []
    for index, row in enumerate(member.get("main_rows", [])):
        distances = _footing_centers(member, row)
        centers.append(distances[0] if distances else None)
        diameter, pitch = row.get("diameter_mm"), row.get("pitch_mm")
        if diameter is not None and pitch is not None and not distances:
            warnings.append("フーチング：芯かぶり・重ね順・各段のあきを確認してください")
        if not distances or diameter is None or pitch is None or row.get("face") is None or row.get("direction") is None:
            continue
        lateral_cover, lateral_warning = _footing_lateral_cover(member, row)
        if lateral_warning:
            warnings.append(lateral_warning)
        for distance in distances:
            y = distance if row["face"] == "上" else geometry["height_mm"] - distance
            left, right = _safe_span("フーチング", geometry, y, diameter, lateral_cover)
            if row["direction"] == direction:
                _check_budget(len(bars) + len(lines) + 1)
                lines.append({"x1_mm": left, "y1_mm": y, "x2_mm": right, "y2_mm": y,
                              "diameter_mm": diameter, "row_indices": [index], "family": "main_rows",
                              "sources": [("main_rows", index)]})
            else:
                ratio = (right - left) / pitch
                if not math.isfinite(ratio) or ratio >= MAX_PREVIEW_BARS:
                    _check_budget(MAX_PREVIEW_BARS + 1)
                count = math.floor(ratio) + 1
                _check_budget(len(bars) + len(lines) + count)
                # Keep the entered pitch; centre the unused remainder equally.
                start = (left + right - (count - 1) * pitch) / 2
                for n in range(count):
                    bars.append(_bar(member, row, "main_rows", index, start + n * pitch, y))
    bars = _finish_bars("フーチング", geometry, bars)
    _reject_line_overlaps(bars, lines)
    return bars, lines, centers, warnings


def _reject_line_overlaps(bars: list[dict], lines: list[dict]) -> None:
    """Check physical crossing layers; contact is allowed, shared space is not."""
    if not lines:
        return
    ordered = sorted(lines, key=lambda line: line["y1_mm"])
    ys = [line["y1_mm"] for line in ordered]
    largest_radius = max(line["diameter_mm"] for line in ordered) / 2
    for index, line in enumerate(ordered):
        radius = line["diameter_mm"] / 2
        last = bisect_right(ys, line["y1_mm"] + radius + largest_radius)
        for other in ordered[index + 1:last]:
            minimum = (line["diameter_mm"] + other["diameter_mm"]) / 2
            if other["y1_mm"] - line["y1_mm"] < minimum - max(1e-7, minimum * 1e-9):
                if min(line["x2_mm"], other["x2_mm"]) > max(line["x1_mm"], other["x1_mm"]):
                    raise EditorError("フーチング / 面内筋の段が重なっています。芯かぶり・あきを確認してください")
    for bar in bars:
        radius = bar["diameter_mm"] / 2
        start = bisect_left(ys, bar["y_mm"] - radius - largest_radius)
        end = bisect_right(ys, bar["y_mm"] + radius + largest_radius)
        for line in ordered[start:end]:
            minimum = (bar["diameter_mm"] + line["diameter_mm"]) / 2
            horizontal = max(line["x1_mm"] - bar["x_mm"], 0, bar["x_mm"] - line["x2_mm"])
            if math.hypot(horizontal, bar["y_mm"] - line["y1_mm"]) < minimum - max(1e-7, minimum * 1e-9):
                raise EditorError("フーチング / 2方向の鉄筋が重なっています。芯かぶり・重ね順を確認してください")


def member_preview(member: str, candidate: dict, geometry: dict,
                   direction: str = "線路") -> tuple[list, list, list, list[str]]:
    """Return detached circles, in-plane lines, effective centres and notices.

    Incomplete engineering inputs produce no invented positions for that row.
    Complete impossible geometry raises EditorError and must not be committed.
    Footing manual coordinates are deliberately excluded: use per-group centre
    and stack controls, keeping two section directions separate.
    """
    validate_member(member, candidate)
    try:
        new_hoops = member == "柱" and "column_hoops" in candidate
        if new_hoops:
            enclosing = candidate["column_hoops"].get("enclosing_diameter_mm")
            if enclosing is not None:
                band_outline(member, candidate, geometry, {"type": "外巻き", "diameter_mm": enclosing})
        rows = column_rebar.hoop_rows(candidate) if member == "柱" else candidate.get("band_rows", [])
        for row in rows:
            if not new_hoops and row.get("sets") == 0:
                continue
            if not new_hoops:
                band_outline(member, candidate, geometry, row)
            if member == "柱" and geometry.get("member_height_mm") is not None:
                if any(row.get(key) is not None and row[key] > geometry["member_height_mm"] for key in ("start_mm", "end_mm")):
                    raise EditorError("柱 / 横補強筋の開始・終了位置: 柱高さ以内にしてください")
        if candidate.get("position_mode", "基本") == "指定":
            if member == "フーチング":
                raise EditorError("フーチングの配置調整は方向別の芯かぶり・重ね順を使用してください")
            _check_budget(len(candidate.get("manual_positions", [])))
            bars = []
            for index, row in enumerate(candidate.get("manual_positions", [])):
                if any(row.get(key) is None for key in ("x_mm", "y_mm", "diameter_mm")):
                    continue
                bar = _bar(candidate, row, "manual_positions", index, row["x_mm"], row["y_mm"])
                if member == "柱" and "manual_basis" in candidate:
                    bar["material"] = row.get("material")
                bars.append(bar)
            return _finish_bars(member, geometry, bars), [], _effective_centers(candidate), []
        if member == "柱":
            if "column_hoops" in candidate or any("distribution" in row for row in candidate.get("main_rows", [])):
                layout = column_layout(candidate, geometry)
                return layout["bars"], [], layout["centers"], [issue["message"] for issue in layout["issues"]]
            centers = _effective_centers(candidate)
            warnings = [_auto_warning(candidate, row) for row, center in zip(candidate.get("main_rows", []), centers)
                        if center is None and row.get("diameter_mm") is not None and row.get("per_face_count") is not None]
            return column_bars(candidate, geometry), [], centers, warnings
        if member == "梁":
            return _beam_preview(candidate, geometry)
        return _footing_preview(candidate, geometry, direction)
    except (ArithmeticError, OverflowError, RecursionError) as exc:
        raise EditorError(f"{member} / 配置: 数値の範囲または段数を確認してください") from exc


def validate_document_rebar(document: dict) -> None:
    """Preflight all stored/candidate members and available cuts before save."""
    if "鉄筋" not in document:
        return
    root = _root(document)
    for member in MEMBERS:
        if member not in root:
            continue
        candidate = load_member(document, member)
        validate_member(member, candidate)
        for direction in DIRECTIONS if member == "フーチング" else ("線路",):
            try:
                geometry = section_geometry(document, member, direction)
            except GeometryIncomplete:
                continue
            member_preview(member, candidate, geometry, direction)

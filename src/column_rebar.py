"""Pure column-specific placement rules; no Tk or rebar facade dependency."""

from __future__ import annotations

import math
from copy import deepcopy

from .editor_model import EditorError


DISTRIBUTION_MODES = ("等分", "中央ピッチ", "両端＋中央ピッチ")


def _number(value, label: str, *, positive=False, integer=False):
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EditorError(f"{label}: 数値または空欄が必要です")
    try:
        finite = math.isfinite(value)
    except (OverflowError, ValueError):
        finite = False
    if not finite or value < 0 or (positive and value == 0):
        raise EditorError(f"{label}: 有限の{'正' if positive else '0以上'}の数値が必要です")
    if integer and int(value) != value:
        raise EditorError(f"{label}: 整数が必要です")


def validate_shapes(member: dict) -> None:
    """Reject unsafe containers before widgets read them; retain incomplete data."""
    for index, row in enumerate(member.get("main_rows", [])):
        if "distribution" in row and not isinstance(row["distribution"], dict):
            raise EditorError(f"柱 / 主筋 [{index + 1}] / 配列: オブジェクトが必要です")
    if "column_hoops" in member:
        _hoop_rows_shape(member["column_hoops"])


def _hoop_rows_shape(hoops: dict) -> list[dict]:
    label = "柱 / 帯鉄筋"
    if not isinstance(hoops, dict):
        raise EditorError(f"{label}: オブジェクトが必要です")
    rows = hoops.get("direction_rows", [])
    if not isinstance(rows, list):
        raise EditorError(f"{label}: 方向別行は配列が必要です")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise EditorError(f"{label} [{index + 1}]: オブジェクトが必要です")
    return rows


def validate_inputs(member: dict) -> None:
    validate_shapes(member)
    for index, row in enumerate(member.get("main_rows", [])):
        if "distribution" not in row:
            continue
        label = f"柱 / 主筋 [{index + 1}] / 配列"
        distribution = row["distribution"]
        mode = distribution.get("mode")
        if mode is not None and mode not in DISTRIBUTION_MODES:
            raise EditorError(f"{label}: 未対応の配列方法です")
        _number(distribution.get("edge_center_mm"), f"{label} / 端部芯距離")
        _number(distribution.get("pitch_mm"), f"{label} / ピッチ", positive=True)
        if mode == "両端＋中央ピッチ" and row.get("per_face_count") == 1:
            raise EditorError(f"{label}: 両端筋の配列は2本以上が必要です")
    if "column_hoops" in member:
        validate_hoops(member["column_hoops"])
    if "manual_basis" in member:
        validate_basis(member["manual_basis"])


def validate_basis(basis: dict) -> None:
    if not isinstance(basis, dict):
        raise EditorError("柱 / 詳細配置の生成元: オブジェクトが必要です")
    version = basis.get("generator_version")
    if isinstance(version, bool) or version != 1:
        raise EditorError("柱 / 詳細配置の生成元: 未対応の生成規則バージョンです")
    if not isinstance(basis.get("geometry"), dict) or not isinstance(basis.get("inputs"), dict):
        raise EditorError("柱 / 詳細配置の生成元: 寸法と基本入力の記録が必要です")
    for key in ("width_mm", "height_mm"):
        value = basis["geometry"].get(key)
        if value is None:
            raise EditorError("柱 / 詳細配置の生成元: 断面寸法の記録が必要です")
        _number(value, "柱 / 詳細配置の生成元 / 断面寸法", positive=True)


def generation_basis(member: dict, geometry: dict) -> dict:
    keys = ("main_rows", "materials", "pure_cover_mm",
            "column_hoops" if "column_hoops" in member else "band_rows")
    basis = {"generator_version": 1,
             "geometry": {"width_mm": geometry.get("cross_mm", geometry.get("width_mm")),
                          "height_mm": geometry.get("rail_mm", geometry.get("height_mm"))},
             "inputs": {key: deepcopy(member[key]) for key in keys if key in member}}
    validate_basis(basis)
    return basis


def detail_status(member: dict, geometry: dict) -> str:
    if member.get("position_mode", "基本") == "基本":
        return "自動"
    if "manual_basis" not in member:
        return "生成元不明"
    return "一致" if member["manual_basis"] == generation_basis(member, geometry) else "基本条件変更"


def has_detail(member: dict) -> bool:
    """A virtual empty list is not an archive; recorded empty edits are."""
    return bool(member.get("manual_positions")) or "manual_basis" in member


def detail_candidate(member: dict, geometry: dict, positions: list[dict]) -> dict:
    """Build a detached full-table edit; never invent a legacy snapshot basis."""
    candidate = deepcopy(member)
    if member.get("position_mode", "基本") == "基本":
        candidate["manual_basis"] = generation_basis(member, geometry)
    candidate["manual_positions"] = deepcopy(positions)
    candidate["position_mode"] = "指定"
    return candidate


def source_token(member: dict, geometry: dict) -> dict:
    """Keep the entire detached input for an exact stale-dialog comparison."""
    return {"member": deepcopy(member), "geometry": deepcopy(geometry)}


def apply_regeneration(member: dict, preview: dict, *, to_auto: bool) -> dict:
    candidate = deepcopy(member)
    if to_auto:
        candidate["position_mode"] = "基本"
    else:
        candidate["manual_positions"] = deepcopy(preview["candidate_bars"])
        candidate["manual_basis"] = deepcopy(preview["basis"])
        candidate["position_mode"] = "指定"
    return candidate


def requires_v2(member: dict) -> bool:
    rows = member.get("main_rows", [])
    return ("column_hoops" in member or "manual_basis" in member
            or isinstance(rows, list) and any(isinstance(row, dict) and "distribution" in row for row in rows))


def validate_hoops(hoops: dict) -> None:
    label = "柱 / 帯鉄筋"
    rows = _hoop_rows_shape(hoops)
    _number(hoops.get("enclosing_diameter_mm"), f"{label} / 外帯筋径", positive=True)
    for index, row in enumerate(rows):
        row_label = f"{label} [{index + 1}]"
        if row.get("direction") not in (None, "線路", "直角"):
            raise EditorError(f"{row_label}: 方向は線路・直角から選んでください")
        for key in ("diameter_mm", "pitch_mm", "effective_legs", "start_mm", "end_mm"):
            _number(row.get(key), f"{row_label} / {key}",
                    positive=key in ("diameter_mm", "pitch_mm"), integer=key == "effective_legs")
        if row.get("material") is not None and not isinstance(row["material"], str):
            raise EditorError(f"{row_label} / 材質: 文字列または空欄が必要です")
        if row.get("start_mm") is not None and row.get("end_mm") is not None and row["end_mm"] < row["start_mm"]:
            raise EditorError(f"{row_label}: 終了位置は開始位置以上にしてください")


def hoop_rows(member: dict) -> list[dict]:
    """Return only the active source; directional totals never become sets."""
    if "column_hoops" in member:
        validate_hoops(member["column_hoops"])
        return member["column_hoops"].get("direction_rows", [])
    return member.get("band_rows", [])


def missing_fields(row: dict, center: float | None) -> list[str]:
    if row.get("per_face_count") == 0:
        return []
    missing = [key for key in ("per_face_count", "diameter_mm", "face_direction")
               if row.get(key) is None]
    if center is None:
        missing.append("center_mm")
    if "distribution" not in row:
        if row.get("endpoints") is None:
            missing.append("endpoints")
        return missing
    distribution = row["distribution"]
    mode, count = distribution.get("mode"), row.get("per_face_count")
    if mode is None:
        missing.append("distribution.mode")
    if count is not None and count > 1:
        if mode == "等分" and row.get("endpoints") is None:
            missing.append("endpoints")
        if mode in ("等分", "両端＋中央ピッチ") and distribution.get("edge_center_mm") is None:
            missing.append("distribution.edge_center_mm")
        if (mode == "中央ピッチ" or mode == "両端＋中央ピッチ" and count > 2) and distribution.get("pitch_mm") is None:
            missing.append("distribution.pitch_mm")
    return missing


def face_positions(row: dict, span: float) -> list[float]:
    """Place one face independently from its perpendicular cover distance."""
    distribution = row["distribution"]
    count = int(row["per_face_count"])
    mode = distribution["mode"]
    if count == 0:
        return []
    if count == 1:
        return [span / 2]
    if mode == "等分":
        edge = distribution["edge_center_mm"]
        if edge * 2 >= span:
            raise EditorError("柱 / 配列: 両端の芯位置が逆転または重複しています")
        offset = 0 if row.get("endpoints", "含む") == "含む" else 1
        divisor = count - 1 if offset == 0 else count + 1
        positions = [edge + (index + offset) * (span - 2 * edge) / divisor
                     for index in range(count)]
        if not offset:
            positions[0], positions[-1] = edge, span - edge
        return positions
    if mode == "中央ピッチ":
        pitch = distribution["pitch_mm"]
        start = (span - (count - 1) * pitch) / 2
        return [start + index * pitch for index in range(count)]
    edge, pitch = distribution["edge_center_mm"], distribution.get("pitch_mm")
    if edge * 2 >= span:
        raise EditorError("柱 / 配列: 両端の芯位置が逆転または重複しています")
    if count == 2:
        return [edge, span - edge]
    interior = count - 2
    start = (span - (interior - 1) * pitch) / 2
    if start < edge or start + (interior - 1) * pitch > span - edge:
        raise EditorError("柱 / 配列: 内部筋が両端筋の区間からはみ出しています")
    return [edge, *(start + index * pitch for index in range(interior)), span - edge]

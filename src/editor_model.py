"""Lossless JSON editing and cautious file replacement, independent of Tk."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .input_formulas import INPUT_FORMULAS, SUPPORT_POSITION_PATHS, support_position_value
from .reaction_inputs import SNOW_LOAD_CASES

JsonPath = tuple[str | int, ...]
KINDS = ("数値", "文字列", "空欄 (null)", "適用外 (-)", "真偽値")
JRSNAP_INPUT_KEYS = ("shear_factor_vcd", "shear_factor_vsd", "shear_factor_vdd", "aggregate_max_mm")
REACTION_LOAD_KEYS = ("固定死荷重_D1", "付加死荷重_D2", *(key for key, _ in SNOW_LOAD_CASES))
MANUAL_REACTION_TOTAL_PATHS = frozenset(
    ("上部工反力", side, point, "合計", key)
    for side, point in (("起点側", "A支点"), ("終点側", "D支点"))
    for key in REACTION_LOAD_KEYS
)


def optional_reaction_path(path: JsonPath) -> bool:
    """Recognize editable blanks in old files without migrating their contents."""
    if path in MANUAL_REACTION_TOTAL_PATHS:
        return True
    if (len(path) == 4 and path[:2] == ("上部構造", "支承データ")
            and path[2] in ("起点側", "終点側") and path[3] == "復旧性制動係数"):
        return True
    return (
        len(path) == 6
        and path[0] == "上部工反力"
        and path[1:3] in (("起点側", "B支点"), ("終点側", "C支点"))
        and path[3] == "支承"
        and isinstance(path[4], int) and not isinstance(path[4], bool) and path[4] >= 0
        and path[5] in {key for key, _ in SNOW_LOAD_CASES}
    )


def optional_jrsnap_path(path: JsonPath) -> bool:
    return (len(path) == 2 and path[0] in ("jrsnap_longitudinal", "jrsnap_transverse")
            and path[1] in JRSNAP_INPUT_KEYS)


class EditorError(ValueError):
    """A user-correctable editor error."""


class SaveConflict(EditorError):
    """The destination no longer matches the version the user inspected."""


def path_label(path: JsonPath) -> str:
    return " / ".join(f"[{part + 1}]" if isinstance(part, int) else part for part in path) or "入力全体"


def get_at(data: Any, path: JsonPath) -> Any:
    for part in path:
        data = data[part]
    return data


def set_at(data: Any, path: JsonPath, value: Any) -> None:
    if not path:
        raise EditorError("入力全体はオブジェクトのままにしてください")
    if optional_jrsnap_path(path):
        settings = data.setdefault(path[0], {})
        if not isinstance(settings, dict):
            raise EditorError(f"{path[0]} はオブジェクトで指定してください")
        settings[path[-1]] = value
        return
    if path in MANUAL_REACTION_TOTAL_PATHS:
        for part in path[:-1]:
            data = data.setdefault(part, {})
        data[path[-1]] = value
        return
    get_at(data, path[:-1])[path[-1]] = value


def formula_source_number(value: Any, path: JsonPath) -> float | None:
    """Read an existing numeric cell without converting numeric-looking text."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EditorError(f"{path_label(path)}: 数値または空欄が必要です")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise EditorError(f"{path_label(path)}: 有限の数値が必要です") from exc
    if not math.isfinite(number):
        raise EditorError(f"{path_label(path)}: 有限の数値が必要です")
    return number


def update_formula_snapshots(data: dict) -> None:
    """Refresh existing formula parents, keeping invalid-source snapshots blank."""
    for formula in INPUT_FORMULAS:
        try:
            owner = get_at(data, formula.path[:-1])
        except (KeyError, IndexError, TypeError):
            continue
        if not isinstance(owner, dict):
            continue
        try:
            result = formula.evaluate(lambda path: formula_source_number(get_at(data, path), path))
            value = float(format(result, ".15g"))
            if not math.isfinite(value):
                value = result
        except (KeyError, IndexError, TypeError, ValueError):
            value = None
        owner[formula.path[-1]] = value
    # f is an input, not a formula snapshot. Supply only legacy missing values.
    def optional(path: JsonPath) -> Any:
        try:
            return get_at(data, path)
        except (KeyError, IndexError, TypeError):
            return None

    for path in SUPPORT_POSITION_PATHS:
        owner = optional(path[:-1])
        if not isinstance(owner, dict) or owner.get(path[-1]) is not None:
            continue
        try:
            owner[path[-1]] = support_position_value(optional, path[1])
        except ValueError:
            pass  # Preserve missing/null and explicit invalid values for validation.


def value_kind(value: Any) -> str:
    if value is None:
        return "空欄 (null)"
    if isinstance(value, bool):
        return "真偽値"
    if isinstance(value, (int, float)):
        return "数値"
    if value == "-":
        return "適用外 (-)"
    return "文字列"


def value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def numeric_field(path: JsonPath) -> bool:
    """Recognize the contract's numeric leaves, including initially blank ones."""
    if optional_jrsnap_path(path):
        return True
    keys = tuple(x for x in path if isinstance(x, str))
    if not keys or keys[0] not in ("上部工反力", "上部構造", "下部構造", "地盤データ"):
        return path == ("schema_version",)
    if "単位" in keys or "選択肢" in keys:
        return False
    text_keys = {"名称", "支承", "土質区分", "層番", "作用方向", "支承名", "車両名", "選択値"}
    if keys[-1] in text_keys:
        return False
    numeric_keys = {
        "支承位置", "固定死荷重_D1", "付加死荷重_D2", "スパン長", "単線終局",
        "曲線半径", "列車速度", "重心高_hs", "支承位置_f", "摩擦係数_μ", "復旧性制動係数", "値",
        "a1_連結部", "a2", "編成数", "受風高", "遠心重心高", "地震重心高",
        "使用性", "安全性(破壊)", "安全性(疲労)", "起点側_df1", "終点側_df2",
        "高水位_hw1", "平水位_hw2", "低水位_hw3", "θ", "タイプ", "梁・躯体",
        "フーチング", "鉛直重量", "慣性力", "上載土", "排除した土", "番号", "X", "Y",
        "本数", "層厚", "N値", "湿潤", "水中", "内部摩擦角_φd", "内部摩擦角の上限値",
        "一軸圧縮強度_qu", "変形係数_Ed",
        *(key for key, _ in SNOW_LOAD_CASES),
    }
    key = keys[-1]
    return key in numeric_keys or (len(key) > 1 and key[0] in "LBWHh" and key[1:].isdigit())


def parse_field(text: str, kind: str, path: JsonPath) -> Any:
    label = path_label(path)
    if kind == "空欄 (null)":
        return None
    if kind == "適用外 (-)":
        if numeric_field(path) and path[0] != "上部工反力":
            raise EditorError(f"{label}: 数値または空欄を指定してください")
        return "-"
    if kind == "文字列":
        if numeric_field(path):
            raise EditorError(f"{label}: 数値または空欄を指定してください")
        return text
    if kind == "真偽値":
        if numeric_field(path) or text.strip().lower() not in ("true", "false"):
            raise EditorError(f"{label}: 真偽値には true または false を指定してください")
        return text.strip().lower() == "true"
    if kind != "数値":
        raise EditorError(f"{label}: 型を選択してください")
    return _parse_numeric_field(text, path, label)


def _parse_numeric_field(text: str, path: JsonPath, label: str) -> int | float | None:
    try:
        normalized = text.strip()
        if not normalized:
            return None
        value = float(normalized)
        if not math.isfinite(value):
            raise ValueError
        if not any(c in normalized.lower() for c in ".e"):
            value = int(normalized)
    except (ValueError, OverflowError) as exc:
        raise EditorError(f"{label}: 有限の数値を入力してください（未入力は「空欄 (null)」）") from exc
    if numeric_field(path) and path[-1] in ("schema_version", "編成数", "本数", "番号", "タイプ"):
        if value != int(value) or value < 0:
            raise EditorError(f"{label}: 0以上の整数が必要です")
        value = int(value)
    if (
        numeric_field(path)
        and (path[:2] in (("下部構造", "寸法"), ("下部構造", "土かぶり"))
             or path[0] == "地盤データ" or path[-1] == "復旧性制動係数")
        and value < 0
    ):
        raise EditorError(f"{label}: 0以上の数値が必要です")
    if path[-1] in ("内部摩擦角_φd", "内部摩擦角の上限値") and value >= 90:
        raise EditorError(f"{label}: 90度未満の値が必要です")
    if optional_jrsnap_path(path):
        if path[-1] == "aggregate_max_mm":
            if not 0.1 <= value <= 999999:
                raise EditorError(f"{label}: 0.1〜999999 mmの数値が必要です")
        elif not 0 < value <= 99.99:
            raise EditorError(f"{label}: 0より大きく99.99以下の数値が必要です")
    return value


def unit_label(data: dict, path: JsonPath) -> str:
    """Read declared units without adding inferred units to the saved data."""
    if "単位" in path or not path:
        return ""
    for length in range(len(path) - 1, -1, -1):
        try:
            parent = get_at(data, path[:length])
        except (KeyError, IndexError, TypeError):
            continue
        if not isinstance(parent, dict) or "単位" not in parent:
            continue
        units = parent["単位"]
        if isinstance(units, dict):
            tail = path[length:]
            found = next((units[k] for k in tail if isinstance(k, str) and k in units), ...)
            if found is ... and path[-1] in ("X", "Y"):
                # The pile table calls its coordinate columns 線路方向_X / 線路直角方向_Y.
                found = units.get("線路方向_X" if path[-1] == "X" else "線路直角方向_Y", ...)
            if found is ...:
                continue
            units = found
        if isinstance(units, str):
            return units
        if units is None:
            return "単位未記載"
    return ""


def _reject_constant(text: str) -> None:
    raise EditorError(f"JSONに有限でない数値があります: {text}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise EditorError(f"JSONのキーが重複しています: {key}")
        result[key] = value
    return result


def encode(data: dict) -> bytes:
    try:
        return (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, UnicodeError, TypeError) as exc:
        raise EditorError(f"JSONとして保存できません: {exc}") from exc


def fingerprint(path: Path) -> str | None:
    if path.is_symlink():
        raise EditorError(f"シンボリックリンクへの保存はできません: {path}")
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


@dataclass
class SaveResult:
    path: Path
    backup: Path | None


def _remove_legacy_reaction_totals(data: dict) -> None:
    """Discard only B/C computed snapshots, preserving A/D inputs and extensions."""
    reactions = data.get("上部工反力")
    if not isinstance(reactions, dict):
        return
    for side, point in (("起点側", "B支点"), ("終点側", "C支点")):
        side_data = reactions.get(side)
        if not isinstance(side_data, dict):
            continue
        point_data = side_data.get(point)
        if isinstance(point_data, dict):
            point_data.pop("合計", None)


class EditorDocument:
    def __init__(self, path: Path, data: dict, source: bytes) -> None:
        self.path = path
        self.data = data
        self._saved = encode(data)
        self._fingerprint = hashlib.sha256(source).hexdigest()
        _remove_legacy_reaction_totals(self.data)
        update_formula_snapshots(self.data)

    @classmethod
    def open(cls, path: str | Path) -> "EditorDocument":
        path = Path(path).absolute()
        if path.is_symlink():
            raise EditorError("シンボリックリンクではなく入力JSON本体を開いてください")
        source = path.read_bytes()
        try:
            data = json.loads(source.decode("utf-8-sig"), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise EditorError(f"JSONを読み込めません: {exc}") from exc
        if not isinstance(data, dict):
            raise EditorError("入力JSONの最上位はオブジェクトである必要があります")
        encode(data)  # Also reject overflows such as 1e999.
        return cls(path, data, source)

    @property
    def dirty(self) -> bool:
        return encode(self.data) != self._saved

    def clone(self, path: JsonPath) -> JsonPath:
        parent = get_at(self.data, path[:-1])
        if not isinstance(parent, list):
            raise EditorError("配列の行を選択してください")
        index = path[-1] + 1
        parent.insert(index, copy.deepcopy(parent[path[-1]]))
        return path[:-1] + (index,)

    def save(self, destination: str | Path | None = None, *, expected: str | None = None) -> SaveResult:
        target = Path(destination).absolute() if destination is not None else self.path
        snapshot = self._fingerprint if target == self.path else expected
        normalized = copy.deepcopy(self.data)
        _remove_legacy_reaction_totals(normalized)
        update_formula_snapshots(normalized)
        payload = encode(normalized)
        if fingerprint(target) != snapshot:
            raise SaveConflict("保存先が読込後に変更・削除されました。別名で保存するか、開き直して変更を確認してください。")
        if target == self.path and payload == self._saved:
            self.data = normalized
            return SaveResult(target, None)
        backup = None
        temporary = None
        try:
            fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            temporary = Path(name)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if snapshot is not None:
                original = target.read_bytes()
                if hashlib.sha256(original).hexdigest() != snapshot:
                    raise SaveConflict("保存先が保存処理中に変更されました。保存を中止しました。")
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                backup = target.with_name(f"{target.name}.{stamp}.bak")
                with backup.open("xb") as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
            if fingerprint(target) != snapshot:
                raise SaveConflict("保存先が保存処理中に変更されました。保存を中止しました。")
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.path = target
        self.data = normalized
        self._saved = payload
        self._fingerprint = hashlib.sha256(payload).hexdigest()
        return SaveResult(target, backup)

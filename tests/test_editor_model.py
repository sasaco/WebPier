from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src import editor_model as model
from src.inputs import parse_input
from src.reaction_inputs import SNOW_LOAD_CASES

# Fixed historical input from fa27cca^, independent of the working input.
SOURCE = Path(__file__).resolve().parent / "fixtures" / "baseline_input.json"


@pytest.mark.parametrize("key", model.JRSNAP_INPUT_KEYS)
@pytest.mark.parametrize("namespace", ["jrsnap_longitudinal", "jrsnap_transverse"])
def test_jrsnap_optional_numeric_input_is_created_only_when_edited(key, namespace):
    data = {"other": {"keep": True}}
    path = (namespace, key)
    assert model.optional_jrsnap_path(path) and model.numeric_field(path)
    assert data == {"other": {"keep": True}}
    value = model.parse_field("25.5" if key == "aggregate_max_mm" else "1.3", "数値", path)
    model.set_at(data, path, value)
    assert data["other"] == {"keep": True}
    assert data[namespace] == {key: value}
    assert len(data) == 2
    assert model.parse_field("", "数値", path) is None
    for kind in ("文字列", "真偽値", "適用外 (-)"):
        with pytest.raises(model.EditorError):
            model.parse_field("1", kind, path)


@pytest.mark.parametrize("key,value", [
    ("shear_factor_vcd", "0"), ("shear_factor_vsd", "-1"), ("shear_factor_vdd", "100"),
    ("aggregate_max_mm", "0.09"), ("aggregate_max_mm", "1000000"),
    ("aggregate_max_mm", "nan"), ("shear_factor_vcd", "inf"),
])
@pytest.mark.parametrize("namespace", ["jrsnap_longitudinal", "jrsnap_transverse"])
def test_jrsnap_invalid_values_are_not_saved(key, value, namespace):
    with pytest.raises(model.EditorError):
        model.parse_field(value, "数値", (namespace, key))


@pytest.fixture
def document(tmp_path):
    target = tmp_path / "入力.json"
    target.write_bytes(SOURCE.read_bytes())
    return model.EditorDocument.open(target)


def walk(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk(item, path + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, path + (index,))
    else:
        yield path, value


def test_all_input_values_round_trip_with_original_types(document, tmp_path):
    original = copy.deepcopy(document.data)
    for path, value in walk(original):
        parsed = model.parse_field(model.value_text(value), model.value_kind(value), path)
        assert parsed == value
        assert type(parsed) is type(value)
    result = document.save(tmp_path / "別入力.json")
    assert result.backup is None
    loaded = model.EditorDocument.open(result.path)
    assert list(walk(loaded.data)) == list(walk(original))
    assert not document.dirty
    parse_input(loaded.data)


@pytest.mark.parametrize(("text", "kind", "path", "expected"), [
    ("", "数値", ("地盤データ", "層", 0, "層厚"), None),
    ("0", "数値", ("地盤データ", "層", 0, "N値"), 0),
    ("0.0", "数値", ("地盤データ", "層", 0, "N値"), 0.0),
    ("-2.441", "数値", ("上部工反力", "支承位置"), -2.441),
    ("-3", "数値", ("下部構造", "杭の配置", "X"), -3),
    ("-3", "数値", ("地盤データ", "将来追加する負値"), -3),
    ("", "適用外 (-)", ("上部工反力", "支承位置"), "-"),
    ("", "空欄 (null)", ("拡張",), None),
    ("true", "真偽値", ("拡張",), True),
    ("001\n改行", "文字列", ("拡張",), "001\n改行"),
    ("", "文字列", ("拡張",), ""),
])
def test_field_value_semantics(text, kind, path, expected):
    result = model.parse_field(text, kind, path)
    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize(("text", "kind", "path"), [
    ("abc", "数値", ("上部構造", "曲線半径")),
    ("nan", "数値", ("上部構造", "曲線半径")),
    ("1e999", "数値", ("上部構造", "曲線半径")),
    ("-1", "数値", ("下部構造", "寸法", "側面", "B8")),
    ("1.5", "数値", ("上部構造", "列車", "編成数")),
    ("90", "数値", ("地盤データ", "層", 0, "内部摩擦角_φd")),
    ("5", "文字列", ("地盤データ", "層", 0, "N値")),
    ("", "適用外 (-)", ("地盤データ", "層", 0, "N値")),
])
def test_bad_values_are_rejected(text, kind, path):
    with pytest.raises(model.EditorError):
        model.parse_field(text, kind, path)


def test_unknown_nested_fields_and_metadata_are_preserved(document, tmp_path):
    document.data["将来の項目"] = {"フラグ": True, "空文字": "", "文字列数値": "001", "多行": "a\nb", "array": [None, -1, {"unknown": []}]}
    document.data["地盤データ"]["層"][0]["内部摩擦角の上限値"] = 38
    original = copy.deepcopy(document.data)
    document.save(tmp_path / "拡張.json")
    assert model.EditorDocument.open(document.path).data == original
    assert document.data["下部構造"]["寸法"]["単位"] is None


def test_backup_keeps_exact_previous_bytes_and_noop_does_not_rewrite(document):
    original = document.path.read_bytes()
    assert document.save().backup is None
    assert document.path.read_bytes() == original
    document.data["下部構造"]["寸法"]["側面"]["B8"] = 6.0
    assert document.dirty
    result = document.save()
    assert result.backup.read_bytes() == original
    assert parse_input(model.EditorDocument.open(result.path).data).b_parts == (0, 6, 0)
    assert not document.dirty


@pytest.mark.parametrize("delete", [False, True])
def test_external_change_or_deletion_blocks_save(document, delete):
    document.data["schema_version"] = 2
    if delete:
        document.path.unlink()
    else:
        document.path.write_bytes(b'{"external": true}')
    with pytest.raises(model.SaveConflict):
        document.save()
    assert document.dirty
    if not delete:
        assert document.path.read_bytes() == b'{"external": true}'


def test_save_as_existing_target_requires_inspected_fingerprint(document, tmp_path):
    target = tmp_path / "existing.json"
    target.write_bytes(b'{"target": 1}')
    with pytest.raises(model.SaveConflict):
        document.save(target)
    expected = model.fingerprint(target)
    result = document.save(target, expected=expected)
    assert result.backup.read_bytes() == b'{"target": 1}'


def test_replace_failure_keeps_original_and_dirty_state(document, monkeypatch):
    original = document.path.read_bytes()
    document.data["schema_version"] = 2
    def fail(*args):
        raise PermissionError("locked")
    monkeypatch.setattr(model.os, "replace", fail)
    with pytest.raises(PermissionError):
        document.save()
    assert document.path.read_bytes() == original
    assert document.dirty
    assert not list(document.path.parent.glob("*.tmp"))
    assert list(document.path.parent.glob("*.bak"))[0].read_bytes() == original


def test_backup_failure_prevents_replacement(document, monkeypatch):
    original = document.path.read_bytes()
    document.data["schema_version"] = 2
    original_open = Path.open
    def fail_backup(path, *args, **kwargs):
        if path.suffix == ".bak":
            raise PermissionError("backup unavailable")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", fail_backup)
    with pytest.raises(PermissionError):
        document.save()
    assert document.path.read_bytes() == original
    assert document.dirty
    assert not list(document.path.parent.glob("*.tmp"))


@pytest.mark.parametrize("content", [b'{"x":NaN}', b'{"x":1e999}', b'{"x":1,"x":2}', b'[]', b'{invalid'])
def test_invalid_json_is_rejected(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_bytes(content)
    with pytest.raises(model.EditorError):
        model.EditorDocument.open(path)


def test_cloning_array_does_not_alias_original(document):
    new_path = document.clone(("地盤データ", "層", 0))
    model.get_at(document.data, new_path)["単位体積重量"]["湿潤"] = 21
    assert document.data["地盤データ"]["層"][0]["単位体積重量"]["湿潤"] == 18


def test_units_are_displayed_without_altering_source(document):
    before = copy.deepcopy(document.data)
    assert model.unit_label(document.data, ("下部構造", "寸法", "側面", "B8")) == "単位未記載"
    assert model.unit_label(document.data, ("地盤データ", "層", 0, "変形係数_Ed")) == "kN/m2"
    assert model.unit_label(document.data, ("上部構造", "列車", "軸重", "地震", "値")) == "kN/m"
    assert document.data == before


def legacy_reaction_input(tmp_path):
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    for side, points in (("起点側", ("A支点", "B支点")), ("終点側", ("C支点", "D支点"))):
        for point in points:
            data["上部工反力"][side].setdefault(point, {})["合計"] = {
                "支承位置": "-",
                "固定死荷重_D1": 99999,
                "付加死荷重_D2": 99999,
                "列車分担": {f"L{i}": 99999 for i in range(1, 5)},
            }
    data["上部工反力"]["起点側"]["A支点"]["注記"] = "保持"
    data["上部工反力"]["起点側"]["B支点"]["追加情報"] = {"合計": "これは拡張データ"}
    data["拡張"] = {"合計": {"memo": "保持"}, "空欄": None, "ゼロ": 0, "適用外": "-"}
    bearing = data["上部工反力"]["起点側"]["B支点"]["支承"][2]
    bearing["固定死荷重_D1"] = None
    bearing["付加死荷重_D2"] = 0
    bearing["列車分担"]["L1"] = "-"
    expected = copy.deepcopy(data)
    for side, points in (("起点側", ("B支点",)), ("終点側", ("C支点",))):
        for point in points:
            expected["上部工反力"][side][point].pop("合計")
    raw = ("\ufeff" + json.dumps(data, ensure_ascii=False, indent=4) + "\n").encode("utf-8")
    path = tmp_path / "旧入力.json"
    path.write_bytes(raw)
    return path, raw, expected


@pytest.mark.parametrize("save_as", [False, True])
def test_legacy_reaction_total_migration_preserves_other_data(tmp_path, save_as):
    path, raw, expected = legacy_reaction_input(tmp_path)
    document = model.EditorDocument.open(path)
    assert document.data == expected
    assert document.dirty
    assert path.read_bytes() == raw
    destination = tmp_path / "新入力.json" if save_as else path
    result = document.save(destination)
    if save_as:
        assert path.read_bytes() == raw
        assert result.backup is None
    else:
        assert result.backup.read_bytes() == raw
    assert not document.dirty
    saved = json.loads(destination.read_text(encoding="utf-8"))
    assert saved == expected
    reopened = model.EditorDocument.open(destination)
    assert reopened.data == expected
    assert not reopened.dirty
    actual_values = dict(walk(reopened.data))
    for value_path, value in walk(expected):
        assert actual_values[value_path] == value
        assert type(actual_values[value_path]) is type(value)
    before_bytes = destination.read_bytes()
    before_backups = set(tmp_path.glob("*.bak"))
    assert reopened.save().backup is None
    assert destination.read_bytes() == before_bytes
    assert set(tmp_path.glob("*.bak")) == before_backups


def test_legacy_reaction_total_migration_replace_failure(tmp_path, monkeypatch):
    path, raw, expected = legacy_reaction_input(tmp_path)
    document = model.EditorDocument.open(path)
    assert document.data == expected

    def fail(*args):
        raise PermissionError("locked")

    monkeypatch.setattr(model.os, "replace", fail)
    with pytest.raises(PermissionError):
        document.save()
    assert path.read_bytes() == raw
    assert document.data == expected
    assert document.dirty
    assert not list(tmp_path.glob("*.tmp"))
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == raw


def test_repository_reaction_input_omits_total_snapshots():
    from src.reaction_inputs import parse_reaction_input

    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    with_stale_totals = copy.deepcopy(source)
    for side, points in (("起点側", ("B支点",)), ("終点側", ("C支点",))):
        for point in points:
            assert "合計" not in source["上部工反力"][side].get(point, {})
            with_stale_totals["上部工反力"][side].setdefault(point, {})["合計"] = {
                "固定死荷重_D1": 99999,
                "付加死荷重_D2": -99999,
                "列車分担": {f"L{i}": 99999 for i in range(1, 5)},
            }
    assert parse_reaction_input(source) == parse_reaction_input(with_stale_totals)


def test_manual_reaction_totals_preserve_zero_negative_and_extension_types(document):
    for side, point in (("起点側", "A支点"), ("終点側", "D支点")):
        base = ("上部工反力", side, point, "合計")
        model.set_at(document.data, base + ("固定死荷重_D1",), 0)
        model.set_at(document.data, base + ("付加死荷重_D2",), -12.5)
        model.get_at(document.data, base)["注記"] = {"文字列数値": "001", "空欄": None}
    expected = copy.deepcopy(document.data)
    original = document.path.read_bytes()
    assert document.save().backup.read_bytes() == original
    reopened = model.EditorDocument.open(document.path)
    assert reopened.data == expected
    assert list(walk(reopened.data)) == list(walk(expected))
    assert not reopened.dirty


def snow_free_input():
    """A pre-extension document, including absent A/D parent objects."""
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    for side, support, outer in (("起点側", "B支点", "A支点"), ("終点側", "C支点", "D支点")):
        for bearing in data["上部工反力"][side][support]["支承"]:
            for key, _ in SNOW_LOAD_CASES:
                bearing.pop(key, None)
        data["上部工反力"][side].pop(outer, None)
    for key, _ in SNOW_LOAD_CASES:
        data["上部工反力"]["単位"].pop(key, None)
    return data


def test_legacy_snow_blanks_do_not_migrate_until_an_input_is_edited(tmp_path):
    data = snow_free_input()
    path = tmp_path / "legacy.json"
    path.write_bytes(model.encode(data))
    raw = path.read_bytes()
    document = model.EditorDocument.open(path)
    assert document.data == data
    assert not document.dirty
    assert document.save().backup is None
    assert path.read_bytes() == raw
    snow = ("上部工反力", "起点側", "A支点", "合計", "雪荷重_10年確率")
    assert model.optional_reaction_path(snow)
    model.set_at(document.data, snow, 0)
    expected = copy.deepcopy(data)
    expected["上部工反力"]["起点側"]["A支点"] = {"合計": {"雪荷重_10年確率": 0}}
    assert document.data == expected
    document.save()
    reopened = model.EditorDocument.open(path)
    assert reopened.data == expected
    assert not reopened.dirty


@pytest.mark.parametrize("key", [key for key, _ in SNOW_LOAD_CASES])
@pytest.mark.parametrize("value", [None, 0, -12.5, "-"])
def test_snow_fields_preserve_numeric_null_and_inapplicable_types(document, key, value):
    for path in (("上部工反力", "起点側", "B支点", "支承", 0, key),
                 ("上部工反力", "終点側", "D支点", "合計", key)):
        assert model.numeric_field(path)
        assert model.optional_reaction_path(path)
        parsed = model.parse_field(model.value_text(value), model.value_kind(value), path)
        assert parsed == value and type(parsed) is type(value)
        model.set_at(document.data, path, parsed)
    document.save()
    saved = model.EditorDocument.open(document.path)
    assert model.get_at(saved.data, path) == value
    assert type(model.get_at(saved.data, path)) is type(value)


def test_virtual_reaction_inputs_do_not_admit_unknown_paths():
    assert not model.optional_reaction_path(("上部工反力", "起点側", "A支点", "合計", "将来荷重"))
    assert not model.optional_reaction_path(("上部工反力", "起点側", "B支点", "支承", 0, "将来荷重"))
    assert not model.optional_reaction_path(("上部工反力", "起点側", "C支点", "支承", 0, "雪荷重_2年確率"))
    assert not model.optional_reaction_path(("上部工反力", "起点側", "B支点", "支承", True, "雪荷重_2年確率"))


def test_snow_units_are_declared_without_inference_for_absent_manual_parents(tmp_path):
    data = snow_free_input()
    data["上部工反力"]["単位"]["雪荷重_2年確率"] = None
    before = copy.deepcopy(data)
    assert model.unit_label(data, ("上部工反力", "起点側", "A支点", "合計", "雪荷重_2年確率")) == "単位未記載"
    assert model.unit_label(data, ("上部工反力", "終点側", "D支点", "合計", "雪荷重_10年確率")) == ""
    assert data == before

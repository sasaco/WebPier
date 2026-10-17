"""The edited input file: strict JSON in, cautious replacement out."""

import json
from pathlib import Path

import pytest

from webpier.core.integrity import dump_json
from webpier.gui.document import MISSING, EditorDocument, EditorError, SaveConflict, fingerprint, lookup, put
from webpier.inputs import parse_input

CURRENT = Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json"


@pytest.fixture
def document(tmp_path):
    target = tmp_path / "入力.json"
    target.write_bytes(CURRENT.read_bytes())
    return EditorDocument.open(target)


def test_opening_keeps_the_data_and_is_clean(document):
    assert document.data == json.loads(CURRENT.read_text(encoding="utf-8"))
    assert not document.dirty
    parse_input(document.data)


@pytest.mark.parametrize("text,message", [
    ('{"a": 1, "a": 2}', "JSONのキーが重複しています: a"),
    ('{"a": NaN}', "JSONに有限でない数値があります: NaN"),
    ("[1]", "入力JSONの最上位はオブジェクトである必要があります"),
    ("{", "JSONを読み込めません"),
])
def test_opening_is_strict(tmp_path, text, message):
    path = tmp_path / "bad.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(EditorError, match=message):
        EditorDocument.open(path)


def test_lookup_and_put():
    data = {"a": [{"b": 1}]}
    assert lookup(data, ("a", 0, "b")) == 1
    assert lookup(data, ("a", 1, "b")) is MISSING
    assert lookup(data, ("a", "x")) is MISSING
    put(data, ("a", 0, "b"), 2.5)
    assert data == {"a": [{"b": 2.5}]}
    with pytest.raises(EditorError, match="入力項目がありません: a\\[3\\].b"):
        put(data, ("a", 3, "b"), 1)


def test_saving_an_unchanged_file_writes_nothing(document):
    before = document.path.stat().st_mtime_ns
    result = document.save()
    assert result.backup is None and document.path.stat().st_mtime_ns == before


def test_saving_writes_strict_json_and_keeps_a_backup(document):
    document.data["上部構造"]["列車"]["編成数"] = 12
    assert document.dirty
    result = document.save()
    assert not document.dirty
    assert result.backup is not None and result.backup.read_bytes() == CURRENT.read_bytes()
    assert document.path.read_bytes() == dump_json(document.data)
    assert parse_input(json.loads(document.path.read_text(encoding="utf-8"))).train.cars == 12
    assert document.fingerprint == fingerprint(document.path)


def test_a_file_changed_after_opening_is_not_overwritten(document):
    document.path.write_text("{}", encoding="utf-8")
    document.data["上部構造"]["列車"]["編成数"] = 12
    with pytest.raises(SaveConflict):
        document.save()
    assert document.path.read_text(encoding="utf-8") == "{}"


def test_save_as_a_new_file_and_an_existing_one(document, tmp_path):
    other = tmp_path / "別.json"
    result = document.save(other)
    assert result.path == other.absolute() and document.path == other.absolute() and result.backup is None
    existing = tmp_path / "既存.json"
    existing.write_text("{}", encoding="utf-8")
    with pytest.raises(SaveConflict):
        document.save(existing)  # the caller did not inspect it
    result = document.save(existing, expected=fingerprint(existing))
    assert result.backup.read_text(encoding="utf-8") == "{}"


def test_links_are_refused(tmp_path, document):
    link = tmp_path / "link.json"
    try:
        link.symlink_to(document.path)
    except OSError:
        pytest.skip("symbolic links are not available")
    with pytest.raises(EditorError, match="シンボリックリンク"):
        EditorDocument.open(link)
    with pytest.raises(EditorError, match="シンボリックリンク"):
        fingerprint(link)


def test_a_failed_replacement_leaves_the_file_and_no_temporary(document, monkeypatch):
    document.data["上部構造"]["列車"]["編成数"] = 12
    before = document.path.read_bytes()

    def fail(*args):
        raise OSError("locked")

    monkeypatch.setattr("webpier.gui.document.os.replace", fail)
    with pytest.raises(OSError, match="locked"):
        document.save()
    assert document.path.read_bytes() == before
    assert sorted(path.name for path in document.path.parent.iterdir() if not path.name.endswith(".bak")) == [
        document.path.name]
    assert document.dirty


def test_a_change_between_backup_and_replacement_is_a_conflict(document, monkeypatch):
    document.data["上部構造"]["列車"]["編成数"] = 12
    real = fingerprint
    calls = []

    def changing(path):
        calls.append(path)
        if len(calls) == 2:
            path.write_text("{}", encoding="utf-8")
        return real(path)

    monkeypatch.setattr("webpier.gui.document.fingerprint", changing)
    with pytest.raises(SaveConflict, match="保存処理中"):
        document.save()

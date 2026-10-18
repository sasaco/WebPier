"""Strict JSON in and out, and content hashes, shared by CLI, GUI and exporters."""

import hashlib
import math

import pytest

from webpier.core.errors import InputError
from webpier.core.integrity import (canonical_sha256, content_sha256, dump_json, file_sha256, folder_files, load_json,
                                    sha256)


def test_load_json_reads_utf8_with_or_without_bom():
    assert load_json('{"a": 1}'.encode("utf-8")) == {"a": 1}
    assert load_json('﻿{"橋脚": 1}'.encode("utf-8")) == {"橋脚": 1}


@pytest.mark.parametrize("text,message", [
    ('{"a": 1, "a": 2}', "キーが重複しています: a"),
    ('{"a": {"b": 1, "b": 1}}', "キーが重複しています: b"),
    ('{"a": NaN}', "有限でない数値があります: NaN"),
    ('{"a": Infinity}', "有限でない数値があります: Infinity"),
    ('{"a": -Infinity}', "有限でない数値があります: -Infinity"),
    ('{"a": 1', "JSONを読み込めません"),
])
def test_load_json_rejects_ambiguous_or_broken_input(text, message):
    with pytest.raises(InputError, match=message):
        load_json(text.encode("utf-8"))


def test_load_json_rejects_numbers_that_overflow_to_infinity():
    with pytest.raises(InputError, match="有限でない数値"):
        load_json(b'{"a": 1e400}')


@pytest.mark.parametrize("text", [r'"\ud800"', r'{"\udc00": null}', r'{"a": ["x\ud83d"]}'])
def test_load_json_rejects_a_lone_surrogate_that_could_not_be_written_back(text):
    # Found by hypothesis: {"\ud800": null} loaded, then dump_json raised UnicodeEncodeError (and a layer name
    # with it failed only when the report was drawn).
    with pytest.raises(InputError, match="対になっていないサロゲート"):
        load_json(text.encode("ascii"))


def test_load_json_keeps_an_escaped_surrogate_pair():
    assert load_json(rb'{"\ud83d\ude00": "\ud83d\ude00"}') == {"😀": "😀"}


def test_load_json_rejects_non_utf8():
    with pytest.raises(InputError, match="JSONを読み込めません"):
        load_json("{\"a\": \"橋\"}".encode("cp932"))


def test_dump_json_is_stable_utf8_with_trailing_newline():
    assert dump_json({"橋": [1, 2.5]}) == '{\n  "橋": [\n    1,\n    2.5\n  ]\n}\n'.encode("utf-8")


def test_dump_json_rejects_non_finite():
    with pytest.raises(ValueError):
        dump_json({"a": math.nan})


def test_sha256_helpers_agree():
    data = b"webpier"
    assert sha256(data) == hashlib.sha256(data).hexdigest()


def test_file_sha256(tmp_path):
    path = tmp_path / "a.bin"
    path.write_bytes(b"pier")
    assert file_sha256(path) == hashlib.sha256(b"pier").hexdigest()


def test_canonical_sha256_ignores_key_order_but_not_values():
    assert canonical_sha256({"a": 1, "b": "橋"}) == canonical_sha256({"b": "橋", "a": 1})
    assert canonical_sha256({"a": 1}) != canonical_sha256({"a": 2})
    with pytest.raises(ValueError):
        canonical_sha256({"a": math.inf})


def test_a_folder_is_hashed_by_the_files_in_it(tmp_path):
    folder = tmp_path / "線路方向_JRSNAP"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.ndt").write_bytes(b"ndt")
    (folder / "sub" / "b.LOG").write_bytes(b"log")
    files = {"a.ndt": hashlib.sha256(b"ndt").hexdigest(), "sub/b.LOG": hashlib.sha256(b"log").hexdigest()}
    assert folder_files(folder) == files
    assert content_sha256(folder) == canonical_sha256(files)
    assert content_sha256(folder / "a.ndt") == file_sha256(folder / "a.ndt")
    (folder / "sub" / "b.LOG").write_bytes(b"other")
    assert content_sha256(folder) != canonical_sha256(files)
    (tmp_path / "empty").mkdir()
    assert folder_files(tmp_path / "empty") == {}


def test_a_folder_with_a_link_or_that_is_not_a_folder_is_refused(tmp_path):
    import _winapi
    target, folder = tmp_path / "target", tmp_path / "folder"
    target.mkdir(), folder.mkdir()
    _winapi.CreateJunction(str(target), str(folder / "link"))
    with pytest.raises(OSError, match="通常ファイルではありません"):
        folder_files(folder)
    with pytest.raises(OSError, match="フォルダーではありません"):
        folder_files(folder / "link")
    (target / "a.txt").write_bytes(b"a")
    with pytest.raises(OSError, match="フォルダーではありません"):
        folder_files(target / "a.txt")


def test_load_json_keeps_finite_floats():
    assert load_json(b'{"a": 1.25, "b": -0.5e3}') == {"a": 1.25, "b": -500.0}

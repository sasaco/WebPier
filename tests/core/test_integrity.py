"""Strict JSON in and out, and content hashes, shared by CLI, GUI and exporters."""

import hashlib
import math

import pytest

from webpier.core.errors import InputError
from webpier.core.integrity import canonical_sha256, dump_json, file_sha256, load_json, sha256


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


def test_load_json_keeps_finite_floats():
    assert load_json(b'{"a": 1.25, "b": -0.5e3}') == {"a": 1.25, "b": -500.0}

"""Native framing and corrupt-engineering-record rejection tests."""

from copy import deepcopy

import pytest
from test_jrsnap_export import build, calculation

from src.inputs import InputError
from src.jrsnap_ndu import serialize_ndu, validate_ndu_bytes


@pytest.fixture(scope="module")
def model():
    return build(calculation())


@pytest.fixture(scope="module")
def data(model):
    return serialize_ndu(model)


def change(data, key, index, value):
    lines = data.decode("cp932").splitlines()
    for i, line in enumerate(lines):
        if line.startswith(key + "="):
            fields = line.split("=", 1)[1].split(",")
            fields[index] = value
            lines[i] = key + "=" + ",".join(fields)
            return ("\r\n".join(lines) + "\r\n").encode("cp932")
    raise AssertionError(key)


def test_native_is_deterministic_cp932_crlf_with_no_old_project_links(model, data):
    assert serialize_ndu(deepcopy(model)) == data
    text = data.decode("cp932")
    assert text.startswith("Virsion=5.2.3.S.4\r\n")
    assert "TishouNum=0\r\nTisou=\r\n" in text
    assert "NDTPath" not in text and "SoilRenkei" not in text and "CHOKU_KISO1=" not in text
    assert b"\n" not in data.replace(b"\r\n", b"")
    summary = validate_ndu_bytes(data)
    assert summary["counts"] == {"nodes": 7, "members": 6, "elements": 6,
                                 "rebar_rows": 11, "member_loads": 8, "joint_loads": 10}


@pytest.mark.parametrize("key,index,value", [
    ("DataInfo", 3, "99"),
    ("DataInfo", 18, "nan"),
    ("DataInfo", 19, "inf"),
    ("ElementInfo4", 6, "9"),
    ("NonLinInfo1", 1, "9"),
    ("NonLinInfo1", 5, "NaN"),
    ("SectInfo1", 4, "0"),
    ("SectConc1", 2, "inf"),
    ("SectSafe1", 6, "nan"),
    ("FootInfo1", 1, "999"),
    ("FootInfo1", 7, "0"),
    ("FootInfo1", 8, "nan"),
    ("FootInfo1", 10, "90"),
    ("FootInfo1", 11, "3"),
    ("MLoadInfo8", 2, "999"),
    ("JLoadInfo9", 3, "1"),
    ("ConbAlpf1", 7, "0"),
])
def test_invalid_physical_fields_and_references_are_rejected(data, key, index, value):
    with pytest.raises(InputError):
        validate_ndu_bytes(change(data, key, index, value))


@pytest.mark.parametrize("mutation", [
    lambda data: data.replace(b"\r\n", b"\n"),
    lambda data: data + b"JointXY8=0,99,8\r\n",
    lambda data: data.replace(b"JibanCaseNum=1\r\n", b""),
    lambda data: data.replace(b"Tisou=\r\n", b""),
    lambda data: data.replace(b"Grid=1,1,1,1", b"Grid=1,1,1,1\r\nGrid=1,1,1,1"),
])
def test_missing_extra_duplicate_and_bad_newline_records_rejected(data, mutation):
    with pytest.raises(InputError):
        validate_ndu_bytes(mutation(data))


def test_reordered_nodes_rejected_even_when_ids_are_valid(data):
    lines = data.decode("cp932").splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("JointXY1="))
    lines[first], lines[first + 1] = lines[first + 1], lines[first]
    with pytest.raises(InputError, match="順序"):
        validate_ndu_bytes(("\r\n".join(lines) + "\r\n").encode("cp932"))


@pytest.mark.parametrize("text", ["bad\nline", "x,y", "a=b", "emoji😀", "x" * 41])
def test_unsafe_text_is_never_substituted_or_written(model, text):
    changed = deepcopy(model)
    changed["cases"][0]["label"] = text
    with pytest.raises(InputError):
        serialize_ndu(changed)

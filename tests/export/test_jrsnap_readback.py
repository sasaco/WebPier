"""Readback of an NDU that JRSNAP has saved: the same records in the same order with the same values.

JRSNAP writes some numbers in its own format (GanmaA 1.2 → 1.20); such a field is the same value and is listed as
normalized. Anything else (a record dropped, added or moved, a field count, a value, a blank) is an error.
"""

from copy import deepcopy

import pytest

from jrsnap_support import model
from webpier.export.jrsnap import write_ndu
from webpier.export.jrsnap.readback import (
    Normalized, ReadbackError, compare_readback, compare_state, parse_records, summarize,
)


@pytest.fixture(scope="module")
def transverse():
    return write_ndu(model("transverse"))


@pytest.fixture(scope="module")
def longitudinal():
    return write_ndu(model("longitudinal"))


def replace(data, old, new):
    old, new = old.encode("cp932"), new.encode("cp932")
    assert data.count(old) == 1, old
    return data.replace(old, new)


def test_records_are_keys_and_fields_in_file_order():
    records = parse_records(b"Virsion=5.2.3.S.4\r\nSHABUZAI_INFO\r\nTisou=\r\nA=1, ,x\r\n")
    assert records == (("Virsion", ("5.2.3.S.4",)), ("SHABUZAI_INFO", None), ("Tisou", ("",)),
                       ("A", ("1", " ", "x")))


@pytest.mark.parametrize("data,message", [
    (b"A=1\r\nB=2", "CRLF"),
    (b"A=1\nB=2\r\n", "CRLF"),
    (b"A=1\r\r\n", "CRLF"),
    (b"A=1\r\n\r\n", "空の行"),
    (b"", "空"),
    (b"A=\x82\r\n", "CP932"),
])
def test_a_file_that_is_not_cp932_records_with_crlf_is_rejected(data, message):
    with pytest.raises(ReadbackError, match=message):
        parse_records(data)


def test_the_same_bytes_read_back_unchanged(transverse):
    readback = compare_readback(transverse, transverse)
    assert readback.records == transverse.count(b"\r\n")
    assert readback.normalized == ()


def test_a_number_written_in_another_format_is_normalized(longitudinal):
    saved = replace(longitudinal, "GanmaA=1.2,1,1,1\r\n", "GanmaA=1.20,1.00,1.00,1.00\r\n")
    assert compare_readback(longitudinal, saved).normalized == (
        Normalized("GanmaA", 0, "1.2", "1.20"), Normalized("GanmaA", 1, "1", "1.00"),
        Normalized("GanmaA", 2, "1", "1.00"), Normalized("GanmaA", 3, "1", "1.00"))


@pytest.mark.parametrize("old,new,message", [
    ("SNAPConbNum=2\r\n", "SNAPConbNum=1\r\n", "SNAPConbNum"),  # a value
    ("GanmaA=1.2,1,1,1\r\n", "GanmaA=1.2,1,1,1,0\r\n", "GanmaA: 欄の数"),
    ("Tisou=\r\n", "Tisou= \r\n", "Tisou"),  # EMPTY and BLANK are different
    ("SHABUZAI_INFO\r\n", "SHABUZAI_INFO=\r\n", "SHABUZAI_INFO"),
    ("LoadTitle1=固定死荷重\r\n", "LoadTitle1=固定荷重\r\n", "LoadTitle1"),
])
def test_a_changed_record_is_an_error(transverse, old, new, message):
    with pytest.raises(ReadbackError, match=message):
        compare_readback(transverse, replace(transverse, old, new))


@pytest.mark.parametrize("written,saved", [("A=1\r\n", "A= 1\r\n"), ("A=Infinity\r\n", "A=Inf\r\n"),
                                           ("A=True\r\n", "A=1\r\n")])
def test_only_a_plain_finite_number_may_be_written_differently(written, saved):
    with pytest.raises(ReadbackError, match="A の 1 欄目"):
        compare_readback(written.encode(), saved.encode())


def test_a_dropped_or_moved_record_is_an_error(transverse):
    lines = transverse.split(b"\r\n")[:-1]
    dropped = b"".join(line + b"\r\n" for line in lines if not line.startswith(b"SNAPConb2="))
    with pytest.raises(ReadbackError, match="レコードの数"):
        compare_readback(transverse, dropped)
    first, second = [index for index, line in enumerate(lines) if line.startswith((b"SNAPConb1=", b"SNAPConb2="))]
    lines[first], lines[second] = lines[second], lines[first]
    with pytest.raises(ReadbackError, match="SNAPConb1"):
        compare_readback(transverse, b"".join(line + b"\r\n" for line in lines))


def test_summary_counts_the_declared_records(transverse, longitudinal):
    assert summarize(parse_records(transverse)) == {
        "counts": {"JointNum": 8, "MemberNum": 7, "ElementNum": 7, "LoadNum": 9, "MLoadNum": 8, "JLoadNum": 11,
                   "SNAPConbNum": 2, "ConbNum": 2},
        "combinations": [["1", "1", "0", "0", "1", "1", "1", "1", "1", "0", "1", "1", "1", " ", " ", " ", " ", " ",
                          " ", "0", "0"],
                         ["1", "1", "0", "0", "1", "1", "1", "1", "0", "1", "1", "1", "1", " ", " ", " ", " ", " ",
                          " ", "0", "0"]],
    }
    assert summarize(parse_records(longitudinal))["counts"]["SNAPConbNum"] == 1


def test_a_count_that_differs_from_its_records_is_an_error(transverse):
    lines = [line for line in transverse.split(b"\r\n")[:-1] if not line.startswith(b"SNAPConb2=")]
    with pytest.raises(ReadbackError, match="SNAPConbNum = 2 に対して SNAPConb が 1 件"):
        summarize(parse_records(b"".join(line + b"\r\n" for line in lines)))


def test_a_missing_count_is_an_error():
    with pytest.raises(ReadbackError, match="JointNum がありません"):
        summarize(parse_records(b"Virsion=5.2.3.S.4\r\n"))


STATE = {"read_code": 0,
         "counts": {"G_intJointNum": 8, "G_intMemberNum": 7, "G_intElementNum": 7, "G_intSectNum": 1,
                    "G_intSuppotNum": 3, "G_intLoadNum": 9, "G_intMLoadNum": 8, "G_intJLoadNum": 11,
                    "G_intConbNum": 2},
         "combinations": [{"rho_m": 1, "alpha_f": 1, "cases": [1, 2, 3, 4, 5, 6, 7, 8, 9],
                           "coefficients": [1, 1, 1, 1, 1, 0, 1, 1, 1]},
                          {"rho_m": 1, "alpha_f": 1, "cases": [1, 2, 3, 4, 5, 6, 7, 8, 9],
                           "coefficients": [1, 1, 1, 1, 0, 1, 1, 1, 1]}]}


def state(**changes):
    value = deepcopy(STATE)
    for path, item in changes.items():
        node = value
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = item
    return value


def test_what_jrsnap_holds_after_reading_is_what_we_wrote(transverse):
    """The probe's literal output for the 0720 NDU of current.json (2026-10-18, JRSNAP 5.2-L03): two combinations."""
    compare_state(parse_records(transverse), STATE)


@pytest.mark.parametrize("changes,message", [
    ({"read_code": 200}, "読込みの戻り値 200"),
    ({"counts/G_intJointNum": 7}, "JointNum = 8 に対して JRSNAP は 7"),
    ({"counts/G_intConbNum": 1, "combinations": STATE["combinations"][:1]}, "SNAPConbNum = 2 に対して JRSNAP は 1"),
    ({"combinations": STATE["combinations"][:1]}, "組合せの数"),
    ({"combinations/1/coefficients/4": 1}, "組合せ 2 の係数"),
    ({"combinations/1/cases": [1, 2, 3, 4, 5, 6, 7, 8]}, "組合せ 2 の荷重ケース"),
    ({"combinations/0/rho_m": 1.1}, "組合せ 1 の ρm"),
    ({"combinations/0/alpha_f": 0.9}, "組合せ 1 の αf"),
])
def test_a_state_that_differs_is_an_error(transverse, changes, message):
    with pytest.raises(ReadbackError, match=message):
        compare_state(parse_records(transverse), state(**changes))

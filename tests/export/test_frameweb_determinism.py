"""The FrameWeb input is a pure function of the calc result: same result, same keys in the same order, same bytes."""

import pytest

from frameweb_support import ASYMMETRIC, PEDESTAL, longitudinal
from webpier.core.integrity import dump_json, sha256
from webpier.export.frameweb import build_frameweb
from webpier.export.frameweb.build import frameweb_document
from webpier.export.frameweb.cases import frameweb_cases
from webpier.export.frameweb.longitudinal import LONGITUDINAL


@pytest.mark.parametrize("changes", [{}, PEDESTAL, ASYMMETRIC], ids=["current", "pedestal", "asymmetric"])
def test_same_result_same_bytes(changes):
    first, second = longitudinal(**changes), longitudinal(**changes)
    a, b = build_frameweb(first), build_frameweb(second)
    assert a == b
    assert dump_json(a) == dump_json(b) and sha256(dump_json(a)) == sha256(dump_json(b))
    assert build_frameweb(first) == a  # the result is not changed by building


def test_key_order_is_by_number():
    document = build_frameweb(longitudinal(**PEDESTAL))
    for table in ("node", "member", "load", "define", "combine", "pickup"):
        assert list(document[table]) == [str(n) for n in range(1, len(document[table]) + 1)], table
    assert list(document["fix_node"]) == ["1", "2"]
    for row in document["combine"].values():
        columns = [int(key[1:]) for key in row if key.startswith("C")]
        assert list(row)[:2] == ["row", "name"] and columns == sorted(columns)
    text = dump_json(document).decode("utf-8")
    assert text.endswith("}\n") and "NaN" not in text and "Infinity" not in text


def test_zero_coefficients_are_left_out():
    # With ρs = 0.004 the serviceability train and impact have the printed factor 0.00: they add nothing, so their columns
    # are left out (build_frameweb then rejects the empty combination 7, see test_frameweb_cases).
    result = longitudinal(**{"上部構造/列車/荷重修正係数/使用性": 0.004})
    document = frameweb_document(result.frame, frameweb_cases(result, LONGITUDINAL))
    assert {key for key in document["combine"]["5"] if key.startswith("C")} == {"C1", "C2", "C6", "C14"}
    assert {key for key in document["combine"]["7"] if key.startswith("C")} == set()

"""The FrameWeb inputs are pure functions of the calc results: same result, same keys in the same order, same bytes."""

import pytest

from frameweb_support import (
    ASYMMETRIC, CURVE, PEDESTAL, T_ASYMMETRIC, T_PEDESTAL, WIDTHS, ground, longitudinal, transverse,
)
from webpier.core.integrity import dump_json, sha256
from webpier.export.frameweb import build_frameweb, build_frameweb_transverse
from webpier.export.frameweb.build import frameweb_document
from webpier.export.frameweb.cases import frameweb_cases
from webpier.export.frameweb.longitudinal import longitudinal_profile


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
    # are left out (build_frameweb then rejects the empty combination of 変動作用, see test_frameweb_cases). 縁応力度 低水位
    # of ① is combination 34 and 変動作用 of ① 42 (decisions 102, 120); D1, D2, Wp3, S2 and 1.0LR of ① (Define 16) remain.
    result = longitudinal(**{"上部構造/列車/荷重修正係数/使用性": 0.004})
    document = frameweb_document(result.frame, frameweb_cases(result, longitudinal_profile(result)))
    assert {key for key in document["combine"]["34"] if key.startswith("C")} == {"C1", "C2", "C5", "C6", "C16"}
    assert {key for key in document["combine"]["42"] if key.startswith("C")} == set()


@pytest.mark.parametrize("changes", [{}, T_PEDESTAL, T_ASYMMETRIC, CURVE, WIDTHS | ground(5.2)],
                         ids=["current", "pedestal", "asymmetric", "curve", "haunch_cut"])
def test_same_transverse_result_same_bytes(changes):
    first, second = transverse(**changes), transverse(**changes)
    a, b = build_frameweb_transverse(first), build_frameweb_transverse(second)
    assert a == b and dump_json(a) == dump_json(b)
    assert build_frameweb_transverse(first) == a
    for table in ("node", "member", "load", "define", "combine", "pickup"):
        assert list(a[table]) == [str(n) for n in range(1, len(a[table]) + 1)], table
    for case in a["load"].values():
        assert [row["row"] for row in case.get("load_member", [])] == list(
            range(1, len(case.get("load_member", [])) + 1))

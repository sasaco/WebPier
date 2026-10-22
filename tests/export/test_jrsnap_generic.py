"""The NDU of 0710 / 0720 with a load model (decision 70): the cases are named and ordered as the load model declares
them, and the validator checks those names and that order."""

import re

import pytest

from generic_support import generic_seismic
from webpier.calc.column_rebar import column_layout
from webpier.calc.embedment import calculate_embedment
from webpier.calc.frame import Direction
from webpier.core.errors import InputError
from webpier.export.jrsnap import LONGITUDINAL, TRANSVERSE, build_ndu, validate_ndu, write_ndu
from webpier.export.jrsnap.profile import generic_profile

TITLES = ["固定死荷重", "付加死荷重", "浮力", "地震時の車荷重", "上部工の慣性力", "活荷重慣性力", "自重による地震時慣性力"]


def built(direction: Direction):
    pier, foundation, result = generic_seismic(direction)
    profile = generic_profile(LONGITUDINAL if direction is Direction.LONGITUDINAL else TRANSVERSE, result)
    model = build_ndu(profile, pier, foundation, calculate_embedment(pier, foundation), column_layout(pier), result)
    return profile, model, write_ndu(model)


@pytest.mark.parametrize("direction", list(Direction))
def test_the_ndu_passes_with_the_cases_the_load_model_declares(direction):
    profile, model, data = built(direction)
    summary = validate_ndu(data, profile)
    assert (summary.cases, summary.combinations) == (7, 4)  # the one combination by the four 照査パターン
    assert [case.title for case in model.cases] == TITLES
    assert [case.increment for case in model.cases] == [0, 0, 0, 0, 1, 4, 1]  # 固定 0, 増分 1, 限定増分 4
    assert [c.coefficients for c in model.combinations] == [(1,) * 7] * 4


def test_the_labels_of_the_loads():
    profile, _, _ = built(Direction.LONGITUDINAL)
    assert list(profile.case_titles) == ["D1", "D2", "WP_NORMAL", "LE", "EQ1", "EQL", "EQ2"]
    assert profile.seat_labels == {"D1": "上部工反力", "D2": "上部工反力", "LE": "地震時の車荷重", "EQ1": "上部工の慣性力",
                                   "EQL": "活荷重慣性力"}
    assert profile.footing_labels == {"D1": "フーチング自重", "D2": "上載土", "WP_NORMAL": "浮力", "EQ2": "フーチング慣性力"}
    assert profile.member_labels == {"D1": "柱自重", "EQ2": "自重慣性力"}
    assert (profile.data_name, profile.control) == (LONGITUDINAL.data_name, LONGITUDINAL.control)


def test_the_validator_checks_the_declared_names_and_order():
    profile, _, data = built(Direction.LONGITUDINAL)
    swapped = data.replace("上部工の慣性力".encode("cp932"), "活荷重慣性力X".encode("cp932"), 1)
    with pytest.raises(InputError, match=re.escape("LoadTitle5: 線路方向の基本ケース5は「上部工の慣性力」が必要です")):
        validate_ndu(swapped, profile)

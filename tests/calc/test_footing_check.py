"""0810 / 0820 フーチングの断面照査 (decision 60, ADR-0008): the conditions Capacita is given, from the input, the bars
and the response values of 0800. One point per direction (部材 フーチング 1000 × H6, 下側引張, N′d 0); the safety
forces are the safety column with the larger Md (Md, Vd, La in mm), the durability moments the short-term and the
long-term Md, the seismic forces the 地震時 column's; the materials and conditions follow 0611 (the 柱の断面照査
conditions, Dmax of the column concrete). Expected values: the hand calculation footing_hand.json and the sample's
bars; nothing is computed by the code under test. The checks themselves are Capacita's.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from footing_support import completed, footing_pier
from webpier.calc.column_check import KR, K4, SAFETY_FACTORS_OF_BODY
from webpier.calc.footing_check import REPORT_SECTIONS, calculate_footing_check
from webpier.core.errors import InputError

HAND = json.loads((Path(__file__).parents[1] / "fixtures" / "example2" / "footing_hand.json").read_text(
    encoding="utf-8"))


def checked(direction="0800_longitudinal", **changes):
    return calculate_footing_check(footing_pier(**changes), completed(direction, **changes))


def test_the_point_is_the_overhang_section_of_one_metre_by_h6():
    check = checked()
    assert (check.direction, check.name, check.member) == ("線路", "線路方向", "フーチング")
    assert (check.width.value, check.depth.value) == (1000, 2700)


def test_the_bars_and_materials_are_the_footings():
    check = checked()
    assert (check.bars.diameter.value, check.bars.count.value, check.bars.cover.value, check.bars.pitch.value) == (
        25, 8, 100, 125)
    assert (check.stirrups.diameter.value, check.stirrups.legs.value, check.stirrups.pitch.value) == (16, 2, 250)
    assert (check.main_steel.grade, check.main_steel.fsy.value, check.main_steel.fsu.value) == ("SD390", 390, 560)
    assert (check.stirrup_steel.grade, check.stirrup_steel.fsu.value) == ("SD390", 560)
    assert (check.fck.value, check.aggregate_max.value) == (27, 25)


def test_the_conditions_are_the_column_checks():
    check = checked()
    assert (check.environment, check.environment_number, check.ecsd.value, check.body, check.jr001, check.jr004) == (
        "常時乾燥", 1, 300, "運輸機構", True, False)
    assert check.safety_factors == SAFETY_FACTORS_OF_BODY["運輸機構"]
    assert (check.kr, check.k4) == (KR, K4)


@pytest.mark.parametrize("direction,column", [("0800_longitudinal", "safety_shear"),
                                              ("0800_transverse", "safety_moment")])
def test_the_safety_forces_are_the_safety_column_with_the_larger_md(direction, column):
    # Hand: along the track Md最大 790.66 < Vd最大 799.16; across it 874.85 > 821.70.
    check, hand = checked(direction), HAND["directions"][direction]["columns"][column]
    assert check.safety.column == column
    assert (check.safety.md.value, check.safety.vd.value, check.safety.la.value) == (
        hand["Md_design"], hand["Vd_design"], round(hand["La"] * 1000))
    assert check.safety.la.unit == "mm" and check.safety.la.digits == 0


@pytest.mark.parametrize("direction", ["0800_longitudinal", "0800_transverse"])
def test_the_durability_moments_are_the_short_and_long_term_columns(direction):
    check, columns = checked(direction), HAND["directions"][direction]["columns"]
    assert (check.durability_short.column, check.durability_short.md.value) == ("short_term",
                                                                               columns["short_term"]["Md_design"])
    assert (check.durability_long.column, check.durability_long.md.value) == ("long_term",
                                                                             columns["long_term"]["Md_design"])
    assert check.durability_short.vd is None and check.durability_long.la is None


@pytest.mark.parametrize("direction,la", [("0800_longitudinal", 1942), ("0800_transverse", 1294)])
def test_the_seismic_forces_are_the_seismic_column(direction, la):
    check, hand = checked(direction), HAND["directions"][direction]["seismic_own_input"]
    assert check.seismic.column == "seismic"
    assert (check.seismic.md.value, check.seismic.vd.value, check.seismic.la.value) == (
        hand["Md_design"], hand["Vd_design"], la)


def test_across_the_track_the_point_and_bars_are_the_other_direction():
    check = checked("0800_transverse")
    assert (check.direction, check.name) == ("直角", "線路直角方向")
    assert (check.bars.diameter.value, check.bars.cover.value) == (29, 127)


def test_the_report_sections_are_the_five_of_the_sample():
    assert checked().sections == REPORT_SECTIONS == (
        "bending_safety_destruction", "shear_safety_destruction", "bending_durability", "bending_restorability_eq",
        "shear_restorability_eq")


@pytest.mark.parametrize("path,message", [
    ("柱の断面照査/水掛かりの程度", "柱の断面照査.水掛かりの程度: 値が必要です"),
    ("柱の断面照査/ε'csd", "柱の断面照査.ε'csd: 値が必要です"),
    ("柱の断面照査/適用基準の機関", "柱の断面照査.適用基準の機関: 値が必要です"),
    ("柱の断面照査/JR-001", "柱の断面照査.JR-001: 値が必要です"),
    ("柱の断面照査/JR-004", "柱の断面照査.JR-004: 値が必要です"),
    ("鉄筋/フーチング/aggregate_max_mm", "鉄筋.フーチング.aggregate_max_mm: 値が必要です"),
])
def test_a_blank_condition_is_an_input_error(path, message):
    with pytest.raises(InputError, match=re.escape(message)):
        checked(**{path: None})

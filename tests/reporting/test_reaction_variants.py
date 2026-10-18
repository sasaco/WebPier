"""0600 variants: each input branch prints the formula it was calculated with.

The generic tests (semantics, hand-check, tables) run for every case of
reaction_report_cases; these check what each variant changes in the text.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from reaction_report_cases import case, text
from webpier.core.printed import LENGTH, Printed


def records(name: str, result=None, pier=None) -> dict[str, str]:
    from webpier.reporting.stages.reaction import semantic_records

    if result is None:
        result, pier = case(name)
    return {record["id"].removeprefix("0600/"): re.sub(r"\s+", "", record["text"])
            for record in semantic_records(result, pier)}


def test_a_pedestal_is_calculated_and_drawn():
    result, pier = case("pedestal")
    actual = records("pedestal")
    sw = result.self_weight
    assert actual["weight.pedestal.volume"] == f"V=7.200×0.250={text(sw.pedestal.rows[0].volume)}m^3"
    assert actual["weight.pedestal.x_l"].endswith("=(2×0.300+1.200−3.000−0.400+0.200)/2=-0.700m")
    assert "|0.250|" in actual["weight.shape.figure"]  # H1 is dimensioned
    assert "0.250" not in records("current")["weight.shape.figure"].replace("2.250", "")
    # The footing haunch (H5 = 0.400) is placed by the column's position, the beam haunch by the beam's.
    # h is the haunch height, defined with z.
    assert actual["weight.footing.haunch.x_l"].startswith("xL=xL(柱)×z/h=")
    assert actual["weight.beam.haunch.x_l"].startswith("xL=xL(はり)×z/h=")
    assert "（hはハンチの高さ。" in actual["weight.beam.z.introduction"]


@pytest.mark.parametrize("name,wedge_side", [("pedestal", "end"), ("mirrored", "origin")])
def test_the_submerged_sloped_soil_is_a_wedge_on_the_lower_side(name: str, wedge_side: str):
    result, _ = case(name)
    actual = records(name)
    high = result.self_weight.buoyancy_high
    assert actual["weight.water.high.wedge"] == (f"b'=min(Bh''/Δdf,B)=min({text(result.self_weight.footing_length)}"
                                                 f"×{text(high.submerged)}/{text(result.self_weight.soil_step)},"
                                                 f"{text(result.self_weight.footing_length)})={text(high.wedge)}m")
    expected = "xL=b''+b'/3−B/2=" if wedge_side == "end" else "xL=2b'/3−B/2="
    assert actual["weight.water.high.wedge.x_l"].startswith(expected)
    # The low water is below the footing top: nothing of the slope is submerged.
    assert actual["weight.water.low.wedge"] == "b'=0.000m"


def test_no_haunch_no_cover_and_no_bearing():
    result, _ = case("bare")
    actual = records("bare")
    assert actual["weight.beam.haunch.x_l"] == "xL=0.000m"  # H3 = 0: no position from z / H3
    assert actual["weight.soil.trapezoid.x_l"] == "xL=0.000m"  # df1 + df2 = 0
    assert actual["weight.soil.centroid.x_l"] == "xL=0.000m"  # ΣV = 0
    assert "weight.soil.centroid.note" in actual
    assert "dead.end.bearings" not in actual and "dead.end.none" in actual
    assert actual["dead.end.sum.d1"] == "RC(D1)=0.00kN"
    assert actual["dead.end.tracks"] == "n=0.000"
    assert actual["long.rail.end.long_rail"].endswith("×0.000=0.00kN")
    assert result.dead.end.track_total.value == 0.0


def test_empty_slots_keep_their_bearing_numbers_and_zero_snow_is_printed():
    actual = records("slots")
    table = actual["dead.origin.bearings"]
    assert [name for name in ("G1", "G2", "G3", "G4", "G7") if f"|{name}|" in table] == ["G1", "G3", "G4", "G7"]
    assert "dead.origin.double.1" not in actual and "dead.origin.double.6" in actual
    assert actual["dead.end.double.9"].startswith("G10=")
    assert actual["dead.origin.sum.snow2"] == "RB(S2)=0.00+0.00+0.00+0.00=0.00kN"
    assert actual["trans.seismic.origin.force"] == "H=(D1+D2+S2)×Kh=(5740.00+520.00+0.00)×1.00=6260.00kN"


def test_p16_uses_the_axle_load_rule_and_ea17_its_own_rule():
    current, ea17 = records("current"), records("ea17")
    assert current["long.brake.rule"] == "車両P-16の制動荷重・始動荷重は軸重式で求める（車両の選択による）。"
    assert current["long.brake.origin.braking"] == "T(制動)=(0.20+0.80/20.000×20.000)×160.00=160.00kN"
    assert current["long.brake.origin.starting"] == "T(始動)=(0.19+0.76/20.000×20.000)×160.00=152.00kN"
    assert current["long.brake.origin.adopted"] == "B=max(T(制動),T(始動))=max(160.00,152.00)=160.00kN"
    assert ea17["long.brake.rule"] == "車両EA-17の制動荷重・始動荷重はEA-17の規定式で求める（車両の選択による）。"
    result, _ = case("ea17")
    loading = result.train.loading
    assert ea17["long.brake.origin.braking"] == (f"T(制動)=(0.27+1.00/16.400)×({text(loading.ra)}+{text(loading.rb)})="
                                                 f"{text(result.longitudinal.origin.braking)}kN")


def test_a_curve_prints_the_centrifugal_coefficient_and_a_straight_track_says_why_it_is_zero():
    current, ea17 = records("current"), records("ea17")
    assert "trans.centrifugal.origin.straight" in current
    assert current["trans.centrifugal.origin.alpha"] == "αc=0.000"
    result, _ = case("ea17")
    alpha = result.transverse.origin.centrifugal_coefficient
    assert ea17["trans.centrifugal.origin.alpha"] == f"αc=V^2/(127R)=130^2/(127×600)={text(alpha)}"
    assert "trans.centrifugal.origin.straight" not in ea17


def test_bearing_types_choose_the_printed_candidates():
    current, ea17 = records("current"), records("ea17")
    # current: B movable, C fixed. ea17: B fixed, C movable.
    for actual, movable, fixed in ((current, "origin", "end"), (ea17, "end", "origin")):
        key = "long.case.safety_lr10_b10"
        assert f"{key}.{movable}.floor" in actual and f"{key}.{movable}.candidate" not in actual
        assert f"{key}.{fixed}.candidate" in actual and f"{key}.{fixed}.floor" not in actual
    assert current["long.seismic_girder.origin.force"].startswith("H=T/n=")
    assert current["long.seismic_girder.end.force"].startswith("H=T=")


def test_the_restorability_braking_factor_is_the_entered_one_or_rho_times_gamma():
    current = records("current")
    key = "long.case.restorability_lr10_b10"
    assert current[f"{key}.end.brake"] == "γB=1.000"  # entered (Example2 7-11)
    assert "end.brake.note" in "".join(k for k in current if k.startswith(key))
    assert current[f"{key}.origin.brake"] == "γB=ρf×1.0=1.231×1.0=1.23"


def test_zero_aggregates_print_their_centroid_without_dividing_by_zero():
    result, pier = case("current")
    sw = result.self_weight
    zero = Printed(0.0, 2, "kN")
    bottom = replace(sw.pier_bottom, weight=zero, structure_weight=zero)
    actual = records("", replace(result, self_weight=replace(sw, pier_bottom=bottom)), pier)
    assert actual["weight.bottom.x_l"] == f"xL={text(sw.pier_bottom.x_l)}m"
    assert actual["weight.bottom.y"] == f"y={text(sw.pier_bottom.y)}m"


def test_a_girder_without_axles_says_so():
    result, pier = case("current")
    loading = result.train.loading
    # Without the two end axles (x = 20.0, 22.2), the last spacing runs from x = 17.2 to D (29.625).
    origin_only = replace(loading, axles=tuple(axle for axle in loading.axles if axle.girder.value == "origin"),
                          end_axles=Printed(0.0, 0, ""), spacings=(*loading.spacings[:4], LENGTH(12.425)))
    actual = records("", replace(result, train=replace(result.train, loading=origin_only)), pier)
    assert actual["train.loading.c"] == f"RC={text(loading.rc)}kN"
    assert "train.loading.c.none" in actual


def test_a_derivation_lhs_must_be_text():
    from webpier.reporting.stages.reaction.manuscript import Manuscript, sub

    with pytest.raises(TypeError, match="導出式"):
        Manuscript().equation("x", sub("T", "1"), "1", wide=True)


def test_duplicate_keys_and_unknown_nodes_are_rejected():
    from webpier.reporting.stages.reaction.manuscript import Manuscript, operand, plain

    m = Manuscript()
    m.paragraph("a", "text")
    with pytest.raises(ValueError, match="重複"):
        m.paragraph("a", "text")
    with pytest.raises(TypeError, match="未対応"):
        plain(object())
    with pytest.raises(TypeError, match="bool"):
        operand(True)
    assert operand(1.5) == "1.5" and operand(2) == "2"


def test_the_axle_count_of_ra_is_read_from_the_result():
    """RA = P × (axles on the girder) − RB: the count is the calculator's, not counted by the report."""
    result, pier = case("current")
    odd = replace(result.train.loading, origin_axles=Printed(7.0, 0, ""))
    actual = records("", replace(result, train=replace(result.train, loading=odd)), pier)
    assert actual["train.loading.a"] == "RA=P×軸数−RB=160.00×7−272.47=367.53kN"

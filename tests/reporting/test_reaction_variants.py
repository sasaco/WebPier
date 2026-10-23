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
    pedestal = f"|桁受け|V1|1.200×6.000×0.250|=|{text(sw.pedestal.rows[0].volume)}|24.5|{text(sw.pedestal.weight)}|"
    assert pedestal in actual["weight.parts.table"]
    assert "|0.250|" in actual["weight.shape.figure"]  # H1 is dimensioned
    assert "0.250" not in records("current")["weight.shape.figure"].replace("2.250", "")
    # The footing haunch (H5 = 0.400) is a row of its own, the prismatoid between B × W and B8 × W8; with the
    # footing's prism the footing has two rows and its weight is their sum (decision 79).
    haunch = f"|フーチング|V5|0.400/6×(6.000×4.600+2.400×9.000+2×(2.400×4.600+6.000×9.000))|=|"
    assert haunch in actual["weight.parts.table"]
    first, second = (text(weight) for weight in sw.footing.weights)
    assert actual["weight.footing.sum.weight"] == f"W={first}+{second}={text(sw.footing.weight)}kN"
    # The overall footing length and width are dimensioned under its parts.
    assert "|6.000|" in actual["weight.shape.figure"] and "|9.000|" in actual["weight.shape.figure"]


@pytest.mark.parametrize("name,wedge_side", [("pedestal", "end"), ("mirrored", "origin")])
def test_the_submerged_sloped_soil_is_a_wedge_on_the_lower_side(name: str, wedge_side: str):
    result, _ = case(name)
    actual = records(name)
    high = result.self_weight.buoyancy_high
    sw = result.self_weight
    assert actual["weight.water.high.wedge"] == (f"b'=min({text(sw.footing_length)}×{text(high.submerged)}"
                                                 f"/{text(sw.soil_step)},{text(sw.footing_length)})={text(high.wedge)}m")
    # The wedge lies on the lower side (its position is of the calculation only, decision 79).
    assert (high.body.rows[2].x_l.value > 0) is (wedge_side == "end")
    # The low water is below the footing top: nothing of the slope is submerged.
    assert actual["weight.water.low.wedge"] == "b'=0.000m"


def test_no_haunch_no_cover_and_no_bearing():
    result, _ = case("bare")
    actual = records("bare")
    sw = result.self_weight
    # H3 = 0 and df1 = df2 = 0: the beam haunch and the soil rows of V = 0 are left out of table 6.2.1, so the beam is
    # one row with no sum (decision 79).
    assert sw.beam.rows[1].volume.value == 0 and sw.overburden.rows[0].volume.value == 0
    shown = sum(row.volume.value != 0 for body in (sw.pedestal, sw.beam, sw.column, sw.footing, sw.overburden)
                for row in body.rows)
    assert actual["weight.parts.table"].count("|=|") == shown
    assert "weight.beam.sum.weight" not in actual
    assert "dead.end.bearings" not in actual
    assert actual["dead.end.sum.d1"] == "RC(D1)=0.00kN"
    assert actual["dead.end.tracks"] == "n=0.000"
    assert actual["long.rail.long_rail.end"].endswith("×0.000=0.00kN")
    assert result.dead.end.track_total.value == 0.0


def test_empty_slots_keep_their_bearing_numbers_and_zero_snow_is_printed():
    actual = records("slots")
    table = actual["dead.origin.bearings"]
    assert [name for name in ("G1", "G2", "G3", "G4", "G7") if f"|{name}|" in table] == ["G1", "G3", "G4", "G7"]
    assert "dead.origin.double.1" not in actual and "dead.origin.double.6" in actual
    assert actual["dead.end.double.9"].startswith("G10=")
    assert actual["dead.origin.sum.snow2"] == "RB(S2)=0.00+0.00+0.00+0.00=0.00kN"
    assert actual["trans.seismic.origin.force"] == "H=(5740.00+520.00+0.00)×1.00=6260.00kN"


def test_p16_uses_the_axle_load_rule_and_ea17_its_own_rule():
    current, ea17 = records("current"), records("ea17")
    assert current["long.brake.braking.formula"] == "制動荷重：(0.20+0.80/Lv・L)・P"
    assert current["long.brake.origin.braking"] == "T(制動)=(0.20+0.80/20.000×20.000)×160.00=160.00kN"
    assert current["long.brake.origin.starting"] == "T(始動)=(0.19+0.76/20.000×20.000)×160.00=152.00kN"
    assert current["long.brake.origin.adopted"] == "B=max(160.00,152.00)=160.00kN"
    assert ea17["long.brake.braking.formula"] == "制動荷重：(0.27+1.00/Lv)・ΣR"
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
    assert current["long.seismic_girder.origin.share"] == "T/n=13580.00/2=6790.00kN"
    assert current["long.seismic_girder.end.share"] == "T=4740.00kN"
    assert current["long.seismic_girder.end.force"] == "※∴H=4740.00kN"
    # The fixed bearing's Rm is the far (movable) bearing's (07 7-5 calls it the fixed bearing's).
    assert current["long.case.safety_lr10_b10.end.vertical.label"] == "他端の可動支承に働く鉛直荷重"
    assert ea17["long.case.safety_lr10_b10.origin.vertical.label"] == "他端の可動支承に働く鉛直荷重"


def test_the_restorability_braking_factor_is_the_entered_one_or_rho_times_gamma():
    current, ea17 = records("current"), records("ea17")
    key = "long.case.restorability_lr10_b10"
    # current: the end girder's factor is entered (Example2 7-11), the origin girder's is ρf × 1.0 = 1.23,
    # which names the combination as 07 7-11 does.
    combination = "・1.0LR+1.23B[1.0D1+1.0D2+1.23(L+I)+S10+1.0LR+1.23Bの組合せ]"
    assert current[f"{key}.label"] == combination
    assert current[f"{key}.origin.applied"] == "※T1=1.0×400.00+1.23×160.00=596.80kN"
    assert current[f"{key}.end.applied"] == "※T2=1.0×200.00+1.000×96.00=296.00kN"
    # ea17 enters no restorability factor: both girders take ρf × 1.0.
    assert ea17[f"{key}.label"] == combination
    assert not [name for name in current if name.endswith(".brake") or name.endswith(".live")]


def test_each_combination_is_named_with_its_printed_factors():
    """07 7-7 to 7-13: γB in the label, γL and γB in the combination, the same names in the summary."""
    actual = records("current")
    assert actual["long.case.service_lr08.label"] == "・0.8LR[1.0D1+1.0D2+S2+1.0LR(8kN/m)の組合せ]"
    assert actual["long.case.safety_lr10_b11.label"] == "・1.0LR+1.35B[1.1D1+1.2D2+1.23(L+I)+S10+1.0LR+1.35Bの組合せ]"
    assert actual["long.case.safety_lr10_b10.origin.vertical.symbols"] == "Rm=1.1D1+1.2D2+1.35複線(L+I)+S10"
    assert "|1.0LR+1.23B|298.40|175.03|473.43|1.1LR+1.23B|" in actual["long.summary.table"]


def test_a_girder_without_axles_prints_its_reactions_as_values():
    result, pier = case("current")
    loading = result.train.loading
    # Without the two end axles (x = 20.0, 22.2), the last spacing runs from x = 17.2 to D (29.625).
    origin_only = replace(loading, axles=tuple(axle for axle in loading.axles if axle.girder.value == "origin"),
                          end_axles=Printed(0.0, 0, ""), spacings=(*loading.spacings[:4], LENGTH(12.425)))
    actual = records("", replace(result, train=replace(result.train, loading=origin_only)), pier)
    assert actual["train.loading.c"] == f"RC={text(loading.rc)}kN"
    assert actual["train.loading.d"] == f"RD={text(loading.rd)}kN"


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
    assert actual["train.loading.a"] == "RA=160.00×7−272.47=367.53kN"


def test_a_long_span_wraps_the_levers_of_its_reaction(tmp_path):
    # P7 終点側 61.390 m carries 12 axles: RC = P × (a1 + … + a12) / l is longer than a line, so the group wraps
    # (more than INLINE_AXLES = 8 levers); the formula still reads the same.
    from copy import deepcopy

    from reaction_report_cases import input_document
    from webpier.calc.reaction import calculate_reaction
    from webpier.inputs import parse_input
    from webpier.reporting.stages.reaction import render_reaction

    data = deepcopy(input_document("current"))
    data["上部構造"]["終点側"]["桁長"]["スパン長"] = 61.39
    pier = parse_input(data)
    result = calculate_reaction(pier)
    assert sum(axle.girder.name == "END" for axle in result.train.loading.axles) > 8
    rc = records("long", result, pier)["train.loading.c"]
    assert rc.startswith("RC=160.00×(") and rc.count("+") > 8
    render_reaction(result, pier, tmp_path / "0600.pdf")  # lays out without overflowing the line

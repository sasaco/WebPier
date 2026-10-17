"""Boundary and formula oracles for explicit JRSNAP engineering inputs."""

import math
from copy import deepcopy
from dataclasses import asdict

import pytest
from test_jrsnap_export import example_input

from src.calculator import calculate
from src.inputs import InputError, parse_input
from src.jrsnap_design_conditions import (
    derive_jrsnap_soil_conditions,
    get_profile,
)
from src.reaction_inputs import parse_reaction_input


def soil_source():
    raw = example_input()
    foundation = calculate(parse_input(raw))
    seismic = {"input": {"geometry": asdict(parse_reaction_input(raw).geometry)}}
    return raw, foundation, seismic


def test_current_soil_depth_weighted_gamma_and_sources():
    source = soil_source()
    before = deepcopy(source)
    result = derive_jrsnap_soil_conditions(*source)
    assert source == before
    assert (result["Df"], result["gamma1"], result["gamma2"], result["phi"]) == (4.7, 10, 12.3, 42.2)
    proof = result["provenance"]
    assert proof["gamma2_raw"] == pytest.approx((2 * 18 + 2.7 * 8) / 4.7)
    assert (proof["wet_segment_m"], proof["submerged_segment_m"]) == (2, 2.7)
    assert proof["df_difference_m"] == 0
    assert result["Ks"] == 8525475 and result["Kv"] == 25576488 and result["kv"] == 405976


def test_reference_published_formula_is_derived_not_copied():
    raw = example_input()
    raw["下部構造"]["土かぶり"]["起点側_df1"] = 1.08
    raw["下部構造"]["土かぶり"]["終点側_df2"] = 1.08
    raw["地盤データ"]["層"][0]["単位体積重量"]["水中"] = 9
    foundation = calculate(parse_input(raw))
    seismic = {"input": {"geometry": asdict(parse_reaction_input(raw).geometry)}}
    result = derive_jrsnap_soil_conditions(raw, foundation, seismic)
    assert result["Df"] == pytest.approx(3.78)
    assert result["provenance"]["gamma2_raw"] == pytest.approx((1.08 * 18 + 2.7 * 9) / 3.78)
    assert result["gamma2"] == 11.6


@pytest.mark.parametrize("water", [0, 4.7, -1, 5, math.inf, math.nan, True, "2.7"])
def test_water_boundaries_rejected_before_any_export(water):
    raw, foundation, seismic = soil_source()
    seismic["input"]["geometry"]["hw2"] = water
    with pytest.raises(InputError, match="hw2"):
        derive_jrsnap_soil_conditions(raw, foundation, seismic)


@pytest.mark.parametrize("difference,accepted", [(0.5e-9, True), (2e-9, False)])
def test_cover_tolerance_checked_before_min(difference, accepted):
    raw, foundation, seismic = soil_source()
    raw["下部構造"]["土かぶり"]["終点側_df2"] += difference
    seismic["input"]["geometry"]["df2"] += difference
    if accepted:
        assert derive_jrsnap_soil_conditions(raw, foundation, seismic)["Df"] == 4.7
    else:
        with pytest.raises(InputError, match="土被り差"):
            derive_jrsnap_soil_conditions(raw, foundation, seismic)


@pytest.mark.parametrize("difference,accepted", [(0.5e-9, True), (2e-9, False)])
def test_surface_depth_tolerance(difference, accepted):
    raw, foundation, seismic = soil_source()
    foundation["layers"][0]["thickness"] += difference
    if accepted:
        assert derive_jrsnap_soil_conditions(raw, foundation, seismic)["Df"] == 4.7
    else:
        with pytest.raises(InputError, match="表層厚"):
            derive_jrsnap_soil_conditions(raw, foundation, seismic)


def test_cover_mismatch_wins_over_surface_mismatch():
    raw, foundation, seismic = soil_source()
    seismic["input"]["geometry"]["df2"] += .1
    foundation["layers"][0]["thickness"] += .2
    with pytest.raises(InputError, match="土被り差"):
        derive_jrsnap_soil_conditions(raw, foundation, seismic)


@pytest.mark.parametrize("field", ["shear_factor_vcd", "shear_factor_vsd", "shear_factor_vdd", "aggregate_max_mm"])
@pytest.mark.parametrize("value", [None, 0, -1, math.nan, math.inf, True, "1.3"])
def test_four_new_engineering_fields_have_no_silent_default(field, value):
    raw = example_input()
    raw["jrsnap_longitudinal"][field] = value
    with pytest.raises(InputError, match=field):
        get_profile(raw)


def test_explicit_inputs_flow_to_named_settings_and_missing_input_is_rejected():
    raw = example_input()
    raw["jrsnap_longitudinal"].update(shear_factor_vcd=1.7, aggregate_max_mm=20.5)
    profile = get_profile(raw)
    assert profile["section"]["safety"]["GBC"] == 1.7
    assert profile["section"]["aggregate_max_mm"] == 20.5
    del raw["jrsnap_longitudinal"]
    with pytest.raises(InputError, match="jrsnap_longitudinal"):
        get_profile(raw)

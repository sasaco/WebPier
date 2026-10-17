"""0610 schema 2 action contracts, independently of the old spreadsheet oracle.

The coefficient table is nominal. Pier impact is resolved for each usage before
combination, with its upstream reduction and Single handoff retained exactly.
Only the new APIs are imported at test execution, so RED is not collection error.
"""

from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal, ROUND_HALF_UP
import importlib
import json
from pathlib import Path
import re
import struct

import pytest

from src.calculator import calculate as calculate_foundation
from src.inputs import InputError, parse_input
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input


FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED_SPRINGS = {
    "long_term": {"Kv": 16777217, "Ks": 16777219, "Kr": 52218663},
    "short_term": {"Kv": 33554435, "Ks": 33554437, "Kr": 104437326},
}
COEFFICIENTS = {
    "service": {"single": {"B": 0.12, "C": 0.24}, "double": {"B": 0.10, "C": 0.20}},
    "ultimate": {"single": {"B": 0.17, "C": 0.31}, "double": {"B": 0.15, "C": 0.30}},
}
SNOW_KEYS = {"s2": "雪荷重_2年確率", "s10": "雪荷重_10年確率", "s30": "雪荷重_30年確率"}


def canonical(source):
    module = importlib.import_module("src.longitudinal_calculator")
    return module.calculate_longitudinal_canonical(
        source["inputs"], source["foundation"], source["reactions"],
        design_conditions=source["conditions"],
    )


def legacy(source):
    module = importlib.import_module("src.longitudinal_calculator")
    return module.calculate_longitudinal_legacy(
        source["inputs"], source["foundation"], source["reactions"],
    )


def rounded(value, places):
    """Independent decimal round; these synthetic values need no 15-digit guard."""
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def single(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def supports(b, c, arms=(-0.4, 0.6)):
    result = {side: {"N": value, "arm": arm, "M": rounded(value * arm, 2)}
              for side, value, arm in zip(("B", "C"), (b, c), arms, strict=True)}
    result.update(N=b + c, M=result["B"]["M"] + result["C"]["M"])
    return result


def assert_supports(actual, expected):
    for key in ("N", "M"):
        assert actual[key] == expected[key]
    for side in ("B", "C"):
        assert {key: actual[side][key] for key in ("N", "arm", "M")} == expected[side]


def component(result, combination_id, basic_id):
    combination = next(row for row in result["combinations"] if row["id"] == combination_id)
    return next(row for row in combination["resolved_components"] if row["basic_case_id"] == basic_id)


def basic(result, identifier):
    return next(row for row in result["basic_cases"] if row["id"] == identifier)


def set_factors(source, ultimate=1.23, service=1.0):
    inputs = source["inputs"]
    source["inputs"] = replace(inputs, train=replace(
        inputs.train, factors_ultimate=ultimate, factors_service=service,
    ))


def set_arms(source, b=0.4, c=0.6):
    inputs = source["inputs"]
    source["inputs"] = replace(inputs, spans=replace(
        inputs.spans, b=replace(inputs.spans.b, f=b), c=replace(inputs.spans.c, f=c),
    ))


@pytest.fixture(scope="module")
def calculated_upstream():
    data = json.loads((FIXTURES / "baseline_input.json").read_text(encoding="utf-8"))
    for name, strength in (("梁", 24), ("柱", 27), ("フーチング", 40)):
        data.setdefault("鉄筋", {}).setdefault(name, {})["concrete_strength_mpa"] = strength
    inputs = parse_reaction_input(data)
    # H1 is present to exercise its documented legacy-body material inheritance.
    inputs = replace(inputs, geometry=replace(inputs.geometry, h1=0.5, b2=0.5, b3=1, w2=1, w3=2),
                     train=replace(inputs.train, factors_ultimate=1.23, factors_service=1.0))
    conditions = importlib.import_module("src.longitudinal_design_conditions")
    return {"data": data, "inputs": inputs,
            "foundation": calculate_foundation(parse_input(data)),
            "reactions": calculate_reactions(inputs),
            "conditions": conditions.parse_longitudinal_design_conditions(data)}


@pytest.fixture
def source(calculated_upstream):
    result = deepcopy(calculated_upstream)
    for term, values in EXPECTED_SPRINGS.items():
        result["foundation"][term].update(Kv=values["Kv"], Ks=values["Ks"],
                                           Kr_longitudinal=values["Kr"],
                                           Kr_transverse=values["Kr"] + 123456)
    result["foundation"]["macro_handoff_single"] = {
        "long_term": {"Kv": 10101, "Ks": 10102, "Kr": 10103},
        "short_term": {"Kv": 20201, "Ks": 20202, "Kr": 20203},
    }
    return result


@pytest.fixture
def synthetic(source):
    set_arms(source)
    set_factors(source, ultimate=1.231)
    reaction = source["reactions"]
    reaction["train"]["raw_reactions"].update(RB=100.0, RC=200.0)
    reaction["dead_loads"]["track_totals"].update(B=2.0, C=3.0)
    for group, tracks in COEFFICIENTS.items():
        for track, sides in tracks.items():
            for side, value in sides.items():
                reaction["train"]["pier"][group][track]["R" + side]["coefficient"] = value
    return source


def test_schema_and_all_nominal_definitions_match_the_reference(source):
    result = canonical(source)
    reference = json.loads((FIXTURES / "longitudinal_example2_cases.json").read_text(encoding="utf-8"))
    model = importlib.import_module("src.longitudinal_example2_cases").build_case_model(
        ultimate_factor=1.23, service_factor=1.0,
    )
    assert result["schema_version"] == 2
    assert result["case_model_version"] == "example2-nonseismic-pier-impact-v1"
    assert len(result["horizontal"]) == 8
    for collection in ("basic_cases", "combinations", "define_cases", "extraction_cases"):
        assert len(result[collection]) == len(model[collection])
        for actual, expected in zip(result[collection], model[collection], strict=True):
            assert {key: actual[key] for key in expected} == expected
    matrix = [list(values) for values in zip(*(row["coefficients"] for row in result["combinations"]), strict=True)]
    assert matrix == reference["coefficient_matrix"]["values"]
    for combination in result["combinations"]:
        resolved = combination["resolved_components"]
        assert [row["basic_case_id"] for row in resolved] == list(range(1, 21))
        assert [row["nominal_factor"] for row in resolved] == combination["coefficients"]
        assert all({"residual_factor", "loads", "resolution"} <= row.keys() for row in resolved)


def test_public_entry_is_canonical_and_full_macro_legacy_remains_explicit(source):
    module = importlib.import_module("src.longitudinal_calculator")
    expected = canonical(source)
    assert expected["schema_version"] == 2
    assert module.calculate_longitudinal(
        source["inputs"], source["foundation"], source["reactions"],
        design_conditions=source["conditions"],
    ) == expected
    old = legacy(source)
    assert old["schema_version"] == 1
    assert old["frame"]["springs"] == source["foundation"]["macro_handoff_single"]


def test_canonical_frame_materials_geometry_and_normal_longitudinal_springs(source):
    result = canonical(source)
    old_frame = legacy(source)["frame"]
    frame = result["frame"]
    assert frame["springs"] == EXPECTED_SPRINGS
    assert set(frame["materials"]) == {"beam", "column", "footing"}
    for name, fck, ec in (("beam", 24, 25e6), ("column", 27, 26.5e6), ("footing", 40, 31e6)):
        assert frame["materials"][name]["fck"] == fck
        assert frame["materials"][name]["Ec"] == ec
    elastic = {row["region"]: row["material_ref"] for row in frame["members"] if row["behavior"] == "elastic"}
    assert elastic == {"h1": "column", "h2": "beam", "h3": "beam", "h4": "column"}
    assert all(row["material_ref"] is None for row in frame["members"] if row["behavior"] == "rigid")
    h1 = frame["material_provenance"]["h1"]
    assert h1 == {"policy": "compatibility_inheritance", "legacy_material_ref": "body",
                  "material_ref": "column", "dedicated_input": False,
                  "input_path": "鉄筋.柱.concrete_strength_mpa"}
    def geometry_only(value):
        value = deepcopy(value)
        for key in ("materials", "material_provenance", "springs", "spring_provenance"):
            value.pop(key, None)
        for row in value["members"]:
            row.pop("material_ref")
        return value
    assert geometry_only(frame) == geometry_only(old_frame)
    provenance = frame["spring_provenance"]
    assert provenance["direction"] == "longitudinal"
    assert provenance["support_node_id"] == frame["support_node_id"]
    expected_components = [
        {"direction": "longitudinal", "term": term, "component": key, "value": value,
         "source_path": f"0500.{term}.{'Kr_longitudinal' if key == 'Kr' else key}",
         "precision": "Double", "unit": "kN·m/rad" if key == "Kr" else "kN/m"}
        for term, values in EXPECTED_SPRINGS.items() for key, value in values.items()
    ]
    assert provenance["components"] == expected_components


def test_legacy_audit_is_old_equations_with_normal_springs_not_full_macro_replay(source):
    result = canonical(source)
    assert {"cells", "transfers", "inertia", "inactive_source_cells"}.isdisjoint(result)
    audit = result["legacy_audit"]
    assert {"cells", "transfers", "inertia", "basic_cases", "combinations"} <= audit.keys()
    assert audit["frame"]["springs"] == EXPECTED_SPRINGS
    assert audit["frame"]["spring_provenance"]["direction"] == "longitudinal"
    assert audit["frame"]["springs"] != legacy(source)["frame"]["springs"]
    dependencies = audit["provenance"]["dependencies"]
    assert "0500.long_term" in dependencies and "0500.short_term" in dependencies
    assert "0500.macro_handoff_single" not in dependencies
    assert "earthquake" not in result["vertical"]["train"]
    assert "earthquake" in audit["vertical"]["train"]
    assert len(audit["basic_cases"]) > 20
    for column, term in (("L", "long_term"), ("T", "short_term")):
        for row, key in ((144, "Kv"), (145, "Ks"), (146, "Kr")):
            assert audit["cells"]["骨組図"][f"{column}{row}"] == EXPECTED_SPRINGS[term][key]


@pytest.mark.parametrize("term", ["long_term", "short_term"])
@pytest.mark.parametrize("field", ["Kv", "Ks", "Kr_longitudinal"])
def test_normal_spring_missing_cannot_fall_back_to_macro(source, term, field):
    del source["foundation"][term][field]
    with pytest.raises(InputError, match=re.escape(f"0500.{term}.{field}")):
        canonical(source)


@pytest.mark.parametrize("change", ["missing", "nan", "different"])
def test_unused_foundation_macro_never_controls_canonical_or_normal_audit(source, change):
    expected = canonical(source)
    if change == "missing":
        del source["foundation"]["macro_handoff_single"]
    else:
        value = float("nan") if change == "nan" else -777.125
        source["foundation"]["macro_handoff_single"] = {term: {key: value for key in ("Kv", "Ks", "Kr")}
                                                           for term in ("long_term", "short_term")}
    assert canonical(source) == expected


def test_canonical_does_not_mutate_inputs_or_upstream(source):
    before = deepcopy(source)
    result = canonical(source)
    assert source == before
    result["frame"]["springs"]["long_term"]["Kr"] = -1
    result["horizontal"][0]["upstream_details"]["B"]["force"] = -1
    assert source == before


def test_dead_water_physics_and_reference_formulas_remain_legacy_equivalent(source):
    set_arms(source, b=0.325, c=0.675)
    reactions = source["reactions"]
    reactions["dead_loads"]["points"]["B"].update(D1=1234.5, D2=37.25)
    reactions["dead_loads"]["points"]["C"].update(D1=678.9, D2=25.75)
    handoff = reactions["macro_handoff_single"]
    for name, n, arm in (("桁受け", 100.25, -0.12), ("はり", 250.5, 0.22),
                         ("高水位", -101.25, -0.125), ("平水位", -87.5, 0.25), ("低水位", -23.75, 0.375)):
        handoff[name].update(N=n, xL=arm)
    result, old = canonical(source), legacy(source)
    for key in ("fixed", "additional", "water"):
        assert result["vertical"][key] == old["vertical"][key]
    geometry = source["inputs"].geometry
    column = rounded(geometry.b6 * geometry.w6 * geometry.unit_weight_body, 2)
    top = result["vertical"]["fixed"]["top"]
    assert top["N"] == rounded(1234.5 + 678.9 + 100.25 + 250.5 - column * (geometry.h2 + geometry.h3), 2)
    assert top["M"] == sum(rounded(n * arm, 2) for n, arm in
                           ((1234.5, -0.325), (678.9, 0.675), (100.25, -0.12), (250.5, 0.22)))
    detail = result["calculation_details"]["fixed"]
    assert detail["components"] == {
        "B": {"N": 1234.5, "arm": -0.325, "M": -401.21},
        "C": {"N": 678.9, "arm": 0.675, "M": 458.26},
        "pedestal": {"N": 100.25, "arm": -0.12, "M": -12.03},
        "beam": {"N": 250.5, "arm": 0.22, "M": 55.11},
    }
    assert detail["sum_N"] == sum((1234.5, 678.9, 100.25, 250.5))
    assert detail["sum_M"] == sum((-401.21, 458.26, -12.03, 55.11))
    assert detail["column_deduction"] == {"intensity": column, "length": geometry.h2 + geometry.h3}
    assert detail["adopted_top"] == {"N": top["N"], "M": top["M"]}
    assert result["vertical"]["additional"]["top"]["N"] == 63.0
    formulas = result["reference_formulas"]
    assert set(formulas) == {"fixed", "water"}
    assert set(formulas["fixed"]) == {"omega2", "omega3"}
    assert set(formulas["water"]) == {"high", "normal", "low"}
    cells = old["cells"]["荷重計算"]
    for section, key, row in (("fixed", "omega2", 23), ("fixed", "omega3", 24),
                              ("water", "high", 64), ("water", "normal", 69), ("water", "low", 74)):
        formula = formulas[section][key]
        assert formula["source_cell"] == f"AB{row}"
        assert {key: formula[key] for key in ("value", "height", "width", "unit_weight")} == {
            "value": cells[f"AB{row}"], "height": cells[f"J{row}"],
            "width": cells[f"N{row}"], "unit_weight": cells[f"R{row}"],
        }


def test_three_snow_probabilities_have_independent_forces_and_moments(source):
    set_arms(source, b=0.325, c=0.675)
    points = source["reactions"]["snow_loads"]["points"]
    for key, b, c in (("s2", 460, 250), ("s10", 740, 400), ("s30", 820, 450)):
        points["B"][SNOW_KEYS[key]], points["C"][SNOW_KEYS[key]] = b, c
    result = canonical(source)
    assert set(result["vertical"]["snow"]) == {"s2", "s10", "s30"}
    for identifier, key, b, c, n, moment in ((6, "s2", 460, 250, 710, 19.25),
                                          (7, "s10", 740, 400, 1140, 29.50),
                                          (8, "s30", 820, 450, 1270, 37.25)):
        loads = result["vertical"]["snow"][key]
        assert_supports(loads, supports(b, c, (-0.325, 0.675)))
        assert (loads["N"], loads["M"]) == (n, moment)
        assert basic(result, identifier)["loads"] == loads


def test_zero_snow_is_valid_without_fallback_to_other_probability(source):
    for side in ("B", "C"):
        for key in SNOW_KEYS.values():
            source["reactions"]["snow_loads"]["points"][side][key] = 0
    result = canonical(source)
    for loads in result["vertical"]["snow"].values():
        assert loads["N"] == loads["M"] == 0


@pytest.mark.parametrize("side", ["B", "C"])
@pytest.mark.parametrize("key", list(SNOW_KEYS.values()))
@pytest.mark.parametrize("missing", [True, False])
def test_snow_missing_or_null_is_a_path_error(source, side, key, missing):
    point = source["reactions"]["snow_loads"]["points"][side]
    if missing:
        del point[key]
    else:
        point[key] = None
    with pytest.raises(InputError, match=re.escape(f"snow_loads.points.{side}.{key}")):
        canonical(source)


def test_raw_train_basics_and_usage_impact_are_separate_families(synthetic):
    result = canonical(synthetic)
    vertical = result["vertical"]
    assert set(vertical["train"]) == {"single", "double"}
    for identifier, track, b, c, n, moment in ((9, "single", 100, 200, 300, 80),
                                             (10, "double", 200, 600, 800, 280)):
        assert_supports(vertical["train"][track], supports(b, c))
        assert (vertical["train"][track]["N"], vertical["train"][track]["M"]) == (n, moment)
        assert basic(result, identifier)["loads"] == vertical["train"][track]
    assert set(vertical["impact"]) == {"service", "ultimate", "maximum"}
    expected = {("service", "single"): (12, 48), ("service", "double"): (20, 120),
                ("ultimate", "single"): (20.9, 76.3), ("ultimate", "double"): (36.9, 221.4),
                ("maximum", "single"): (23, 83.7), ("maximum", "double"): (40.5, 243)}
    for (usage, track), (b, c) in expected.items():
        assert_supports(vertical["impact"][usage][track], supports(single(b), single(c)))
    for identifier, track in ((11, "single"), (12, "double")):
        family = basic(result, identifier)
        assert set(family["usage_loads"]) == {"service", "ultimate", "maximum"}
        for usage in ("service", "ultimate", "maximum"):
            assert family["usage_loads"][usage] == vertical["impact"][usage][track]
        assert family["loads"] == family["usage_loads"]["ultimate"]


@pytest.mark.parametrize("ultimate,service,ordinary,maximum,service_nominal", [
    (1.231, 1.0, 1.23, 1.35, 0.75), (1.235, 1.0, 1.24, 1.36, 0.75),
    (0.0, 1.0, 0.0, 0.0, 0.75), (1.23, 1.2, 1.23, 1.35, 0.9),
    (1.23, 0.0, 1.23, 1.35, 0.0),
])
def test_resolved_train_impact_apply_usage_factor_once_and_preserve_upstream_cp(
    synthetic, ultimate, service, ordinary, maximum, service_nominal,
):
    set_factors(synthetic, ultimate, service)
    result = canonical(synthetic)
    # Selection is independent of the product's combination dispatch logic.
    usage_cases = [(identifier, "maximum", "double", maximum, maximum) for identifier in (1, 10)]
    usage_cases += [(identifier, "ultimate", "double", ordinary, ordinary) for identifier in (3, 8, 12)]
    usage_cases += [(5, "service", "double", service, service_nominal)]
    usage_cases += [(identifier, "service", "single", service, service_nominal) for identifier in (7, 15, 16)]
    for case_id, usage, track, factor, nominal_impact in usage_cases:
        group = "service" if usage == "service" else "ultimate"
        track_counts = (1, 1) if track == "single" else (2, 3)
        adopted_l = [(raw * factor) * count for raw, count in zip((100, 200), track_counts, strict=True)]
        cp = COEFFICIENTS[group][track]
        adopted_i = [single(rounded(load * cp[side], 1))
                     for side, load in zip(("B", "C"), adopted_l, strict=True)]
        lid, iid = (9, 11) if track == "single" else (10, 12)
        train_component = component(result, case_id, lid)
        impact_component = component(result, case_id, iid)
        assert_supports(train_component["loads"], supports(*adopted_l))
        assert_supports(impact_component["loads"], supports(*adopted_i))
        assert train_component["nominal_factor"] == factor
        assert impact_component["nominal_factor"] == pytest.approx(nominal_impact, rel=0, abs=1e-12)
        if factor:
            assert train_component["residual_factor"] == impact_component["residual_factor"] == 1
        resolution = impact_component["resolution"]
        assert resolution["usage"] == usage
        assert resolution["track"] == track
        assert resolution["effective_train_factor"] == factor
        assert resolution["pier_coefficients"] == cp
        assert resolution["coefficient_source_paths"] == {
            side: f"0600.train.pier.{group}.{track}.R{side}.coefficient" for side in ("B", "C")
        }
    if service == 1.2:
        assert_supports(component(result, 5, 12)["loads"], supports(24, 144))
    for case_id in (2, 11):
        assert_supports(component(result, case_id, 10)["loads"], supports(200 * ordinary, 600 * ordinary))
        for iid in (11, 12):
            excluded = component(result, case_id, iid)
            assert excluded["nominal_factor"] == 0
            assert excluded["loads"]["N"] == excluded["loads"]["M"] == 0


def test_train_factor_is_applied_before_track_count_without_reassociation(synthetic):
    synthetic["reactions"]["train"]["raw_reactions"]["RB"] = 1.0000000000000002e16
    synthetic["reactions"]["dead_loads"]["track_totals"]["B"] = 2.1
    result = canonical(synthetic)
    assert component(result, 3, 10)["loads"]["B"]["N"] == 2.5830000000000004e16
    assert 2.5830000000000004e16 != 1.0000000000000002e16 * (1.23 * 2.1)


def test_train_adoption_retains_double_precision_before_independent_impact_rounding(synthetic):
    reaction = synthetic["reactions"]
    reaction["train"]["raw_reactions"].update(RB=100.123456789, RC=200.987654321)
    reaction["dead_loads"]["track_totals"].update(B=2.3, C=0.7)
    result = canonical(synthetic)
    loads = component(result, 3, 10)["loads"]
    impact = component(result, 3, 12)["loads"]
    for side, raw, count, cp in (("B", 100.123456789, 2.3, 0.15),
                                 ("C", 200.987654321, 0.7, 0.30)):
        expected = (raw * 1.23) * count
        assert loads[side]["N"] == expected
        assert loads[side]["N"] != single(expected)
        assert impact[side]["N"] == single(rounded(expected * cp, 1))


@pytest.mark.parametrize("ds", [0, 120])
def test_pier_reduction_is_adopted_from_upstream_and_not_recomputed_at_maximum(synthetic, ds):
    reaction = synthetic["reactions"]
    du, load_total = 400, 800
    reaction["train"].update(Ds=ds, Du=du)
    expected_cp = {}
    for side, load, girder_cp in (("B", 200, 0.30), ("C", 600, 0.50)):
        reaction["train"]["girder"]["ultimate"]["double"]["R" + side].update(
            train=load, coefficient=girder_cp,
        )
        cp = girder_cp * (1 - ds / (load_total + du + ds))
        expected_cp[side] = cp
        reaction["train"]["pier"]["ultimate"]["double"]["R" + side].update(
            train=load, coefficient=cp, impact=rounded(load * cp, 1),
        )
    result = canonical(synthetic)
    maximum = component(result, 1, 12)
    assert maximum["resolution"]["pier_coefficients"] == expected_cp
    b = single(rounded((100 * 1.35) * 2 * expected_cp["B"], 1))
    c = single(rounded((200 * 1.35) * 3 * expected_cp["C"], 1))
    assert_supports(maximum["loads"], supports(b, c))
    if ds:
        recomputed = 0.30 * (1 - ds / (800 * 1.35 + du + ds))
        assert expected_cp["B"] != recomputed
        assert b != single(rounded(270 * recomputed, 1))


def test_existing_0600_rejects_zero_pier_reduction_denominator():
    module = importlib.import_module("src.reaction_calculator")
    girder = {group: {track: {side: {"train": 0, "coefficient": 0.3} for side in ("RB", "RC")}
                      for track in ("single", "double")} for group in ("ultimate", "service")}
    with pytest.raises(InputError, match="分母"):
        module._pier_train_table(girder, ds=0, du=0, cells={})


def test_rounded_upstream_train_and_impact_packets_cannot_replace_raw_resolution(synthetic):
    before = canonical(synthetic)
    for kind in ("列車荷重", "衝撃荷重"):
        for group in ("安全性", "使用性"):
            for track in ("単線", "複線"):
                synthetic["reactions"]["macro_handoff_single"][kind][group][track].update(RB=9876.125, RC=5432.25)
    after = canonical(synthetic)
    for key in ("train", "impact"):
        assert before["vertical"][key] == after["vertical"][key]
    assert before["basic_cases"] == after["basic_cases"]
    assert before["combinations"] == after["combinations"]
    assert before["legacy_audit"]["vertical"]["train"] != after["legacy_audit"]["vertical"]["train"]


def test_horizontal_mapping_adopts_single_and_keeps_current_0600_details(synthetic):
    reactions = synthetic["reactions"]
    packet = reactions["macro_handoff_single"]
    mapping = [(13, "longitudinal", "線路荷重強度", 0), (14, "longitudinal", "線路荷重強度", 1),
               (15, "longitudinal", "線路荷重強度", 4), (16, "longitudinal", "線路荷重強度", 5),
               (17, "longitudinal", "線路荷重強度", 6), (18, "longitudinal_snow_cases", "線路雪荷重強度", 0),
               (19, "longitudinal", "線路荷重強度", 7), (20, "longitudinal_snow_cases", "線路雪荷重強度", 1)]
    for index, (_, rows_key, packet_key, upstream_index) in enumerate(mapping):
        row = reactions[rows_key][upstream_index]
        for side, offset in (("B", 10.1), ("C", 20.2)):
            adopted = single(100 * (index + 1) + offset)
            packet[packet_key][upstream_index]["R" + side] = adopted
            row[side]["force"] = adopted + 0.125
            row[side]["effective_brake_coefficient"] = 1.17 if side == "B" else 1.29
            row[side]["friction_candidates"] = {"bearing": 121 + index, "remote": 232 + index}
        row["combination"]["include_impact"] = True
    expected_details = deepcopy(reactions)
    result = canonical(synthetic)
    assert [row["id"] for row in result["horizontal"]] == list(range(13, 21))
    for identifier, rows_key, packet_key, upstream_index in mapping:
        row = next(row for row in result["horizontal"] if row["id"] == identifier)
        force = packet[packet_key][upstream_index]
        assert row["B"] == force["RB"] and row["C"] == force["RC"]
        assert row["total"] == force["RB"] + force["RC"]
        assert row["upstream_details"] == expected_details[rows_key][upstream_index]
        assert basic(result, identifier)["loads"] == row
    assert basic(result, 19)["loads"]["upstream_details"]["B"]["effective_brake_coefficient"] == 1.17
    assert basic(result, 19)["loads"]["upstream_details"]["C"]["effective_brake_coefficient"] == 1.29
    # Removing vertical I does not remove the bearing-friction I already adopted
    # by 0600. Canonical 17 uses row 6, whose original-formula Rm includes L + I.
    for case_id in (2, 11):
        assert component(result, case_id, 12)["loads"]["N"] == 0
        assert component(result, case_id, 17)["loads"] == basic(result, 17)["loads"]
        assert component(result, case_id, 17)["loads"]["upstream_details"]["combination"]["include_impact"] is True


def scale_physical(value, factor):
    """Independent whitelist: never multiply IDs, arms, cells, or provenance."""
    if not isinstance(value, dict):
        return deepcopy(value)
    return {key: item * factor if key in {"N", "M", "intensity"} else
            (scale_physical(item, factor) if isinstance(item, dict) and key not in {"source_cells", "upstream_details"}
             else deepcopy(item)) for key, item in value.items()}


def test_non_train_scaling_keeps_arms_ids_and_metadata(synthetic):
    result = canonical(synthetic)
    for case_id in range(1, 17):
        for identifier in range(1, 9):
            resolved = component(result, case_id, identifier)
            assert resolved["loads"] == scale_physical(basic(result, identifier)["loads"], resolved["nominal_factor"])


def test_horizontal_sign_variants_preserve_every_vertical_force_and_eccentric_moment(synthetic):
    result = canonical(synthetic)
    springs = deepcopy(result["frame"]["springs"])
    for case in result["combinations"]:
        active_horizontal = any(row["basic_case_id"] >= 13 and row["nominal_factor"] != 0
                                for row in case["resolved_components"])
        assert [variant["horizontal_sign"] for variant in case["variants"]] == ([1, -1] if active_horizontal else [1])
        for variant in case["variants"]:
            assert len(variant["resolved_components"]) == 20
            for actual, base in zip(variant["resolved_components"], case["resolved_components"], strict=True):
                expected = deepcopy(base)
                if base["basic_case_id"] >= 13:
                    for key in ("B", "C", "total"):
                        expected["loads"][key] *= variant["horizontal_sign"]
                assert actual == expected
    assert result["frame"]["springs"] == springs
    by_id = {row["id"]: row for row in result["combinations"]}
    extracted = [identifier for group in result["extraction_cases"] for identifier in group["combination_ids"]]
    assert sorted(extracted) == list(range(1, 17))
    assert all(by_id[identifier]["resolved_components"] and by_id[identifier]["variants"] for identifier in extracted)


@pytest.mark.parametrize("path", [
    ("train", "raw_reactions", "RB"), ("dead_loads", "track_totals", "C"),
    ("train", "pier", "ultimate", "double", "RB", "coefficient"),
    ("train", "pier", "service", "single", "RC", "coefficient"),
    ("macro_handoff_single", "線路荷重強度", 6, "RB"),
    ("macro_handoff_single", "線路雪荷重強度", 1, "RC"),
])
@pytest.mark.parametrize("bad", ["missing", None, float("nan"), float("inf"), True])
def test_required_action_upstream_is_path_validated(synthetic, path, bad):
    parent = synthetic["reactions"]
    for part in path[:-1]:
        parent = parent[part]
    if bad == "missing":
        del parent[path[-1]]
    else:
        parent[path[-1]] = bad
    with pytest.raises(InputError) as error:
        canonical(synthetic)
    text = str(error.value)
    assert all(str(part) in text for part in path)


def test_mismatched_upstream_input_sha_is_rejected(source):
    source["foundation"].setdefault("provenance", {})["input_sha256"] = "a" * 64
    source["reactions"].setdefault("provenance", {})["input_sha256"] = "b" * 64
    with pytest.raises(InputError, match="SHA256"):
        canonical(source)

"""Weight/dead-load comparisons against independently recalculated Excel cells."""

from copy import deepcopy
from dataclasses import replace
import importlib

import pytest

from src.inputs import InputError
from src.reaction_inputs import parse_reaction_input
from legacy_reaction_oracle import load_legacy_reaction_oracle, parse_legacy_reaction_input


ORACLE = load_legacy_reaction_oracle("reaction_excel_oracle.json")
CASES = ORACLE["cases"]
COMPONENTS = ("桁受け", "はり", "柱", "フーチング", "上載土", "高水位", "平水位", "低水位")


def module():
    return importlib.import_module("src.reaction_weights")


def key_cells():
    cells = [f"X{i}" for start, stop in ((62, 67), (92, 95), (111, 116), (146, 149),
                                           (181, 183), (217, 219), (251, 253), (285, 287),
                                           (313, 316), (330, 333)) for i in range(start, stop + 1)]
    cells += ["X83", "X84", "X137", "X138"]
    cells += [f"{col}{row}" for row in (88, 89, 142, 143) for col in ("J", "N", "Q", "U", "X", "AB", "AE")]
    cells += [f"{col}{row}" for row in (90, 144) for col in ("J", "Q", "X", "AE")]
    cells += [f"{col}{row}" for row in (*range(175, 179), *range(212, 216), *range(246, 250), *range(280, 284))
              for col in ("K", "O", "R", "V", "Y")]
    cells += [f"{col}{row}" for row in (179, 216, 250, 284) for col in ("K", "R", "Y")]
    cells += [f"{col}{row}" for row in (*range(308, 311), *range(323, 328))
              for col in ("I", "M", "P", "T", "W", "AA", "AD")]
    cells += [f"{col}{row}" for row in (311, 328) for col in ("I", "P", "W", "AD")]
    return cells


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case"])
def test_all_public_weights_and_intermediate_cells_match_excel(case):
    result = module().calculate_weights(parse_legacy_reaction_input(case["input"]).geometry)
    for name in COMPONENTS:
        assert result["components"][name] == pytest.approx(case["public_values"][name], rel=1e-12, abs=1e-10), name
    expected = case["formula_values"]["橋脚自重"]
    for cell in key_cells():
        if cell in expected:
            assert result["cells"][cell] == pytest.approx(expected[cell], rel=1e-12, abs=1e-10), cell
    for name, first in (("pier_bottom", 313), ("footing_center", 330)):
        assert result[name] == dict(zip(("N", "xL", "xC", "hG"), (expected[f"X{i}"] for i in range(first, first + 4))))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case"])
def test_dead_cells_and_double_track_distribution_match_excel(case):
    result = module().calculate_dead(parse_legacy_reaction_input(case["input"]))
    for cell, expected in case["formula_values"]["死荷重"].items():
        assert result["cells"][cell] == pytest.approx(expected), cell
    assert result["double_track_factors"] == {
        side: tuple(values) for side, values in case["public_values"]["複線分担率"].items()
    }
    for side in ("B", "C"):
        assert len(result["slots"][side]) == 10
        assert result["track_totals"][side] == pytest.approx(sum(result["double_track_factors"][side]))


def test_dead_recalculates_bc_cached_total_and_tenth_slot():
    data = deepcopy(CASES[0]["input"])
    for side, points in (("起点側", ("B支点",)), ("終点側", ("C支点",))):
        for point in points:
            data["上部工反力"][side][point]["合計"] = {"固定死荷重_D1": 9999}
    last = data["上部工反力"]["起点側"]["B支点"]["支承"][9]
    last.update(固定死荷重_D1=10, 付加死荷重_D2=15)
    last["列車分担"].update(L1=0.2, L2=0.3, L3=0.9)
    result = module().calculate_dead(parse_reaction_input(data))
    assert result["points"]["A"] == result["points"]["B"] == {"D1": 900, "D2": 15, "total": 915}
    assert result["girders"]["AB"] == {"D1": 1800, "D2": 30, "total": 1830}
    assert result["double_track_factors"]["B"][9] == 0.5
    assert result["track_totals"]["B"] == 1.5


def test_manual_ad_reactions_reach_dead_cells_and_girder_totals():
    data = deepcopy(CASES[0]["input"])
    data["上部工反力"]["起点側"].setdefault("A支点", {})["合計"] = {
        "固定死荷重_D1": 0, "付加死荷重_D2": -12.5,
    }
    data["上部工反力"]["終点側"].setdefault("D支点", {})["合計"] = {
        "固定死荷重_D1": 123.25, "付加死荷重_D2": 7,
    }
    result = module().calculate_dead(parse_reaction_input(data))
    assert result["points"]["A"] == {"D1": 0, "D2": -12.5, "total": -12.5}
    assert result["points"]["D"] == {"D1": 123.25, "D2": 7, "total": 130.25}
    assert result["girders"]["AB"] == {"D1": 890, "D2": -12.5, "total": 877.5}
    assert result["girders"]["CD"] == {"D1": 963.25, "D2": 7, "total": 970.25}
    assert {key: result["cells"][key] for key in ("J10", "J11", "V10", "V11", "Z12", "AD12")} == {
        "J10": 0, "J11": -12.5, "V10": 123.25, "V11": 7, "Z12": 877.5, "AD12": 970.25,
    }


def test_source_cells_exclude_untransferred_positions_and_text_height_cells():
    inputs = parse_reaction_input(CASES[0]["input"])
    dead = module().calculate_dead(inputs)
    for row in (20, 28, 38, 46):
        for col in ("M", "P", "S", "V", "Y"):
            assert f"{col}{row}" not in dead["cells"]
    assert dead["slots"]["B"][0]["position"] == -2.441
    weights = module().calculate_weights(inputs.geometry)
    assert "AA327" not in weights["cells"]
    assert "AD327" not in weights["cells"]


def test_zero_haunch_and_zero_beam_define_finite_zero_moments():
    g = parse_reaction_input(CASES[0]["input"]).geometry
    result = module().calculate_weights(replace(g, h3=0, h2=0))
    assert result["components"]["はり"] == {"N": 0, "xL": 0, "xC": 0, "hG": 0}
    assert result["cells"]["J89"] == result["cells"]["Q89"] == result["cells"]["AE89"] == 0
    assert any("H3=0" in warning for warning in result["warnings"])
    assert any("ゼロ" in warning for warning in result["warnings"])


def test_zero_soil_and_water_centroids():
    g = parse_reaction_input(CASES[0]["input"]).geometry
    result = module().calculate_weights(replace(g, df1=0, df2=0, h5=0, hw1=0, hw2=0, hw3=0))
    for name in ("上載土", "高水位", "平水位", "低水位"):
        assert result["components"][name] == {"N": 0, "xL": 0, "xC": 0}


def test_negative_water_keeps_literal_base_volume_and_warns():
    g = parse_reaction_input(CASES[0]["input"]).geometry
    result = module().calculate_weights(replace(g, hw1=-1))
    assert result["components"]["高水位"]["N"] == 385
    assert result["cells"]["K212"] == -38.5
    assert any("負水位" in warning for warning in result["warnings"])


def test_unusual_original_references_have_specific_warnings():
    case = next(case for case in CASES if case["case"] == "pedestal_nonzero")
    result = module().calculate_weights(parse_reaction_input(case["input"]).geometry)
    assert any("I308=X63" in warning for warning in result["warnings"])
    assert any("W311" in warning and "W328" in warning for warning in result["warnings"])
    g = parse_reaction_input(CASES[0]["input"]).geometry
    result = module().calculate_weights(replace(g, h5=1, w7=1, b7=2))
    assert any("O177=X115" in warning for warning in result["warnings"])


@pytest.mark.parametrize("changes", [{"b6": 0.0001, "w6": 0.0001}, {"unit_weight_body": 1e308}])
def test_zero_rounded_area_and_nonfinite_results_are_input_errors(changes):
    g = parse_reaction_input(CASES[0]["input"]).geometry
    with pytest.raises(InputError):
        module().calculate_weights(replace(g, **changes))


SNOW_KEYS = ("雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率")


def snow_example():
    data = deepcopy(CASES[0]["input"])
    for side, point, multiplier, ten, thirty in (
        ("起点側", "B支点", 1, 3, 2), ("終点側", "C支点", 2, 4, 1),
    ):
        for index, row in enumerate(data["上部工反力"][side][point]["支承"]):
            row.update(dict(zip(SNOW_KEYS, (multiplier * (index + 1), ten, thirty))))
        data["上部工反力"][side][point]["合計"] = dict(zip(SNOW_KEYS, ("-", True, float("inf"))))
    data["上部工反力"]["起点側"].setdefault("A支点", {})["合計"] = {
        SNOW_KEYS[0]: 10, SNOW_KEYS[2]: 0,
    }
    data["上部工反力"]["終点側"].setdefault("D支点", {})["合計"] = dict(zip(SNOW_KEYS, (-5, None, -7)))
    return data


def test_snow_fixed_vectors_are_independent_and_cached_totals_are_ignored():
    data = snow_example()
    before = deepcopy(data)
    result = module().calculate_snow(parse_reaction_input(data))
    assert data == before
    assert set(result) == {"points", "girders", "slots"}
    assert result["points"] == {
        "A": dict(zip(SNOW_KEYS, (10, 30, 0))),
        "B": dict(zip(SNOW_KEYS, (55, 30, 20))),
        "C": dict(zip(SNOW_KEYS, (110, 40, 10))),
        "D": dict(zip(SNOW_KEYS, (-5, 40, -7))),
    }
    assert result["girders"] == {
        "AB": dict(zip(SNOW_KEYS, (65, 60, 20))),
        "CD": dict(zip(SNOW_KEYS, (105, 80, 3))),
    }
    assert result["slots"] == {
        "B": [dict(zip(SNOW_KEYS, values)) for values in (
            (1, 3, 2), (2, 3, 2), (3, 3, 2), (4, 3, 2), (5, 3, 2),
            (6, 3, 2), (7, 3, 2), (8, 3, 2), (9, 3, 2), (10, 3, 2),
        )],
        "C": [dict(zip(SNOW_KEYS, values)) for values in (
            (2, 4, 1), (4, 4, 1), (6, 4, 1), (8, 4, 1), (10, 4, 1),
            (12, 4, 1), (14, 4, 1), (16, 4, 1), (18, 4, 1), (20, 4, 1),
        )],
    }
    assert all(type(value) is float for point in result["points"].values() for value in point.values())


def test_snow_tenth_slot_is_included_and_unset_ends_fall_back_per_case():
    data = deepcopy(CASES[0]["input"])
    data["上部工反力"]["起点側"]["B支点"]["支承"][9].update(dict(zip(SNOW_KEYS, (7, 11, 13))))
    data["上部工反力"]["終点側"]["C支点"]["支承"][9].update(dict(zip(SNOW_KEYS, (17, 19, 23))))
    result = module().calculate_snow(parse_reaction_input(data))
    assert result["points"]["A"] == result["points"]["B"] == dict(zip(SNOW_KEYS, (7, 11, 13)))
    assert result["points"]["D"] == result["points"]["C"] == dict(zip(SNOW_KEYS, (17, 19, 23)))
    assert result["girders"]["AB"] == dict(zip(SNOW_KEYS, (14, 22, 26)))
    assert result["girders"]["CD"] == dict(zip(SNOW_KEYS, (34, 38, 46)))
    assert result["slots"]["B"][9] == dict(zip(SNOW_KEYS, (7, 11, 13)))
    assert result["slots"]["C"][9] == dict(zip(SNOW_KEYS, (17, 19, 23)))
    for side in ("B", "C"):
        assert all(row == dict.fromkeys(SNOW_KEYS, 0) for row in result["slots"][side][:9])


def test_explicit_zero_and_negative_end_snow_values_are_used_for_both_ends():
    data = snow_example()
    for side, point in (("起点側", "A支点"), ("終点側", "D支点")):
        data["上部工反力"][side][point]["合計"] = dict(zip(SNOW_KEYS, (0, -2, -3)))
    result = module().calculate_snow(parse_reaction_input(data))
    assert result["points"]["A"] == result["points"]["D"] == dict(zip(SNOW_KEYS, (0, -2, -3)))
    assert result["girders"]["AB"] == dict(zip(SNOW_KEYS, (55, 28, 17)))
    assert result["girders"]["CD"] == dict(zip(SNOW_KEYS, (110, 38, 7)))


@pytest.mark.parametrize("key", SNOW_KEYS)
@pytest.mark.parametrize("side,point", [("起点側", "B支点"), ("終点側", "C支点")])
def test_snow_detail_sum_overflow_has_contributing_input_path(key, side, point):
    data = deepcopy(CASES[0]["input"])
    rows = data["上部工反力"][side][point]["支承"]
    rows[0][key] = rows[9][key] = 1e308
    with pytest.raises(InputError, match=rf"上部工反力\.{side}\.{point}\.支承\[9\]\.{key}"):
        module().calculate_snow(parse_reaction_input(data))


@pytest.mark.parametrize("key", SNOW_KEYS)
@pytest.mark.parametrize("side,point,end", [("起点側", "B支点", "A支点"), ("終点側", "C支点", "D支点")])
@pytest.mark.parametrize("explicit_end", [False, True])
def test_snow_girder_sum_overflow_has_end_input_path(key, side, point, end, explicit_end):
    data = deepcopy(CASES[0]["input"])
    data["上部工反力"][side][point]["支承"][9][key] = 1e308
    if explicit_end:
        data["上部工反力"][side].setdefault(end, {}).setdefault("合計", {})[key] = 1e308
    with pytest.raises(InputError, match=rf"上部工反力\.{side}\.{end}\.合計\.{key}"):
        module().calculate_snow(parse_reaction_input(data))

"""Quality checks for the independently transcribed transverse PDF reference."""

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

import pytest


REFERENCE = Path(__file__).parent / "fixtures" / "transverse_example2_cases.json"
SOURCE_SHA256 = "b6a7f5658b9f98ee8a7d6b29691edcb0209bc7455fa8309d4e3a2e16605474de"


@pytest.fixture(scope="module")
def reference():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("collection", "count"),
    [("basic_cases", 17), ("define_cases", 15), ("combinations", 16), ("extraction_cases", 8)],
)
def test_reference_numbering_and_semantic_keys_are_complete(reference, collection, count):
    rows = reference[collection]
    assert [row["id"] for row in rows] == list(range(1, count + 1))
    assert len({row["key"] for row in rows}) == count
    assert all(re.fullmatch(r"[a-z][a-z0-9_]+", row["key"]) for row in rows)


def test_reference_source_hash_and_physical_pages_match_original(reference):
    source = reference["source"]
    assert source["path"] == ".claude/docs/Example橋脚2/09_直角.pdf"
    assert source["sha256"] == SOURCE_SHA256
    original = Path(__file__).resolve().parents[1] / source["path"]
    assert hashlib.sha256(original.read_bytes()).hexdigest() == SOURCE_SHA256
    assert source["pages"] == [13, 14, 15]
    for collection, page in (
        ("basic_cases", 13), ("define_cases", 13), ("combinations", 14), ("extraction_cases", 15),
    ):
        assert all(row["source_page"] == page for row in reference[collection])
    assert reference["coefficient_matrix"]["source_page"] == 14


def test_reference_basic_case_order_springs_and_tracks_match_original(reference):
    rows = reference["basic_cases"]
    assert [row["key"] for row in rows] == [
        "dead_fixed", "dead_additional", "buoyancy_high", "buoyancy_normal", "buoyancy_low",
        "snow_2_year", "snow_10_year", "snow_30_year", "train_up", "train_down", "train_double",
        "impact_up", "impact_down", "impact_double", "vehicle_lateral", "wind_with_train", "wind_without_train",
    ]
    assert [row["spring_case"] for row in rows] == [1] * 8 + [2] * 9
    assert [row["action_domain"] for row in rows] == ["vertical"] * 14 + ["horizontal"] * 3
    assert [row["track"] for row in rows[8:14]] == ["up", "down", "double"] * 2
    assert all(row["label"] for row in rows)


def test_reference_define_candidates_are_alternatives_not_sums(reference):
    rows = reference["define_cases"]
    assert [row["signed_basic_case_ids"] for row in rows] == [
        [1], [2], [3], [4], [5], [6], [7], [8], [9, 10], [11], [12, 13], [14],
        [15, -15], [16, -16], [17, -17],
    ]
    assert [row["selection_kind"] for row in rows] == [
        *(["identity"] * 8), "track_alternative", "identity", "track_alternative", "identity",
        "horizontal_sign", "horizontal_sign", "horizontal_sign",
    ]
    assert reference["adopted_policy"]["define_alternatives_are_added"] is False


def test_reference_single_track_train_and_impact_options_are_coupled(reference):
    basics = {row["id"]: row for row in reference["basic_cases"]}
    train, impact = reference["define_cases"][8], reference["define_cases"][10]
    assert train["selection_group"] == impact["selection_group"] == "single_track"
    assert train["option_keys"] == impact["option_keys"] == ["up", "down"]
    for define in (train, impact):
        assert [basics[number]["track"] for number in define["signed_basic_case_ids"]] == define["option_keys"]
        assert all(number > 0 for number in define["signed_basic_case_ids"])
    assert reference["adopted_policy"]["single_track_options_must_match"] is True


def test_reference_only_horizontal_defines_reverse_their_own_force_and_moment(reference):
    basics = {row["id"]: row for row in reference["basic_cases"]}
    for define in reference["define_cases"]:
        ids = define["signed_basic_case_ids"]
        if define["selection_kind"] == "horizontal_sign":
            assert ids == [ids[0], -ids[0]]
            assert basics[ids[0]]["action_domain"] == "horizontal"
            assert define["sign_scope"] == "horizontal_action_only"
            assert define["option_keys"] == ["positive", "negative"]
        else:
            assert all(number > 0 for number in ids)
            assert define["sign_scope"] == "positive_only"
    policy = reference["adopted_policy"]
    assert policy["signed_components"] == ["H", "M_from_same_horizontal_action"]
    assert policy["vertical_loads_and_eccentric_moments_are_negated_by_define"] is False


def test_reference_preserves_source_symbol_differences(reference):
    definitions = reference["define_cases"]
    assert [(definitions[i]["source_symbol"], definitions[i]["combination_symbol"]) for i in (9, 11)] == [
        ("L3", "L2"), ("I3", "I2"),
    ]
    assert [(definitions[i]["source_symbol"], definitions[i]["combination_symbol"]) for i in (5, 6, 7)] == [
        ("SS2", "S2"), ("SS10", "S10"), ("SS30", "S30"),
    ]


def test_reference_matrix_has_240_explicit_define_coefficients(reference):
    matrix = reference["coefficient_matrix"]
    assert matrix["orientation"] == "define_case_rows_by_combination_columns"
    assert matrix["row_define_case_ids"] == list(range(1, 16))
    assert matrix["column_combination_ids"] == list(range(1, 17))
    values = matrix["values"]
    assert len(values) == 15
    assert all(len(row) == 16 for row in values)
    flat = [value for row in values for value in row]
    assert len(flat) == 240
    assert all(type(value) in (int, float) and math.isfinite(value) for value in flat)
    assert set(flat) == {0, 0.75, 1, 1.1, 1.2, 1.23, 1.35}
    assert sum(value != 0 for value in flat) == 83
    assert reference["reference_conditions"]["coefficient_kind"] == "nominal"
    assert reference["reference_conditions"]["safety_rho"] == 1.23


def test_reference_all_16_columns_match_independent_rowwise_pdf_transcription(reference):
    # A second reading of the landscape table, by combination rather than
    # the fixture's Define-row orientation. Unlisted cells are literal dashes.
    expected = [
        {1: 1.1, 2: 1.2, 7: 1, 10: 1.35, 12: 1.35, 13: 1.23, 14: 1},
        {1: 1.1, 2: 1.2, 7: 1, 10: 1.23, 12: 1.23, 13: 1.35, 14: 1},
        {1: 1.1, 2: 1.2, 6: 1, 15: 1.2},
        {1: 1.1, 2: 1.2, 8: 1},
        {1: 1, 2: 1, 6: 1, 10: 1, 12: 0.75},
        {1: 1, 2: 1, 6: 1},
        {9: 1, 11: 0.75},
        {1: 1, 2: 1, 7: 1, 10: 1.23, 12: 1.23, 13: 1.23, 14: 1},
        {1: 1, 2: 1, 8: 1, 14: 1},
        {1: 1.1, 2: 1.2, 5: 1, 7: 1, 10: 1.35, 12: 1.35, 13: 1.23, 14: 1},
        {1: 1.1, 2: 1.2, 5: 1, 7: 1, 10: 1.23, 12: 1.23, 13: 1.35, 14: 1},
        {1: 1.1, 2: 1.2, 5: 1, 6: 1, 15: 1.2},
        {1: 1.1, 2: 1.2, 5: 1, 8: 1},
        {1: 1, 2: 1, 4: 1, 6: 1},
        {1: 1, 2: 1, 5: 1, 6: 1, 9: 1, 11: 0.75},
        {1: 1, 2: 1, 3: 1, 6: 1, 9: 1, 11: 0.75},
    ]
    observed_columns = list(zip(*reference["coefficient_matrix"]["values"], strict=True))
    assert len(observed_columns) == len(expected)
    for column, nonzero in zip(observed_columns, expected, strict=True):
        assert list(column) == [nonzero.get(number, 0) for number in range(1, 16)]


def test_reference_extraction_groups_cover_every_combination_once(reference):
    rows = reference["extraction_cases"]
    groups = [row["combination_ids"] for row in rows]
    assert groups == [[1, 2, 3, 4], [5], [6], [7], [8, 9], [10, 11, 12, 13], [14], [15, 16]]
    assert Counter(number for group in groups for number in group) == Counter(range(1, 17))
    assert [row["label"] for row in rows] == [
        "安全性（破壊）", "永久＋変動", "永久作用", "変動作用", "復旧性（損傷）",
        "安全性（安定）", "長期支持性能", "短期支持性能",
    ]


def test_reference_adopted_exceptions_are_not_rewritten_as_pdf_facts(reference):
    policy = reference["adopted_policy"]
    assert policy["shelter_added"] is False
    assert policy["existing_input_preserved"] is True
    assert policy["wind"]["preserve_current_H_M"] is True
    assert policy["wind"]["example_M_difference_is_accepted"] is True
    assert policy["impact"]["policy"] == "preserve_0600_pier_reduction"
    assert policy["impact"]["undiminished_example_values_are_acceptance_targets"] is False
    assert policy["structural_response_calculated"] is False
    assert policy["extraction_extrema_calculated"] is False

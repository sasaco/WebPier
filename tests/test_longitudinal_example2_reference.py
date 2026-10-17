"""Quality checks for the independently transcribed PDF reference, not product TDD."""

from collections import Counter
import json
import math
from pathlib import Path
import re

import pytest


REFERENCE = Path(__file__).parent / "fixtures" / "longitudinal_example2_cases.json"


@pytest.fixture(scope="module")
def reference():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("collection", "count"),
    [("basic_cases", 20), ("combinations", 16), ("extraction_cases", 8)],
)
def test_numbering_and_semantic_ids_are_complete_and_unique(reference, collection, count):
    rows = reference[collection]
    assert [row["id"] for row in rows] == list(range(1, count + 1))
    keys = [row["key"] for row in rows]
    assert len(set(keys)) == count
    assert all(re.fullmatch(r"[a-z][a-z0-9_]+", key) for key in keys)
    assert all(row["label"] for row in rows)


def test_matrix_has_all_320_explicit_nominal_coefficients(reference):
    matrix = reference["coefficient_matrix"]
    assert matrix["orientation"] == "basic_case_rows_by_combination_columns"
    assert matrix["row_basic_case_ids"] == list(range(1, 21))
    assert matrix["column_combination_ids"] == list(range(1, 17))
    values = matrix["values"]
    assert len(values) == 20
    assert all(len(row) == 16 for row in values)
    flat = [value for row in values for value in row]
    assert len(flat) == 320
    assert all(type(value) in (int, float) and math.isfinite(value) for value in flat)
    assert set(flat) == {0, 0.75, 1, 1.1, 1.2, 1.23, 1.35}
    assert reference["reference_conditions"]["coefficient_kind"] == "nominal"
    assert reference["reference_conditions"]["safety_rho"] == 1.23


def test_basic_case_springs_match_source_and_sign_domains(reference):
    rows = reference["basic_cases"]
    assert [row["spring_case"] for row in rows] == [
        1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 1, 1, 2, 2, 2, 1, 2, 1,
    ]
    assert [row["action_domain"] for row in rows] == ["vertical"] * 12 + ["horizontal"] * 8


def test_define_only_expands_horizontal_actions(reference):
    defines = reference["define_cases"]
    assert [row["id"] for row in defines] == list(range(1, 21))
    assert [row["basic_case_id"] for row in defines] == list(range(1, 21))
    for row in defines:
        number = row["id"]
        if number <= 12:
            assert row["signed_basic_case_ids"] == [number]
            assert row["sign_scope"] == "positive_only"
        else:
            assert row["signed_basic_case_ids"] == [number, -number]
            assert row["sign_scope"] == "horizontal_action_only"
    policy = reference["adopted_policy"]
    assert policy["sign_expansion_scope"] == "horizontal_action_only"
    assert policy["vertical_loads_and_eccentric_moments_are_negated_by_define"] is False


def test_extraction_groups_cover_all_combinations_exactly_once(reference):
    groups = [row["combination_ids"] for row in reference["extraction_cases"]]
    assert groups == [[1, 2, 3, 4], [5], [6], [7], [8, 9], [10, 11, 12, 13], [14], [15, 16]]
    assert Counter(number for group in groups for number in group) == Counter(range(1, 17))


def test_source_pages_are_explicit_and_traceable(reference):
    source = reference["source"]
    assert source["pages"] == [9, 10, 11]
    assert re.fullmatch(r"[0-9a-f]{64}", source["sha256"])
    for collection, page in (
        ("basic_cases", 9), ("define_cases", 9), ("combinations", 10), ("extraction_cases", 11),
    ):
        assert all(row["source_page"] == page for row in reference[collection])
    assert reference["coefficient_matrix"]["source_page"] == 10
    assert reference["reference_conditions"]["source_page"] == 10


def test_adopted_pier_impact_policy_is_separate_from_example_nominal_table(reference):
    impact = reference["adopted_policy"]["impact"]
    assert impact["policy"] == "preserve_0600_pier_reduction"
    assert impact["upstream_source_page"] == 13
    assert impact["family_ids"] == [11, 12]
    assert impact["values_are_usage_specific"] is True
    assert impact["undiminished_example_values_are_acceptance_targets"] is False

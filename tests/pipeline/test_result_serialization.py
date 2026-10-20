"""Result dataclasses become deterministic JSON: Printed is its printed number, enums their value."""

import enum
import json
from dataclasses import dataclass
from decimal import Decimal

import pytest

from pipeline_support import footing_document
from webpier.core.integrity import load_json
from webpier.core.printed import FORCE, LENGTH, Printed
from webpier.inputs import parse_input
from webpier.pipeline.serialize import result_document, to_json
from webpier.pipeline.stages import STAGES


class Side(enum.Enum):
    ORIGIN = "起点側"
    END = "終点側"


class Number(enum.IntEnum):
    ONE = 1


@dataclass(frozen=True)
class Inner:
    force: Printed
    side: Side


@dataclass(frozen=True)
class Outer:
    name: str
    inner: Inner
    parts: tuple[Printed, ...]
    roles: frozenset[Side]
    by_number: dict[int, str]
    missing: None = None
    flag: bool = True
    count: int = 3


def test_dataclass_fields_in_declaration_order():
    value = Outer("柱", Inner(FORCE(12.345), Side.END), (LENGTH(1), LENGTH(2.5)), frozenset(Side),
                  {2: "b", 1: "a"})
    assert to_json(value) == {
        "name": "柱", "inner": {"force": 12.35, "side": "終点側"}, "parts": [1.0, 2.5],
        "roles": ["終点側", "起点側"], "by_number": {"2": "b", "1": "a"}, "missing": None, "flag": True,
        "count": 3}
    assert list(to_json(value)) == ["name", "inner", "parts", "roles", "by_number", "missing", "flag", "count"]


def test_mapping_keys_become_strings():
    assert to_json({Side.ORIGIN: 1, Number.ONE: 2, "x": [3]}) == {"起点側": 1, "1": 2, "x": [3]}


def test_sets_are_sorted_by_their_json_so_the_order_never_depends_on_hashing():
    assert to_json({3, 1, 2}) == [1, 2, 3]
    assert to_json(frozenset({Side.ORIGIN, Side.END})) == ["終点側", "起点側"]


def test_colliding_keys_are_a_bug():
    with pytest.raises(ValueError, match="キーが重複します: 1"):
        to_json({1: "a", "1": "b"})


@pytest.mark.parametrize("key", [1.5, (1, 2), None, True])
def test_keys_must_be_strings_integers_or_enums(key):
    with pytest.raises(TypeError, match="JSONのキーにできません"):
        to_json({key: 1})


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_floats_are_a_bug(value):
    with pytest.raises(ValueError, match="有限でない数値"):
        to_json([value])


def test_unknown_types_are_a_bug():
    with pytest.raises(TypeError, match="JSONにできない値です: complex"):
        to_json(1j)


def test_a_class_is_not_a_dataclass_value():
    with pytest.raises(TypeError, match="JSONにできない値です: type"):
        to_json(Inner)


def test_result_document_records_stage_input_and_implementation():
    document = result_document("0610", {"a": 1}, input_file="input.json", input_sha256="ab" * 32,
                               implementation_sha256="cd" * 32)
    assert document == {"schema_version": 1, "stage": "0610",
                        "input": {"file": "input.json", "sha256": "ab" * 32},
                        "implementation_sha256": "cd" * 32, "result": {"a": 1}}


def test_every_stage_result_serializes_to_strict_json_and_back():
    pier = parse_input(footing_document())  # 0800 needs the footing bars (decision 60)
    results = {}
    for stage in [stage for stage in STAGES.stages if stage.calculate is not None]:  # 0711, 0721, 0910 calculate nothing
        results[stage.id] = stage.calculate(pier, {name: results[name] for name in stage.depends_on if name in results})
        encoded = json.dumps(to_json(results[stage.id]), ensure_ascii=False, allow_nan=False).encode()
        decoded = load_json(encoded)
        assert decoded == to_json(results[stage.id])
        assert isinstance(decoded, dict) and decoded


def test_a_decimal_of_a_load_model_is_its_number_and_the_addin_is_recorded():
    # decision 70: the load model's values are Decimal; the add-in is recorded only when there is one
    assert to_json({"vertical": Decimal("300.00"), "height": Decimal("-1.500")}) == {"vertical": 300.0, "height": -1.5}
    plain = result_document("0600", None, input_file="input.json", input_sha256="a", implementation_sha256="b")
    assert "addin" not in plain
    added = result_document("0600", None, input_file="input.json", input_sha256="a", implementation_sha256="b",
                            addin={"name": "x"})
    assert list(added) == ["schema_version", "stage", "input", "implementation_sha256", "addin", "result"]

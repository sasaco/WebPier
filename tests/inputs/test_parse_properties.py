"""Properties of parse_input over the field table (decisions 5, 15, 17, 19): the current input with one scalar
changed is read at the field's printed digits, or refused with an input error naming that scalar. Nothing is ever
filled in or rounded silently."""

import json
from copy import deepcopy
from dataclasses import fields as dataclass_fields, is_dataclass
from decimal import Decimal
from pathlib import Path

from hypothesis import assume, given, strategies as st

from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import fields, parse_input
from webpier.inputs.fields import field, path_text, pattern

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
FREE_TEXT = "出典"  # decision 19: free description, not validated


def walk(value, path=()):
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, (*path, index))


NODES = list(walk(CURRENT))
SCALARS = [(path, value) for path, value in NODES
           if not isinstance(value, (dict, list)) and pattern(path_text(path)) in fields.FIELDS]
NUMBERS = [path for path, _ in SCALARS if field(path).kind == "number"]
INTEGERS = [path for path, _ in SCALARS if field(path).kind == "integer"]
REQUIRED = [path for path, _ in SCALARS if not field(path).nullable and field(path).kind != "blank"]
OBJECTS = [path for path, value in NODES if isinstance(value, dict) and path[:1] != (FREE_TEXT,)]
# A field's own messages; any other refusal of a valid value comes from a rule between fields.
OWN = ("小数", "正の数値が必要です", "0以上の数値が必要です", "有限の数値が必要です", "値が必要です")


def changed(path, value):
    document = deepcopy(CURRENT)
    owner = document
    for key in path[:-1]:
        owner = owner[key]
    owner[path[-1]] = value
    return document


def error_of(document):
    try:
        return parse_input(document), None
    except InputError as exc:
        return None, str(exc)


def printed_values(value):
    """Every Printed in the parsed model."""
    if isinstance(value, Printed):
        yield value
    elif is_dataclass(value):
        for item in dataclass_fields(value):
            yield from printed_values(getattr(value, item.name))
    elif isinstance(value, dict):
        for item in value.values():
            yield from printed_values(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from printed_values(item)


def at_digits(digits, low, high):
    """A number written with at most *digits* decimals in [low, high]."""
    scale = 10 ** digits
    return st.integers(min_value=round(low * scale), max_value=round(high * scale)).map(
        lambda units: float(Decimal(units).scaleb(-digits)))


@st.composite
def valid_number(draw):
    path = draw(st.sampled_from(NUMBERS))
    spec = field(path)
    low = {"positive": 10 ** -spec.precision.digits, "nonnegative": 0, "any": -1000}[spec.sign]
    value = draw(at_digits(spec.precision.digits, low, 1000))
    assume(spec.limit is None or spec.limit.test(value))
    return path, value


@given(valid_number())
def test_a_valid_number_is_stored_at_its_printed_digits(case):
    path, value = case
    spec = field(path)
    pier, message = error_of(changed(path, value))
    if pier is None:  # refused by a rule between fields, never by the field's own rules
        assert not any(message.startswith(f"{path_text(path)}: {own}") for own in OWN), message
        assert spec.limit is None or not message.endswith(spec.limit.message)
        return
    assert Printed(value, spec.precision.digits, spec.unit) in set(printed_values(pier))


@given(st.sampled_from(NUMBERS), st.integers(min_value=1, max_value=10**6), st.integers(min_value=1, max_value=9))
def test_a_number_finer_than_its_digits_is_refused(path, units, last):
    digits = field(path).precision.digits
    value = float(Decimal(units).scaleb(-digits) + Decimal(last).scaleb(-digits - 1))
    assert error_of(changed(path, value))[1].startswith(f"{path_text(path)}: 小数{digits}桁までで入力してください")


@given(st.sampled_from([path for path in NUMBERS if field(path).sign != "any"]), st.data())
def test_a_number_of_the_wrong_sign_is_refused(path, data):
    spec = field(path)
    high = 0 if spec.sign == "positive" else -10 ** -spec.precision.digits
    value = data.draw(at_digits(spec.precision.digits, -1000, high))
    expected = "正の数値が必要です" if spec.sign == "positive" else "0以上の数値が必要です"
    assert error_of(changed(path, value))[1] == f"{path_text(path)}: {expected}"


@given(st.sampled_from([path for path in NUMBERS if field(path).limit is not None]), st.data())
def test_a_number_out_of_its_range_is_refused(path, data):
    spec = field(path)
    low = {"positive": 10 ** -spec.precision.digits, "nonnegative": 0, "any": -10**6}[spec.sign]
    value = data.draw(at_digits(spec.precision.digits, low, 10**6))
    assume(not spec.limit.test(value))
    assert error_of(changed(path, value))[1] == f"{path_text(path)}: {spec.limit.message}"


@given(st.sampled_from(INTEGERS), st.data())
def test_an_integer_out_of_its_range_is_refused(path, data):
    spec = field(path)
    value = data.draw(st.one_of(st.integers(max_value=spec.minimum - 1), st.integers(min_value=spec.maximum + 1),
                                st.just(spec.minimum + 0.5), st.just(True)))
    assert error_of(changed(path, value))[1].startswith(f"{path_text(path)}: {spec.minimum}～{spec.maximum}の整数")


@given(st.sampled_from(REQUIRED))
def test_a_blank_where_the_field_needs_a_value_is_refused_never_filled(path):
    assert error_of(changed(path, None))[1].startswith(f"{path_text(path)}:")


@given(st.sampled_from(OBJECTS), st.text(min_size=1, max_size=6))
def test_an_unknown_key_is_always_refused(path, key):
    owner = CURRENT
    for part in path:
        owner = owner[part]
    assume(key not in owner)
    document = changed((*path, key), 0)
    expected = f"{path_text((*path, key))}: 未知の入力項目です"
    assert error_of(document)[1] == expected

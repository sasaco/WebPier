"""Properties of the strict JSON reader and writer (decisions 14, 15): what loads can be written back, and the
constructs strict JSON refuses are refused wherever they appear."""

import json

import pytest
from hypothesis import given, strategies as st

from webpier.core.errors import InputError
from webpier.core.integrity import canonical_sha256, dump_json, load_json

# Text as a JSON file can spell it, lone surrogates (\ud800) included.
TEXT = st.text(alphabet=st.characters(), max_size=8)
SCALARS = st.one_of(st.none(), st.booleans(), st.integers(min_value=-10**30, max_value=10**30),
                    st.floats(allow_nan=False, allow_infinity=False), TEXT)
VALUES = st.recursive(SCALARS, lambda children: st.one_of(
    st.lists(children, max_size=4), st.dictionaries(TEXT, children, max_size=4)), max_leaves=12)


def spelled(value) -> bytes:
    """*value* as a JSON file written by any tool: ASCII with escapes."""
    return json.dumps(value, ensure_ascii=True).encode("ascii")


def loads_or_refuses(data: bytes):
    try:
        return load_json(data)
    except InputError:
        return None


@given(VALUES)
def test_whatever_loads_is_written_back_and_loads_as_the_same_value(value):
    loaded = loads_or_refuses(spelled(value))
    if loaded is None:
        return
    assert load_json(dump_json(loaded)) == loaded
    assert canonical_sha256(loaded) == canonical_sha256(load_json(dump_json(loaded)))


@given(st.recursive(st.one_of(st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False,
                                                                                    allow_infinity=False),
                              st.text(alphabet=st.characters(exclude_categories=["Cs"]), max_size=8)),
                    lambda children: st.one_of(st.lists(children, max_size=4),
                                               st.dictionaries(st.text(max_size=4), children, max_size=4)),
                    max_leaves=12))
def test_values_of_unicode_text_round_trip_exactly(value):
    assert load_json(dump_json(value)) == value


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity", "1e400", "-1e400"])
@given(value=VALUES)
def test_non_finite_numbers_are_refused_wherever_they_are(constant, value):
    for document in (f"[{spelled(value).decode()}, {constant}]", f'{{"a": {{"b": [{constant}]}}}}', constant):
        with pytest.raises(InputError):
            load_json(document.encode())


@given(st.dictionaries(st.text(max_size=4), VALUES, min_size=1, max_size=4), st.data())
def test_a_duplicate_key_is_refused_at_any_depth(mapping, data):
    key = data.draw(st.sampled_from(sorted(mapping)))
    body = spelled(mapping).decode()
    duplicated = "{" + json.dumps(key) + ": null, " + body[1:]
    for document in (duplicated, f"[{duplicated}]", f'{{"outer": {duplicated}}}'):
        with pytest.raises(InputError, match="重複"):
            load_json(document.encode())


@given(st.binary(max_size=16))
def test_bytes_are_loaded_or_refused_as_an_input_error(data):
    try:
        load_json(data)
    except InputError:
        pass

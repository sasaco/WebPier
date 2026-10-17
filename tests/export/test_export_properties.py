"""Properties of the external inputs over varied piers (decision 15): an NDU reads back to the records written,
and a FrameWeb document is valid and survives the JSON round trip unchanged."""

from decimal import Decimal

from hypothesis import given, settings, strategies as st

import jrsnap_support
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.core.integrity import dump_json, load_json
from webpier.core.printed import Printed
from webpier.export.frameweb import build_frameweb, build_frameweb_transverse, validate_frameweb
from webpier.export.jrsnap import validate_ndu, write_ndu
from webpier.export.jrsnap.readback import compare_readback, parse_records, summarize
from webpier.export.jrsnap.records import records
from webpier.export.jrsnap.writer import field, number
from webpier.inputs import parse_input

DIRECTIONS = ("longitudinal", "transverse")
ORIGIN, END = "上部工反力/起点側/B支点/", "上部工反力/終点側/C支点/"


def at_digits(digits, low, high):
    scale = 10 ** digits
    return st.integers(min_value=round(low * scale), max_value=round(high * scale)).map(
        lambda units: float(Decimal(units).scaleb(-digits)))


@st.composite
def piers(draw):
    """current.json with other bearing loads, seat offsets and a support layer modulus."""
    changes = {}
    for slots, count in ((ORIGIN, 4), (END, 2)):
        for index in range(count):
            for key in ("固定死荷重_D1", "付加死荷重_D2", "雪荷重_2年確率"):
                changes[f"{slots}{index}/{key}"] = draw(at_digits(2, 0, 3000))
    for side in ("起点側", "終点側"):
        changes[f"上部構造/{side}/支承位置_f"] = draw(at_digits(3, 0.1, 1.2))
    changes["地盤データ/層/1/変形係数_Ed"] = draw(st.integers(min_value=1000, max_value=10**6))
    return jrsnap_support.document(**changes)


# What the writer is given: a printed value read as the decimal of its double (at most 17 digits) or a constant.
WRITTEN = st.one_of(st.floats(allow_nan=False, allow_infinity=False).map(lambda value: Decimal(repr(value))),
                    st.decimals(min_value=-10**6, max_value=10**6, places=3, allow_nan=False, allow_infinity=False))


@given(WRITTEN)
def test_a_number_is_written_as_its_plain_decimal(value):
    text = number(value)
    assert Decimal(text) == value
    assert "E" not in text.upper() and text != "-0"
    assert "." not in text or not text.endswith(("0", "."))


@settings(max_examples=25)
@given(piers(), st.sampled_from(DIRECTIONS))
def test_an_ndu_reads_back_to_the_records_written(data, direction):
    model = jrsnap_support.model(direction, data)
    written = write_ndu(model)
    parsed = parse_records(written)
    expected = records(model)
    assert len(parsed) == len(expected)
    for (key, fields), (expected_key, values) in zip(parsed, expected):
        assert key == expected_key
        if values is None:
            assert fields is None
            continue
        assert fields == tuple(field(value) for value in values)
        for text, value in zip(fields, values):
            if isinstance(value, Printed):
                assert Decimal(text) == Decimal(repr(value.value))
    readback = compare_readback(written, written)
    assert readback.records == len(parsed) and readback.normalized == ()
    summary, counts = validate_ndu(written, model.profile), summarize(parsed)["counts"]
    assert (counts["JointNum"], counts["ElementNum"]) == (summary.joints, summary.elements)


@settings(max_examples=25)
@given(piers(), st.sampled_from(DIRECTIONS))
def test_a_frameweb_document_is_valid_and_survives_the_json_round_trip(data, direction):
    p = parse_input(data)
    foundation, reaction = calculate_foundation(p), calculate_reaction(p)
    if direction == "longitudinal":
        document = build_frameweb(calculate_longitudinal(p, foundation, reaction))
    else:
        document = build_frameweb_transverse(calculate_transverse(p, foundation, reaction))
    validate_frameweb(document)
    again = load_json(dump_json(document))
    assert again == document
    validate_frameweb(again)

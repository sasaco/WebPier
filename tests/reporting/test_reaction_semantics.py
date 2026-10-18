"""0600 semantics: every printed number is a ReactionResult (or input) value at its digits.

Three independent checks:
1. Each Printed of the result, replaced by a sentinel, is printed as that sentinel at
   its digits: the report reads every value from the result and rounds nothing.
   No value of the result is left out.
2. Every number written in a formula or table is the text of a result or input
   value, or a constant of the formula: the report computes no number.
3. Key lines (decisions 11, 22, 23, 24, 27, and the braking rule) are written here
   from the result with an independent formatter and compared as text.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from reaction_report_cases import CASES, case, dotted, leaves, replaced, text
from webpier.calc.reaction.self_weight import Part
from webpier.core.printed import Printed

SENTINEL = 8765.4321
# Constants that formulas write (structure of the formula, or calc constants), and small labels.
CONSTANTS = {
    "0", "1", "2", "3", "4", "6", "10", "30", "12", "200", "127", "2000", "8",
    "0.5", "0.75", "1.0", "1.1", "1.2", "1.00", "0.20", "0.30", "0.2", "1.5", "3.0", "10.0",
    "0.80", "0.19", "0.76", "0.27", "0.25", "0.95",
}
# Numbers that are names, not values: the 0.8 LR combination and references to other sections.
NAMES = {"0.8", "6.1", "6.3"}


def records(result, pier) -> dict[str, str]:
    from webpier.reporting.stages.reaction import semantic_records

    found = semantic_records(result, pier)
    ids = [record["id"] for record in found]
    assert len(ids) == len(set(ids))
    return {record["id"]: record["text"] for record in found}


def sentinel(value: Printed) -> Printed:
    return Printed(float(f"{SENTINEL:.{value.digits}f}"), value.digits, value.unit)


def pattern(value: Printed) -> re.Pattern[str]:
    return re.compile(r"(?<![\d.])" + re.escape(text(value)) + r"(?![\d])")


def omitted(result) -> tuple[str, ...]:
    """Paths of the values that are not printed: a 桁受け of volume 0 is left out (decision 41)."""
    sw = result.self_weight
    if sw.pedestal.volume.value != 0:
        return ()
    assert sw.pier_bottom.rows[0].part is Part.PEDESTAL and sw.footing_centre.rows[0].part is Part.PEDESTAL
    return ("self_weight.pedestal.", "self_weight.pedestal_area", "self_weight.pier_bottom.rows.0.",
            "self_weight.footing_centre.rows.0.")


def test_every_result_value_is_printed_from_the_result_at_its_digits():
    """One value at a time: replaced by a sentinel, it is printed as the sentinel at its digits."""
    result, pier = case("current")
    baseline = "\n".join(records(result, pier).values())
    assert "8765" not in baseline
    skipped = omitted(result)
    assert skipped  # the current input has no 桁受け
    missing = []
    for path, value in leaves(result):
        if dotted(path).startswith(skipped):
            continue
        mark = sentinel(value)
        changed = "\n".join(records(replaced(result, path, mark), pier).values())
        if not pattern(mark).search(changed):
            missing.append(dotted(path))
    assert missing == []


@pytest.mark.parametrize("name", list(CASES))
def test_every_result_value_of_each_variant_is_printed_at_its_digits(name: str):
    """All values at once, each a distinct sentinel (90000 + its index): every branch of the variant reads them."""
    result, pier = case(name)
    marks = {}
    for index, (path, value) in enumerate(leaves(result)):
        mark = Printed(float(f"{90000 + index}.{'1234567890'[:value.digits]}" if value.digits else 90000 + index),
                       value.digits, value.unit)
        result = replaced(result, path, mark)
        marks[dotted(path)] = mark
    printed_text = "\n".join(records(result, pier).values())
    assert [key for key, mark in marks.items() if not pattern(mark).search(printed_text)] == []


NUMBER = re.compile(r"(?<![A-Za-z\d.])\d+(?:\.\d+)?(?![\d.])")


@pytest.mark.parametrize("name", list(CASES))
def test_every_number_written_is_a_result_or_input_value_or_a_formula_constant(name: str):
    result, pier = case(name)
    allowed = CONSTANTS | NAMES
    for source in (result, pier):
        allowed |= {text(value).lstrip("-") for _, value in leaves(source)}
    unknown = {}
    for key, value in records(result, pier).items():
        if "heading" in key:
            continue
        for number in NUMBER.findall(value.replace(pier.train.vehicle, "")):
            if number not in allowed:
                unknown.setdefault(key, []).append(number)
    assert unknown == {}, unknown


INPUT_SHEET_SYMBOL = re.compile(r"(?<![A-Za-z])[BHW][1-9](?!\d)|df[12]")


def _nodes(value):
    """Every node of an authored unit value, depth first."""
    from gridlayoutpdf import Equation, Row, Script
    from webpier.reporting.equations import Definition
    from webpier.reporting.stages.reaction.manuscript import CellSpec, TableSpec

    yield value
    children = ()
    if isinstance(value, Row):
        children = value.items
    elif isinstance(value, Script):
        children = (value.base, value.subscript, value.superscript)
    elif isinstance(value, Equation):
        children = (value.lhs, value.rhs, value.result, value.unit)
    elif isinstance(value, Definition):
        children = (value.symbol, value.text, value.value, value.unit)
    elif isinstance(value, CellSpec):
        children = (value.content,)
    elif isinstance(value, TableSpec):
        children = value.rows
    elif isinstance(value, tuple):
        children = value
    for child in children:
        yield from _nodes(child)


@pytest.mark.parametrize("name", list(CASES))
def test_no_input_sheet_symbol_and_no_stacked_fraction_is_printed(name: str):
    """B1-B9, W1-W9, H1-H6, df1 and df2 name cells of the input sheet and are not defined in the report:
    a formula writes their values (decision of the 0600 layout). Fractions are written on the line."""
    from gridlayoutpdf import Fraction
    from webpier.reporting.stages.reaction import content

    result, pier = case(name)
    found = {key: INPUT_SHEET_SYMBOL.findall(value) for key, value in records(result, pier).items()}
    assert {key: symbols for key, symbols in found.items() if symbols} == {}
    stacked = [unit.key for unit in content(result, pier)
               if any(isinstance(node, Fraction) for node in _nodes(unit.value))]
    assert stacked == []


def test_the_double_track_impact_is_one_expression_rounded_once():
    """Decision 23: i = i_single × (1 − L/200), the factor is not rounded alone."""
    result, pier = case("current")
    actual = records(result, pier)
    span = pier.spans.origin
    expected = f"=0.245×(1−{text(span.span)}/200)={text(result.train.ultimate.origin_impact.double)}"
    assert any(expected in re.sub(r"\s+", "", value) for value in actual.values()), expected


def test_the_movable_bearing_prints_every_candidate_with_the_friction_floor():
    """Decision 11: H = min(T/n, max(μ·Rm, μ·T/n)), μ from the input (not 0.1 of the old sheet).

    As in Example2 07 7-5 the candidates are printed and H is concluded ("※ ∴ H").
    """
    result, pier = case("ea17")
    found = {key: value.replace(" ", "") for key, value in records(result, pier).items()}
    combination = result.longitudinal.cases[2]
    bearing = combination.end  # the end girder's movable bearing in this variant
    key = f"0600/long.case.{combination.case.name.lower()}.end"
    mu = text(pier.spans.end.mu)
    assert found[key + ".share"] == f"T/n={text(bearing.applied)}/2={text(bearing.share)}kN"
    assert found[key + ".friction"] == f"μ・Rm={mu}×{text(bearing.vertical)}={text(bearing.friction)}kN"
    assert found[key + ".floor"] == f"μ・T/n={mu}×{text(bearing.share)}={text(bearing.friction_floor)}kN"
    assert found[key + ".force"] == f"※∴H={text(bearing.force)}kN"


def test_the_footing_centre_height_leaves_out_the_soil():
    """Decision 24: hG = ΣN·y / ΣN of the structure; the soil is in N, xL and xC only."""
    result, pier = case("current")
    actual = "\n".join(records(result, pier).values()).replace(" ", "")
    total = result.self_weight.footing_centre
    assert f"={text(total.moment_y)}/{text(total.structure_weight)}={text(total.y)}m" in actual
    # without the soil, and without the 桁受け of volume 0 (decision 41)
    structure = "+".join(text(row.weight) for row in total.rows[:-1] if row.part is not Part.PEDESTAL)
    assert f"={structure}={text(total.structure_weight)}kN" in actual


def test_the_exact_haunch_centroid_is_printed_with_its_operands():
    """Decision 22: z from b0, w0, Δb, Δw of the haunch; Example2's frustum value is 0.001 m higher."""
    result, pier = case("current")
    actual = "\n".join(records(result, pier).values())
    assert text(result.self_weight.beam_haunch_centroid) == "0.389"
    shape = result.self_weight.beam_haunch_shape
    for value in (shape.lower_length, shape.lower_width, shape.length_change, shape.width_change):
        assert text(value) in actual
    assert "0.390" not in actual


def test_no_pier_impact_is_printed():
    """Decision 27: the pier impact (RC標準 解4.4.4, Ds, Du) is not part of 0600."""
    actual = "\n".join(records(*case("current")).values())
    assert "橋脚く体に対する衝撃" not in actual and "Ds" not in actual and "Du" not in actual


@pytest.mark.parametrize("name,rule", [("current", "軸重式"), ("ea17", "EA-17の規定式")])
def test_the_braking_formula_names_the_vehicle_and_its_rule(name: str, rule: str):
    result, pier = case(name)
    actual = "\n".join(records(result, pier).values())
    assert f"車両 {pier.train.vehicle}" in actual and rule in actual


def test_the_report_reads_the_result_not_the_input():
    """A result whose values differ from what the input gives is printed as is."""
    result, pier = case("current")
    weight = replace(result.self_weight.beam, weight=Printed(1234.56, 2, "kN"))
    odd = replace(result, self_weight=replace(result.self_weight, beam=weight))
    assert "1234.56" in "\n".join(records(odd, pier).values())


def test_unit_text_follows_the_result_units():
    result, pier = case("current")
    odd = replace(result, self_weight=replace(result.self_weight, column=replace(
        result.self_weight.column, weight=Printed(1.0, 0, "furlong"))))
    with pytest.raises(ValueError, match="単位"):
        records(odd, pier)


# Example2 (.claude/docs/Example橋脚2) values the report prints for the current input, as transcribed
# in tests/fixtures/example2 (07 7-1..7-18, 08 p.8-3). The calc tests check the values; this checks
# that each is printed, written as the original prints it.
EXAMPLE2 = {
    "7-1 RB": "272.47", "7-1 RC": "294.92", "7-2 ρf": "1.231", "7-2 iF double": "0.222", "7-2 iF end": "0.521",
    "7-2 iF service": "0.167", "7-2 seismic RA": "320.00", "7-4 LR T1": "400.00", "7-4 braking T2": "96.00",
    "7-4 seismic T1": "13580.00", "7-4 seismic T2": "4740.00", "7-5 train T1": "128.00", "7-7 HB": "298.40",
    "7-7 HC": "175.03", "7-14 HB": "52.71", "7-14 HC": "58.98", "7-15 HB": "197.00", "7-18 HB": "6720.00",
    "7-18 train HB": "96.00", "8-3 footing": "4167.45", "8-3 soil": "1830.60", "8-3 high water": "-2381.40",
    "8-3 normal water": "-1701.00",
}


def test_the_example2_values_are_printed_for_the_current_input():
    actual = "\n".join(records(*case("current")).values())
    assert [key for key, value in EXAMPLE2.items() if not re.search(r"(?<![\d.])" + re.escape(value) + r"(?!\d)",
                                                                    actual)] == []

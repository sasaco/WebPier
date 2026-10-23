"""0600 semantics: every printed number is a ReactionResult (or input) value at its digits.

Three independent checks:
1. Each Printed of the result, replaced by a sentinel, is printed as that sentinel at
   its digits: the report reads every value from the result and rounds nothing.
   No value of the result is left out, but those 6.2 does not print (decision 79).
2. Every number written in a formula or table is the text of a result or input
   value, or a constant of the formula: the report computes no number.
3. Key lines (decisions 11, 23, 27, 79) are written here from the result with an
   independent formatter and compared as text, and nothing explains more than the
   samples do (decision 55).
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from reaction_report_cases import CASES, case, dotted, leaves, replaced, text
from webpier.core.printed import Printed

SENTINEL = 8765.4321
# Constants that formulas write (structure of the formula, or calc constants), and small labels.
CONSTANTS = {
    "0", "1", "2", "3", "4", "6", "10", "30", "12", "200", "127", "2000", "8",
    "0.5", "0.75", "1.0", "1.1", "1.2", "1.00", "0.20", "0.30", "0.2", "1.5", "3.0", "10.0",
    "0.80", "0.19", "0.76", "0.27", "0.25", "0.95",
}
# Numbers that are names, not values: the 0.8 LR combination.
NAMES = {"0.8"}


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


# The self-weight values 6.2 does not print (decision 79): the centroids and their moments (the frame and the
# eccentric moments of 0610/0620 use them), the totals about the column bottom and the footing centre, the haunch
# centroids, the areas, and ΣV of each part (table 6.2.1 prints its rows; the buoyancy prints its sum).
UNPRINTED = re.compile(
    r"self_weight\.(?:"
    r"(?:pedestal|beam|column|footing|overburden|buoyancy_\w+\.body)(?:\.rows\.\d+)?\."
    r"(?:x_l|x_c|y|moment_l|moment_c|moment_y)"
    r"|(?:pier_bottom|footing_centre|footing_haunch_shape)\..*"
    r"|(?:beam|footing)_haunch_centroid|beam_haunch_shape\.(?:length|width)_change"
    r"|(?:pedestal|beam_top|beam_bottom|footing_top)_area"
    r"|(?:pedestal|beam|column|footing|overburden)\.volume)")
PART_VALUE = re.compile(
    r"self_weight\.(pedestal|beam|column|footing|overburden)\.(?:(weight)|rows\.(\d+)\.volume|weights\.(\d+))")


WATER_VALUE = re.compile(r"self_weight\.buoyancy_(high|normal|low)\.(?:(rise|submerged|wedge|rectangle)|body\.rows\.(\d+)\.volume)")


def omitted(result, path: str) -> bool:
    """A value that is not printed: one of UNPRINTED, a 桁受け of volume 0 (decision 41), a row of table 6.2.1 whose V
    is 0, and the weight of a part that the table prints in one row (its W is the row's)."""
    sw = result.self_weight
    if UNPRINTED.fullmatch(path) or sw.pedestal.volume.value == 0 and path.startswith("self_weight.pedestal."):
        return True
    water = WATER_VALUE.fullmatch(path)
    if water is not None:  # decision 86: what is 0 in 6.2 (3) is not printed
        body = getattr(sw, "buoyancy_" + water[1])
        return body.submerged.value == 0 if water[2] in ("rise", "submerged", "wedge", "rectangle") else \
            body.body.rows[int(water[3])].volume.value == 0
    dry = re.fullmatch(r"self_weight\.buoyancy_(high|normal|low)\.body\.(volume|unit_weight)", path)
    if dry is not None:  # nothing under water: only N = 0 is printed
        return all(row.volume.value == 0 for row in getattr(sw, "buoyancy_" + dry[1]).body.rows)
    if path == "self_weight.column_area":
        return all(getattr(sw, "buoyancy_" + name).body.rows[1].volume.value == 0 for name in ("high", "normal", "low"))
    found = PART_VALUE.fullmatch(path)
    if found is None:
        return False
    shown = [row.volume.value != 0 for row in getattr(sw, found[1]).rows]
    return sum(shown) < 2 if found[2] else not shown[int(found[3] or found[4])]


def test_every_result_value_is_printed_from_the_result_at_its_digits():
    """One value at a time: replaced by a sentinel, it is printed as the sentinel at its digits."""
    result, pier = case("current")
    baseline = "\n".join(records(result, pier).values())
    assert "8765" not in baseline
    assert result.self_weight.pedestal.volume.value == 0  # the current input has no 桁受け
    missing = []
    for path, value in leaves(result):
        if omitted(result, dotted(path)):
            continue
        mark = sentinel(value)
        changed = "\n".join(records(replaced(result, path, mark), pier).values())
        if not pattern(mark).search(changed):
            missing.append(dotted(path))
    assert missing == [], missing


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
    assert [key for key, mark in marks.items()
            if not omitted(result, key) and not pattern(mark).search(printed_text)] == []


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
    from webpier.reporting.stages.reaction.manuscript import CellSpec, TableSpec, Wrapped

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
    elif isinstance(value, Wrapped):
        children = (value.node,)
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


def test_table_6_2_1_writes_each_row_and_the_parts_of_more_rows_are_summed():
    """Decision 79: each row of table 6.2.1 is V as numbers = V, γ and W = V × γ (a row whose V is 0 is left out);
    a part of more rows has W, the sum of its rows. Written here from the input with an independent formatter."""
    result, pier = case("current")
    found = {key.removeprefix("0600/"): value.replace(" ", "") for key, value in records(result, pier).items()}
    sw, s = result.self_weight, pier.substructure
    b, w, h = ({index: text(value) for index, value in size.items()} for size in (s.b, s.w, s.h))
    bf, wf = text(sw.footing_length), text(sw.footing_width)
    b0, w0 = text(sw.beam_haunch_shape.lower_length), text(sw.beam_haunch_shape.lower_width)
    beam, column, footing, soil = sw.beam, sw.column, sw.footing, sw.overburden
    rows = [("はり", beam, 0, f"{b[1]}×{w[1]}×{h[2]}"),
            ("", beam, 1, f"{h[3]}/6×({b0}×{w[1]}+{b[1]}×{w0}+2×({b[1]}×{w[1]}+{b0}×{w0}))"),
            ("柱", column, 0, f"{b[6]}×{w[6]}×{h[4]}"),
            ("フーチング", footing, 1, f"{bf}×{wf}×{h[6]}"),
            ("上載土", soil, 0, f"{bf}×{wf}×({text(s.df1)}+{text(s.df2)})/2"),
            ("", soil, 1, f"−{b[6]}×{w[6]}×{text(sw.soil_depth_at_column)}")]
    expected = "|".join(f"{name + '|' if name else ''}V{index + 1}|{numbers}|=|{text(body.rows[row].volume)}|"
                        f"{text(body.unit_weight)}|{text(body.weights[row])}"
                        for index, (name, body, row, numbers) in enumerate(rows))
    assert found["weight.parts.table"].endswith(expected)
    assert found["weight.parts.text"] == "橋脚く体，フーチングおよび上載土の自重を表6.2.1に示す．"
    assert found["weight.parts.title"] == "表6.2.1橋脚く体，フーチングおよび上載土の自重"
    for part, body in (("beam", beam), ("overburden", soil)):
        first, second = (text(weight) for weight in body.weights[:2])
        second = f"({second})" if second.startswith("-") else second
        assert found[f"weight.{part}.sum.weight"] == f"W={first}+{second}={text(body.weight)}kN"
    # The footing's haunch (V = 0) is left out, so the footing is one row and has no sum; nor has the column.
    assert footing.rows[0].volume.value == 0 and "weight.footing.sum.weight" not in found
    assert "weight.column.sum.weight" not in found


def test_no_pier_impact_is_printed():
    """Decision 27: the pier impact (RC標準 解4.4.4, Ds, Du) is not part of 0600."""
    actual = "\n".join(records(*case("current")).values())
    assert "橋脚く体に対する衝撃" not in actual and "Ds" not in actual and "Du" not in actual


# The sentences and symbolic formulas of the samples (07 7-4, 7-5, 7-14; Example橋脚 0600 p14, p33).
SAMPLE_TEXT = {
    "制動荷重および始動荷重の特性値は下式によって求める。",
    "線路方向の列車荷重慣性力は、車輪とレールとの粘着係数 μ = 0.20 とする。",
    "列車荷重に遠心荷重係数 αc を乗じた値とする。",
    "直線区間のため遠心荷重は考慮しない。",
    "制動荷重：(0.27 + 1.00/Lv)・ΣR",
    "始動荷重：(0.25 + 0.95/Lv)・ΣR",
}
# Tables whose header is a sample's: table 6.2.1 is the table 2.1.2 of Example橋脚3 (its γ, decision 79).
SAMPLE_TABLES = {"0600/weight.parts.table"}
# What explains or names a formula beyond the samples: sentences, "ここに" definitions, symbolic steps.
EXPLAINING = re.compile(r"とする|である|乗じ|求め|作用させ|載荷し|ここに|Σ|×\s*n\b|γ|軸数|L\s*×\s*α|H\s*×\s*y")


@pytest.mark.parametrize("name", list(CASES))
def test_nothing_is_explained_beyond_the_samples(name: str):
    """Decision 55: no sentence, definition or symbolic step that the samples do not write."""
    found = {key: value for key, value in records(*case(name)).items()
             if value not in SAMPLE_TEXT and "heading" not in key and key not in SAMPLE_TABLES
             and EXPLAINING.search(value)}
    assert found == {}


def test_the_report_reads_the_result_not_the_input():
    """A result whose values differ from what the input gives is printed as is."""
    result, pier = case("current")
    weight = replace(result.self_weight.beam, weight=Printed(1234.56, 2, "kN"))
    odd = replace(result, self_weight=replace(result.self_weight, beam=weight))
    assert "1234.56" in "\n".join(records(odd, pier).values())


def test_unit_text_follows_the_result_units():
    result, pier = case("current")
    odd = replace(result, self_weight=replace(result.self_weight, beam=replace(
        result.self_weight.beam, weight=Printed(1.0, 0, "furlong"))))
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

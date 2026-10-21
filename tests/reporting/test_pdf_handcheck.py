"""The hand-check reader: printed numbers alone reproduce each formula (decision 15)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from foundation_report_cases import CASES, CURRENT, case
from pdf_handcheck import formula_checks, tokens_text
from webpier.calc.embedment import applicable_embedment
from webpier.calc.foundation import calculate_foundation
from webpier.core.printed import Printed
from webpier.inputs import parse_input
from webpier.reporting.stages.foundation import render_foundation

# surface 1, Bv 1, Av 1, kv 2, Kv 2, ks 2, Ks 2, Iv 2, Kr 4; and γ2 where it applies (decision 40)
FOUNDATION_FORMULAS = 17


def render(tmp_path: Path, result, pier, embedment, name: str = "0500.pdf") -> Path:
    return render_foundation(result, pier, embedment, tmp_path / name)


@pytest.mark.parametrize("name", list(CASES))
def test_every_printed_formula_reproduces_its_result(tmp_path: Path, name: str):
    result, pier, embedment = case(name)
    checks = formula_checks(render(tmp_path, result, pier, embedment))
    assert len(checks) == FOUNDATION_FORMULAS + (embedment is not None)
    assert [check for check in checks if not check.ok] == []


def test_the_reader_sees_products_powers_inline_fractions_roots_and_min(tmp_path: Path):
    checks = formula_checks(render(tmp_path, *case("current")))
    expressions = [check.expression for check in checks]
    assert "2.700+0.000+min(2.000,2.000)" in expressions
    assert "sqrt(63.000)" in expressions
    assert "7.000*9.000" in expressions
    assert "6.9*0.5*165760*7.937**(-1/2)" in expressions
    assert "1/3*202988" in expressions  # 0500 prints its fractions inline, as the reference
    assert "9.000*7.000**(3)/12" in expressions
    assert "405976*425.250000" in expressions
    gamma = next(check for check in checks if check.printed == "12.3")
    assert (gamma.expression, gamma.ok) == ("((4.700-2.700)*18.0+2.700*8.0)/4.700", True)
    kr = next(check for check in checks if check.expression == "405976*425.250000")
    assert (kr.printed, kr.page) == ("172,641,294", 3)


def wrong(result, field: str):
    """A result whose printed value no longer follows from the printed factors."""
    long_term = result.long_term
    changes = {
        "Kv": lambda: replace(result, long_term=replace(long_term, Kv=Printed(long_term.Kv.value + 1, 0, "kN/m"))),
        "kv": lambda: replace(result, long_term=replace(long_term, kv=Printed(long_term.kv.value + 1, 0, "kN/m3"))),
        "width": lambda: replace(result, width=Printed(7.938, 3, "m")),
        "inertia": lambda: replace(result, inertia_transverse=Printed(425.251, 6, "m4")),
        "surface": lambda: replace(result, surface_thickness=Printed(4.701, 3, "m")),
        "area": lambda: replace(result, area=Printed(63.001, 3, "m2")),
    }
    return changes[field]()


@pytest.mark.parametrize("field,expected", [
    ("Kv", {"202988*63.000"}),
    # kv itself is the result of the power formula and a factor of six others.
    # 202989/3 still prints 67663, so ks stays consistent.
    ("kv", {"6.9*0.5*165760*7.937**(-1/2)", "202989*63.000", "202989*257.250000", "202989*425.250000"}),
    ("width", {"sqrt(63.000)", "6.9*0.5*165760*7.938**(-1/2)", "6.9*1.0*165760*7.938**(-1/2)"}),
    ("inertia", {"7.000*9.000**(3)/12", "202988*425.251000", "405976*425.251000"}),
    ("surface", {"2.700+0.000+min(2.000,2.000)"}),
    # √63.001 still prints 7.937.
    ("area", {"7.000*9.000", "202988*63.001", "405976*63.001", "67663*63.001", "135325*63.001"}),
])
def test_a_value_that_does_not_follow_from_the_printed_factors_is_found(tmp_path: Path, field: str, expected: set[str]):
    result, pier, embedment = case("current")
    checks = formula_checks(render(tmp_path, wrong(result, field), pier, embedment))
    assert len(checks) == FOUNDATION_FORMULAS + 1
    assert {check.expression for check in checks if not check.ok} == expected


def test_a_gamma2_that_does_not_follow_from_the_printed_values_is_found(tmp_path: Path):
    result, pier, embedment = case("current")
    wrong = replace(embedment, normal=replace(embedment.normal, unit_weight=Printed(12.2, 1, "kN/m3")))
    checks = formula_checks(render(tmp_path, result, pier, wrong))
    assert {check.expression for check in checks if not check.ok} == {"((4.700-2.700)*18.0+2.700*8.0)/4.700"}


def test_a_wrapped_formula_is_read_across_its_lines(tmp_path: Path):
    """The deep footing's surface thickness fills its term columns, so its result stands on a line of its own; a
    longer formula without term columns wraps at its operators. Both are read across their lines."""
    import pymupdf
    from gridlayoutpdf import Equation, Operator, Row
    from webpier.reporting.document import report
    from webpier.reporting.equations import TERM_SPACE, equation_group

    path = render(tmp_path, *case("deep"))
    check = next(check for check in formula_checks(path) if check.printed == "23.720")
    assert (check.expression, check.ok) == ("12.345+1.250+min(10.125,10.500)", True)
    with pymupdf.open(path) as pdf:
        assert pdf[0].search_for("23.720")[-1].y0 - pdf[0].search_for("12.345")[0].y0 > 10
    long = equation_group(Equation("X", Row(*["1.111", Operator("+")] * 20, "1.111", gap=TERM_SPACE),
                                   result="23.331", unit="m"),
                          left=4, first_equal=6, second_equal=21, result_right=26, unit_start=27)
    path = report(long).render(tmp_path / "wrapped.pdf", invariant=True)
    with pymupdf.open(path) as pdf:
        first = pdf[0].search_for("1.111")[0]
        result = pdf[0].search_for("23.331")[0]
    assert result.y0 - first.y0 > 10      # the result is printed on a later line
    (check,) = formula_checks(path)
    assert (check.expression, check.ok) == ("+".join(["1.111"] * 21), True)


def test_tokens_text_shows_the_structure_read_back():
    assert tokens_text([("num", "7.937"), ("sup", [("op", "-"), ("num", "1"), ("op", "/"), ("num", "2")])]) == "7.937^(-1/2)"
    assert tokens_text([("frac", [("num", "1")], [("num", "3")]), ("root", [("num", "63.000")]),
                        ("word", "B"), ("sub", [("word", "v")])]) == "(1)/(3)√(63.000)B_(v)"


def test_figure_strokes_are_not_read_as_fraction_bars_or_radicals(tmp_path: Path):
    """A horizontal 0.5-0.8 pt stroke is a fraction bar only with text above and below it, and a
    radical only with text under it; an arrow with its label, or a spring, keeps the label as text."""
    import pymupdf
    from gridlayoutpdf import Figure, Line, Polyline, Text
    from pdf_handcheck import read_lines
    from webpier.reporting.document import report, paragraph
    from webpier.reporting.styles import BODY, columns_for, rows_for

    figure = Figure(columns_for(240), rows_for(72),
                    Line(20, 30, 70, 30, .8), Text(40, 26, "H", BODY),  # an arrow shaft with its label above
                    Polyline(((100, 40), (105, 35), (110, 40), (120, 30), (160, 30)), .5),  # a spring lead
                    Text(130, 44, "Hw3", BODY), Text(170, 34, "P", BODY))
    path = report(figure, paragraph("x = 1 + 2 = 3")).render(tmp_path / "strokes.pdf")
    with pymupdf.open(path) as pdf:
        texts = [tokens_text(tokens) for _, tokens in read_lines(pdf[0])]
    assert "H" in texts and not any("/" in text or "√" in text for text in texts)
    assert any(text.startswith("Hw3") for text in texts)
    assert [check.ok for check in formula_checks(path)] == [True]


def test_a_cover_of_several_layers_prints_each_part_and_reproduces_gamma2(tmp_path: Path):
    # decision 64: 表層 1.050 (18.0 / 8.0), ローム 1.000 (17.0 / 7.0), 支持層 the rest 2.650 (19.0 / 10.0), hw2 2.700:
    # (1.050 × 18.0 + 0.950 × 17.0 + 0.050 × 7.0 + 2.650 × 10.0) / 4.700 = 13.170… → 13.2
    data = deepcopy(CURRENT)
    layers = data["地盤データ"]["層"]
    layers[0]["層厚"] = 1.05
    layers.insert(1, deepcopy(layers[0]) | {"層番": "ローム", "層厚": 1.0, "土質区分": "粘性土", "N値": 4,
                                           "単位体積重量": {"湿潤": 17.0, "水中": 7.0}})
    pier = parse_input(data)
    result = calculate_foundation(pier)
    checks = formula_checks(render(tmp_path, result, pier, applicable_embedment(pier, result)))
    gamma = next(check for check in checks if check.printed == "13.2")
    assert (gamma.expression, gamma.ok) == ("(1.050*18.0+0.950*17.0+0.050*7.0+2.650*10.0)/4.700", True)
    assert [check for check in checks if not check.ok] == []

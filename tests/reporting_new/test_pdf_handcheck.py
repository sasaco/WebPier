"""The hand-check reader: printed numbers alone reproduce each formula (decision 15)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from foundation_report_cases import CASES, case
from pdf_handcheck import formula_checks, tokens_text
from webpier.core.printed import Printed
from webpier.reporting.stages.foundation import render_foundation

# surface 1, Bv 1, Av 1, kv 2, Kv 2, ks 2, Ks 2, Iv 2, Kr 4
FOUNDATION_FORMULAS = 17


def render(tmp_path: Path, result, pier, name: str = "0500.pdf") -> Path:
    return render_foundation(result, pier, tmp_path / name)


@pytest.mark.parametrize("name", list(CASES))
def test_every_printed_formula_reproduces_its_result(tmp_path: Path, name: str):
    checks = formula_checks(render(tmp_path, *case(name)))
    assert len(checks) == FOUNDATION_FORMULAS
    assert [check for check in checks if not check.ok] == []


def test_the_reader_sees_products_powers_fractions_roots_and_min(tmp_path: Path):
    checks = formula_checks(render(tmp_path, *case("current")))
    expressions = [check.expression for check in checks]
    assert "2.700+0.000+min(2.000,2.000)" in expressions
    assert "sqrt(63.000)" in expressions
    assert "7.000*9.000" in expressions
    assert "6.9*0.5*165760*7.937**(-1/2)" in expressions
    assert "((1)/(3))*202988" in expressions
    assert "((9.000*7.000**(3))/(12))" in expressions
    assert "405976*425.250000" in expressions
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
    ("inertia", {"((7.000*9.000**(3))/(12))", "202988*425.251000", "405976*425.251000"}),
    ("surface", {"2.700+0.000+min(2.000,2.000)"}),
    # √63.001 still prints 7.937.
    ("area", {"7.000*9.000", "202988*63.001", "405976*63.001", "67663*63.001", "135325*63.001"}),
])
def test_a_value_that_does_not_follow_from_the_printed_factors_is_found(tmp_path: Path, field: str, expected: set[str]):
    result, pier = case("current")
    checks = formula_checks(render(tmp_path, wrong(result, field), pier))
    assert len(checks) == FOUNDATION_FORMULAS
    assert {check.expression for check in checks if not check.ok} == expected


def test_a_wrapped_formula_is_read_across_its_lines(tmp_path: Path):
    import pymupdf

    path = render(tmp_path, *case("deep"))
    with pymupdf.open(path) as pdf:
        first = pdf[0].search_for("12.345")[0]
        result = max(pdf[0].search_for("23.720"), key=lambda hit: hit.y0)  # the first is in the table
    assert result.y0 - first.y0 > 10      # the result is printed on the next line
    check = next(check for check in formula_checks(path) if check.printed == "23.720")
    assert (check.expression, check.ok) == ("12.345+1.250+min(10.125,10.500)", True)


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
    from webpier.reporting.styles import BODY, grid_units

    figure = Figure(grid_units(240), grid_units(72),
                    Line(20, 30, 70, 30, .8), Text(40, 26, "H", BODY),  # an arrow shaft with its label above
                    Polyline(((100, 40), (105, 35), (110, 40), (120, 30), (160, 30)), .5),  # a spring lead
                    Text(130, 44, "Hw3", BODY), Text(170, 34, "P", BODY))
    path = report(figure, paragraph("x = 1 + 2 = 3")).render(tmp_path / "strokes.pdf")
    with pymupdf.open(path) as pdf:
        texts = [tokens_text(tokens) for _, tokens in read_lines(pdf[0])]
    assert "H" in texts and not any("/" in text or "√" in text for text in texts)
    assert any(text.startswith("Hw3") for text in texts)
    assert [check.ok for check in formula_checks(path)] == [True]

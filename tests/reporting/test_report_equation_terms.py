"""Term columns of report equations: right-aligned numbers, centered operators, inline fractions."""

from __future__ import annotations

from typing import Any

import pytest


def _texts(commands: Any) -> list[Any]:
    from gridlayoutpdf import Text

    return [command for command in commands if isinstance(command, Text) and command.text.strip()]


def _walk(node: Any):
    yield node
    for child in getattr(node, "items", ()):
        yield from _walk(child)


def test_term_columns_align_numbers_right_and_operators_center_across_equations():
    from gridlayoutpdf import Equation
    from webpier.reporting import document, equations, fonts as font_module, styles

    fonts = font_module.load_fonts()
    page = document.report(equations.equation_group(
        Equation("W", equations.terms("5.1", "×", "0.5", "×", "68600")),
        Equation("H", equations.terms("12.25", "×", "3", "×", "(", "1", "+", "0.222", ")")),
    ), fonts=fonts).layout()[0]
    lines: dict[float, list[Any]] = {}
    for command in _texts(page.commands):
        lines.setdefault(round(command.y, 2), []).append(command)
    first, second = (sorted(line, key=lambda command: command.x) for _, line in sorted(lines.items()))

    def width(command: Any) -> float:
        return fonts.measure(command.text, styles.BODY).width

    def right(command: Any) -> float:
        return command.x + width(command)

    def center(command: Any) -> float:
        return command.x + width(command) / 2

    # W = 5.1 × 0.5 × 68600 / H = 12.25 × 3 × (1 + 0.222)
    w_numbers, w_operators = [first[2], first[4], first[6]], [first[3], first[5]]
    h_numbers, h_operators = [second[2], second[4], second[-1]], [second[3], second[5]]
    assert [command.text for command in w_numbers] == ["5.1", "0.5", "68600"]
    assert [command.text for command in h_numbers] == ["12.25", "3", ")"]
    for upper, lower in zip(w_numbers, h_numbers):
        assert right(upper) == pytest.approx(right(lower), abs=.01)
    for upper, lower in zip(w_operators, h_operators):
        assert upper.text == lower.text == "×"
        assert center(upper) == pytest.approx(center(lower), abs=.01)
    for line in (first[2:7], second[2:6]):
        for left, following in zip(line, line[1:]):
            assert following.x - right(left) >= equations.TERM_GAP - .01
    # 0500 p1 keeps 9.2-9.4 pt, 0600 p16's derivation columns 5.8-8.7 pt: one gap for every report.
    assert equations.TERM_GAP == pytest.approx(62 * .12)


def test_equations_of_another_term_shape_do_not_share_term_columns():
    """A short "2 / 3" after a five-column row keeps the line it has alone: rows share term columns only
    when their column count and aligns match (or neither has term columns)."""
    from gridlayoutpdf import Equation
    from webpier.reporting import document, equations

    long = Equation("X", equations.terms("12345.678", "×", "LR", "×", "1.0"))
    short = Equation("Y", equations.terms("2", "/", "3"))
    plain = Equation("Z", "a + b")

    def lines(*items: Equation) -> list[list[tuple[float, str]]]:
        page = document.report(equations.equation_group(*items)).layout()[0]
        found: dict[float, list[tuple[float, str]]] = {}
        for command in _texts(page.commands):
            found.setdefault(round(command.y, 2), []).append((round(command.x, 2), command.text))
        return [sorted(line) for _, line in sorted(found.items())]

    alone = lines(short)[0]
    assert lines(long, short)[1] == alone
    assert lines(short, long)[0] == alone
    assert lines(long, plain, short)[2] == alone
    # The same shape still shares its columns: "2" ends under "12345.678".
    same = lines(long, Equation("Y", equations.terms("2", "/", "3", "×", "4")))
    assert same[1] != lines(Equation("Y", equations.terms("2", "/", "3", "×", "4")))[0]


def test_parenthesized_terms_are_one_unbroken_term():
    from gridlayoutpdf import Equation, LayoutContext, Literal, Operator, Row, TermStop, measure_block
    from webpier.reporting import equations, fonts as font_module, styles

    row = equations.terms("(", "1", "+", "(", "0.2", "−", "c", ")", ")", "×", Operator("/"), "2")
    assert row.gap == equations.TERM_SPACE == 4.95
    assert [type(item) for item in row.items[::2]] == [TermStop] * 4
    assert [item.align for item in row.items[::2]] == ["right", "center", "center", "right"]
    group = row.items[1]
    inner = Row("(", "0.2", " ", Operator("−"), " ", "c", ")", gap=0)
    assert group == Row("(", "1", " ", Operator("+"), " ", inner, ")", gap=0)
    assert row.items[3] == Operator("×") and row.items[5] == Operator("/") and row.items[7] == Literal("2")

    # Too wide for one line: the RHS falls back to wrapping only between terms.
    long = equations.terms(*(part for index in range(8)
                             for part in ((("×",) if index else ()) + ("(", "1.000", "+", "0.222", ")"))))
    context = LayoutContext(font_module.load_fonts(), styles.report_profile(), styles.REPORT_STYLE)
    measured = measure_block(equations.equation_group(Equation("X", long)), context, 300)
    lines = ["".join(command.text for command in sorted(_texts(part.commands), key=lambda c: c.x))
             for part in measured.parts]
    assert len(lines) > 1
    for line in lines:
        assert line.count("(") == line.count(")")
        assert "(1.000+0.222)" in line

    for unbalanced in (("(", "1"), ("1", ")"), ("(", "(", "1", ")")):
        with pytest.raises(ValueError, match="unmatched"):
            equations.terms(*unbalanced)


def test_over_is_an_inline_parenthesized_fraction():
    from gridlayoutpdf import Fraction, Operator, Row
    from webpier.reporting import document, equations

    numerator = Row("a", " ", Operator("+"), " ", "b", gap=0)
    node = equations.over(numerator, "c")
    assert node == Row(Row("(", numerator, ")", gap=0), "/", "c", gap=0)
    assert not any(isinstance(item, Fraction) for item in _walk(node))
    simple = equations.over(equations.script("A", subscript="s"), Row("2"))
    assert simple == Row(equations.script("A", subscript="s"), "/", Row("2"), gap=0)
    page = document.report(document.math_line(node)).layout()[0]
    assert "".join(command.text for command in sorted(
        (command for command in page.commands if hasattr(command, "text")), key=lambda c: c.x)) == "(a + b)/c"


def _pdf_lines(path: Any) -> list[list[tuple[int, list[tuple[float, float, str]]]]]:
    """Per page, the words of each text line (x0, x1, text) by baseline, read back from the PDF."""
    import pymupdf

    pages = []
    with pymupdf.open(path) as pdf:
        for page in pdf:
            lines: list[tuple[float, list[tuple[float, float, str]]]] = []
            for x0, _, x1, bottom, text, *_ in sorted(page.get_text("words"), key=lambda w: (w[3], w[0])):
                if lines and abs(lines[-1][0] - bottom) < 1.5:
                    lines[-1][1].append((x0, x1, text))
                else:
                    lines.append((bottom, [(x0, x1, text)]))
            pages.append([sorted(words) for _, words in lines])
    return pages


def _assert_columns_line_up(lines: list[list[tuple[float, float, str]]]) -> None:
    """Between the first "=" and the result's "=", each number column ends at one x and each operator
    column is centered on one x; the result "=" and the result's right edge are shared too."""
    rows = []
    for words in lines:
        equals = [index for index, word in enumerate(words) if word[2] in ("=", "＝")]
        assert len(equals) == 2, words
        rows.append((words[equals[0] + 1:equals[1]], words[equals[1]:equals[1] + 2]))
    def same(values: list[float]) -> bool:
        return max(values) - min(values) < .05

    for column in range(min(len(terms) for terms, _ in rows)):
        if column % 2:
            assert same([(terms[column][0] + terms[column][1]) / 2 for terms, _ in rows]), column
        else:
            assert same([terms[column][1] for terms, _ in rows]), column
    assert same([result[0][0] for _, result in rows]) and same([result[1][1] for _, result in rows])


def test_consecutive_0600_derivations_share_term_columns_across_lines(tmp_path: Any):
    """07 7-5: "μ・Rm = 0.10 × 6 720.00 = 672.00 kN" and "μ・T / n = 0.10 × 160.00 = 16.00 kN" are one
    group of equations: their numbers and operators stand in the same columns. "T / n = 320.00/2" above
    them is one term written right after its "=", not spread over their columns."""
    from reaction_report_cases import case
    from webpier.reporting.stages.reaction import render_reaction

    result, pier = case("current")
    found = 0
    for lines in _pdf_lines(render_reaction(result, pier, tmp_path / "0600.pdf")):
        for index in range(len(lines) - 2):
            heads = [" ".join(word[2] for word in line[:3]) for line in lines[index:index + 3]]
            if heads[0] == "T / n" and heads[1].startswith("μ・Rm") and heads[2].startswith("μ・T /"):
                _assert_columns_line_up(lines[index + 1:index + 3])
                share = lines[index]
                equal = next(position for position, word in enumerate(share) if word[2] in ("=", "＝"))
                assert "/" in share[equal + 1][2] and share[equal + 2][2] in ("=", "＝"), share
                found += 1
    assert found >= 2


def test_consecutive_0610_actions_share_term_columns_and_keep_their_words(tmp_path: Any):
    """0610 p3: the buoyancy at the high, normal and low water levels line up, each with its word."""
    from frame_report_cases import chain
    from webpier.reporting.stages.longitudinal import build_longitudinal

    pier, reaction, result, _ = chain("current")
    pages = _pdf_lines(build_longitudinal(result, reaction, pier).render(tmp_path / "0610.pdf", invariant=True))
    for lines in pages:
        words = [line[0][2] for line in lines]
        if "高水位" in words:
            start = words.index("高水位")
            assert words[start:start + 3] == ["高水位", "平水位", "低水位"]
            group = lines[start:start + 3]
            assert all(line[0][0] == pytest.approx(117.0, abs=.01) for line in group)
            _assert_columns_line_up(group)
            break
    else:
        raise AssertionError("浮力の式がありません")


def test_equation_group_breaks_pages_only_between_equations_not_kept():
    from gridlayoutpdf import Equation, LayoutContext, measure_block
    from webpier.reporting import equations, fonts as font_module, styles

    context = LayoutContext(font_module.load_fonts(), styles.report_profile(), styles.REPORT_STYLE)
    items = [Equation("X", equations.terms("1.0", "×", "2.0"), label="語" if index == 1 else "",
                      block_id=f"e{index}") for index in range(3)]
    measured = measure_block(equations.equation_group(*items, keep=(True, False, False), block_id="g"),
                             context, 400)
    assert [part.metadata["equation_block_id"] for part in measured.parts] == ["e0", "e1", "e2"]
    assert measured.break_after == (2,) and not measured.prefer_keep
    kept = measure_block(equations.equation_group(*items, keep=(True, True, False)), context, 400)
    assert kept.break_after == () and kept.prefer_keep
    single = measure_block(equations.equation_group(items[0], keep=(False,)), context, 400)
    assert single.break_after is None and single.prefer_keep
    with pytest.raises(ValueError, match="one flag per equation"):
        equations.equation_group(*items, keep=(True,))


def test_a_frame_equation_word_never_covers_its_symbol():
    from gridlayoutpdf import Equation, LayoutOverflowError
    from webpier.reporting import document, equations
    from webpier.reporting.stages import frame_report

    block = frame_report._LabelledBlock(("断面二次モーメントの見出し",), equations.equation_group(
        Equation("I", "1", block_id="frame/inertia"), left=117, first_equal=frame_report.FIRST_EQUAL), 117)
    with pytest.raises(LayoutOverflowError, match="frame/inertia"):
        document.report(block).layout()

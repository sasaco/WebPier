"""The "ここに、" definition list and source-tagged headings on the grid (reference 0500 p1/p2 for their form)."""

from __future__ import annotations

from typing import Any

import pytest

ORIGIN_X, PITCH_X, PITCH_Y = 50.88, 16.08, 15.48
# Body columns: the block from column 4, "：" on the boundary before column 8, "(=" before column 21, the value
# ending at column 25 and the unit from column 26.
LEFT, COLON, VALUE_EQUAL, VALUE_RIGHT, UNIT_START = 4, 8, 21, 25, 26


def x(column: int) -> float:
    return ORIGIN_X + column * PITCH_X


def _texts(page: Any) -> list[Any]:
    from gridlayoutpdf import Text

    return [command for command in page.commands if isinstance(command, Text) and command.text.strip()]


def _right(fonts: Any, command: Any) -> float:
    return command.x + fonts.measure(command.text, command.style).width


def _centre(fonts: Any, command: Any) -> float:
    return command.x + fonts.measure(command.text, command.style).width / 2


def _layout(*blocks: Any) -> tuple[Any, Any]:
    """Lay out *blocks* and a following body line (a heading must precede body text)."""
    from webpier.reporting import document, fonts as font_module

    pages = document.report(*blocks, document.paragraph("本文")).layout()
    assert len(pages) == 1
    return font_module.load_fonts(), pages[0]


def test_definitions_right_align_symbols_against_one_colon_column():
    from gridlayoutpdf import Row
    from webpier.reporting import equations

    items = (
        equations.Definition(equations.script("k", subscript="h"), "フーチング前面の水平地盤反力係数"),
        equations.Definition(equations.script("ρ", subscript="gk"), "地盤反力係数に関する地盤修正係数"),
        equations.Definition(equations.script("E", subscript="d"), "地盤の変形係数", value="68600",
                             unit=Row("kN/m", equations.script("", superscript="2"), gap=0)),
    )
    fonts, page = _layout(equations.definitions(
        *items, left=LEFT, colon=COLON, value_equal=VALUE_EQUAL, value_right=VALUE_RIGHT,
        unit_start=UNIT_START, block_id="definitions"))
    texts = _texts(page)
    colons = sorted((command for command in texts if command.text == "："), key=lambda command: command.y)
    assert len(colons) == 3
    for command in colons:
        assert _centre(fonts, command) == pytest.approx(x(COLON), abs=.01)
    assert [b.y - a.y for a, b in zip(colons, colons[1:])] == pytest.approx([PITCH_Y, PITCH_Y], abs=1e-6)

    def line(colon: Any) -> list[Any]:
        return [command for command in texts if abs(command.y - colon.y) < 6]  # scripts move ≤ 4.92

    lines = [line(colon) for colon in colons]
    labels = [command for command in texts if command.text == "ここに、"]
    assert len(labels) == 1 and labels[0] in lines[0]
    symbols = [[command for command in found if command.x < colons[0].x - 1 and command.text != "ここに、"]
               for found in lines]
    # "ここに、" leads the first symbol directly, inside the block.
    assert labels[0].y == pytest.approx(colons[0].y) and labels[0].x >= x(LEFT) - 1e-6
    assert _right(fonts, labels[0]) == pytest.approx(min(command.x for command in symbols[0]), abs=.01)
    symbol_rights = [max(_right(fonts, command) for command in found) for found in symbols]
    assert symbol_rights == pytest.approx([symbol_rights[0]] * 3, abs=.01)
    assert [command.text for command in lines[1] if command.text == "ρ"] == ["ρ"]
    texts_after = [min((command for command in found if command.x > colons[0].x), key=lambda command: command.x)
                   for found in lines]
    assert [command.text for command in texts_after] == [
        "フーチング前面の水平地盤反力係数", "地盤反力係数に関する地盤修正係数", "地盤の変形係数"]
    assert [command.x for command in texts_after] == pytest.approx([texts_after[0].x] * 3, abs=1e-6)
    (equal,) = [command for command in texts if command.text == "(="]
    (value,) = [command for command in texts if command.text == "68600"]
    assert equal.y == pytest.approx(colons[2].y)
    assert x(VALUE_EQUAL - 1) <= equal.x <= x(VALUE_EQUAL)
    assert x(VALUE_EQUAL) < value.x and _right(fonts, value) <= x(VALUE_RIGHT) + 1e-6
    unit = [command for command in lines[2] if command.x >= x(UNIT_START) - 1e-6]
    assert "".join(command.text for command in sorted(unit, key=lambda command: command.x)) == "kN/m2)"


def test_definition_value_without_unit_is_closed_and_validation():
    from gridlayoutpdf import LayoutOverflowError
    from webpier.reporting import equations

    fonts, page = _layout(equations.definitions(
        equations.Definition("B", "フーチング底面の換算幅", value="5.100"),
        left=LEFT, colon=COLON, value_equal=VALUE_EQUAL, value_right=VALUE_RIGHT, unit_start=UNIT_START))
    (close,) = [command for command in _texts(page) if command.text == ")"]
    assert close.x >= x(UNIT_START) - 1e-6
    with pytest.raises(ValueError):
        equations.definitions(left=LEFT, colon=COLON)
    with pytest.raises(ValueError):
        equations.definitions(equations.Definition("B", "幅", unit="m"), left=LEFT, colon=COLON)
    # A label and first symbol reaching left of the block are an error, never a wrap.
    with pytest.raises(LayoutOverflowError):
        _layout(equations.definitions(equations.Definition("WWWW", "幅"), left=LEFT, colon=LEFT + 2))


@pytest.mark.parametrize(("text", "column"), [
    ("1) フーチング底面の鉛直地盤反力係数", 18),
    ("1) フーチング底面の鉛直地盤反力係数の算定値の検討", 19),
])
def test_heading_tag_stands_in_its_own_column(text: str, column: int):
    from webpier.reporting import document, styles

    fonts, page = _layout(document.heading(text, left=3, tag="【基礎標準 13.2.2.2】", block_id="h"))
    texts = _texts(page)
    (tag,) = [command for command in texts if command.text == "【基礎標準 13.2.2.2】"]
    (title,) = [command for command in texts if command.text == text]
    assert tag.x == pytest.approx(x(column), abs=1e-6)
    assert tag.y == title.y and tag.style == title.style == styles.HEADING
    assert tag.x >= _right(fonts, title) + styles.HEADING.size - 1e-6


def test_heading_without_tag_is_one_grid_row_of_the_heading_and_tag_overflow_raises():
    from gridlayoutpdf import Heading, LayoutOverflowError, Leading
    from webpier.reporting import document, styles

    text = "(1) フーチング底面の鉛直地盤ばね定数"
    plain = _layout(document.heading(text, left=3, block_id="h"))[1]
    manual = _layout(document.indent_to(Leading(Heading(text, style=styles.HEADING, block_id="h"), 1), 3))[1]
    assert plain.commands == manual.commands
    with pytest.raises(LayoutOverflowError):
        _layout(document.heading(text, left=3, tag="【" + "基礎標準" * 12 + "】"))
    with pytest.raises(LayoutOverflowError):
        _layout(document.heading("見出し" * 60, left=3, tag="【基礎標準】"))

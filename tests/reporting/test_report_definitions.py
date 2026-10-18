"""The "ここに、" definition list and source-tagged headings, against reference 0500 p1/p2."""

from __future__ import annotations

from typing import Any

import pytest

# Reference 0500 p1: "：" at 210.96, "(=" at 341.64, unit at 413.4. "ここに、" starts at 157.8
# there; the block edge stands a little left, since a subscript follows its base 0.9 pt later here.
LEFT, COLON, VALUE_EQUAL, VALUE_RIGHT, UNIT_START = 152.04, 210.96, 341.64, 408.96, 413.4


def _texts(page: Any) -> list[Any]:
    from gridlayoutpdf import Text

    return [command for command in page.commands if isinstance(command, Text) and command.text.strip()]


def _right(fonts: Any, command: Any) -> float:
    return command.x + fonts.measure(command.text, command.style).width


def _layout(*blocks: Any) -> tuple[Any, Any]:
    """Lay out *blocks* and a following body line (a heading must precede body text)."""
    from webpier.reporting import document, fonts as font_module

    fonts = font_module.load_fonts()
    pages = document.report(*blocks, document.paragraph("本文"), fonts=fonts).layout()
    assert len(pages) == 1
    return fonts, pages[0]


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
        assert command.x == pytest.approx(COLON, abs=.06)
    assert [b.y - a.y for a, b in zip(colons, colons[1:])] == pytest.approx([14.28, 14.28], abs=1e-6)

    def line(colon: Any) -> list[Any]:
        return [command for command in texts if abs(command.y - colon.y) < 6]  # scripts move ≤ 4.92

    lines = [line(colon) for colon in colons]
    labels = [command for command in texts if command.text == "ここに、"]
    assert len(labels) == 1 and labels[0] in lines[0]
    symbols = [[command for command in found if command.x < COLON - 1 and command.text != "ここに、"]
               for found in lines]
    # "ここに、" leads the first symbol directly, inside the block.
    assert labels[0].y == pytest.approx(colons[0].y) and labels[0].x >= LEFT - 1e-6
    assert _right(fonts, labels[0]) == pytest.approx(min(command.x for command in symbols[0]), abs=.01)
    symbol_rights = [max(_right(fonts, command) for command in found) for found in symbols]
    assert symbol_rights == pytest.approx([symbol_rights[0]] * 3, abs=.01)
    # One half-width space separates each symbol from its colon.
    assert COLON - symbol_rights[0] == pytest.approx(4.95, abs=.07)
    assert [command.text for command in lines[1] if command.text == "ρ"] == ["ρ"]
    texts_after = [min((command for command in found if command.x > COLON), key=lambda command: command.x)
                   for found in lines]
    assert [command.text for command in texts_after] == [
        "フーチング前面の水平地盤反力係数", "地盤反力係数に関する地盤修正係数", "地盤の変形係数"]
    for colon, text in zip(colons, texts_after):
        assert text.x == pytest.approx(colon.x + 9.9, abs=.13)
    (equal,) = [command for command in texts if command.text == "(="]
    (value,) = [command for command in texts if command.text == "68600"]
    assert equal.x == pytest.approx(VALUE_EQUAL, abs=.06) and equal.y == pytest.approx(colons[2].y)
    assert _right(fonts, value) == pytest.approx(VALUE_RIGHT, abs=1e-6)
    unit = [command for command in lines[2] if command.x >= UNIT_START - 1e-6]
    assert min(command.x for command in unit) == pytest.approx(UNIT_START, abs=1e-6)
    assert "".join(command.text for command in sorted(unit, key=lambda command: command.x)) == "kN/m2)"


def test_definition_value_without_unit_is_closed_and_validation():
    from gridlayoutpdf import LayoutOverflowError
    from webpier.reporting import equations

    fonts, page = _layout(equations.definitions(
        equations.Definition("B", "フーチング底面の換算幅", value="5.100"),
        left=LEFT, colon=COLON, value_equal=VALUE_EQUAL, value_right=VALUE_RIGHT, unit_start=UNIT_START))
    (close,) = [command for command in _texts(page) if command.text == ")"]
    assert close.x == pytest.approx(UNIT_START, abs=1e-6)
    with pytest.raises(ValueError):
        equations.definitions(left=LEFT, colon=COLON)
    with pytest.raises(ValueError):
        equations.definitions(equations.Definition("B", "幅", unit="m"), left=LEFT, colon=COLON)
    # A label and first symbol reaching left of the block are an error, never a wrap.
    with pytest.raises(LayoutOverflowError):
        _layout(equations.definitions(equations.Definition("WWWW", "幅"), left=LEFT, colon=COLON))


@pytest.mark.parametrize(("text", "expected"), [
    ("1) フーチング底面の鉛直地盤反力係数", 340.80),
    ("1) フーチング底面の鉛直地盤反力係数の算定値", 369.84),
])
def test_heading_tag_stands_in_its_own_column(text: str, expected: float):
    from webpier.reporting import document, styles

    fonts, page = _layout(document.heading(text, left=137.52, tag="【基礎標準 13.2.2.2】", block_id="h"))
    texts = _texts(page)
    (tag,) = [command for command in texts if command.text == "【基礎標準 13.2.2.2】"]
    (title,) = [command for command in texts if command.text == text]
    assert tag.x == pytest.approx(expected, abs=1e-6)
    assert tag.y == title.y and tag.style == title.style == styles.HEADING
    assert tag.x >= _right(fonts, title) + 9.9 - 1e-6
    untagged = _layout(document.heading(text, left=137.52, block_id="h"))[1]
    assert [command for command in page.commands if command is not tag] == list(untagged.commands)


def test_heading_without_tag_is_unchanged_and_tag_overflow_raises():
    from gridlayoutpdf import Heading, LayoutOverflowError, Leading
    from webpier.reporting import document, styles

    text = "(1) フーチング底面の鉛直地盤ばね定数"
    plain = _layout(document.heading(text, left=123, block_id="h"))[1]
    manual = _layout(document.indent_to(Leading(Heading(text, style=styles.HEADING, block_id="h"),
                                                styles.grid_units(styles.BODY_LEADING)), 123))[1]
    assert plain.commands == manual.commands
    with pytest.raises(LayoutOverflowError):
        _layout(document.heading(text, left=123, tag="【" + "基礎標準" * 12 + "】"))
    with pytest.raises(LayoutOverflowError):
        _layout(document.heading("見出し" * 60, left=123, tag="【基礎標準】"))

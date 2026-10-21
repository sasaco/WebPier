"""Generic report composition on GridLayoutPdf's common grid: fonts by name, grid units, flow, tables, equations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf
import pytest

ORIGIN_X, PITCH_X, PITCH_Y = 50.88, 16.08, 15.48


def native_signature(pdf: pymupdf.Document) -> list[tuple[Any, ...]]:
    return [(page.number, line["dir"], span["font"], span["size"], character["c"],
             tuple(character["origin"]), tuple(character["bbox"]))
            for page in pdf for block in page.get_text("rawdict")["blocks"]
            for line in block.get("lines", []) for span in line["spans"]
            for character in span["chars"]]


def test_positions_are_whole_grid_columns_and_rows_of_the_reference_a4_grid():
    from gridlayoutpdf import A4_PORTRAIT_REFERENCE
    from webpier.reporting import styles

    assert styles.report_profile() == A4_PORTRAIT_REFERENCE
    grid = styles.report_profile().grid
    assert (grid.origin_x, grid.pitch_x, grid.pitch_y, grid.columns, grid.rows) == (ORIGIN_X, PITCH_X, PITCH_Y, 30, 47)
    assert (styles.columns_pt(4), styles.rows_pt(2), styles.column_x(4)) == pytest.approx(
        (4 * PITCH_X, 2 * PITCH_Y, ORIGIN_X + 4 * PITCH_X))
    assert (styles.columns_for(PITCH_X), styles.columns_for(PITCH_X + .01), styles.rows_for(0)) == (1, 2, 0)
    for value in (-1, 1.5, True, "1"):
        with pytest.raises(ValueError):
            styles.count(value, "columns")
    with pytest.raises(ValueError):
        styles.columns_for(float("nan"))
    assert (styles.BODY.font, styles.BODY.size, styles.HEADING.font, styles.HEADING.size, styles.SMALL.size) == (
        "MS Mincho", 10, "MS Gothic", 10, 6.5)


def test_fonts_are_named_real_faces_without_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from gridlayoutpdf import FontError
    from webpier.reporting import fonts, styles

    files = fonts.font_files()
    assert set(files) == {"body", "heading", "caption", "dimension"}
    assert [files[role].name.lower() for role in ("body", "heading", "caption", "dimension")] == [
        "msmincho.ttc", "msgothic.ttc", "msgothic.ttc", "calibri.ttf"]
    registry = fonts.load_fonts()
    assert (registry.resolve(styles.BODY_FONT).face_index, registry.resolve(styles.HEADING_FONT).face_index,
            registry.resolve(styles.CAPTION_FONT).face_index) == (0, 0, 2)
    monkeypatch.setenv("WINDIR", str(tmp_path))
    monkeypatch.delenv("SystemRoot", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    with pytest.raises(FontError):
        fonts.font_files()
    with pytest.raises(FontError):
        fonts.load_fonts()


def _origins(path: Path) -> dict[str, tuple[float, float]]:
    with pymupdf.open(path) as pdf:
        return {span["text"]: span["origin"] for block in pdf[0].get_text("dict")["blocks"]
                for line in block.get("lines", []) for span in line["spans"]}


def test_indentation_rows_columns_spacer_and_no_page_number(tmp_path: Path):
    from webpier.reporting import document

    block = document.paragraph("一行目\n二行目\n三行目", left=4, block_id="body")
    columns = document.columns(document.paragraph("左", left=0), document.paragraph("右", left=0), widths=(3, 3))
    path = document.report(document.heading("見出し", left=1), block, document.spacer(2), columns).render(
        tmp_path / "rows.pdf")
    origins = _origins(path)
    assert origins["見出し"][0] == pytest.approx(ORIGIN_X + PITCH_X, abs=.01)
    assert origins["一行目"][0] == pytest.approx(ORIGIN_X + 4 * PITCH_X, abs=.01)
    assert origins["二行目"][1] - origins["一行目"][1] == pytest.approx(PITCH_Y, abs=.01)
    assert origins["一行目"][1] - origins["見出し"][1] == pytest.approx(PITCH_Y, abs=.01)
    assert origins["左"][1] - origins["三行目"][1] == pytest.approx(3 * PITCH_Y, abs=.01)
    assert origins["右"][0] - origins["左"][0] == pytest.approx(4 * PITCH_X, abs=.01)
    with pymupdf.open(path) as pdf:  # the reference prints no page number
        assert [line for line in pdf[0].get_text().splitlines() if line.strip()] == [
            "見出し", "一行目", "二行目", "三行目", "左", "右"]


def test_a_blank_line_never_starts_a_page_nor_stacks():
    from webpier.reporting import document

    out: list = []
    document.blank(out)
    assert out == []
    out.append(document.paragraph("本文"))
    document.blank(out)
    document.blank(out)
    assert len(out) == 2 and document.is_blank(out[-1]) and out[-1].discard_at_page_top


def test_repeated_header_follows_actual_pages(tmp_path: Path):
    from webpier.reporting import document

    title = "0610 線路方向荷重"
    path = document.report(document.paragraph("\n".join(f"本文{index:03}" for index in range(110))),
                           header=title).render(tmp_path / "header.pdf")
    with pymupdf.open(path) as pdf:
        assert len(pdf) >= 3
        for page in pdf:
            assert page.get_text().count(title) == 1
            header = page.search_for(title)[0]
            assert header.x0 == pytest.approx(ORIGIN_X, abs=.5)
            assert header.y1 < page.search_for("本文")[0].y0
    without = document.report(document.heading("見出し"), document.paragraph("本文")).layout()
    assert [command.text for command in without[0].commands if hasattr(command, "text")] == ["見出し", "本文"]


def test_a_tagged_heading_puts_its_tag_on_its_row_from_the_tag_column(tmp_path: Path):
    from gridlayoutpdf import LayoutOverflowError
    from webpier.reporting import document

    short = document.heading("5.1 支持力", tag="【基礎標準 13.2.2.2】", block_id="short")
    long = document.heading("5.2 フーチング底面の鉛直地盤反力係数の算定値の検討の内容", tag="【基礎標準】", block_id="long")
    origins = _origins(document.report(short, document.paragraph("本文"), long, document.paragraph("本文")).render(
        tmp_path / "tags.pdf"))
    assert origins["【基礎標準 13.2.2.2】"] == pytest.approx(
        (ORIGIN_X + 18 * PITCH_X, origins["5.1 支持力"][1]), abs=.01)
    tag_x = origins["【基礎標準】"][0]
    assert tag_x > ORIGIN_X + 18 * PITCH_X and (tag_x - ORIGIN_X) / PITCH_X == pytest.approx(round((tag_x - ORIGIN_X) / PITCH_X))
    with pytest.raises(LayoutOverflowError):
        # 44 characters end in column 28; the tag needs three more columns than the body's 30.
        document.report(document.heading("あ" * 44, tag="【出典】"), document.paragraph("本文")).layout()


def test_tables_take_grid_columns_and_rows_with_medium_frames_and_hair_rules(tmp_path: Path):
    from gridlayoutpdf import Fraction, Line, render_xlsx
    from webpier.reporting import document, tables

    blocks = [tables.table((6, 4), [["名称", "12.3400"], ["ROW-2", "-0.5000"]], numeric_columns=(1,), block_id="grid"),
              document.spacer(),
              tables.table((2, 6), [[tables.cell(tables.VerticalLabel("作用", 3), rowspan=3), "上"], ["中"], ["下"]],
                           block_id="label"),
              tables.table((4,), [[tables.math_cell(Fraction("1", "2"), align="center")]], row_heights=None,
                           block_id="math"),
              tables.table((4, 4), [["a", "1"], ["合計", "1"]], inner=None, outer=None,
                           horizontal={1: tables.OUTER}, split=False, block_id="open")]
    pages = document.report(*blocks).layout()
    # The table rules are medium (1 pt) and hair (0.25 pt); the fraction bar is the math's own.
    widths = {round(command.width, 2) for command in pages[0].commands if isinstance(command, Line)}
    assert {.25, 1.0} <= widths and not widths & {.12, .96}
    path = tmp_path / "tables.pdf"
    document.report(*blocks).render(path)
    with pymupdf.open(path) as pdf:
        page = pdf[0]
        first, second = page.search_for("名称")[0], page.search_for("ROW-2")[0]
        assert second.y0 - first.y0 == pytest.approx(PITCH_Y, abs=.02)
        assert any(entry[1] == (0.0, -1.0) and entry[4] in "作用" for entry in native_signature(pdf))
    result = render_xlsx([("tables", pages)], tmp_path / "tables.xlsx", strict=True)
    assert not result.shifts and not result.fallbacks
    with pytest.raises(ValueError):
        tables.table((2.5,), [["x"]])
    with pytest.raises(ValueError):
        tables.table((2,), [["x"]], row_heights=0)


def test_equation_relations_stand_on_column_boundaries():
    from gridlayoutpdf import Equation, Text
    from webpier.reporting import document, equations, fonts as font_module, styles

    fonts = font_module.load_fonts()
    block = equations.equation_group(Equation("x", equations.terms("1", "+", "2"), result="3", unit="m"), left=4,
                                     first_equal=8, second_equal=20, result_right=24, unit_start=25, block_id="eq")
    page = document.report(block).layout()[0]
    relations = [command for command in page.commands if isinstance(command, Text) and command.text == "="]
    centres = [command.x + fonts.measure("=", styles.BODY).width / 2 for command in relations]
    assert centres == pytest.approx([ORIGIN_X + 8 * PITCH_X, ORIGIN_X + 20 * PITCH_X], abs=.01)
    result = next(command for command in page.commands if isinstance(command, Text) and command.text == "3")
    unit = next(command for command in page.commands if isinstance(command, Text) and command.text == "m")
    assert result.x + fonts.measure("3", styles.BODY).width <= ORIGIN_X + 24 * PITCH_X
    assert unit.x >= ORIGIN_X + 25 * PITCH_X
    with pytest.raises(ValueError):
        equations.equation_group(Equation("x", "1"), first_equal=7.5)
    with pytest.raises(ValueError):
        equations.equation_group(Equation("x", "1"), Equation("y", "2"), keep=(True,))


def test_equations_of_another_shape_and_kept_equations_break_only_between_runs(tmp_path: Path):
    from gridlayoutpdf import Equation, LayoutContext, measure_block, render_xlsx
    from webpier.reporting import document, equations, fonts as font_module, styles

    lines = (Equation("A", equations.terms("4.50", "×", "2.70"), result="12.15", unit="m2", label="断面積"),
             Equation("B", equations.terms("1.00", "×", "2.00"), result="2.00", unit="m2"),
             Equation("I", equations.terms("4.50", "×", "2.70", "×", "2.70"), result="32.805", unit="m4"),
             Equation("N", equations.terms("123.4", "+", "56.7"), result="180.1", unit="kN"))
    context = LayoutContext(font_module.load_fonts(), styles.report_profile(), styles.REPORT_STYLE)
    anchors = {"left": 4, "first_equal": 11, "second_equal": 22, "result_right": 26, "unit_start": 27}

    def measured(keep):
        return measure_block(equations.equation_group(*lines, block_id="eq", keep=keep, **anchors), context, 482.4)

    kept = measured((False, True, False, False))
    # A and B share their term columns (one run, two rows); I and N each have a shape of their own.
    assert [part.rows for part in kept.parts] == [2, 1, 1]
    assert kept.break_after == (2,) and not kept.prefer_keep
    assert measured(None).prefer_keep
    pages = document.report(equations.equation_group(*lines, block_id="eq", keep=(False, True, False, False),
                                                     **anchors)).layout()
    result = render_xlsx([("eq", pages)], tmp_path / "eq.xlsx", strict=True)
    assert not result.shifts and not result.fallbacks


def test_terms_that_do_not_fit_their_grid_columns_are_an_overflow():
    from gridlayoutpdf import Equation, LayoutOverflowError
    from webpier.reporting import document, equations

    wide = Equation("x", equations.terms(*("123456.789", "+") * 6, "1"))
    with pytest.raises(LayoutOverflowError, match="term_fallback"):
        document.report(equations.equation_group(wide, left=4, first_equal=8, block_id="wide")).layout()


def test_scripts_use_the_reference_offsets():
    from gridlayoutpdf import Text
    from webpier.reporting import equations, fonts as font_module, styles

    fonts = font_module.load_fonts()
    for node, delta in ((equations.script("m", superscript="2"), -4.92), (equations.script("I", subscript="B"), 1.92)):
        commands = [command for command in node.measure(fonts, styles.BODY).commands if isinstance(command, Text)]
        assert commands[1].style.size == pytest.approx(6.5)
        assert commands[1].y - commands[0].y == pytest.approx(delta, abs=.06)


def _body_baselines(*blocks: Any) -> list[float]:
    from gridlayoutpdf import Text
    from webpier.reporting import document

    page = document.report(*blocks).layout()[0]
    # Main 10 pt glyphs only; 6.5 pt scripts sit off the row baseline by design.
    return sorted({round(command.y, 2) for command in page.commands
                   if isinstance(command, Text) and command.style.size == pytest.approx(10)})


def test_equations_math_lines_and_paragraphs_advance_one_grid_row_a_line():
    from gridlayoutpdf import Equation
    from webpier.reporting import document, equations

    baselines = _body_baselines(
        equations.equation_group(
            Equation("x", "1+2", result="3", unit="m"),
            Equation(equations.script("A", subscript="s"), equations.script("m", superscript="2")),
            second_equal=22, result_right=26, unit_start=27),
        document.math_line("本文の一行"),
        document.math_line(equations.script("σ", subscript="c")),
        document.paragraph("段落一\n段落二"),
    )
    assert [later - earlier for earlier, later in zip(baselines, baselines[1:])] == pytest.approx([PITCH_Y] * 5,
                                                                                                abs=.01)


def test_a_line_taller_than_a_grid_row_is_an_overflow():
    # A row is strict: a stacked fraction does not widen its row, it is an error.
    from gridlayoutpdf import Equation, Fraction, LayoutOverflowError
    from webpier.reporting import document, equations

    for block in (document.math_line(Fraction("a", "b"), block_id="tall"),
                  equations.equation_group(Equation("x", Fraction("a", "b")), block_id="tall")):
        with pytest.raises(LayoutOverflowError):
            document.report(block).layout()

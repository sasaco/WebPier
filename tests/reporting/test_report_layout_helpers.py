"""Generic report composition on GridLayoutPdf: fonts, point units, flow, tables, equations."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pymupdf
import pytest

APPEARANCE = Path(__file__).parents[1] / "fixtures" / "reporting" / "appearance" / "reference-style.json"


def native_signature(pdf: pymupdf.Document) -> list[tuple[Any, ...]]:
    return [(page.number, line["dir"], span["font"], span["size"], character["c"],
             tuple(character["origin"]), tuple(character["bbox"]))
            for page in pdf for block in page.get_text("rawdict")["blocks"]
            for line in block.get("lines", []) for span in line["spans"]
            for character in span["chars"]]


@pytest.fixture(scope="module")
def reference() -> dict[str, Any]:
    return json.loads(APPEARANCE.read_text("utf-8"))


def test_measured_point_units_are_exact_and_never_snap():
    from webpier.reporting import styles

    assert styles.grid_units(14.28) == 119
    assert styles.grid_units(14.52) == 121
    assert styles.grid_units(0) == 0
    for value in (0.01, -1, float("nan"), float("inf"), True, "1"):
        with pytest.raises(ValueError):
            styles.grid_units(value)
    with pytest.raises(ValueError, match="positive"):
        styles.grid_units(1.2, pitch=0)
    profile = styles.report_profile()
    assert (profile.width, profile.height) == (595, 842)
    assert (profile.grid.origin_x, profile.grid.origin_y) == (48, 86.28)


def test_fonts_are_explicit_real_faces_without_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from webpier.reporting import fonts

    registry = fonts.load_fonts()
    assert registry.resolve("body").path.name.lower() == "msmincho.ttc"
    assert registry.resolve("heading").path.name.lower() == "msgothic.ttc"
    assert (registry.resolve("body").face_index, registry.resolve("heading").face_index) == (0, 0)
    assert registry.resolve("symbol").face_index == 1
    assert registry.resolve("caption").face_index == 2
    assert set(fonts.font_files()) == {"body", "heading", "symbol", "caption", "dimension", "italic"}
    with pytest.raises(Exception, match="font"):
        fonts.load_fonts(tmp_path)
    monkeypatch.delenv("WINDIR")
    with pytest.raises(Exception, match="WINDIR"):
        fonts.font_files()


def test_leading_indentation_columns_spacer_and_no_page_number(tmp_path: Path):
    from gridlayoutpdf import LayoutContext, LayoutOverflowError, measure_block
    from webpier.reporting import document, fonts as font_module, styles

    fonts = font_module.load_fonts()
    block = document.paragraph("一行目\n二行目\n三行目", left=117, block_id="body")
    measured = measure_block(block, LayoutContext(fonts, styles.report_profile(), styles.REPORT_STYLE), 528)
    assert [part.rows * .12 for part in measured.parts] == pytest.approx([14.28] * 3)
    with pytest.raises(LayoutOverflowError, match="leading"):
        measure_block(document.paragraph("短すぎる", leading=4.8),
                      LayoutContext(fonts, styles.report_profile(), styles.REPORT_STYLE), 528)
    columns = document.columns(document.paragraph("左", left=48), document.paragraph("右", left=48),
                               widths=(48, 48), gap=14.52)
    path = document.report(block, document.spacer(28.56), columns, fonts=fonts).render(tmp_path / "leading.pdf")
    with pymupdf.open(path) as pdf:
        page = pdf[0]
        origins = {span["text"]: span["origin"] for block in page.get_text("dict")["blocks"]
                   for line in block.get("lines", []) for span in line["spans"]}
        # The reference's first baseline: 86.28 (top) + 11.52 (baseline offset).
        assert origins["一行目"] == pytest.approx((117, 97.80), abs=.01)
        assert origins["二行目"][1] - origins["一行目"][1] == pytest.approx(14.28, abs=.01)
        assert origins["左"][1] - origins["三行目"][1] == pytest.approx(42.84, abs=.01)
        assert origins["右"][0] - origins["左"][0] == pytest.approx(62.52, abs=.01)
        # The reference prints no page number: only the authored text is on the page.
        assert [line for line in page.get_text().splitlines() if line.strip()] == ["一行目", "二行目", "三行目", "左", "右"]


def test_repeated_header_follows_actual_pages(tmp_path: Path):
    from webpier.reporting import document

    title = "0610 線路方向荷重"
    path = document.report(document.paragraph("\n".join(f"本文{index:03}" for index in range(110))),
                           header=title).render(tmp_path / "header.pdf")
    with pymupdf.open(path) as pdf:
        assert len(pdf) >= 3
        for page in pdf:
            assert page.get_text().count(title) == 1
            header = next(span for block in page.get_text("dict")["blocks"]
                          for line in block.get("lines", []) for span in line["spans"] if span["text"] == title)
            # Two body leadings above the body origin: 86.28 - 28.56 + 11.52.
            assert header["origin"] == pytest.approx((48, 69.24), abs=.03)
    without = document.report(document.heading("見出し"), document.paragraph("本文")).layout()
    assert [command.text for command in without[0].commands if hasattr(command, "text")] == ["見出し", "本文"]


def test_overlay_keeps_the_exact_scene_and_rejects_drift(tmp_path: Path):
    from gridlayoutpdf import Line, Text
    from webpier.reporting import document, fonts as font_module

    fonts = font_module.load_fonts()
    pages = document.report(document.paragraph("照査値 12.3400 = 12.3400"), fonts=fonts).layout()
    overlaid = document.coarse_overlay(pages)
    document.validate_overlay(pages, overlaid)
    assert overlaid[0].commands[:len(pages[0].commands)] == pages[0].commands
    for axis in ("x", "y"):
        commands = list(overlaid[0].commands)
        index = next(index for index, command in enumerate(commands) if isinstance(command, Text))
        commands[index] = replace(commands[index], **{axis: getattr(commands[index], axis) + .12})
        with pytest.raises(ValueError, match="body scene"):
            document.validate_overlay(pages, (replace(overlaid[0], commands=tuple(commands)),))
    with pytest.raises(ValueError, match="page count"):
        document.validate_overlay(pages, ())
    with pytest.raises(ValueError, match="non-diagnostic"):
        document.validate_overlay(pages, pages)
    red = replace(overlaid[0], commands=(*pages[0].commands, Line(48, 72, 60, 72, .12, (1, 0, 0))))
    with pytest.raises(ValueError, match="non-diagnostic"):
        document.validate_overlay(pages, (red,))
    with pytest.raises(ValueError, match="step_x"):
        document.coarse_overlay(pages, step_x=0)
    artifacts = document.write_proof(pages, fonts, tmp_path)
    with pymupdf.open(artifacts.normal) as normal, pymupdf.open(artifacts.overlay) as overlay:
        assert native_signature(normal) == native_signature(overlay)
    assert artifacts.trace.is_file()
    assert len(list(tmp_path.glob("*.png"))) == 2 * len(pages)


def test_role_specific_row_heights_math_cells_and_vertical_label(tmp_path: Path, reference: dict[str, Any]):
    from gridlayoutpdf import Fraction, render_pdf
    from webpier.reporting import document, fonts as font_module, tables

    fonts = font_module.load_fonts()
    blocks = []
    for name, spec in reference["tables"].items():
        blocks.append(tables.table((144, 72), [[name, "12.3400"], ["ROW-2", "-0.5000"]],
                                   row_heights=spec["nominal_row_height_pt"], block_id=name))
        blocks.append(document.spacer())
    blocks.append(tables.table((36, 108), [[tables.cell(tables.VerticalLabel("作用"), rowspan=3), "上"],
                                          ["中"], ["下"]], row_heights=(14.28, 14.28, 14.28)))
    blocks.append(tables.table((72,), [[tables.math_cell(Fraction("1", "2"))]], row_heights=None))
    pages = document.report(*blocks, fonts=fonts).layout()
    path = tmp_path / "roles.pdf"
    render_pdf(pages, path, fonts)
    with pymupdf.open(path) as pdf:
        for name, spec in reference["tables"].items():
            page = next(page for page in pdf if name in page.get_text())
            first = page.search_for(name)[0]
            second = next(hit for hit in page.search_for("ROW-2") if hit.y0 > first.y0)
            assert second.y0 - first.y0 == pytest.approx(spec["nominal_row_height_pt"], abs=.02)
        assert any(entry[1] == (0.0, -1.0) and entry[4] in "作用" for entry in native_signature(pdf))


def test_equation_origins_match_independent_source_roles(tmp_path: Path, reference: dict[str, Any]):
    from gridlayoutpdf import Equation, EquationAnchors, EquationGroup
    from webpier.reporting import document, equations, styles

    roles = [(name, role) for name, role in reference["roles"].items() if "equals" in name]
    blocks = [equations.equation_group(Equation("a", "b", relation=role["source"]["sample"]["text"]),
                                      left=117, first_equal=role["source"]["sample"]["x"], block_id=name)
              for name, role in roles]
    blocks.append(equations.equation_group(Equation("x", "1+2", result="3", unit="m"), left=152.04,
                                           first_equal=184.44, second_equal=460.32, result_right=525.96,
                                           unit_start=530.4))
    path = document.report(*blocks).render(tmp_path / "source-equals.pdf")
    with pymupdf.open(path) as pdf:
        glyphs = [entry for entry in native_signature(pdf) if entry[4] in ("=", "＝")]
        assert len(glyphs) == len(roles) + 2
        for glyph, (_, role) in zip(glyphs, roles):
            assert abs(glyph[-2][0] - role["source"]["sample"]["x"]) <= .06
        assert abs(glyphs[-2][-2][0] - 184.44) <= .06 and abs(glyphs[-1][-2][0] - 460.32) <= .06
    # A relation center misused as the text origin is detectably off the source column.
    wrong = document.indent_to(EquationGroup(Equation("a", "b"), anchors=EquationAnchors(styles.grid_units(169.92 - 117)),
                                             style=styles.BODY), 117)
    with pymupdf.open(document.report(wrong).render(tmp_path / "wrong.pdf")) as pdf:
        origin = next(entry[-2][0] for entry in native_signature(pdf) if entry[4] == "=")
        assert abs(origin - reference["roles"]["foundation.symbolic_equals"]["source"]["sample"]["x"]) > .5


def test_scripts_use_measured_baseline_offsets(reference: dict[str, Any]):
    from gridlayoutpdf import Text
    from webpier.reporting import equations, fonts as font_module, styles

    fonts = font_module.load_fonts()
    for node, role in ((equations.script("m", superscript="2"), "common.superscript"),
                       (equations.script("I", subscript="B"), "common.subscript")):
        commands = [command for command in node.measure(fonts, styles.BODY).commands if isinstance(command, Text)]
        assert commands[1].style.size == pytest.approx(6.5)
        assert commands[1].y - commands[0].y == pytest.approx(reference["roles"][role]["baseline_delta_pt"], abs=.06)



def _body_baselines(*blocks: Any) -> list[float]:
    from gridlayoutpdf import Text
    from webpier.reporting import document

    page = document.report(*blocks).layout()[0]
    # Main 9.9 pt glyphs only; 6.5 pt scripts sit off the row baseline by design.
    return sorted({round(command.y, 2) for command in page.commands
                   if isinstance(command, Text) and command.style.size == pytest.approx(9.9)})


def test_equations_and_math_lines_advance_on_the_body_leading():
    from gridlayoutpdf import Equation
    from webpier.reporting import document, equations

    baselines = _body_baselines(
        equations.equation_group(
            Equation("x", "1+2", result="3", unit="m"),
            Equation("A", equations.script("m", superscript="2")),
            second_equal=460.32, result_right=525.96, unit_start=530.4),
        document.math_line("本文の一行"),
        document.math_line(equations.script("I", superscript="2")),
        document.paragraph("段落一\n段落二"),
    )
    # Body origin 86.28 + baseline offset 11.52, then one 14.28 pt row per printed line.
    assert baselines == pytest.approx([97.80 + 14.28 * row for row in range(6)], abs=.01)


def test_subscripted_lines_advance_on_the_body_leading():
    # A 6.5 pt subscript reaches 11.52 + 2.83 pt below the row top, 0.07 pt past
    # 14.28 pt; the 0.12 pt overhang keeps the row instead of growing it to 14.40 pt.
    from gridlayoutpdf import Equation
    from webpier.reporting import document, equations

    baselines = _body_baselines(
        equations.equation_group(Equation(equations.script("A", subscript="s"), "1")),
        document.math_line(equations.script("σ", subscript="c")),
        document.paragraph("段落"),
    )
    assert baselines == pytest.approx([97.80 + 14.28 * row for row in range(3)], abs=.01)


def test_a_line_taller_than_the_body_leading_is_an_overflow():
    # The leading is strict: a stacked fraction does not widen its row, it is an error.
    from gridlayoutpdf import Equation, Fraction, LayoutOverflowError
    from webpier.reporting import document, equations

    for block in (document.math_line(Fraction("a", "b"), block_id="tall"),
                  equations.equation_group(Equation("x", Fraction("a", "b")), block_id="tall")):
        with pytest.raises(LayoutOverflowError):
            document.report(block).layout()

"""Independent native-PDF proofs for the shared report composition layer."""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any, TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pymupdf


def api(name: str) -> ModuleType:
    return importlib.import_module(f"src.reporting.{name}")


def native_signature(pdf: pymupdf.Document) -> list[tuple[Any, ...]]:
    return [(page.number, line["dir"], span["font"], span["size"], character["c"],
             tuple(character["origin"]), tuple(character["bbox"]))
            for page in pdf for block in page.get_text("rawdict")["blocks"]
            for line in block.get("lines", []) for span in line["spans"]
            for character in span["chars"]]


def physical_frame_fixture(name: str, direction: str) -> tuple[dict, dict]:
    """Read the independent geometry matrix, without a production model builder."""
    from copy import deepcopy
    from dataclasses import asdict
    import json
    from src.reaction_inputs import parse_reaction_input

    root = Path(__file__).parents[1] / "fixtures"
    case = json.loads((root / "pier_models/expectations.json").read_text("utf-8"))["cases"][name]
    path = root / "pier_models" / case["input_fixture"] if case["input_fixture"] else root / "baseline_input.json"
    geometry = asdict(parse_reaction_input(json.loads(path.read_text("utf-8"))).geometry)
    for overrides in case["geometry_overrides"].values():
        geometry.update({key.lower(): value for key, value in overrides.items()})
    return geometry, deepcopy(case["directions"][direction])


def test_measured_point_units_are_exact_and_do_not_silently_round() -> None:
    styles = api("styles")
    assert styles.grid_units(14.28) == 119
    assert styles.grid_units(26.52) == 221
    assert styles.grid_units(14.52) == 121
    assert styles.grid_units(0) == 0
    for value in (0.01, -1, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            styles.grid_units(value)


def test_fonts_are_explicit_real_faces_with_no_cid_fallback(tmp_path: Path) -> None:
    fonts = api("fonts")
    registry = fonts.load_fonts()
    assert registry.resolve("body").face_index == 0
    assert registry.resolve("heading").face_index == 0
    assert registry.resolve("body").path.name.lower() == "msmincho.ttc"
    assert registry.resolve("heading").path.name.lower() == "msgothic.ttc"
    assert set(fonts.font_files()) == {"body", "heading", "symbol", "caption", "dimension", "italic"}
    assert registry.resolve("symbol").face_index == 1
    assert registry.resolve("caption").face_index == 2
    with pytest.raises(Exception, match="msmincho|font|Font|書体"):
        fonts.load_fonts(tmp_path)


def test_display_strings_and_legacy_numeric_precision_are_preserved() -> None:
    formatting = api("formatting")
    for value in ("-0.00", "12.3400", "", "-", "1.000E+03"):
        assert formatting.display(value) == value
    with pytest.raises(TypeError):
        formatting.display(12.34)
    assert formatting.number(None) == ""
    assert formatting.number(1234.567, 2, comma=True) == "1,234.57"
    assert formatting.number(-0.0, 2) == "-0.00"


def test_explicit_leading_indentation_columns_spacer_and_footer(tmp_path: Path) -> None:
    import pymupdf
    from gridlayoutpdf import LayoutContext, LayoutOverflowError, measure_block

    document, styles = api("document"), api("styles")
    fonts = api("fonts").load_fonts()
    profile = styles.report_profile()
    block = document.paragraph("一行目\n二行目\n三行目", left=117, block_id="body")
    measured = measure_block(block, LayoutContext(fonts, profile, styles.REPORT_STYLE), 528)
    assert [part.rows * .12 for part in measured.parts] == pytest.approx([14.28] * 3)
    with pytest.raises(LayoutOverflowError, match="leading"):
        measure_block(document.paragraph("短すぎる", leading=4.8),
                      LayoutContext(fonts, profile, styles.REPORT_STYLE), 528)
    columns = document.columns(document.paragraph("左", left=48),
                               document.paragraph("右", left=48), widths=(48, 48), gap=14.52)
    report = document.report(block, document.spacer(28.56), columns,
                             fonts=fonts, footer="{page} / {pages}")
    path = report.render(tmp_path / "leading.pdf")
    with pymupdf.open(path) as pdf:
        page = pdf[0]
        origins = {span["text"]: span["origin"] for block in page.get_text("dict")["blocks"]
                   for line in block.get("lines", []) for span in line["spans"]}
        assert origins["一行目"] == pytest.approx((117, 83.52), abs=.01)
        assert origins["二行目"][1] - origins["一行目"][1] == pytest.approx(14.28, abs=.01)
        assert origins["三行目"][1] - origins["二行目"][1] == pytest.approx(14.28, abs=.01)
        assert origins["左"][1] - origins["三行目"][1] == pytest.approx(42.84, abs=.01)
        assert origins["右"][0] - origins["左"][0] == pytest.approx(62.52, abs=.01)
        assert "1 / 1" in page.get_text()


def test_overlay_keeps_exact_native_scene_and_rejects_position_drift(tmp_path: Path) -> None:
    import pymupdf
    from gridlayoutpdf import Text

    document = api("document")
    fonts = api("fonts").load_fonts()
    pages = document.report(document.paragraph("照査値 12.3400 = 12.3400"), fonts=fonts).layout()
    overlaid = document.coarse_overlay(pages)
    document.validate_overlay(pages, overlaid)
    assert overlaid[0].commands[:len(pages[0].commands)] == pages[0].commands
    assert len(overlaid[0].commands) - len(pages[0].commands) < 120
    for axis in ("x", "y"):
        commands = list(overlaid[0].commands)
        index = next(index for index, command in enumerate(commands) if isinstance(command, Text))
        commands[index] = replace(commands[index], **{axis: getattr(commands[index], axis) + .12})
        with pytest.raises(ValueError, match="body|scene|本文"):
            document.validate_overlay(pages, (replace(overlaid[0], commands=tuple(commands)),))
    artifacts = document.write_proof(pages, fonts, tmp_path)
    with pymupdf.open(artifacts.normal) as normal, pymupdf.open(artifacts.overlay) as overlay:
        assert native_signature(normal) == native_signature(overlay)
        assert normal[0].get_text() == overlay[0].get_text()
    assert artifacts.trace.is_file()
    assert len(list(tmp_path.glob("*.png"))) == 2 * len(pages)


def test_dense_long_table_preserves_rows_headers_rowspan_and_order(tmp_path: Path) -> None:
    import pymupdf
    from gridlayoutpdf import Cell, LayoutContext, LayoutOverflowError, measure_block

    tables, styles, document = api("tables"), api("styles"), api("document")
    fonts = api("fonts").load_fonts()
    rows = [[tables.cell("区分", rowspan=2), tables.cell("荷重値", colspan=2, align="center")],
            [tables.cell("鉛直"), tables.cell("水平")]]
    for number in range(70):
        rows.append([tables.cell(f"CASE-{number:03}", rowspan=2), f"{number}.00", "-12.3400"])
        rows.append(["0.0000", "+0.5000"])
    table = tables.table((72, 72, 72), rows, row_heights=14.28, header_rows=2, block_id="long-table")
    pages = document.report(table, fonts=fonts).layout()
    assert len(pages) >= 3
    path = tmp_path / "long.pdf"
    from gridlayoutpdf import render_pdf
    render_pdf(pages, path, fonts)
    with pymupdf.open(path) as pdf:
        text = "".join(page.get_text() for page in pdf)
        for number in range(70):
            assert text.count(f"CASE-{number:03}") == 1
        assert [text.index(f"CASE-{number:03}") for number in range(70)] == sorted(
            text.index(f"CASE-{number:03}") for number in range(70))
        for page in pdf:
            assert page.get_text().count("区分") == 1
            assert page.get_text().count("荷重値") == 1
            assert page.get_text().count("-12.3400") == page.get_text().count("+0.5000")
            starts = [hit.y0 for hit in page.search_for("-12.3400")]
            assert all(b - a == pytest.approx(28.56, abs=.02) for a, b in zip(starts, starts[1:]))
            for span in [span for block in page.get_text("dict")["blocks"]
                         for line in block.get("lines", []) for span in line["spans"]]:
                assert span["color"] == 0
                assert span["size"] == pytest.approx(9.9, abs=.01)
    context = LayoutContext(fonts, styles.report_profile(), styles.REPORT_STYLE)
    with pytest.raises(LayoutOverflowError):
        measure_block(tables.table((72,), [["収まらない"]], row_heights=4.8), context, 528)
    huge = tables.table((72, 72), [[Cell("長い行群", rowspan=60), "値"],
                                  *[["値"] for _ in range(59)]], row_heights=14.28)
    with pytest.raises(LayoutOverflowError):
        document.report(huge, fonts=fonts).layout()


def test_formula_anchors_fraction_script_and_legal_long_wrap(tmp_path: Path) -> None:
    import pymupdf
    from gridlayoutpdf import Equation, Fraction, Operator, Row

    equations, document = api("equations"), api("document")
    fonts = api("fonts").load_fonts()
    group = equations.equation_group(
        Equation("A", Fraction(Row("12.3400", Operator("×"), "5.6700"), "2"),
                 result="34.9839", unit=equations.script("m", superscript="2")),
        Equation("Σ", Row(*[item for number in range(18)
                            for item in ((Operator("+") if number else ""), str(number))]),
                 result="153.0000", unit="kN"),
        left=117, first_equal=169.92, second_equal=402.24, result_right=460.32, unit_start=474.84,
        block_id="equations",
    )
    path = document.report(group, fonts=fonts).render(tmp_path / "equations.pdf")
    with pymupdf.open(path) as pdf:
        chars = [entry for entry in native_signature(pdf) if entry[4] == "="]
        origins = [entry[-2][0] for entry in chars]
        assert origins.count(pytest.approx(169.92, abs=.06)) == 2
        assert origins.count(pytest.approx(402.24, abs=.06)) == 2
        assert any(entry[4] == "2" and entry[3] == pytest.approx(6.5, abs=.01)
                   for entry in native_signature(pdf))
        text = "".join(page.get_text() for page in pdf)
        assert "34.9839" in text and "153.0000" in text
        assert len({entry[-2][1] for entry in native_signature(pdf) if entry[4] == "+"}) >= 2


def test_dynamic_figure_changes_geometry_and_rejects_unreadable_labels() -> None:
    from gridlayoutpdf import LayoutContext, LayoutOverflowError, Line, Text, measure_block

    figures, styles = api("figures"), api("styles")
    fonts = api("fonts").load_fonts()
    context = LayoutContext(fonts, styles.report_profile(), styles.REPORT_STYLE)
    first = figures.frame_diagram((figures.Node("1", 0, 0), figures.Node("2", 1, 2),
                                   figures.Node("3", 2, 0)), (("1", "2"), ("2", "3")))
    second = figures.frame_diagram((figures.Node("1", 0, 0), figures.Node("2", 1.5, 2),
                                    figures.Node("3", 2, 0)), (("1", "2"), ("2", "3")))
    a, b = (measure_block(figure, context, 528) for figure in (first, second))
    assert [command for command in a.commands if isinstance(command, Line)] != [
        command for command in b.commands if isinstance(command, Line)]
    assert {command.text for command in a.commands if isinstance(command, Text)} == {"1", "2", "3"}
    assert all(command.style.size == 9.9 and command.style.font == "heading"
               for command in a.commands if isinstance(command, Text))
    for bad in (float("inf"), float("nan")):
        with pytest.raises(ValueError):
            figures.Node("invalid", bad, 0)
    crowded = figures.frame_diagram(tuple(figures.Node(str(number), 0, 0) for number in range(50)), ())
    with pytest.raises(LayoutOverflowError, match="label"):
        measure_block(crowded, context, 528)
    extreme = figures.frame_diagram((figures.Node("a", -1e308, 0), figures.Node("b", 1e308, 0)), ())
    with pytest.raises(ValueError, match="range"):
        measure_block(extreme, context, 528)


def test_role_specific_row_heights_math_cells_and_native_vertical_label(tmp_path: Path) -> None:
    import json
    import pymupdf
    from gridlayoutpdf import Fraction, render_pdf

    tables, document = api("tables"), api("document")
    fonts = api("fonts").load_fonts()
    reference = json.loads((Path(__file__).parents[1] / "fixtures/reporting/appearance/reference-style.json").read_text("utf-8"))
    blocks = []
    for name, spec in reference["tables"].items():
        height = spec["nominal_row_height_pt"]
        blocks.append(tables.table((144, 72), [[name, "12.3400"], ["ROW-2", "-0.5000"]],
                                   row_heights=height, block_id=name))
        blocks.append(document.spacer())
    blocks.append(tables.table((36, 108), [[tables.cell(tables.VerticalLabel("作用"), rowspan=3), "上"],
                                          ["中"], ["下"]], row_heights=14.28))
    blocks.append(tables.table((72,), [[tables.math_cell(Fraction("1", "2"))]], row_heights=42.84))
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


def build_current_proofs(directory: Path) -> dict[str, dict[str, Any]]:
    """Build six QA PDFs from frozen WebPier results, without calling a calculator."""
    import copy
    import json
    import time
    from gridlayoutpdf import Equation, Fraction, Operator, Row

    document, tables = api("document"), api("tables")
    equations, figures, styles = api("equations"), api("figures"), api("styles")
    fixture = Path(__file__).parents[1] / "fixtures/reporting"
    reference = json.loads((fixture / "appearance/reference-style.json").read_text("utf-8"))
    results = {stage: json.loads((fixture / f"baseline/results/{stage}.json").read_text("utf-8"))
               for stage in ("0500", "0600", "0610")}
    original = copy.deepcopy(results)
    fonts = api("fonts").load_fonts()
    typography = []
    selected = ("foundation.chapter", "foundation.section", "foundation.body", "foundation.subsection",
                "common.chapter", "common.section", "common.body", "common.subsection", "common.subsubsection")
    for name in selected:
        role = reference["roles"][name]
        left = role["source"]["anchor_x_pt"] + role["relative_x_pt"]
        typography.append(document.paragraph(f"{name} 書式確認", left=left,
                                             style=styles.HEADING if role["font"] == "MS-Gothic" else styles.BODY))
    equal_roles = [(name, role) for name, role in reference["roles"].items() if "equals" in name]
    for name, role in equal_roles:
        typography.append(document.paragraph(name))
        typography.append(equations.equation_group(Equation("a", "b", relation=role["source"]["sample"]["text"]),
                                                   first_equal=role["source"]["sample"]["x"], block_id=name))
    soil_rows = [[tables.cell("地層", rowspan=2, style=styles.HEADING),
                  tables.cell("土質", rowspan=2, style=styles.HEADING),
                  tables.cell("層厚", rowspan=2, style=styles.HEADING),
                  tables.cell("単位重量", colspan=2, style=styles.HEADING, align="center"),
                  tables.cell("N値", rowspan=2, style=styles.HEADING)],
                 [tables.cell("湿潤", style=styles.HEADING), tables.cell("水中", style=styles.HEADING)]]
    for layer in results["0500"]["layers"]:
        values = (layer["name"], layer["soil_type"], "" if layer["thickness"] is None else f"{layer['thickness']:.3f}",
                  f"{layer['unit_weight_wet']:.1f}", f"{layer['unit_weight_submerged']:.1f}", f"{layer['n_value']:.1f}")
        soil_rows.append([tables.cell(value, style=styles.HEADING) for value in values])
    geometry = results["0500"]["foundation"]
    reaction = results["0600"]["train"]["girder"]["ultimate"]["single"]["RB"]
    properties = equations.equation_group(
        Equation("A", Row(f"{geometry['B']:.3f}", Operator("×"), f"{geometry['L']:.3f}"),
                 result=f"{geometry['area']:.3f}", unit=equations.script("m", superscript="2")),
        Equation("B", Fraction("A", "L"), result=f"{geometry['B']:.3f}", unit="m"),
        Equation(equations.script("I", subscript="B"),
                 Row(f"{reaction['train']:.4f}", Operator("×"), f"{reaction['coefficient']:.3f}"),
                 result=f"{reaction['impact']:.1f}", unit="kN"),
        left=123, first_equal=169.92, second_equal=460.32, result_right=518.4, unit_start=532.92,
    )
    frame = results["0610"]["frame"]
    diagram = figures.frame_diagram(tuple(figures.Node(str(node["id"]), node["x"], node["y"]) for node in frame["nodes"]),
                                    tuple((str(member["node_i"]), str(member["node_j"])) for member in frame["members"]))
    engineering = [document.heading("地盤・式・現在の骨組", left=93.96), document.spacer(),
                   document.indent_to(tables.table((84, 84, 84, 84, 84, 74.4), soil_rows,
                                                   row_heights=14.28, header_rows=2, block_id="soil"), 76.92),
                   document.spacer(), properties, document.spacer(), diagram]
    combination_rows = [[tables.cell("組合せ", rowspan=2), tables.cell("基本ケース", rowspan=2),
                         tables.cell("組合せ係数（組内のケース順）", colspan=4, align="center")],
                        ["1", "2", "3", "4"]]
    for start in range(0, len(results["0610"]["combinations"]), 4):
        group = results["0610"]["combinations"][start:start + 4]
        for index, case in enumerate(results["0610"]["basic_cases"]):
            prefix = [] if index else [tables.cell("\n".join(f"CASE-{combination['id']:02}" for combination in group),
                                                  rowspan=len(results["0610"]["basic_cases"]))]
            combination_rows.append([*prefix, f"{case['id']:02} {case['symbol']}",
                                     *[f"{combination['coefficients'][index]:g}" for combination in group]])
    combinations = [document.heading("作用組合せ"),
                    tables.table((72, 144, 72, 72, 72, 72), combination_rows, header_rows=2,
                                 row_heights=14.28, block_id="current-combinations")]
    output = {}
    for stem, blocks in (("typography", typography), ("engineering", engineering), ("long-table", combinations)):
        start = time.perf_counter()
        pages = document.report(*blocks, fonts=fonts).layout()
        artifacts = document.write_proof(pages, fonts, directory, stem=stem)
        output[stem] = {"pages": len(pages), "seconds": time.perf_counter() - start,
                        "normal": str(artifacts.normal), "overlay": str(artifacts.overlay),
                        "trace": str(artifacts.trace)}
    import pymupdf
    with pymupdf.open(output["typography"]["normal"]) as pdf:
        glyphs = [entry for entry in native_signature(pdf) if entry[4] in ("=", "＝")]
        output["typography"]["role_errors"] = [
            {"role": name, "source_x_pt": role["source"]["sample"]["x"], "actual_x_pt": glyph[-2][0],
             "error_pt": glyph[-2][0] - role["source"]["sample"]["x"]}
            for glyph, (name, role) in zip(glyphs, equal_roles, strict=True)]
    assert results == original
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "proof-summary.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def test_current_webpier_values_and_independent_reference_styles_in_full_proofs(tmp_path: Path) -> None:
    import json
    import pymupdf
    from reportlab.pdfbase.ttfonts import TTFont

    output = build_current_proofs(tmp_path)
    assert output["long-table"]["pages"] >= 2
    assert all(abs(item["error_pt"]) <= .06 for item in output["typography"]["role_errors"])
    for item in output.values():
        with pymupdf.open(item["normal"]) as normal, pymupdf.open(item["overlay"]) as overlay:
            assert native_signature(normal) == native_signature(overlay)
            assert all(page.get_images() == [] for page in normal)
    fixture = Path(__file__).parents[1] / "fixtures/reporting"
    reference = json.loads((fixture / "appearance/reference-style.json").read_text("utf-8"))
    fonts = api("fonts").load_fonts()
    font_faces = {TTFont(f"verify-{name}", str(face.path), subfontIndex=face.face_index).face.name.decode("ascii"): face
                  for name in ("body", "heading") for face in (fonts.resolve(name),)}
    with pymupdf.open(output["typography"]["normal"]) as pdf:
        spans = [span for page in pdf for block in page.get_text("dict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"]]
        for span in spans:
            name = span["text"].split(" ")[0]
            if name not in reference["roles"] or "equals" in name:
                continue
            role = reference["roles"][name]
            # GridLayoutPdf names embedded faces by SHA; MuPDF truncates span
            # names. Resolve that identity to the independently read TTC name.
            face = font_faces[role["font"]]
            assert len(span["font"]) >= 20 and face.pdf_name.startswith(span["font"])
            assert span["size"] == pytest.approx(role["size_pt"], abs=role["size_tolerance_pt"])
            assert span["origin"][0] == pytest.approx(role["source"]["anchor_x_pt"] + role["relative_x_pt"], abs=.02)
            assert span["color"] == 0
    with pymupdf.open(output["engineering"]["normal"]) as pdf:
        text = "".join(page.get_text() for page in pdf)
        for value in ("4.700", "63.000", "335.4067", "0.245", "82.2", "90.0"):
            assert value in text
        glyphs = [entry for entry in native_signature(pdf) if not entry[4].isspace()]
        for base, child, expected in (("m", "2", reference["roles"]["common.superscript"]["baseline_delta_pt"]),
                                      ("I", "B", reference["roles"]["common.subscript"]["baseline_delta_pt"])):
            pair = next((a, b) for a, b in zip(glyphs, glyphs[1:]) if a[4] == base and b[4] == child)
            assert pair[1][-2][1] - pair[0][-2][1] == pytest.approx(expected, abs=.06)
    current = json.loads((fixture / "baseline/results/0610.json").read_text("utf-8"))
    with pymupdf.open(output["long-table"]["normal"]) as pdf:
        for page in pdf:
            assert page.get_text().count("基本ケース") == 1
        for case_index, case in enumerate(current["basic_cases"]):
            hits = [(page, rect) for page in pdf
                    for rect in page.search_for(f"{case['id']:02} {case['symbol']}")]
            assert len(hits) == 4
            for group_index, (page, rect) in enumerate(hits):
                for column in range(4):
                    region = pymupdf.Rect(264 + column * 72, rect.y0 - .1,
                                          336 + column * 72, rect.y1 + .1)
                    assert page.get_text(clip=region).strip() == f"{current['combinations'][group_index * 4 + column]['coefficients'][case_index]:g}"
    assert len(list(tmp_path.glob("*.png"))) == 2 * sum(item["pages"] for item in output.values())


def test_equation_origins_match_independent_source_roles_and_center_misuse_fails(tmp_path: Path) -> None:
    import json
    import pymupdf
    from gridlayoutpdf import Equation, EquationAnchors, EquationGroup

    document, equations, styles = api("document"), api("equations"), api("styles")
    fixture = Path(__file__).parents[1] / "fixtures/reporting/appearance/reference-style.json"
    reference = json.loads(fixture.read_text("utf-8"))
    roles = [(name, role) for name, role in reference["roles"].items() if "equals" in name]
    blocks = [equations.equation_group(Equation("a", "b", relation=role["source"]["sample"]["text"]),
                                      left=117, first_equal=role["source"]["sample"]["x"], block_id=name)
              for name, role in roles]
    fonts = api("fonts").load_fonts()
    path = document.report(*blocks, fonts=fonts).render(tmp_path / "source-equals.pdf")
    with pymupdf.open(path) as pdf:
        glyphs = [entry for entry in native_signature(pdf) if entry[4] in ("=", "＝")]
        assert len(glyphs) == len(roles)
        for glyph, (_, role) in zip(glyphs, roles, strict=True):
            assert abs(glyph[-2][0] - role["source"]["sample"]["x"]) <= .06
    wrong = document.indent_to(EquationGroup(Equation("a", "b"),
                                             anchors=EquationAnchors(styles.grid_units(169.92 - 117)),
                                             style=styles.BODY), 117)
    path = document.report(wrong, fonts=fonts).render(tmp_path / "wrong-center.pdf")
    with pymupdf.open(path) as pdf:
        origin = next(entry[-2][0] for entry in native_signature(pdf) if entry[4] == "=")
        assert abs(origin - reference["roles"]["foundation.symbolic_equals"]["source"]["sample"]["x"]) > .5


def test_script_uses_measured_reference_baseline_offsets() -> None:
    import json
    from gridlayoutpdf import Text

    equations, styles = api("equations"), api("styles")
    fonts = api("fonts").load_fonts()
    reference = json.loads((Path(__file__).parents[1] / "fixtures/reporting/appearance/reference-style.json").read_text("utf-8"))
    for node, expected in ((equations.script("m", superscript="2"), reference["roles"]["common.superscript"]["baseline_delta_pt"]),
                           (equations.script("I", subscript="B"), reference["roles"]["common.subscript"]["baseline_delta_pt"])):
        commands = [command for command in node.measure(fonts, styles.BODY).commands if isinstance(command, Text)]
        assert commands[1].style.size == pytest.approx(6.5)
        assert commands[1].y - commands[0].y == pytest.approx(expected, abs=.06)


@pytest.mark.parametrize("name", ("default", "parapet_asymmetric", "parapet_tiny_eccentric", "h2_h3_zero"))
@pytest.mark.parametrize("direction", ("b", "w"))
@pytest.mark.parametrize("aspect", ((1, 1), (100, .01), (.01, 100)))
def test_native_physical_frame_keeps_graph_and_readable_annotations(name: str, direction: str,
                                                                  aspect: tuple[float, float]) -> None:
    import copy
    import math
    from gridlayoutpdf import LayoutContext, Line, Text, command_bounds, measure_block
    geometry, expected = physical_frame_fixture(name, direction)
    horizontal, vertical = aspect
    geometry = {key: value * (horizontal if key.startswith(("b", "w")) else vertical)
                for key, value in geometry.items()}
    frame = copy.deepcopy(expected)
    for node in frame["nodes"]:
        node["x"] *= horizontal
        node["y"] *= vertical
    frame["nodes"].reverse()
    frame["members"].reverse()
    snapshot = copy.deepcopy((geometry, frame))
    fonts, styles = api("fonts").load_fonts(), api("styles")
    context = LayoutContext(fonts, styles.report_profile(), styles.REPORT_STYLE)
    block = api("figures").physical_frame(geometry, frame, direction)
    measured = measure_block(block, context, 528)
    assert (geometry, frame) == snapshot
    assert all(getattr(command, "color", (0, 0, 0)) in ((0, 0, 0), (1, 1, 1)) for command in measured.commands)
    members = [command for command in measured.commands if isinstance(command, Line) and command.width in (.8, 1.6)]
    assert len(members) == len(frame["members"])
    nodes = {node["id"]: node for node in frame["nodes"]}
    segments = []
    for command, member in zip(members, frame["members"], strict=True):
        first, second = nodes[member["node_i"]], nodes[member["node_j"]]
        dx, dy = second["x"] - first["x"], second["y"] - first["y"]
        drawn_dx, drawn_dy = command.x2 - command.x1, command.y1 - command.y2
        segments.append((dx, dy, drawn_dx, drawn_dy, command))
        assert command.width == (1.6 if member["behavior"] == "rigid" else .8)
    longest = max(segments, key=lambda item: math.hypot(item[0], item[1]))
    scale = math.hypot(longest[2], longest[3]) / math.hypot(longest[0], longest[1])
    for dx, dy, drawn_dx, drawn_dy, command in segments:
        tolerance = 4 * max(math.ulp(value) for value in (command.x1, command.y1, command.x2, command.y2))
        assert drawn_dx == pytest.approx(dx * scale, abs=tolerance)
        assert drawn_dy == pytest.approx(dy * scale, abs=tolerance)
        if math.hypot(dx, dy) * scale > tolerance:
            assert math.hypot(drawn_dx, drawn_dy) > 0
    labels = [command for command in measured.commands if isinstance(command, Text)]
    assert len([label for label in labels if label.style.size == 9.9 and label.quarter_turns == 0]) == len(nodes)
    assert len([label for label in labels if label.style.size == 8]) == len(members)
    boxes = [command_bounds(label, fonts) for label in labels]
    assert all(box.x >= 0 and box.y >= 0 and box.right <= 528 and box.bottom <= 432 for box in boxes)
    for i, first in enumerate(boxes):
        assert all(first.right <= second.x or second.right <= first.x or first.bottom <= second.y or second.bottom <= first.y
                   for second in boxes[i + 1:])


def test_native_physical_frame_rejects_too_small_fit_without_shrinking() -> None:
    from gridlayoutpdf import LayoutContext, measure_block
    geometry, frame = physical_frame_fixture("parapet_asymmetric", "b")
    fonts, styles = api("fonts").load_fonts(), api("styles")
    context = LayoutContext(fonts, styles.report_profile(), styles.REPORT_STYLE)
    with pytest.raises(ValueError, match="readable|fit"):
        measure_block(api("figures").physical_frame(geometry, frame, "b", width=96, height=96), context, 528)


def test_repeated_document_header_and_chapter_footer_follow_actual_pages(tmp_path: Path) -> None:
    import pymupdf

    document = api("document")
    title = "0610 線路方向荷重"
    path = document.report(document.paragraph("\n".join(f"本文{index:03}" for index in range(110))),
                           header=title, footer="8-{page}").render(tmp_path / "header.pdf")
    with pymupdf.open(path) as pdf:
        assert len(pdf) >= 3
        for index, page in enumerate(pdf, 1):
            assert page.get_text().count(title) == 1
            assert page.get_text().count(f"8-{index}") == 1
            spans = [span for block in page.get_text("dict")["blocks"]
                     for line in block.get("lines", []) for span in line["spans"]]
            header = next(span for span in spans if span["text"] == title)
            assert header["origin"] == pytest.approx((48, 54.96), abs=.03)
            assert header["size"] == pytest.approx(9.9, abs=.01)


@pytest.mark.parametrize("direction", ("b", "w"))
def test_native_physical_frame_keeps_vector_layers_and_opaque_node_backing(
        tmp_path: Path, direction: str) -> None:
    import math
    import pymupdf
    from gridlayoutpdf import Circle, Line, Rectangle, Text, render_pdf

    geometry, frame = physical_frame_fixture("parapet_asymmetric", direction)
    document = api("document").report(api("figures").physical_frame(geometry, frame, direction), footer=None)
    pages = document.layout()
    commands = pages[0].commands
    first_white = next(index for index, command in enumerate(commands)
                       if isinstance(command, Rectangle) and command.fill == (1, 1, 1))
    outlines = commands[:first_white]
    assert outlines and all(isinstance(command, Line) and command.width == .35 and command.dash == (2, 2)
                            and command.color == (0, 0, 0) for command in outlines)
    assert all(math.hypot(command.x2 - command.x1, command.y2 - command.y1) > 0 for command in outlines)
    disks = [command for command in commands if isinstance(command, Circle)]
    assert len(disks) == len(frame["nodes"])
    assert all(disk.fill == (0, 0, 0) and not disk.stroke and disk.radius == 1.7 for disk in disks)
    members = [index for index, command in enumerate(commands)
               if isinstance(command, Line) and command.width in (.8, 1.6)]
    assert len(members) == len(frame["members"])
    assert first_white < min(members) < next(index for index, command in enumerate(commands) if isinstance(command, Text))
    path = tmp_path / f"native-vector-layers-{direction}.pdf"
    render_pdf(pages, path, document.fonts)
    with pymupdf.open(path) as pdf:
        page = pdf[0]
        assert not page.get_images()
        drawings = page.get_drawings()
        for drawing in drawings[:len(outlines)]:
            assert drawing["type"] == "s" and drawing["fill"] is None
            assert drawing["color"] == (0, 0, 0) and drawing["width"] == pytest.approx(.35)
            assert drawing["stroke_opacity"] == 1 and drawing["dashes"] == "[ 2 2 ] 0"
        model = [drawing for drawing in drawings
                 if drawing["width"] == pytest.approx(.8) or drawing["width"] == pytest.approx(1.6)]
        assert len(model) == len(frame["members"])
        first_model = min(drawing["seqno"] for drawing in model)
        masks = [drawing for drawing in drawings if drawing["fill"] == (1, 1, 1)
                 and len(outlines) <= drawing["seqno"] < first_model]
        assert masks and all(drawing["type"] == "f" and drawing["fill_opacity"] == 1 for drawing in masks)
        nodes = [drawing for drawing in drawings if drawing["fill"] == (0, 0, 0) and drawing["type"] == "f"]
        assert len(nodes) == len(frame["nodes"]) and all(first_model < node["seqno"] for node in nodes)
        labels = [span for span in page.get_texttrace() if span["dir"] == (1, 0)
                  and span["size"] == pytest.approx(9.9)]
        assert len(labels) == len(frame["nodes"])
        for label in labels:
            left, top, right, bottom = label["bbox"]
            assert any(drawing["rect"].x0 <= left and drawing["rect"].x1 >= right
                       and drawing["rect"].y0 <= top and drawing["rect"].y1 >= bottom for drawing in masks)
            assert first_model < label["seqno"]


def test_native_frame_metric_failure_does_not_mutate_layout_or_later_measurement(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from copy import deepcopy
    from gridlayoutpdf import LayoutContext, TextMetrics, TextStyle, measure_block

    geometry, frame = physical_frame_fixture("parapet_asymmetric", "w")
    block = api("figures").physical_frame(geometry, frame, "w")
    snapshot = deepcopy((geometry, frame, block.geometry, block.frame))
    styles, fonts = api("styles"), api("fonts").load_fonts()
    context = LayoutContext(fonts, styles.report_profile(), styles.REPORT_STYLE)
    expected = measure_block(block, context, 528)
    measure = fonts.measure
    calls: list[str] = []

    def failing(text: str, style: TextStyle) -> TextMetrics:
        calls.append(text)
        if "." in text:
            raise RuntimeError("dimension measurement failed")
        return measure(text, style)

    with monkeypatch.context() as patch:
        patch.setattr(fonts, "measure", failing)
        with pytest.raises(RuntimeError, match="dimension measurement failed"):
            measure_block(block, context, 528)
    assert calls
    assert (geometry, frame, block.geometry, block.frame) == snapshot
    assert measure_block(block, context, 528) == expected
    assert context.profile == styles.report_profile() and context.style == styles.REPORT_STYLE


@pytest.mark.parametrize("name,direction", (("default", "b"), ("parapet_asymmetric", "w")))
def test_native_dimension_strings_have_readable_separation_in_actual_pdf(
        tmp_path: Path, name: str, direction: str) -> None:
    import pymupdf

    geometry, frame = physical_frame_fixture(name, direction)
    path = api("document").report(api("figures").physical_frame(geometry, frame, direction),
                                   footer=None).render(tmp_path / f"dimension-gap-{name}.pdf")
    with pymupdf.open(path) as pdf:
        dimensions = [span for span in pdf[0].get_texttrace() if span["dir"] == (0, -1)]
        values = ["".join(chr(char[0]) for char in span["chars"]) for span in dimensions]
        assert "1.175" in values and "0.225" in values
        for first in dimensions:
            for second in dimensions:
                a, b = first["bbox"], second["bbox"]
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[1]:
                    assert b[1] - a[3] >= 8 - .002

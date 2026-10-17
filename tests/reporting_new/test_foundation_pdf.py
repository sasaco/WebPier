"""0500 PDF: the drawn text is the manuscript, bytes are deterministic, appearance meets the reference."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from gridlayoutpdf import Equation, Fraction, Literal, Root, Row, Script, Text

from foundation_report_cases import CASES, case
from webpier.inputs.model import Soil
from webpier.reporting.stages.foundation import FOOTER, build_foundation, content, render_foundation

ROOT = Path(__file__).parents[2]
APPEARANCE = ROOT / "tests" / "fixtures" / "reporting" / "appearance" / "reference-style.json"
_spec = importlib.util.spec_from_file_location("reporting_appearance_measure", ROOT / "scripts" / "reporting_appearance.py")
assert _spec is not None and _spec.loader is not None
measure = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = measure
_spec.loader.exec_module(measure)

FOOTER_PREFIX = FOOTER.split("{")[0]


def drawn(value: Any) -> str:
    """What a node draws as text: fraction bars and radicals are strokes, not characters."""
    if isinstance(value, str):
        return value
    if isinstance(value, Literal):
        return value.text
    if isinstance(value, Row):
        return "".join(drawn(item) for item in value.items)
    if isinstance(value, Script):
        return drawn(value.base) + drawn(value.subscript or "") + drawn(value.superscript or "")
    if isinstance(value, Fraction):
        return drawn(value.numerator) + drawn(value.denominator)
    if isinstance(value, Root):
        return drawn(value.body)
    if isinstance(value, Equation):
        result = "" if value.result is None else value.result_relation + drawn(value.result)
        return drawn(value.lhs) + value.relation + drawn(value.rhs) + result + drawn(value.unit or "")
    if isinstance(value, tuple):
        return "".join(drawn(item) for item in value)
    raise TypeError(type(value).__name__)


def squeeze(text: str) -> str:
    return re.sub(r"\s+", "", text)


def expected_drawing(result, pier, embedment) -> str:
    parts = []
    for unit in content(result, pier, embedment):
        if unit.key == "soil.header":
            # The second header row (湿潤・水中) is drawn after the first row.
            first = tuple(value if index != 4 else value[0] for index, value in enumerate(unit.value))
            parts.append(drawn(first) + drawn(unit.value[4][1:]))
        else:
            parts.append(drawn(unit.value))
    return squeeze("".join(parts))


def scene_texts(pages) -> list[str]:
    return [command.text for page in pages for command in page.commands
            if isinstance(command, Text) and not command.text.startswith(FOOTER_PREFIX)]


@pytest.mark.parametrize("name", list(CASES))
def test_the_scene_draws_every_record_in_order_and_the_pdf_has_the_same_text(tmp_path: Path, name: str):
    result, pier, embedment = case(name)
    document = build_foundation(result, pier, embedment)
    pages = document.layout()
    assert squeeze("".join(scene_texts(pages))) == expected_drawing(result, pier, embedment)
    path = render_foundation(result, pier, embedment, tmp_path / "0500.pdf")
    with pymupdf.open(path) as pdf:
        assert len(pdf) == len(pages)
        for number, (page, scene) in enumerate(zip(pdf, pages), 1):
            pdf_chars = Counter(squeeze(page.get_text()))
            scene_chars = Counter(squeeze("".join(command.text for command in scene.commands if isinstance(command, Text))))
            assert pdf_chars == scene_chars
            assert f"5 - {number}" in page.get_text()
            assert not page.get_images()


def test_same_input_gives_the_same_bytes_in_this_and_another_process(tmp_path: Path):
    first = render_foundation(*case("current"), tmp_path / "a.pdf").read_bytes()
    second = render_foundation(*case("current"), tmp_path / "b.pdf").read_bytes()
    assert first == second
    assert b"CreationDate" not in first or b"D:20000101000000" in first
    script = ("import sys; sys.path[:0] = [sys.argv[2], sys.argv[3]]\n"
              "from foundation_report_cases import case\n"
              "from webpier.reporting.stages.foundation import render_foundation\n"
              "render_foundation(*case('current'), sys.argv[1])\n")
    other = tmp_path / "c.pdf"
    subprocess.run([sys.executable, "-X", "utf8", "-c", script, str(other), str(Path(__file__).parent), str(ROOT)],
                   check=True, cwd=tmp_path)
    assert other.read_bytes() == first
    assert render_foundation(*case("clay"), tmp_path / "d.pdf").read_bytes() != first


def test_render_replaces_the_target_only_after_a_complete_layout(tmp_path: Path):
    from gridlayoutpdf import LayoutError
    from webpier.core.printed import Printed

    result, pier, embedment = case("current")
    huge = replace(pier.soil.layers[1], deformation_modulus=Printed(1e100, 0, "kN/m2"))
    pier = replace(pier, soil=Soil((pier.soil.layers[0], huge)))
    path = tmp_path / "previous.pdf"
    path.write_bytes(b"previous-published-bytes")
    with pytest.raises(LayoutError):
        render_foundation(result, pier, embedment, path)
    assert path.read_bytes() == b"previous-published-bytes"


def test_a_long_soil_table_keeps_every_row_across_pages(tmp_path: Path):
    result, pier, embedment = case("current")
    template = pier.soil.layers[1]
    layers = (pier.soil.layers[0], *(replace(template, name=f"層{index:03d}") for index in range(60)))
    layers = (*layers[:30], replace(layers[30], soil_type="砂質土と粘性土の互層を含む区分"), *layers[31:])
    path = render_foundation(result, replace(pier, soil=Soil(layers)), embedment, tmp_path / "long.pdf")
    with pymupdf.open(path) as pdf:
        text = "".join(page.get_text() for page in pdf)
        assert len(pdf) > 3
        assert all(text.count(f"層{index:03d}") == 1 for index in range(60))
        assert "砂質土と粘性土の互層を含む区分" in text.replace("\n", "")


def test_long_names_wrap_without_shrinking_and_labels_stay_with_their_equations(tmp_path: Path):
    result, pier, embedment = case("current")
    name, soil_type = "長い地層名称と砂礫を含む地層", "砂質土と粘性土の互層を含む区分"
    surface = replace(pier.soil.layers[0], name=name, soil_type=soil_type)
    path = render_foundation(result, replace(pier, soil=Soil((surface, pier.soil.layers[1]))), embedment, tmp_path / "names.pdf")
    with pymupdf.open(path) as pdf:
        text = "".join(page.get_text() for page in pdf).replace("\n", "")
        assert text.count(name) == 1 and text.count(soil_type) == 1
        for page in pdf:
            body = [line.strip() for line in page.get_text().splitlines()
                    if line.strip() and not line.startswith(FOOTER_PREFIX)]
            assert body[-1] not in ("・長期", "・短期")
            for direction, label in (("Kr_longitudinal", "線路方向"), ("Kr_transverse", "線路直角方向")):
                if label in page.get_text():
                    # The direction's subsection, Iv to the short-term Kr, is on one page.
                    assert f"{getattr(result.short_term, direction).value:,.0f}" in page.get_text().replace(" ", "")
        spans = [span for page in pdf for block in page.get_text("dict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"] if span["text"] and span["text"] in name]
        assert spans and all(span["size"] == pytest.approx(9.9, abs=.1) for span in spans)


ROLES = ("chapter", "section", "body", "subsection", "subsubsection", "table_header", "table_header_compressive",
         "table_value", "symbolic_equals", "substitution_equals", "result_equals")


def test_typography_and_soil_table_match_the_independent_reference_roles(tmp_path: Path):
    from reportlab.pdfbase.ttfonts import TTFont

    result, pier, embedment = case("current")
    reference = json.loads(APPEARANCE.read_text(encoding="utf-8"))
    document = build_foundation(result, pier, embedment)
    path = document.render(tmp_path / "appearance.pdf", invariant=True)
    faces = {TTFont(f"verify-{name}", str(face.path), subfontIndex=face.face_index).face.name.decode("ascii"): face
             for name in ("body", "heading") for face in (document.fonts.resolve(name),)}
    with pymupdf.open(path) as pdf:
        samples = [sample for page in pdf for sample in measure.text_samples(page)]
        for role_name in ROLES:
            role = reference["roles"]["foundation." + role_name]
            selector = role["source"]["selector_exact_text"]
            if role_name == "table_value":
                selector = "4.700"  # the surface thickness of this input; the reference printed 4.000
            matches = [sample for sample in samples if sample.text.startswith(selector)]
            if "equals" in role_name:
                matches = [sample for sample in matches if abs(sample.x - role["source"]["selector_x_pt"]) < .5]
            assert matches, role_name
            sample = matches[0]
            face = faces[role["font"]]
            assert len(sample.font) >= 20 and face.pdf_name.startswith(sample.font)
            assert measure.role_errors(replace(sample, font=role["font"]), role, anchor_x=93.96) == [], role_name
        # Negative checks: the 8.9 pt caption is that one measured role only.
        header = next(sample for sample in samples if sample.text == "層番")
        assert measure.role_errors(replace(header, font="MS-Gothic", size=8.9), reference["roles"]["foundation.table_header"])
        compressive = next(sample for sample in samples if sample.text == "一軸圧縮強度")
        assert measure.role_errors(replace(compressive, font="MS-Gothic", size=9.9),
                                   reference["roles"]["foundation.table_header_compressive"])
        unit = next(sample for sample in samples if sample.text == "qu(kN/m")
        assert unit.size == pytest.approx(9.9, abs=.1)
        exponent = next(sample for sample in samples if sample.text == "2" and sample.page == unit.page
                        and abs(sample.baseline - unit.baseline + 4.92) < .06 and 0 < sample.x - unit.x < 50)
        assert exponent.size == pytest.approx(6.5, abs=.1)
        rules = measure.native_rules(pdf[0])
        vertical = [rule for rule in rules if rule.axis == "v" and abs(rule.coordinate - 76.92) <= .5]
        assert vertical
        bands = [band for band in measure.painted_rule_bands(rules, axis="h", crossing=310)
                 if min(rule.start for rule in vertical) - .5 <= band.coordinate <= max(rule.end for rule in vertical) + .5]
        contract = reference["tables"]["foundation.soil"]
        rows = 2 + len(pier.soil.layers)
        assert measure.table_errors([band.coordinate for band in bands], [contract["nominal_row_height_pt"]] * rows) == []
        assert {round(rule.width, 2) for rule in rules if rule.axis == "v"} == {0.12, 0.96}
        assert bands[0].width == pytest.approx(contract["thick_rule_pt"], abs=.001)
        assert bands[-1].width == pytest.approx(contract["thick_rule_pt"], abs=.001)
        assert bands[1].width == pytest.approx(contract["thin_rule_pt"], abs=.001)
        # The public Table draws shared row-part boundaries separately: a 0.24 pt union,
        # reported as is and never claimed equal to the reference's single 0.12 pt rule.
        assert all(band.width == pytest.approx(2 * contract["thin_rule_pt"], abs=.001) for band in bands[2:-1])
        assert all(measure.monochrome_errors(page) == [] for page in pdf)


def test_scripts_sit_at_the_measured_offsets_in_the_kv_equations(tmp_path: Path):
    reference = json.loads(APPEARANCE.read_text(encoding="utf-8"))["roles"]
    path = render_foundation(*case("current"), tmp_path / "scripts.pdf")
    with pymupdf.open(path) as pdf:
        chars = [(char["c"], char["origin"], span["size"]) for block in pdf[0].get_text("rawdict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"] for char in span["chars"]
                 if not char["c"].isspace()]
    # The first symbolic equation: k with subscript v, ..., B with subscript v and superscript -1/2.
    index = next(index for index, (c, _, size) in enumerate(chars)
                 if c == "k" and size > 8 and chars[index + 1][0] == "v" and chars[index + 1][2] < 8)
    main, subscript = chars[index][1], chars[index + 1][1]
    superscript = next(origin for c, origin, size in chars[index:] if c == "-" and size < 8)
    assert subscript[1] - main[1] == pytest.approx(reference["common.subscript"]["baseline_delta_pt"], abs=.06)
    assert superscript[1] - main[1] == pytest.approx(reference["common.superscript"]["baseline_delta_pt"], abs=.06)

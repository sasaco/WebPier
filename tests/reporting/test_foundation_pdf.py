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
from gridlayoutpdf import Equation, Literal, Root, Row, Script, TermStop, Text

from foundation_report_cases import CASES, case
from webpier.inputs.model import Soil
from webpier.reporting.equations import Definition
from webpier.reporting.stages.foundation import build_foundation, content, render_foundation

ROOT = Path(__file__).parents[2]
APPEARANCE = ROOT / "tests" / "fixtures" / "reporting" / "appearance" / "reference-style.json"
_spec = importlib.util.spec_from_file_location("reporting_appearance_measure", ROOT / "scripts" / "reporting_appearance.py")
assert _spec is not None and _spec.loader is not None
measure = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = measure
_spec.loader.exec_module(measure)

PAGE_NUMBER = re.compile(r"^\d+ - \d+$", re.MULTILINE)  # the reference prints no page numbers


def drawn(value: Any) -> str:
    """What a node draws as text: radicals are strokes and term columns spaces, not characters."""
    if isinstance(value, str):
        return value
    if isinstance(value, TermStop):
        return ""
    if isinstance(value, Literal):
        return value.text
    if isinstance(value, Row):
        return "".join(drawn(item) for item in value.items)
    if isinstance(value, Script):
        return drawn(value.base) + drawn(value.subscript or "") + drawn(value.superscript or "")
    if isinstance(value, Root):
        return drawn(value.body)
    if isinstance(value, Equation):
        result = "" if value.result is None else value.result_relation + drawn(value.result)
        return drawn(value.lhs) + value.relation + drawn(value.rhs) + result + drawn(value.unit or "")
    if isinstance(value, Definition):
        result = "" if value.value is None else "(=" + drawn(value.value) + drawn(value.unit or "") + ")"
        return drawn(value.symbol) + "：" + drawn(value.text) + result
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
            parts.append(unit.lead + drawn(unit.value))
    return squeeze("".join(parts))


def scene_texts(pages) -> list[str]:
    return [command.text for page in pages for command in page.commands
            if isinstance(command, Text)]


@pytest.mark.parametrize("name", list(CASES))
def test_the_scene_draws_every_record_in_order_and_the_pdf_has_the_same_text(tmp_path: Path, name: str):
    result, pier, embedment = case(name)
    document = build_foundation(result, pier, embedment)
    pages = document.layout()
    assert squeeze("".join(scene_texts(pages))) == expected_drawing(result, pier, embedment)
    path = render_foundation(result, pier, embedment, tmp_path / "0500.pdf")
    with pymupdf.open(path) as pdf:
        assert len(pdf) == len(pages)
        for page, scene in zip(pdf, pages):
            pdf_chars = Counter(squeeze(page.get_text()))
            scene_chars = Counter(squeeze("".join(command.text for command in scene.commands if isinstance(command, Text))))
            assert pdf_chars == scene_chars
            assert not PAGE_NUMBER.search(page.get_text())
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
                    if line.strip()]
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


def _rows(page) -> list[list[dict]]:
    """The 9.9 pt spans of *page* by baseline, left to right (scripts left out)."""
    rows: dict[float, list[dict]] = {}
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["size"] > 8 and span["text"].strip():
                    rows.setdefault(round(span["origin"][1], 2), []).append(span)
    return [sorted(spans, key=lambda span: span["origin"][0]) for _, spans in sorted(rows.items())]


def _substitution_terms(path: Path) -> list[list[dict]]:
    """The right-hand terms of each substitution: between the "=" at 184.44 and the result's "=" at 460.32."""
    found = []
    with pymupdf.open(path) as pdf:
        for page in pdf:
            for spans in _rows(page):
                equals = [span for span in spans if span["text"].strip() == "="]
                if (len(equals) >= 2 and abs(equals[0]["origin"][0] - 184.44) < .1
                        and abs(equals[-1]["origin"][0] - 460.32) < .1):
                    found.append([span for span in spans
                                  if equals[0]["bbox"][2] < span["origin"][0] < equals[-1]["origin"][0]])
    return found


@pytest.mark.parametrize("name", list(CASES))
def test_the_terms_of_one_family_stand_in_the_same_columns(tmp_path: Path, name: str):
    """kv, Kv, ks, Ks, Iv and Kr: each number ends, and each operator is centred, in one column for
    the long- and short-term (and both directions') equations, though labels and blank lines part them."""
    from foundation_report_cases import text

    result, pier, embedment = case(name)
    lines = _substitution_terms(render_foundation(result, pier, embedment, tmp_path / "terms.pdf"))
    springs = (result.long_term, result.short_term)
    kv = {text(values.kv) for values in springs}
    inertia = {text(result.inertia_longitudinal), text(result.inertia_transverse)}

    def first(line: list[dict]) -> str:
        return line[0]["text"].strip()

    families = {
        "kv": [line for line in lines if len(line) == 7 and first(line) == text(result.coefficient)],
        "Kv": [line for line in lines if len(line) == 3 and first(line) in kv and line[2]["text"] == text(result.area)],
        "ks": [line for line in lines if first(line) == result.shear_ratio_text],
        "Ks": [line for line in lines if len(line) == 3 and first(line) in {text(values.ks) for values in springs}
               and line[2]["text"] == text(result.area)],
        "Iv": [line for line in lines if len(line) == 5 and line[-1]["text"] == "12"],
        "Kr": [line for line in lines if len(line) == 3 and first(line) in kv and line[2]["text"] in inertia],
    }
    assert {family: len(found) for family, found in families.items()} == {
        "kv": 2, "Kv": 2, "ks": 2, "Ks": 2, "Iv": 2, "Kr": 4}
    for family, found in families.items():
        for column in range(len(found[0])):
            spans = [line[column] for line in found]
            if column % 2:   # an operator: centred
                centres = [(span["bbox"][0] + span["bbox"][2]) / 2 for span in spans]
                assert centres == pytest.approx([centres[0]] * len(spans), abs=.01), (family, column)
            else:            # a number: right-aligned
                rights = [span["bbox"][2] for span in spans]
                assert rights == pytest.approx([rights[0]] * len(spans), abs=.01), (family, column)


@pytest.mark.parametrize("name", list(CASES))
def test_every_definition_puts_its_colon_in_one_column(tmp_path: Path, name: str):
    """Reference p1/p2: the "：" of every "ここに、" list at 210.96; "ここに、" opens each list once."""
    result, pier, embedment = case(name)
    units = content(result, pier, embedment)
    path = render_foundation(result, pier, embedment, tmp_path / "definitions.pdf")
    colons, labels = [], 0
    with pymupdf.open(path) as pdf:
        for page in pdf:
            labels += page.get_text().count("ここに、")
            for block in page.get_text("rawdict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        chars = span["chars"]
                        colons.extend(char["origin"][0] for previous, char in zip(chars, chars[1:])
                                      if char["c"] == "：" and previous["c"].isspace())
    assert len(colons) == sum(unit.kind == "definition" for unit in units)
    assert colons == pytest.approx([210.96] * len(colons), abs=.06)
    assert labels == sum(unit.lead == "ここに、" for unit in units)

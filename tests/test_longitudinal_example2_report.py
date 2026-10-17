"""0610 public report contracts, including the physical 20 by 16 matrix grid."""

import builtins
from copy import deepcopy
from dataclasses import replace
import importlib
import io
import json
from pathlib import Path
import re
import unicodedata

import fitz
import pytest

from src.calculator import calculate as calculate_foundation
from src.inputs import parse_input
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input


FIXTURES = Path(__file__).parent / "fixtures"
SHA = "b79a2b097a264eaa81beb440a935e779741028d3b4de3533d2021b46eab127523"


def normalized(text):
    return unicodedata.normalize("NFKC", text).replace(",", "")


def numbers(text):
    return [float(value) for value in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])", normalized(text))]


def assert_value(text, value, places=2):
    assert any(abs(found - value) <= 0.5001 * 10 ** -places for found in numbers(text)), value


@pytest.fixture(scope="module")
def result():
    data = json.loads((FIXTURES / "baseline_input.json").read_text(encoding="utf-8"))
    for part, strength in (("梁", 24), ("柱", 27), ("フーチング", 40)):
        data.setdefault("鉄筋", {}).setdefault(part, {})["concrete_strength_mpa"] = strength
    inputs = parse_reaction_input(data)
    inputs = replace(inputs,
                     geometry=replace(inputs.geometry, h1=0.5, b2=0.5, b3=1, w2=1, w3=2, hw1=2, hw2=1, hw3=0.5),
                     spans=replace(inputs.spans, b=replace(inputs.spans.b, f=0.325), c=replace(inputs.spans.c, f=0.675)),
                     train=replace(inputs.train, factors_ultimate=1.23, factors_service=1.0))
    foundation = calculate_foundation(parse_input(data))
    foundation["long_term"].update(Kv=16777217, Ks=16777219, Kr_longitudinal=52218663)
    foundation["short_term"].update(Kv=33554435, Ks=33554437, Kr_longitudinal=104437326)
    reactions = calculate_reactions(inputs)
    reactions["train"]["raw_reactions"].update(RB=100.123456789, RC=200.987654321)
    reactions["dead_loads"]["track_totals"].update(B=2.3, C=0.7)
    for key, b, c in (("雪荷重_2年確率", 460, 250), ("雪荷重_10年確率", 740, 400), ("雪荷重_30年確率", 820, 450)):
        reactions["snow_loads"]["points"]["B"][key] = b
        reactions["snow_loads"]["points"]["C"][key] = c
    conditions = importlib.import_module("src.longitudinal_design_conditions")
    value = importlib.import_module("src.longitudinal_calculator").calculate_longitudinal_canonical(
        inputs, foundation, reactions, design_conditions=conditions.parse_longitudinal_design_conditions(data),
    )
    value["provenance"]["input_sha256"] = SHA
    return value


def renumber_nodes(result):
    """Keep the model graph and its anchor metadata consistent after renumbering."""
    frame = result["frame"]
    mapping = {node["id"]: node["id"] + 100 for node in frame["nodes"]}
    for node in frame["nodes"]:
        node["id"] = mapping[node["id"]]
    for member in frame["members"]:
        member["node_i"], member["node_j"] = mapping[member["node_i"]], mapping[member["node_j"]]
    frame["node_ids"] = {key: mapping[value] for key, value in frame["node_ids"].items()}
    frame["support_node_id"] = mapping[frame["support_node_id"]]
    frame["spring_provenance"]["support_node_id"] = frame["support_node_id"]
    for node in frame["legacy_nodes"]:
        node["active_node_id"] = mapping[node["active_node_id"]]
    for anchor in frame["load_anchors"].values():
        for key in ("node_id", "from_node_id", "to_node_id", "equivalent_node_id"):
            if key in anchor:
                anchor[key] = mapping[anchor[key]]


def guard_result_only_reads(monkeypatch, output_paths):
    allowed = {path.resolve() for path in output_paths}
    def guard(file, mode="r"):
        if not isinstance(file, (str, bytes, Path)) or not ("r" in mode or "+" in mode):
            return
        path = Path(file.decode() if isinstance(file, bytes) else file)
        if path.resolve() in allowed:
            return
        # Python modules and font files remain readable. Source documents,
        # runtime inputs, independent fixtures and old layout JSON do not.
        if path.suffix.lower() in (".json", ".pdf") or "fixtures" in path.parts:
            pytest.fail(f"Renderer must use the result, not a source file: {path}")
    for owner in (builtins, io):
        original = owner.open
        def opened(file, mode="r", *args, _original=original, **kwargs):
            guard(file, mode)
            return _original(file, mode, *args, **kwargs)
        monkeypatch.setattr(owner, "open", opened)


@pytest.fixture(scope="module")
def reports(result, tmp_path_factory):
    directory = tmp_path_factory.mktemp("longitudinal-example2-report")
    values = [deepcopy(result), deepcopy(result)]
    for value in values:
        value.pop("legacy_audit")
        value.pop("cells", None)
    for row, combination in enumerate(values[1]["combinations"]):
        combination["coefficients"] = [(101 + 20 * row + column) / 100 for column in range(20)]
    renumber_nodes(values[1])
    paths = [directory / "canonical.pdf", directory / "sentinels.pdf"]
    before = deepcopy(values)
    with pytest.MonkeyPatch.context() as monkeypatch:
        guard_result_only_reads(monkeypatch, paths)
        renderer = importlib.import_module("src.longitudinal_report")
        for value, path in zip(values, paths, strict=True):
            renderer.render_longitudinal_report(value, path)
    assert values == before
    return values, paths


def read_text(path):
    with fitz.open(path) as document:
        return [page.get_text() for page in document]


def body_between(pages, start, end):
    """Body text from one heading to the next, across variable page breaks.

    Repeated document headers and page footers are page furniture, so a footer
    such as 8-5 is never read as a negative case reference.
    """
    lines = [line for page in pages for line in page.splitlines()
             if "SHA256" not in line and line.strip() != "0610 線路方向荷重"]
    text = "\n".join(lines)
    return text[text.index(start):text.index(end, text.index(start))]


def test_public_report_module_delegates_to_the_native_stage(monkeypatch, tmp_path):
    public = importlib.import_module("src.longitudinal_report")
    calls = []
    monkeypatch.setattr(public, "render", lambda result, path: calls.append((result, path)))
    public.render_longitudinal_report({"schema_version": 2}, tmp_path / "x.pdf")
    assert calls == [({"schema_version": 2}, tmp_path / "x.pdf")]


def test_reference_order_a4_pages_continuous_numbers_and_input_sha(reports):
    _, paths = reports
    for path in paths:
        with fitz.open(path) as document:
            pages = [page.get_text() for page in document]
            # Variable pages: content order matters, never the old fixed 8 sheets.
            assert len(pages) >= 2
            assert all("荷重図" not in text for text in pages)
            for index, page in enumerate(document, 1):
                assert page.mediabox.width == pytest.approx(595, abs=1)
                assert page.mediabox.height == pytest.approx(842, abs=1)
                assert page.get_text().strip()
                footer = page.get_text(clip=fitz.Rect(0, 800, 595, 842))
                assert SHA[:12] in footer
                assert re.search(rf"(?<!\d)8-{index}(?!\d)", footer), (index, footer)
            selectors = [lambda text: "骨組" in text,
                         lambda text: "断面" in text and "材料" in text,
                         lambda text: "固定死荷重" in text and "付加死荷重" in text and "高水位" in text,
                         lambda text: "雪荷重" in text and "列車荷重" in text,
                         lambda text: "衝撃荷重" in text and "水平" in text,
                         lambda text: "基本ケース" in text and ("Define" in text or "定義ケース" in text),
                         lambda text: "荷重組合せ" in text,
                         lambda text: "抽出ケース" in text]
            indices = [next(i for i, text in enumerate(pages) if selector(text)) for selector in selectors]
            assert indices == sorted(indices), indices


def test_frame_materials_six_normal_springs_h1_and_rigid_regions(reports):
    values, paths = reports
    for result, path in zip(values, paths, strict=True):
        pages = read_text(path)
        text = "\n".join(pages[:2])
        for label in ("梁", "柱", "フーチング", "線路方向", "長期", "短期", "支持", "Double", "H1", "継承", "剛"):
            assert label in text
        for material in result["frame"]["materials"].values():
            assert_value(text, material["fck"], 1)
            assert_value(text, material["Ec"], 0)
        for term in result["frame"]["springs"].values():
            for value in term.values():
                assert_value(text, value, 0)
        assert_value(text, result["frame"]["support_node_id"], 0)
        for node in result["frame"]["nodes"]:
            assert_value(text, node["id"], 0)


def test_dead_and_water_formulas_remain_and_d2_omega_and_seismic_pages_are_absent(reports):
    values, paths = reports
    result = values[0]
    pages = read_text(paths[0])
    text = "\n".join(pages)
    dead = body_between(pages, "固定死荷重", "雪荷重")
    for label in ("高水位", "平水位", "低水位"):
        assert label in dead
    for kind, key in (("fixed", "top"), ("fixed", "footing"), ("additional", "top"), ("additional", "soil")):
        for field in ("N", "M"):
            assert_value(dead, result["vertical"][kind][key][field])
    for water in result["vertical"]["water"].values():
        for field in ("N", "M"):
            assert_value(dead, water[field])
    for formulas in result["reference_formulas"].values():
        for formula in formulas.values():
            assert_value(dead, formula["value"])
    detail = result["calculation_details"]["fixed"]
    for component in detail["components"].values():
        for key in ("N", "arm", "M"):
            assert_value(dead, component[key], 3 if key == "arm" else 2)
    for key in ("sum_N", "sum_M"):
        assert_value(dead, detail[key])
    assert_value(dead, detail["column_deduction"]["intensity"])
    assert_value(dead, detail["column_deduction"]["length"], 3)
    for value in detail["adopted_top"].values():
        assert_value(dead, value)
    for label in ("桁受け", "はり等(0600集約)", "H2+H3"):
        assert label in normalized(dead).replace(" ", "")
    normalized_text = normalized(text)
    assert re.search(r"ω\s*2", normalized_text)
    assert re.search(r"ω\s*3", normalized_text)
    assert not re.search(r"ω\s*[4-7]", normalized_text)
    assert "地震" not in normalized_text.replace("非地震", "")
    assert "慣性力" not in text
    assert not re.search(r"(?:ばね|バネ)\s*(?:番号)?\s*3", text)


def test_snow_raw_train_usage_impact_and_all_horizontal_values_are_printed(reports):
    values, paths = reports
    result, pages = values[0], read_text(paths[0])
    snow_train = next(page for page in pages if "雪荷重" in page and "列車荷重" in page)
    impact_horizontal = next(page for page in pages if "衝撃荷重" in page and "水平" in page)
    for label in ("S2", "S10", "S30", "単線", "複線"):
        assert label in snow_train
    for loads in (*result["vertical"]["snow"].values(), *result["vertical"]["train"].values()):
        for field in ("N", "M"):
            assert_value(snow_train, loads[field])
        for side in ("B", "C"):
            assert_value(snow_train, loads[side]["N"])
    for label in ("使用性", "安全性", "最大", "単線", "複線", "橋脚", "低減"):
        assert label in impact_horizontal
    for tracks in result["vertical"]["impact"].values():
        for loads in tracks.values():
            for side in ("B", "C"):
                assert_value(impact_horizontal, loads[side]["N"])
            assert_value(impact_horizontal, loads["N"])
            assert_value(impact_horizontal, loads["M"])
    for row in result["horizontal"]:
        for field in ("B", "C", "total"):
            assert_value(impact_horizontal, row[field])


# Authored native matrix: frame x=48, ID 18 pt, label 54 pt, 20 x 22.8 pt.
MATRIX_LEFT, MATRIX_PITCH = 48 + 18 + 54, 22.8


def matrix_cells(page, combination_ids):
    """Read physical bbox centers in the authored native table columns.

    Logical columns are basics, logical rows are combinations located by their
    printed ID. Dashes mean zero, never an omitted row or a transposed matrix.
    """
    words = page.get_text("words")
    # Other ID tables may share the page; read only between the matrix
    # introduction and the note that follows it.
    top = next(word[3] for word in words if word[4].startswith("20基本を列"))
    bottom = next(word[1] for word in words if word[4].startswith("組合せ1") and word[1] > top)
    rows = {}
    for x0, y0, x1, y1, text, *_ in words:
        # The ID cell may share a whitespace-free word with the label cell.
        identifier = re.match(r"\d+", text.strip())
        if x0 < MATRIX_LEFT - 54 and top < y0 < bottom and identifier:
            rows.setdefault(int(identifier[0]), (y0, y1))
    bands = [rows[identifier] for identifier in combination_ids]
    # Neighbouring cells are separated by rules, not spaces, so assign each
    # glyph to a physical cell instead of trusting whitespace word breaks.
    texts = [["" for _ in range(20)] for _ in range(16)]
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                for char in span["chars"]:
                    x0, y0, x1, y1 = char["bbox"]
                    x, y = (x0 + x1) / 2, (y0 + y1) / 2
                    row = next((index for index, (top, bottom) in enumerate(bands) if top <= y <= bottom), -1)
                    column = int((x - MATRIX_LEFT) // MATRIX_PITCH) if x >= MATRIX_LEFT else -1
                    if 0 <= row < 16 and 0 <= column < 20:
                        texts[row][column] += char["c"]
    cells = [[[] for _ in range(20)] for _ in range(16)]
    for row, values in enumerate(texts):
        for column, text in enumerate(values):
            token = normalized(text).strip()
            if not token:
                continue
            if token in ("-", "―", "—", "−", "ー"):
                cells[row][column].append(0.0)
            elif re.fullmatch(r"[+-]?\d+(?:\.\d+)?", token):
                cells[row][column].append(float(token))
            else:
                pytest.fail(f"Unexpected coefficient text at ({row + 1}, {column + 1}): {token}")
    assert all(len(cell) <= 1 for row in cells for cell in row), "duplicate coefficient in a physical cell"
    return [[cell[0] if cell else 0 for cell in row] for row in cells], sum(bool(cell) for row in cells for cell in row)


def test_all_320_nominal_cells_match_pdf_reference_and_unique_sentinels_by_coordinate(reports):
    values, paths = reports
    reference = json.loads((FIXTURES / "longitudinal_example2_cases.json").read_text(encoding="utf-8"))
    expected_matrices = [[list(row) for row in zip(*reference["coefficient_matrix"]["values"], strict=True)],
                         [row["coefficients"] for row in values[1]["combinations"]]]
    for index, (path, expected) in enumerate(zip(paths, expected_matrices, strict=True)):
        with fitz.open(path) as document:
            candidates = [page for page in document if "荷重組合せ" in page.get_text()]
            assert len(candidates) == 1
            page = candidates[0]
            actual, populated = matrix_cells(page, [row["id"] for row in values[index]["combinations"]])
            assert actual == expected
            assert len(actual) * len(actual[0]) == 320
            if index == 1:
                assert populated == 320
            coefficient_sizes = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        x0, y0, x1, y1 = span["bbox"]
                        x, y = (x0 + x1) / 2, (y0 + y1) / 2
                        if MATRIX_LEFT <= x < MATRIX_LEFT + 20 * MATRIX_PITCH and re.fullmatch(r"\d+\.\d+", span["text"].strip()):
                            coefficient_sizes.append(span["size"])
            assert coefficient_sizes
            # Reference body typography, 9.9 pt; never shrunk to fit the matrix.
            assert all(size == pytest.approx(9.9, abs=0.1) for size in coefficient_sizes)


def test_basic_define_and_extraction_ids_and_references_are_complete(reports):
    values, paths = reports
    result, pages = values[0], read_text(paths[0])
    definitions = body_between(pages, "基本ケース・定義ケース", "荷重組合せ")
    for row in result["basic_cases"]:
        assert_value(definitions, row["id"], 0)
        assert normalized(row["symbol"]) in normalized(definitions)
    for row in result["define_cases"]:
        assert_value(definitions, row["id"], 0)
        if row["id"] >= 13:
            assert re.search(rf"(?:±\s*{row['id']}(?!\d)|-\s*{row['id']}(?!\d))", normalized(definitions))
        else:
            assert not re.search(rf"(?:±|-)(?:\s*){row['id']}(?!\d)", normalized(definitions))
    extraction = body_between(pages, "抽出ケース", "応答解析")
    for row in result["extraction_cases"]:
        assert_value(extraction, row["id"], 0)
        assert normalized(row["label"]) in normalized(extraction)
        for identifier in row["combination_ids"]:
            assert_value(extraction, identifier, 0)

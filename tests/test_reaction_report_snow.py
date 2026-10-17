"""Snow-row values and legacy cells in the native 0600 tables."""

from collections import Counter
from copy import deepcopy
from dataclasses import replace
import re
import sys

import pymupdf as fitz
import pytest

from legacy_reaction_oracle import load_legacy_reaction_oracle
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from src.reaction_report import render_reaction_report
from src.reaction_report_layout import format_value, load_layout
from src.reaction_report_values import build_display_values
from src.inputs import InputError


KEYS = ("雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率")
LABELS = ("雪荷重 2年確率", "雪荷重 10年確率", "雪荷重 30年確率")
SUPPORT_VALUES = ((10, 55, 110, -5, 65, 105),
                  (30, 30, 40, 40, 60, 80),
                  (0, 20, 10, -7, 20, 3))
SLOT_VALUES = {"B": (tuple(range(1, 11)), (3,) * 10, (2,) * 10),
               "C": (tuple(range(2, 21, 2)), (4,) * 10, (1,) * 10)}


def _input_with_snow() -> dict:
    data = deepcopy(load_legacy_reaction_oracle("reaction_excel_oracle.json")["cases"][0]["input"])
    for side, point, name in (("起点側", "B支点", "B"), ("終点側", "C支点", "C")):
        for index, slot in enumerate(data["上部工反力"][side][point]["支承"]):
            slot["支承位置"] = index
            slot.update({key: SLOT_VALUES[name][case][index] for case, key in enumerate(KEYS)})
    data["上部工反力"]["起点側"].setdefault("A支点", {}).setdefault("合計", {}).update(
        {KEYS[0]: 10, KEYS[2]: 0})
    data["上部工反力"]["終点側"].setdefault("D支点", {}).setdefault("合計", {}).update(
        {KEYS[0]: -5, KEYS[1]: None, KEYS[2]: -7})
    return data


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _opening(document: fitz.Document) -> str:
    """Compact dead/snow tables, from the report start to the self-weight section."""
    flow = "".join(re.sub(r"6-\d+$", "", _compact(page.get_text())) for page in document)
    return flow[:flow.index("(3)橋脚自重の計算")]


def _rows(opening: str, label: str) -> list[list[str]]:
    """Every printed row of one snow label, in report order (support, B, C)."""
    rows = []
    for match in re.finditer(re.escape(_compact(label)), opening):
        rest = re.match(r"(?:-?\d+\.\d)+", opening[match.end():])
        rows.append(re.findall(r"-?\d+\.\d", rest[0]) if rest else [])
    return rows


def _snow_tables(opening: str) -> list[list[list[str]]]:
    """[label][table] cells: the support table, then B and C girder groups."""
    return [_rows(opening, label) for label in LABELS]


def _expected_tables(*, zero: bool = False, b=range(10), c=range(10)) -> list[list[list[str]]]:
    def text(value):
        return f"{0 if zero else value:.1f}"
    tables = []
    for case in range(3):
        rows = [[text(value) for value in SUPPORT_VALUES[case]]]
        for side, indices in (("B", b), ("C", c)):
            for start in (0, 5):
                selected = [index for index in indices if start <= index < start + 5]
                if selected:
                    rows.append([text(SLOT_VALUES[side][case][index]) for index in selected])
        tables.append(rows)
    return tables


@pytest.fixture
def snow_pdf(tmp_path):
    result = calculate_reactions(parse_reaction_input(_input_with_snow()))
    path = tmp_path / "snow.pdf"
    render_reaction_report(result, path)
    return result, path


def test_all_18_support_and_60_girder_values_and_labels_are_complete(snow_pdf):
    _, path = snow_pdf
    with fitz.open(path) as document:
        assert any("支承に働く水平荷重のまとめ" in page.get_text() for page in document)
        opening = _opening(document)
        assert _snow_tables(opening) == _expected_tables()
        for label in LABELS:
            assert opening.count(_compact(label)) == 5
        assert opening.count("6.1死荷重・雪荷重") == 1
        assert opening.count("D1+D2") == 1
        # Direct A/D inputs used red in the source. By the approved
        # monochrome contract, every input and calculated value is black.
        pages = [page for page in document if "雪荷重" in page.get_text()][:2]
        assert all(span["color"] == 0 for page in pages for block in page.get_text("dict")["blocks"]
                   for line in block.get("lines", ()) for span in line["spans"])


def test_all_legacy_d1_d2_and_train_cells_keep_their_display_values(snow_pdf):
    result, path = snow_pdf
    layout = load_layout()
    display = build_display_values(result)["死荷重"]
    expected, checked = Counter(), 0
    for source in layout["pages"][:2]:
        for cell in source["cells"]:
            value = display.get(cell["address"], result["cells"]["死荷重"].get(
                cell["address"], cell.get("value")))
            if not isinstance(value, (int, float)):
                continue
            checked += 1
            # A blank-zero cell is printed empty, so it adds no expected word.
            if not (value == 0 and cell.get("blank_zero")):
                expected[format_value(value, layout["styles"][cell["style"]]["format"])] += 1
    assert checked == 118
    with fitz.open(path) as document:
        end = next(index for index, page in enumerate(document) if "橋脚自重の計算" in page.get_text())
        printed = Counter(word[4] for page in document[:end + 1] for word in page.get_text("words"))
    assert not expected - printed


def test_snow_tables_stay_within_the_native_frame(snow_pdf):
    _, path = snow_pdf
    with fitz.open(path) as document:
        for page in document:
            assert page.rect == fitz.Rect(0, 0, 595, 842)
            for block in page.get_text("blocks"):
                assert block[0] >= -.6 and block[2] <= 595.6
                assert block[1] >= -.6 and block[3] <= 842.6
            assert all(47.5 <= drawing["rect"].x0 <= drawing["rect"].x1 <= 576.5
                       and 71.5 <= drawing["rect"].y0 <= drawing["rect"].y1 <= 792.5
                       for drawing in page.get_drawings())


def test_snow_missing_then_present_does_not_accumulate_rows_or_mutate_cache(tmp_path):
    result = calculate_reactions(parse_reaction_input(_input_with_snow()))
    original, cached = deepcopy(result), deepcopy(load_layout())
    data = _input_with_snow()
    for side, local, outer in (("起点側", "B支点", "A支点"), ("終点側", "C支点", "D支点")):
        branch = data["上部工反力"][side]
        for row in [*branch[local]["支承"], branch[outer]["合計"]]:
            for key in KEYS:
                row.pop(key, None)
    no_snow = calculate_reactions(parse_reaction_input(data))
    original_no_snow = deepcopy(no_snow)
    paths = [tmp_path / f"{index}.pdf" for index in range(3)]
    for state, path in zip((result, no_snow, result), paths):
        render_reaction_report(state, path)
    assert result == original
    assert no_snow == original_no_snow
    assert load_layout() == cached
    assert paths[0].read_bytes() == paths[2].read_bytes()
    with fitz.open(paths[1]) as document:
        assert _snow_tables(_opening(document)) == _expected_tables(zero=True)
    # Self weights, centrifugal/lateral/wind loads keep their exact text, while
    # snow-linked workings change with the snow loads.
    with fitz.open(paths[0]) as snow, fitz.open(paths[1]) as empty:
        def flow(document):
            return "".join(re.sub(r"6-\d+$", "", _compact(page.get_text())) for page in document)
        for start, end in (("(3)橋脚自重の計算", "6.2列車荷重"), ("(1)遠心荷重", "(4)地震時慣性力荷重")):
            sections = [text[text.index(start):text.index(end, text.index(start))]
                        for text in (flow(snow), flow(empty))]
            assert sections[0] == sections[1]
        snow_working = next(page for page in snow if "※T1＝" in _compact(page.get_text()))
        empty_working = next(page for page in empty if "※T1＝" in _compact(page.get_text()))
        assert snow_working.get_text() != empty_working.get_text()
        for state, page in ((result, snow_working), (no_snow, empty_working)):
            detail = state["longitudinal"][0]["B"]
            field = "local_vertical" if detail["bearing"] == "可動" else "remote_vertical"
            assert f'{detail[field]:.2f}' in _compact(page.get_text())
        assert snow[-1].get_text() != empty[-1].get_text()
        for state, document in ((result, snow), (no_snow, empty)):
            assert f'{state["transverse"][6]["B"]["force"]:.2f}' in flow(document)


def test_only_tenth_slot_snow_reaches_g10_and_support_totals(tmp_path):
    data = _input_with_snow()
    for side, point in (("起点側", "B支点"), ("終点側", "C支点")):
        for index, slot in enumerate(data["上部工反力"][side][point]["支承"]):
            slot.update({key: (17.3 if index == 9 else 0) for key in KEYS})
    result = calculate_reactions(parse_reaction_input(data))
    path = tmp_path / "tenth.pdf"
    render_reaction_report(result, path)
    with fitz.open(path) as document:
        for rows in _snow_tables(_opening(document)):
            support, b_first, b_second, c_first, c_second = rows
            assert support[1] == support[2] == "17.3"
            assert b_first == c_first == ["0.0"] * 5
            assert b_second == c_second == ["0.0"] * 4 + ["17.3"]


def test_unbreakable_snow_value_is_rejected_by_layout_without_mutation(tmp_path):
    """A 31-digit value cannot fit a numeric cell at 9.9 pt; never shrink it."""
    from gridlayoutpdf.errors import LayoutError

    data = _input_with_snow()
    for side, point in (("起点側", "B支点"), ("終点側", "C支点")):
        for slot in data["上部工反力"][side][point]["支承"]:
            slot.update(dict.fromkeys(KEYS, 0))
    data["上部工反力"]["起点側"]["B支点"]["支承"][0][KEYS[0]] = 1e30
    # Explicit zero keeps A+B finite.
    data["上部工反力"]["起点側"]["A支点"]["合計"].update({KEYS[0]: 0, KEYS[1]: -1e30, KEYS[2]: 0})
    data["上部工反力"]["終点側"]["D支点"]["合計"].update(dict.fromkeys(KEYS, 0))
    result = calculate_reactions(parse_reaction_input(data))
    original = deepcopy(result)
    path = tmp_path / "large-snow.pdf"
    with pytest.raises(LayoutError):
        render_reaction_report(result, path)
    assert not path.exists()
    assert result == original


def _max_float_snow_input():
    data = _input_with_snow()
    for side, point in (("起点側", "B支点"), ("終点側", "C支点")):
        for slot in data["上部工反力"][side][point]["支承"]:
            slot.update(dict.fromkeys(KEYS, 0))
    data["上部工反力"]["起点側"]["B支点"]["支承"][0][KEYS[0]] = sys.float_info.max
    data["上部工反力"]["起点側"]["A支点"]["合計"].update(
        {KEYS[0]: 0, KEYS[1]: -sys.float_info.max, KEYS[2]: 0})
    data["上部工反力"]["終点側"]["D支点"]["合計"].update(dict.fromkeys(KEYS, 0))
    return data


def test_snow_above_single_range_is_rejected_by_horizontal_calculation():
    with pytest.raises(InputError):
        calculate_reactions(parse_reaction_input(_max_float_snow_input()))


def test_snow_display_keeps_excel_one_decimal_half_away_rounding(tmp_path):
    data = _input_with_snow()
    for side, point in (("起点側", "B支点"), ("終点側", "C支点")):
        for slot in data["上部工反力"][side][point]["支承"]:
            slot.update(dict.fromkeys(KEYS, 0))
    data["上部工反力"]["起点側"]["B支点"]["支承"][0].update(
        dict(zip(KEYS, (.05, 1.25, 2.35))))
    data["上部工反力"]["起点側"]["A支点"]["合計"].update(
        dict(zip(KEYS, (1.25, -1.25, 1.2499999999999998))))
    data["上部工反力"]["終点側"]["D支点"]["合計"].update(
        dict(zip(KEYS, (-2.35, 2.35, -.05))))
    path = tmp_path / "half-rounding.pdf"
    render_reaction_report(calculate_reactions(parse_reaction_input(data)), path)
    expected = (("1.3", "0.1", "0.0", "-2.4", "1.3", "-2.4"),
                ("-1.3", "1.3", "0.0", "2.4", "0.0", "2.4"),
                ("1.3", "2.4", "0.0", "-0.1", "3.6", "-0.1"))
    with fitz.open(path) as document:
        for case, rows in enumerate(_snow_tables(_opening(document))):
            assert rows[0] == list(expected[case])
            assert rows[1][0] == ("0.1", "1.3", "2.4")[case]


@pytest.mark.parametrize(("b_indices", "c_indices"), [
    ((), ()),
    ((0,), (9,)),
    ((0, 1, 2, 3), (0, 1)),
    (tuple(range(5)), tuple(range(6))),
    (tuple(range(10)), tuple(range(10))),
    ((0, 2, 9), (5,)),
])
def test_girder_columns_follow_positions_and_keep_original_values(
        tmp_path, b_indices, c_indices):
    inputs = parse_reaction_input(_input_with_snow())
    rows = {}
    for side, indices in (("b", b_indices), ("c", c_indices)):
        rows[side] = tuple(replace(row, position=-index if index in indices else None)
                           for index, row in enumerate(getattr(inputs.dead, side)))
    # Position 0 remains configured even when every reaction is zero.
    rows["b"] = (replace(rows["b"][0], d1=0, d2=0, factors=(0, 0, 0, 0)),
                 *rows["b"][1:])
    inputs = replace(inputs, dead=replace(inputs.dead, **rows),
                     snow=replace(inputs.snow, b=((0, 0, 0), *inputs.snow.b[1:])))
    result = calculate_reactions(inputs)
    original, cached = deepcopy(result), deepcopy(load_layout())
    path = tmp_path / "configured-girders.pdf"
    render_reaction_report(result, path)
    with fitz.open(path) as document:
        opening = _opening(document)
        end = next(index for index, page in enumerate(document) if "橋脚自重の計算" in page.get_text())
        labels = re.findall(r"\bG\d+\b", "\n".join(page.get_text() for page in document[:end + 1]))
        assert labels == [f"G{i + 1}" for i in (*b_indices, *c_indices)]
        for case, tables in enumerate(_snow_tables(opening)):
            expected = []
            for side, indices in (("B", b_indices), ("C", c_indices)):
                for start in (0, 5):
                    selected = [index for index in indices if start <= index < start + 5]
                    if selected:
                        expected.append([f"{0 if side == 'B' and index == 0 else SLOT_VALUES[side][case][index]:.1f}"
                                         for index in selected])
            assert tables[1:] == expected
    # Null-position loads remain in totals; rendering only changes visibility.
    assert result["snow_loads"]["points"]["B"][KEYS[0]] == 54
    assert result == original and load_layout() == cached

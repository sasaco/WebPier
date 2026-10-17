"""Opening dead/snow tables flow completely and in order before self-weight."""

from copy import deepcopy
import re

import pymupdf
import pytest

from legacy_reaction_oracle import load_legacy_reaction_oracle
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from src.reaction_report import render_reaction_report


SNOW_LABELS = ("雪荷重 2年確率", "雪荷重 10年確率", "雪荷重 30年確率")


def _configured_input(b_count, c_count):
    data = deepcopy(load_legacy_reaction_oracle("reaction_excel_oracle.json")["cases"][0]["input"])
    for side, point, count, dead_base, snow_base in (
        ("起点側", "B支点", b_count, 100, 10),
        ("終点側", "C支点", c_count, 200, 40),
    ):
        for index, row in enumerate(data["上部工反力"][side][point]["支承"]):
            row["支承位置"] = index if index < count else None
            row["固定死荷重_D1"] = dead_base + index + .1
            row["付加死荷重_D2"] = dead_base / 10 + index + .2
            row["列車分担"] = {"L1": .1, "L2": .2, "L3": 0, "L4": 0}
            for case, years in enumerate((2, 10, 30)):
                row[f"雪荷重_{years}年確率"] = snow_base + 10 * case + index
    return data


def _compact(text):
    return re.sub(r"\s+", "", text)


@pytest.mark.parametrize("b_count,c_count", [
    pytest.param(4, 2, id="four-and-two"),
    pytest.param(10, 10, id="ten-and-ten"),
])
def test_opening_tables_flow_completely_before_self_weight(tmp_path, b_count, c_count):
    result = calculate_reactions(parse_reaction_input(_configured_input(b_count, c_count)))
    original = deepcopy(result)
    path = tmp_path / "opening-tables.pdf"
    render_reaction_report(result, path)
    with pymupdf.open(path) as document:
        texts = [_compact(page.get_text()) for page in document]
        weights = next(index for index, text in enumerate(texts) if "橋脚自重の計算" in text)
        # Pages vary with content, but no empty page may precede self-weight.
        assert all(texts[index] for index in range(weights + 1))
        flow = "".join(re.sub(r"6-\d+$", "", text) for text in texts[:weights + 1])
        opening = flow[:flow.index("(3)橋脚自重の計算")]
        positions = [opening.index(heading) for heading in ("(1)支点反力", "(2)主桁反力", "1)起点側桁", "2)終点側桁")]
        assert positions == sorted(positions)
        for heading in ("(1)支点反力", "(2)主桁反力", "1)起点側桁", "2)終点側桁"):
            assert opening.count(heading) == 1
        assert not any("起点側桁" in text or "終点側桁" in text for text in texts[weights + 1:])
        table_count = 1 + (b_count + 4) // 5 + (c_count + 4) // 5
        for label in SNOW_LABELS:
            assert opening.count(_compact(label)) == table_count
        assert re.findall(r"\bG\d+\b", "\n".join(page.get_text() for page in document[:weights + 1])) == (
            [f"G{i + 1}" for i in range(b_count)] + [f"G{i + 1}" for i in range(c_count)])
        # Every girder value stays in its own row and in girder order; each
        # five-girder table repeats the complete row labels.
        for count, dead_base, snow_base in ((b_count, 100, 10), (c_count, 200, 40)):
            for start in range(0, count, 5):
                girders = range(start, min(count, start + 5))
                rows = (("固定死荷重D1", [f"{dead_base + i + .1:.1f}" for i in girders]),
                        ("付加死加重D2", [f"{dead_base / 10 + i + .2:.1f}" for i in girders]),
                        ("下り", ["0.100"] * len(girders)), ("上り", ["0.200"] * len(girders)),
                        ("複線", ["0.300"] * len(girders)),
                        *((_compact(label), [f"{snow_base + 10 * case + i:.1f}" for i in girders])
                          for case, label in enumerate(SNOW_LABELS)))
                for label, values in rows:
                    assert label + "".join(values) in opening, (label, values)
        for case in range(3):
            b, c = 145 + 100 * case, 445 + 100 * case
            row = _compact(SNOW_LABELS[case]) + "".join(f"{value:.1f}" for value in (b, b, c, c, 2 * b, 2 * c))
            assert row in opening
        for page in document[:weights + 1]:
            assert page.rect == pymupdf.Rect(0, 0, 595, 842)
            # Reference typography: 9.9 pt text and 6.5 pt subscripts only.
            sizes = {round(span["size"], 1) for block in page.get_text("dict")["blocks"]
                     for line in block.get("lines", ()) for span in line["spans"]}
            assert sizes <= {9.9, 6.5}
            assert all(47.5 <= drawing["rect"].x0 <= drawing["rect"].x1 <= 576.5
                       and 71.5 <= drawing["rect"].y0 <= drawing["rect"].y1 <= 792.5
                       for drawing in page.get_drawings())
            assert all(0 <= block[0] <= block[2] <= 595 and 0 <= block[1] <= block[3] <= 842
                       for block in page.get_text("blocks"))
    assert result == original

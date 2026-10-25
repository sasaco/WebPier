"""The ground of a pile row as the JRSNAP model takes it (decision 93).

The expected values are those of the JRSNAP sample 01_サンプル(V53)：RC橋脚L (tests/fixtures/jrsnap/pile_s_springs.json: the
numbers JRSNAP saved in the NDU when it linked the .sdc of SOIL-JR 5.3, tests/fixtures/soiljr/pile_s53.sdc): the 51 rows of
the nodes of its three pile rows and the 60 elements. Two Kv2 values (and what is copied from them) differ in the last digit:
2086.25 is a tie that JRSNAP's Single arithmetic rounds down and WebPier's exact decimals up (a difference of method).
"""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from webpier.calc.pile_seismic import divide, pile_row
from webpier.core.errors import InputError
from webpier.core.printed import LENGTH
from webpier.export.soiljr.sdc_seismic import parse_seismic

FIXTURES = Path(__file__).parents[1] / "fixtures"
EXPECTED = json.loads((FIXTURES / "jrsnap" / "pile_s_springs.json").read_text(encoding="utf-8"))
ALONG = parse_seismic((FIXTURES / "soiljr" / "pile_s53.sdc").read_bytes()).direction("橋軸方向")
# the rows of the sample: first joint of the pile, and the column of the row (+x is the push: the right one is the first)
ROWS = {"left": (7, 3), "centre": (28, 2), "right": (49, 1)}
TIES = {25, 67}  # the node at the bottom of the fourth layer of the left and of the right pile


def dec(text: str) -> Decimal:
    return Decimal(text)


def test_the_elements_of_a_layer_are_d_each_and_what_is_left_is_cut_by_one_and_a_half_d():
    d = Decimal(1)
    assert divide([dec("2.6")], d) == [[1, 1, dec("0.6")]]
    assert divide([dec("5.4")], d) == [[1, 1, 1, 1, dec("0.7"), dec("0.7")]]  # 1.4 is over D and under 1.5 D: halved
    assert divide([dec("5.0"), dec("4.0")], d) == [[1] * 5, [1] * 4]
    assert divide([dec("1.5")], d) == [[1, dec("0.5")]]  # 1.5 D or more: an element of D, then 0.5
    assert divide([dec("0.4"), dec("1.0")], d) == [[dec("0.4")], [1]]  # up to D: one element
    assert divide([dec("0")], d) == [[]]  # a layer without thickness has no element
    assert divide([dec("2.4")], dec("1.2")) == [[dec("1.2"), dec("1.2")]]  # D = 1.2: 1.2 is left, up to D


def test_the_nodes_of_the_three_rows_are_the_ones_of_the_sample():
    for first, row in ROWS.values():
        model = pile_row(ALONG, row, LENGTH(1.0))
        assert model.column == row and model.length.value == 19.0
        depths = [Decimal(repr(node.depth.value)) for node in model.nodes]
        joints = [dec(EXPECTED["joints_y"][str(first + index)]) - dec(EXPECTED["joints_y"][str(first)])
                  for index in range(len(depths))]
        assert depths == joints


def test_every_row_of_the_nodes_and_every_element_of_the_sample_is_reproduced():
    checked = elements = 0
    for first, row in ROWS.values():
        model = pile_row(ALONG, row, LENGTH(1.0))
        for index, node in enumerate(model.nodes):
            key = str(first + index)
            if node.springs is None:
                assert key not in EXPECTED["SuppotInfo"]
                continue
            s = node.springs
            fields = [s.push_first, s.push_yield, s.pull_yield, s.push_second, s.push_ultimate, s.pull_ultimate,
                      s.push_second, s.pull_first, s.pull_second, s.pull_second]
            got = [Decimal(repr(field.value)) for field in fields]
            want = [dec(text) for text in EXPECTED["SuppotInfo"][key]]
            if first + index in TIES:
                kv2 = (3, 6, 8, 9)  # Kv2 and what is copied from it: 2086.25 is rounded up here, down by JRSNAP
                assert [g for i, g in enumerate(got) if i not in kv2] == [w for i, w in enumerate(want) if i not in kv2]
                assert [got[i] - want[i] for i in kv2] == [dec("0.1")] * 4
            else:
                assert got == want, key
            checked += 1
        for index, element in enumerate(model.elements):
            want = [dec(text) for text in EXPECTED["JibanShogenInfo"][str(first + index)]]
            got = [Decimal(repr(value.value)) for value in (element.horizontal, element.pressure_top, element.pressure_bottom)]
            assert got == want, first + index
            elements += 1
    assert (checked, elements) == (51, 60)


def test_a_row_the_direction_does_not_have_is_an_error():
    with pytest.raises(InputError, match="杭列 4 がありません"):
        pile_row(ALONG, 4, LENGTH(1.0))
    with pytest.raises(InputError, match="杭列 0 がありません"):
        pile_row(ALONG, 0, LENGTH(1.0))


def test_the_diameter_must_be_positive():
    with pytest.raises(InputError, match="杭径が正の値ではありません"):
        pile_row(ALONG, 1, LENGTH(0.0))


def test_the_springs_at_the_tip_of_a_short_pile_are_not_supported():
    with pytest.raises(InputError, match="杭先端の水平ばねまたは回転ばね"):
        pile_row(replace(ALONG, tip=replace(ALONG.tip, horizontal=(1.0, 1.0, 1.0))), 1, LENGTH(1.0))
    with pytest.raises(InputError, match="杭先端の水平ばねまたは回転ばね"):
        pile_row(replace(ALONG, tip=replace(ALONG.tip, rotation=(1.0, 1.0, 1.0))), 1, LENGTH(1.0))


def test_the_part_with_a_spring_must_fit_in_the_layer_below_one_over_beta():
    layers = list(ALONG.layers)
    layers[1] = replace(layers[1], push=replace(layers[1].push, length=4.5))  # 5.0 less the 0.785 above 1/β is 4.215
    with pytest.raises(InputError, match="層 2 の押込み側: ⊿l（4.5 m）"):
        pile_row(replace(ALONG, layers=tuple(layers)), 1, LENGTH(1.0))
    layers[1] = replace(ALONG.layers[1], pull=replace(ALONG.layers[1].pull, length=4.5))
    with pytest.raises(InputError, match="層 2 の引抜き側: ⊿l（4.5 m）"):
        pile_row(replace(ALONG, layers=tuple(layers)), 1, LENGTH(1.0))


def test_a_spring_under_a_tenth_keeps_two_decimals():
    layers = list(ALONG.layers)
    layers[2] = replace(layers[2], push=replace(layers[2].push, first=(0.0, 0.0, 0.0), second=(0.05, 0.0, 0.0)))
    model = pile_row(replace(ALONG, layers=tuple(layers)), 1, LENGTH(1.0))
    tiny = [node.springs.push_second for node in model.nodes if node.springs and 0 < node.springs.push_second.value < 0.1]
    assert tiny and all(spring.digits == 2 for spring in tiny)

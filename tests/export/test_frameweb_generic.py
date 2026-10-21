"""The FrameWeb input of 0610 / 0620 with a load model (decision 70), and the zero row of an empty extraction group.

FEMPython keeps a load case whose one node row is ty = 0 and gives its pickup and reactions as 0 (checked with the
real runner on a copy of P7's 線路方向.json, 2026-10-20); a case without rows it skips.
"""

from copy import deepcopy
import re

import pytest

from generic_support import generic_frame
from webpier.calc.frame import Direction
from webpier.core.errors import InputError
from webpier.core.integrity import dump_json, load_json
from webpier.export.frameweb import build_frameweb_generic, validate_frameweb


@pytest.fixture(scope="module")
def longitudinal():
    return build_frameweb_generic(generic_frame(Direction.LONGITUDINAL))


@pytest.fixture(scope="module")
def transverse():
    return build_frameweb_generic(generic_frame(Direction.TRANSVERSE))


def test_the_document_is_valid_after_a_json_round_trip(longitudinal, transverse):
    for document in (longitudinal, transverse):
        validate_frameweb(load_json(dump_json(document)))


def test_the_load_cases_are_the_basic_cases(longitudinal):
    loads = longitudinal["load"]
    assert [(loads[n]["symbol"], loads[n]["name"], loads[n]["fix_node"]) for n in sorted(loads, key=int)] == [
        ("D1", "固定死荷重", 1), ("D2", "付加死荷重", 1), ("WP_HIGH", "浮力（高水位）", 1),
        ("WP_NORMAL", "浮力（平水位）", 1), ("WP_LOW", "浮力（低水位）", 1), ("L", "車荷重", 2), ("BR", "制動荷重", 2),
        ("ZERO", "断面力0", 1)]
    # L: N = 550.00 and M = 71.25 at the beam top (ty = N downward, rz = M: build).
    assert loads["6"]["load_node"] == [{"n": "1", "tx": None, "ty": 550, "tz": None, "rx": None, "ry": None,
                                        "rz": 71.25, "row": 1}]
    # BR: H = 35.00 and M = 52.50.
    assert loads["7"]["load_node"][0]["tx"] == 35 and loads["7"]["load_node"][0]["rz"] == 52.5


def test_the_zero_case_is_one_row_of_zero(longitudinal):
    zero = longitudinal["load"]["8"]
    assert zero["load_node"] == [{"n": "1", "tx": None, "ty": 0, "tz": None, "rx": None, "ry": None, "rz": None,
                                  "row": 1}]
    assert "load_member" not in zero


def test_the_defines_combines_and_pickups(longitudinal):
    assert longitudinal["define"]["4"] == {"row": 4, "C1": 7, "C2": -7}  # BR in either direction
    assert longitudinal["define"]["7"] == {"row": 7, "C1": 8}
    assert longitudinal["combine"]["1"] == {"row": 1, "name": "破壊 車最大", "C1": 1.1, "C2": 1.2, "C3": 1.35, "C4": 1}
    assert longitudinal["combine"]["7"] == {"row": 7, "name": "該当する組合せなし（断面力0）", "C7": 1}
    pickups = longitudinal["pickup"]
    assert [pickups[n]["name"] for n in sorted(pickups, key=int)] == [
        "安全性（破壊）", "永久＋変動", "永久作用", "変動作用", "使用性（損傷）", "安全性（安定）", "長期支持性能", "短期支持性能"]
    assert pickups["4"] == {"row": 4, "name": "変動作用", "C1": 7}


def test_the_wind_on_the_pier_is_a_member_load(transverse):
    wind = transverse["load"]["6"]
    assert (wind["symbol"], wind["fix_node"]) == ("PIER_WIND_1", 2)
    assert "load_node" not in wind and wind["load_member"]


@pytest.mark.parametrize("rows,message", [
    ([{"n": "1", "tx": 0, "ty": 0, "tz": None, "rx": None, "ry": None, "rz": None, "row": 1}],
     "load.8.load_node[1]: 0 の成分は null、成分のない行は書きません"),
    ([{"n": "1", "tx": None, "ty": 0, "tz": None, "rx": None, "ry": None, "rz": None, "row": 1},
      {"n": "1", "tx": None, "ty": 1, "tz": None, "rx": None, "ry": None, "rz": None, "row": 2}],
     "load.8.load_node[1]: 0 の成分は null、成分のない行は書きません"),
    ([{"n": "1", "tx": None, "ty": 1, "tz": None, "rx": None, "ry": None, "rz": 0, "row": 1}],
     "load.8.load_node[1]: 0 の成分は null、成分のない行は書きません"),
])
def test_a_zero_is_only_the_one_row_ty_0_of_a_case(longitudinal, rows, message):
    document = deepcopy(longitudinal)
    document["load"]["8"]["load_node"] = rows
    with pytest.raises(InputError, match=re.escape(message)):
        validate_frameweb(document)

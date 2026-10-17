"""0620 FrameWeb nodes, members, sections and springs: Example2 09 pp.9-1, 9-2 and its FrameWeb file."""

import json
from pathlib import Path

import pytest

from frameweb_support import EXAMPLE2_09, T09, T_ASYMMETRIC, T_PEDESTAL, transverse
from webpier.calc.frame import NodeRole
from webpier.core.integrity import sha256
from webpier.export.frameweb import build_frameweb_transverse

ROOT = Path(__file__).parents[2]
TOP_LEVEL = ["node", "fix_node", "member", "element", "load", "define", "combine", "pickup", "dimension"]


@pytest.fixture(scope="module")
def current():
    return build_frameweb_transverse(transverse())


def test_the_fixture_is_a_copy_of_the_example2_file():
    raw = (ROOT / EXAMPLE2_09["source"]["json"]).read_bytes()
    assert sha256(raw) == EXAMPLE2_09["source"]["sha256"]
    saved = json.loads(raw.decode("utf-8-sig"))
    # The view state "three" and the analysis "result" are left out of the copy.
    assert set(saved) - set(TOP_LEVEL) == {"three", "result"}
    assert {key: saved[key] for key in TOP_LEVEL} == {key: EXAMPLE2_09[key] for key in TOP_LEVEL}


def test_top_level_is_that_of_the_example2_file(current):
    assert list(current) == TOP_LEVEL
    assert current["dimension"] == EXAMPLE2_09["dimension"] == 2


def test_nodes_and_members_are_those_of_example2(current):
    # 9-1: nodes 1 to 6 from the beam top to the footing base; members 1-3 the column section, 4-5 rigid.
    assert current["node"] == EXAMPLE2_09["node"]
    assert current["member"] == EXAMPLE2_09["member"]


def test_sections_are_those_of_example2(current):
    elements, example = current["element"]["1"], EXAMPLE2_09["element"]["1"]
    assert list(current["element"]) == ["1"] and list(elements) == list(example) == ["1", "2"]
    for number in ("1", "2"):
        assert {k: v for k, v in elements[number].items() if k != "n"} == {
            k: v for k, v in example[number].items() if k != "n"}
    printed = {item["key"]: item["value"] for item in T09["section_properties"]["items"] if "value" in item}
    # 9-2: b = 2.70 normal to the plane, h = 4.50 in it: A = 12.150, I = 2.70 × 4.50^3 / 12 = 20.50313.
    assert (elements["1"]["A"], elements["1"]["Iz"]) == (printed["column_area"], printed["column_inertia"])
    assert elements["1"]["E"] == 26500000
    # Names are free text: the parts using the section (Example2 "柱") and the rigid region.
    assert [elements[n]["n"] for n in ("1", "2")] == ["はり・ハンチ・柱", "剛域"]


def test_springs_are_those_of_9_1(current):
    # fix_node 1 = long-term, 2 = short-term; tx = Ks, ty = Kv, rz = Kr across the track at node 6.
    assert current["fix_node"] == EXAMPLE2_09["fix_node"]
    (table,) = T09["frame_model"]["tables"]
    rows = {row["key"]: [cell["value"] for cell in row["cells"]] for row in table["rows"]}
    for term, column in (("1", 0), ("2", 1)):
        (row,) = current["fix_node"][term]
        assert (row["n"], row["tx"], row["ty"], row["rz"]) == (
            "6", rows["Ks"][column], rows["Kv"][column], rows["Kr"][column])


def test_pedestal_adds_an_arm_and_its_own_section():
    result = transverse(**T_PEDESTAL)
    document = build_frameweb_transverse(result)
    base, seat = result.frame.node(NodeRole.PEDESTAL_BASE), result.frame.node(NodeRole.PEDESTAL_TOP)
    assert (document["node"][str(base.number)], document["node"][str(seat.number)]) == (
        {"x": -0.5, "y": 10.3, "z": None}, {"x": -0.5, "y": 10.6, "z": None})
    arm, pedestal = document["member"]["6"], document["member"]["7"]
    assert (arm["ni"], arm["nj"], pedestal["ni"], pedestal["nj"]) == (1, 7, 7, 8)
    elements = document["element"]["1"]
    assert elements[str(arm["e"])]["n"] == "剛域"
    # B3 = 1.000 normal to the plane, W3 = 7.000 in it: A = 7.000, I = 1.000 × 7.000^3 / 12 = 28.58333.
    assert {key: elements[str(pedestal["e"])][key] for key in ("A", "Iz", "E", "n")} == {
        "A": 7, "Iz": 28.58333, "E": result.frame.materials.beam.ec, "n": "桁受け"}


def test_asymmetric_footing_makes_an_inclined_rigid_member():
    # W7 = 2.500, W9 = 2.000: the column axis is 0.250 from the footing centre; the springs stay at the centre.
    result = transverse(**T_ASYMMETRIC)
    document = build_frameweb_transverse(result)
    top, centroid = result.frame.node(NodeRole.FOOTING_TOP), result.frame.node(NodeRole.FOOTING_CENTROID)
    assert (document["node"][str(top.number)]["x"], document["node"][str(centroid.number)]["x"]) == (0.25, 0)
    member = document["member"]["4"]
    assert (member["ni"], member["nj"]) == (top.number, centroid.number)
    assert document["element"]["1"][str(member["e"])]["n"] == "剛域"
    (row,) = document["fix_node"]["1"]
    assert row["n"] == str(result.frame.support.node)

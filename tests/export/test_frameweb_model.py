"""FrameWeb nodes, members, sections and springs: Example2 08 pp.8-1, 8-2 and its FrameWeb file."""

import pytest

from frameweb_support import ASYMMETRIC, CENTRED_PEDESTAL, CONCRETES, EXAMPLE2, L08, PEDESTAL, longitudinal, mirrored_nodes
from webpier.calc.frame import NodeRole
from webpier.export.frameweb import build_frameweb

TOP_LEVEL = ["node", "fix_node", "member", "element", "load", "define", "combine", "pickup", "dimension"]


@pytest.fixture(scope="module")
def current():
    return build_frameweb(longitudinal())


def test_top_level_is_the_example2_file_without_the_view_state(current):
    # Example2 also saves "three" (the camera of the 3D view): a GUI state, not part of the model.
    assert list(current) == TOP_LEVEL
    fixture_only = {"fixture_schema_version", "source", "coefficient_matrix", "known_differences"}
    # The fixture keeps the Example2 tables except "three" and "dimension" (Example2 saves dimension 2).
    assert set(EXAMPLE2) - fixture_only == set(TOP_LEVEL) - {"dimension"}
    assert current["dimension"] == 2


def test_nodes_are_those_of_example2(current):
    # 8-1: nodes 1 to 6 from the beam top to the footing base; the same numbers and coordinates, y downward.
    assert current["node"] == mirrored_nodes(EXAMPLE2["node"])
    assert current["node"]["1"]["y"] == -10.3 and current["node"]["6"]["y"] == 0


def test_members_are_those_of_example2(current):
    # 8-1 / 8-2: members 1-3 the column section, 4-5 the rigid footing. The beam and the column concrete are both
    # f'ck 27.0 here, so they are one section as in Example2.
    assert current["member"] == EXAMPLE2["member"]


def test_sections_are_those_of_example2(current):
    elements = current["element"]
    assert list(elements) == ["1"]
    example = EXAMPLE2["element"]["1"]
    assert list(elements["1"]) == list(example) == ["1", "2"]
    for number in ("1", "2"):
        ours, theirs = elements["1"][number], example[number]
        assert {key: value for key, value in ours.items() if key != "n"} == {
            key: value for key, value in theirs.items() if key != "n"}
    printed = {item["key"]: item for item in L08["section_properties"]["items"]}
    assert (elements["1"]["1"]["A"], elements["1"]["1"]["Iz"]) == (
        printed["column_area"]["value"], printed["column_inertia"]["value"])  # 12.150, 7.38113
    assert elements["1"]["1"]["E"] == 26500000  # 2.65 × 10^7
    # Names are free text: the parts using the section, and the rigid region (Example2 "柱", "剛域").
    assert [elements["1"][n]["n"] for n in ("1", "2")] == ["はり・ハンチ・柱", "剛域"]


def test_springs_are_those_of_8_1(current):
    # fix_node 1 = long-term, 2 = short-term (8-9 バネ 1 / 2); tx = Ks, ty = Kv, rz = Kr at node 6.
    assert current["fix_node"] == EXAMPLE2["fix_node"]
    rows = {row["key"]: [cell["value"] for cell in row["cells"]]
            for row in L08["frame_model"]["tables"][0]["rows"]}
    for term, column in (("1", 0), ("2", 1)):
        (row,) = current["fix_node"][term]
        assert (row["tx"], row["ty"], row["rz"]) == (rows["Ks"][column], rows["Kv"][column], rows["Kr"][column])


def test_different_concretes_make_separate_sections():
    result = longitudinal(**CONCRETES)
    document = build_frameweb(result)
    elements = document["element"]["1"]
    assert [member["e"] for member in document["member"].values()] == [1, 1, 2, 3, 3]
    materials = result.frame.materials
    assert (elements["1"]["E"], elements["2"]["E"]) == (materials.beam.ec, materials.column.ec)
    assert elements["1"]["E"] != elements["2"]["E"]
    assert [elements[n]["n"] for n in ("1", "2", "3")] == ["はり・ハンチ", "柱", "剛域"]
    assert elements["1"]["A"] == elements["2"]["A"] == 12.15


def test_pedestal_adds_an_arm_and_its_own_section():
    result = longitudinal(**PEDESTAL)
    document = build_frameweb(result)
    frame = result.frame
    seat = frame.node(NodeRole.PEDESTAL_TOP)
    base = frame.node(NodeRole.PEDESTAL_BASE)
    assert document["node"][str(base.number)] == {"x": 0.175, "y": -10.3, "z": None}
    assert document["node"][str(seat.number)] == {"x": 0.175, "y": -10.6, "z": None}
    # numbered from the upper left (JRSNAP 2.1.6): pedestal top 1, beam top 2, base 3; members in the order of their ends: pedestal 1, arm 2
    arm, pedestal = document["member"]["2"], document["member"]["1"]
    cap = frame.node(NodeRole.CAP_TOP)
    assert (arm["ni"], arm["nj"], pedestal["ni"], pedestal["nj"]) == (cap.number, base.number, base.number, seat.number)
    assert (seat.number, base.number, cap.number) == (1, 3, 2)
    elements = document["element"]["1"]
    assert elements[str(arm["e"])]["n"] == "剛域"
    section = frame.pedestal_section
    assert {key: elements[str(pedestal["e"])][key] for key in ("A", "Iz", "E", "n")} == {
        "A": section.area.value, "Iz": section.inertia.value, "E": frame.materials.beam.ec, "n": "桁受け"}
    assert (section.area.value, section.inertia.value) == (7.0, 0.58333)  # 7.000 × 1.000; 7.000 × 1.000^3 / 12


def test_centred_pedestal_rises_from_the_beam_top():
    document = build_frameweb(longitudinal(**CENTRED_PEDESTAL))
    assert len(document["member"]) == 6  # no arm: the pedestal base is the beam-top node
    assert (document["member"]["1"]["ni"], document["member"]["1"]["nj"]) == (2, 1)  # the beam top 2 → the top 1
    assert document["node"]["1"] == {"x": 0, "y": -10.6, "z": None}


def test_asymmetric_footing_makes_an_inclined_rigid_member():
    result = longitudinal(**ASYMMETRIC)
    document = build_frameweb(result)
    top, centroid = result.frame.node(NodeRole.FOOTING_TOP), result.frame.node(NodeRole.FOOTING_CENTROID)
    assert (document["node"][str(top.number)]["x"], document["node"][str(centroid.number)]["x"]) == (0.35, 0)
    member = document["member"]["4"]
    assert (member["ni"], member["nj"]) == (top.number, centroid.number)
    assert document["element"]["1"][str(member["e"])]["n"] == "剛域"
    (row,) = document["fix_node"]["1"]
    assert row["n"] == str(result.frame.support.node)

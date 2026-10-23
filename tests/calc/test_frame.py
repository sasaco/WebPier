"""The analysis frame shared by 0610/0620/0710/0720: Example2 8-1/8-2, 9-1/9-2, 10-1/10-5 and hand geometry."""

import json
from decimal import Decimal

import pytest

from reaction_support import FIXTURES, D, pier, q
from webpier.calc.foundation import calculate_foundation
from webpier.calc.frame import BODY_REGIONS, Direction, NodeRole, Region, build_frame
from webpier.calc.materials import calculate_materials
from webpier.calc.reaction import calculate_reaction
from webpier.core.printed import FORCE, LENGTH
from webpier.core.errors import InputError
from webpier.loadmodel import Side

L08 = json.loads((FIXTURES / "example2" / "longitudinal.json").read_text(encoding="utf-8"))
T09 = json.loads((FIXTURES / "example2" / "transverse.json").read_text(encoding="utf-8"))
S10 = json.loads((FIXTURES / "example2" / "seismic_longitudinal.json").read_text(encoding="utf-8"))
DIMS = "下部構造/寸法/{group}/{key}"
SIDE, FRONT, HEIGHT = "側面", "正面", "高さ"


def items(document, key):
    section = next(item for item in document["sections"] if item["key"] == key)
    return {item["key"]: item for item in section["items"] if "value" in item}, section


def springs(document):
    _, section = items(document, "frame_model")
    table = section["tables"][0]
    return {row["key"]: [cell["value"] for cell in row["cells"]] for row in table["rows"]}


def frame(p=None, direction=Direction.LONGITUDINAL, **options):
    p = p or pier()
    return build_frame(p, calculate_reaction(p).self_weight, calculate_foundation(p), calculate_materials(p),
                       direction, **options)


def dims(**sizes):
    """Input variant from B3=.., W3=.., H1=.. style keyword sizes."""
    groups = {"B": SIDE, "W": FRONT, "H": HEIGHT}
    return pier(**{DIMS.format(group=groups[key[0]], key=key): value for key, value in sizes.items()})


def lengths(result):
    return [member.height.value for member in result.members]


def test_example2_8_1_longitudinal_frame():
    model, _ = items(L08, "frame_model")
    result = frame()
    assert [node.number for node in result.nodes] == [1, 2, 3, 4, 5, 6]
    assert lengths(result) == [model[f"member{n}_length"]["value"] for n in range(1, 6)]  # 2.000 0.700 4.900 1.350 1.350
    assert [node.y.value for node in result.nodes] == [10.3, 8.3, 7.6, 2.7, 1.35, 0.0]
    assert {node.x.value for node in result.nodes} == {0.0}
    assert [(m.start, m.end) for m in result.members] == [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6)]
    assert [m.region for m in result.members] == [Region.BEAM, Region.HAUNCH, Region.COLUMN,
                                                  Region.FOOTING_UPPER, Region.FOOTING_LOWER]
    assert [m.rigid for m in result.members] == [False, False, False, True, True]  # 8-2: footing all rigid
    assert result.node(NodeRole.CAP_TOP).number == 1
    assert result.node(NodeRole.FOOTING_TOP).number == 4
    assert result.node(NodeRole.FOOTING_CENTROID).number == 5
    assert result.support.node == result.node(NodeRole.FOOTING_BOTTOM).number == 6
    assert [m.number for m in result.column_line] == [1, 2, 3]  # q acts on members 1-3 (8-3)


def test_example2_8_1_springs_long_and_short():
    printed = springs(L08)
    support = frame().support
    assert [support.long_term.kv.value, support.short_term.kv.value] == printed["Kv"]
    assert [support.long_term.kr.value, support.short_term.kr.value] == printed["Kr"]
    assert support.long_term.ks.value == printed["Ks"][0]
    # 8-1 prints Ks short 8,525,475 = 0500 ks 135325 × A 63.000 (not 2 × long); 0500 gives the same.
    assert support.short_term.ks.value == printed["Ks"][1]


def test_example2_9_1_transverse_springs_use_kr_transverse():
    printed = springs(T09)
    support = frame(direction=Direction.TRANSVERSE).support
    assert [support.long_term.kr.value, support.short_term.kr.value] == printed["Kr"]
    assert [support.long_term.kv.value, support.short_term.kv.value] == printed["Kv"]


@pytest.mark.parametrize("document,direction", [(L08, Direction.LONGITUDINAL), (T09, Direction.TRANSVERSE)])
def test_example2_section_8_2_and_9_2(document, direction):
    printed, _ = items(document, "section_properties")
    section = frame(direction=direction).column_section
    assert section.width.value == printed["column_b"]["value"]
    assert section.depth.value == printed["column_h"]["value"]
    assert (section.area.value, section.area.digits) == (printed["column_area"]["value"], 3)
    assert (section.inertia.value, section.inertia.digits) == (printed["column_inertia"]["value"], 5)
    result = frame(direction=direction)
    assert all(m.section == section for m in result.members if not m.rigid)
    assert all(m.section is None and m.material is None for m in result.members if m.rigid)


def test_materials_by_region():
    p = pier(**{"鉄筋/梁/concrete_strength_mpa": 24.0, "鉄筋/柱/concrete_strength_mpa": 30.0})
    result = frame(p)
    by_region = {m.region: m.material for m in result.members}
    assert by_region[Region.BEAM].strength.value == by_region[Region.HAUNCH].strength.value == 24.0
    assert by_region[Region.COLUMN].strength.value == 30.0
    assert result.materials.footing.modulus.value == 2.65  # 9-2 prints the footing Ec; the footing is rigid


def test_example2_10_1_column_base_micro_member_for_0710():
    nodes = S10["model"]["nodes"]
    result = frame(column_base_micro_member=True, elastic_regions=frozenset({Region.COLUMN_BASE}))
    assert lengths(result) == [segment["value"] for segment in nodes["segment_lengths"]]  # 2.0 0.7 4.89 0.01 1.35 1.35
    assert [node.number for node in result.nodes] == nodes["node_numbers_top_to_bottom"]
    elements = S10["model"]["elements"]["rows"]
    assert [m.rigid for m in result.members] == [row["nonlinear"] == "剛域" for row in elements]
    assert [(m.start, m.end) for m in result.members] == [(row["i_node"], row["j_node"]) for row in elements]
    micro = result.members[3]
    assert micro.region is Region.COLUMN_BASE and micro.material.strength.value == 27.0
    assert result.node(NodeRole.MICRO_TOP).y.value == 2.71  # 0.010 above the footing top, cut from H4
    assert [m.number for m in result.column_line] == [1, 2, 3, 4]


def test_micro_member_needs_h4_longer_than_it():
    with pytest.raises(InputError, match=r"下部構造\.寸法\.高さ\.H4.*0\.010"):
        frame(dims(H4=0.01), column_base_micro_member=True)


def test_elastic_regions_must_have_a_section():
    with pytest.raises(ValueError, match="FOOTING_UPPER"):
        frame(elastic_regions=frozenset({Region.FOOTING_UPPER}))
    assert Region.FOOTING_UPPER not in BODY_REGIONS


def test_zero_haunch_and_beam_merge_nodes():
    result = frame(dims(H2=0.0, H3=0.0))
    assert lengths(result) == [4.9, 1.35, 1.35]
    top = result.node(NodeRole.CAP_TOP)
    assert top is result.node(NodeRole.BEAM_BOTTOM) is result.node(NodeRole.COLUMN_TOP)
    assert top.roles == frozenset({NodeRole.CAP_TOP, NodeRole.BEAM_BOTTOM, NodeRole.COLUMN_TOP})
    assert [m.number for m in result.members] == [1, 2, 3]
    assert [m.region for m in result.column_line] == [Region.COLUMN]


def test_zero_haunch_only():
    result = frame(dims(H3=0.0))
    assert [m.region for m in result.members][:2] == [Region.BEAM, Region.COLUMN]
    assert lengths(result) == [2.0, 4.9, 1.35, 1.35]


def test_asymmetric_footing_puts_the_column_axis_off_the_footing_centre():
    # B7 = 2.500, B9 = 1.800: the column axis is (B7 − B9)/2 = 0.350 from the footing centre (toward the end side).
    p = dims(B7=2.5, B9=1.8, H5=0.5, H6=2.2, B8=3.0, W8=5.0)
    result = frame(p)
    x_c = q((D(2.5) - D(1.8)) / 2, 3)
    for role in (NodeRole.CAP_TOP, NodeRole.COLUMN_TOP, NodeRole.FOOTING_TOP):
        assert D(result.node(role).x.value) == x_c
    for role in (NodeRole.FOOTING_CENTROID, NodeRole.FOOTING_BOTTOM):
        assert result.node(role).x.value == 0.0
    footing = calculate_reaction(p).self_weight.footing
    assert result.node(NodeRole.FOOTING_CENTROID).y.value == footing.y.value
    upper = next(m for m in result.members if m.region is Region.FOOTING_UPPER)
    assert (D(upper.offset.value), upper.height.value) == (-x_c, round(2.7 - footing.y.value, 3))
    assert upper.rigid
    # The transverse frame uses W7/W9, still symmetric.
    assert {n.x.value for n in frame(p, Direction.TRANSVERSE).nodes} == {0.0}


def test_pedestal_with_offset():
    # Pedestal centre from the column axis (2·B2 + B3 − B1 − B4 + B5)/2 = (1.0 + 1.0 − 2.7)/2 = −0.350.
    result = frame(dims(B2=0.5, B3=1.0, W2=1.0, W3=7.0, H1=0.3))
    # Numbered from the upper left (JRSNAP 2.1.6): the pedestal top 1, then at the beam top the pedestal base
    # (left, x = −0.350) 2 and the beam top 3; the members in the order of their ends: stub 1, arm 2, beam 3 …
    base, top = result.node(NodeRole.PEDESTAL_BASE), result.node(NodeRole.PEDESTAL_TOP)
    assert (base.number, top.number, result.node(NodeRole.CAP_TOP).number) == (2, 1, 3)
    assert (base.x.value, base.y.value) == (-0.35, 10.3)
    assert (top.x.value, top.y.value) == (-0.35, 10.6)
    stub, arm = result.members[:2]
    assert (arm.region, arm.rigid, arm.start, arm.end) == (Region.PEDESTAL_ARM, True, 3, 2)
    assert (arm.offset.value, arm.height.value) == (-0.35, 0.0)
    assert (stub.region, stub.rigid, stub.start, stub.end, stub.height.value) == (Region.PEDESTAL, False, 2, 1, 0.3)
    section = result.pedestal_section
    assert (section.width.value, section.depth.value) == (7.0, 1.0)
    assert section.area.value == 7.0
    assert Decimal(repr(section.inertia.value)) == q(D(7.0) * D(1.0) ** 3 / 12, 5)  # 0.58333
    assert stub.section == section and stub.material.strength.value == 27.0  # pedestal: beam concrete
    transverse = frame(dims(B2=0.5, B3=1.0, W2=1.0, W3=7.0, H1=0.3), Direction.TRANSVERSE).pedestal_section
    assert (transverse.width.value, transverse.depth.value) == (1.0, 7.0)
    assert Decimal(repr(transverse.inertia.value)) == q(D(1.0) * D(7.0) ** 3 / 12, 5)  # 28.58333
    assert [m.number for m in result.column_line] == [3, 4, 5]  # the pedestal is not on the column line
    # Decision 80: the origin bearing line −0.325 is within −0.350 ± 1.000/2 (on the pedestal), the end one +0.675
    # is not (on the beam top).
    assert result.seats == (NodeRole.PEDESTAL_TOP, NodeRole.CAP_TOP) and result.top is top
    assert result.seat_offset(Side.ORIGIN).value == -0.35 and result.seat_offset(Side.END).value == 0.0
    assert [m.number for m in result.pedestal_members] == [1]
    with pytest.raises(InputError, match="別の座"):  # the train path needs both girders on one seat
        result.bearing_seat


def test_centred_pedestal_shares_the_cap_top_node():
    # 2·B2 + B3 = B1: centred, so no arm.
    result = frame(dims(B2=0.85, B3=1.0, W2=1.0, W3=7.0, H1=0.3))
    assert result.node(NodeRole.PEDESTAL_BASE) is result.node(NodeRole.CAP_TOP)
    assert result.members[0].region is Region.PEDESTAL  # the pedestal top is node 1, the beam top 2
    assert Region.PEDESTAL_ARM not in {m.region for m in result.members}
    assert (result.members[0].start, result.members[0].end) == (2, 1)
    # The origin bearing line −0.325 is on it (0 ± 0.500), the end one +0.675 is not: no offset on either seat.
    assert result.seats == (NodeRole.PEDESTAL_TOP, NodeRole.CAP_TOP)
    assert result.seat_offset(Side.ORIGIN).value == result.seat_offset(Side.END).value == 0.0


def test_both_girders_on_the_pedestal_share_its_top():
    # Centre (2 × 0.3 + 2.4 − 2.7)/2 = 0.150, half 1.200: −0.325 and +0.675 are both on it (decision 81).
    result = frame(dims(B2=0.3, B3=2.4, W2=0.5, W3=8.0, H1=0.3))
    top = result.node(NodeRole.PEDESTAL_TOP)
    assert result.seats == (NodeRole.PEDESTAL_TOP, NodeRole.PEDESTAL_TOP)
    assert result.bearing_seat is top and result.bearing_offset.value == 0.15


@pytest.mark.parametrize("b2,end", [(1.175, NodeRole.PEDESTAL_TOP), (1.174, NodeRole.CAP_TOP)])
def test_a_bearing_line_on_the_pedestal_edge_is_on_it(b2, end):
    # Centre b2 + 0.425 − 1.350, half 0.425: its end edge 0.675 (b2 = 1.175) is the end bearing line, 0.674 not.
    result = frame(dims(B2=b2, B3=0.85, W2=1.0, W3=7.0, H1=0.3))
    assert result.seats == (NodeRole.CAP_TOP, end)


def test_no_pedestal_without_h1():
    result = frame(dims(B2=0.5, B3=1.0, W3=7.0))
    assert result.bearing_seat is result.node(NodeRole.CAP_TOP)  # H1 = 0: the bearings sit on the beam top
    assert result.seats == (NodeRole.CAP_TOP, NodeRole.CAP_TOP) and result.top is result.bearing_seat
    assert result.pedestal_members == () and result.girder(Side.ORIGIN) is None
    assert result.bearing_offset.value == 0.0
    assert result.pedestal_section is None
    with pytest.raises(KeyError):
        result.node(NodeRole.PEDESTAL_TOP)


@pytest.mark.parametrize("sizes,path", [({"H1": 0.3, "B3": 0.0, "W3": 7.0}, "B3"),
                                        ({"H1": 0.3, "B3": 1.0, "W3": 0.0}, "W3")])
def test_pedestal_needs_a_section(sizes, path):
    with pytest.raises(InputError, match=rf"下部構造\.寸法.*{path}"):
        frame(dims(**sizes))


def test_section_rounded_to_zero_is_an_input_error():
    # I = 4.500 × 0.010^3 / 12 = 3.75e-7 -> 0.00000
    with pytest.raises(InputError, match=r"B6.*W6"):
        frame(dims(B6=0.01, B8=0.01))


def test_pier_height_is_the_beam_top_above_the_footing_top():
    # Example2 8-1: 7.600 = H2 + H3 + H4 = 2.000 + 0.700 + 4.900, the dimension from node 1 to node 4.
    result = frame()
    assert result.pier_height.value == 7.6 and result.pier_height.digits == 3
    top, footing = result.node(NodeRole.CAP_TOP), result.node(NodeRole.FOOTING_TOP)
    assert D(result.pier_height.value) == D(top.y.value) - D(footing.y.value)
    # Without beam and haunch it is the column; with the micro member it still includes it (7.590 + 0.010).
    assert frame(dims(H2=0.0, H3=0.0)).pier_height.value == 4.9
    assert frame(column_base_micro_member=True).pier_height.value == 7.6


SPLIT = dict(B2=1.175, B3=0.85, W2=1.0, W3=7.0, H1=0.3)  # the origin girder on the beam top, the end one on the pedestal


def girders(sizes, forces=(6720, 2370), **changes):
    """The 0720 frame of *sizes* (B3=.. style) and other input *changes*, with the girder *forces* (origin, end)."""
    groups = {"B": SIDE, "W": FRONT, "H": HEIGHT}
    changes = {DIMS.format(group=groups[key[0]], key=key): value for key, value in sizes.items()} | changes
    return frame(pier(**changes), Direction.TRANSVERSE, column_base_micro_member=True,
                 elastic_regions={Region.COLUMN_BASE}, girder_levels=tuple(FORCE(force) for force in forces))


def test_girder_levels_above_the_seat_of_each_girder():
    # Decision 80: the origin girder on the beam top 10.300 + 2.750 = 13.050, the end one on the pedestal top
    # 10.600 + 2.750 = 13.350; both above the pier top (10.600), chained down to it.
    result = girders(SPLIT)
    origin, end, top = (result.node(role) for role in (NodeRole.GIRDER_ORIGIN, NodeRole.GIRDER_END,
                                                       NodeRole.PEDESTAL_TOP))
    assert [(n.number, n.y.value) for n in (end, origin, top)] == [(1, 13.35), (2, 13.05), (3, 10.6)]
    chain = [(m.start, m.end, m.height.value) for m in result.members if m.region is Region.GIRDER]
    assert chain == [(1, 2, 0.3), (2, 3, 2.45)]
    assert result.girder(Side.ORIGIN) is origin and result.girder(Side.END) is end
    # The control node is the girder with the larger force: the origin's 6720 kN (not a weighted level).
    assert result.node(NodeRole.CONTROL) is origin and len(result.nodes) == 10  # the pedestal base is the beam top


@pytest.mark.parametrize("forces,role", [((2370, 6720), NodeRole.GIRDER_END), ((100, 100), NodeRole.GIRDER_END),
                                         ((0, 0), NodeRole.GIRDER_END)])
def test_the_control_node_is_the_girder_with_the_larger_force(forces, role):
    result = girders(SPLIT, forces)  # equal forces: the higher level, the end girder's
    assert result.node(NodeRole.CONTROL) is result.node(role)


def test_a_girder_level_below_the_pier_top_is_an_input_error():
    # The origin girder on the beam top at 10.300 + 0.100 = 10.400, below the pedestal top 10.600.
    with pytest.raises(InputError, match=r"上部構造\.起点側\.高さ.*桁受け天端"):
        girders(SPLIT, **{"上部構造/起点側/高さ/h1": 0.0, "上部構造/起点側/高さ/h2": 0.1})

"""0710 by hand for inputs other than Example2: Kh, seismic train, girder lengths, bearings, H1, footing, water."""

from decimal import Decimal

import pytest

from reaction_support import D, END_SLOTS, ORIGIN_SLOTS, document, pier, q, value
from seismic_longitudinal_support import chain, points, seismic
from webpier.calc.frame import NodeRole, Region
from webpier.calc.longitudinal import BasicCase, Item
from webpier.calc.seismic_longitudinal import SeismicCase
from webpier.core.errors import InputError
from webpier.inputs import parse_input
from webpier.calc import vehicles
from webpier.core.printed import LINE_LOAD

C = SeismicCase
DIMS = {"B": "下部構造/寸法/側面/", "W": "下部構造/寸法/正面/", "H": "下部構造/寸法/高さ/"}
WEIGHTS = "下部構造/単位体積重量/"
SURFACE_WET = "地盤データ/層/0/単位体積重量/湿潤"


def dims(**sizes):
    return {DIMS[key[0]] + key: size for key, size in sizes.items()}


def hand_intensity(along, across, gamma, kh=1):
    return q(D(along) * D(across) * D(gamma) * D(kh), 2)


def test_self_weight_inertia_with_unround_sizes_and_unit_weights():
    # Hw = b × w × γ × Kh (Kh = 1.00), each rounded once to 2 decimals.
    p = pier(**dims(B1=2.655, W1=8.95, B4=0.105, B5=0.2, W4=2.275, W5=2.125, B6=2.35, W6=4.45)
             | {WEIGHTS + "梁・躯体": 24.7})
    inertia = seismic(p).self_weight
    assert value(inertia.beam_top.value) == hand_intensity(2.655, 8.95, 24.7)  # 586.927575 -> 586.93
    # Haunch bottom (2.655 − 0.105 − 0.200) × (8.950 − 2.275 − 2.125) = 2.350 × 4.550
    assert (inertia.beam_bottom.along.value, inertia.beam_bottom.across.value) == (2.35, 4.55)
    assert value(inertia.beam_bottom.value) == hand_intensity(2.35, 4.55, 24.7)  # 264.10475 -> 264.10
    assert value(inertia.column.value) == hand_intensity(2.35, 4.45, 24.7)  # 258.30025 -> 258.30
    assert inertia.beam_top.unit_weight.value == 24.7
    loads = {load.member: (load.start.value, load.end.value) for load in seismic(p).basic(C.SELF_INERTIA).member_loads}
    assert loads[2] == (-586.93, -264.1)  # the haunch taper ends at its own bottom section, not at the column


def test_girder_and_train_inertia_are_not_multiplied_again():
    # The 0600 forces already carry Kh = 1.00 and the adhesion 0.20; 0710 puts them on the frame unchanged.
    _, reaction, _, result = chain()
    assert value(result.basic(C.GIRDER_INERTIA).points[0].h) == -value(reaction.longitudinal.seismic_girder.total)
    assert value(result.basic(C.TRAIN_INERTIA).points[0].h) == -value(reaction.longitudinal.seismic_train.total)
    # 13580 / 2 (movable B) + 4740 (fixed C) = 11530; (320 + 320) × 0.20 / 2 + (160 + 160) × 0.20 = 128.
    assert result.basic(C.GIRDER_INERTIA).points[0].h.value == -11530.0
    assert result.basic(C.TRAIN_INERTIA).points[0].h.value == -128.0


def test_earthquake_train_load_zero(monkeypatch):
    monkeypatch.setattr(vehicles, "P16_SEISMIC", LINE_LOAD.exact(0))  # the vehicle's, no input (decision 101)
    result = seismic(pier())
    assert [row.n.value for row in result.train.rows] == [0.0, 0.0]
    assert points(result.basic(C.TRAIN)) == {1: (0.0, 0.0, 0.0)}
    assert points(result.basic(C.TRAIN_INERTIA)) == {1: (0.0, 0.0, 0.0)}
    assert len(result.basic_cases) == 8  # a zero case stays in the table and the combination
    assert points(result.basic(C.GIRDER_INERTIA)) == {1: (0.0, -11530.0, 0.0)}


def test_whole_girder_lengths():
    # Origin 0.600 + 21.350 + 0.550 = 22.500 m, end 0.400 + 12.125 + 0.375 = 12.900 m, e = 32.00 kN/m.
    p = pier(**{"上部構造/起点側/桁長/L1": 0.6, "上部構造/起点側/桁長/スパン長": 21.35, "上部構造/起点側/桁長/L2": 0.55,
                "上部構造/終点側/桁長/L1": 0.4, "上部構造/終点側/桁長/スパン長": 12.125, "上部構造/終点側/桁長/L2": 0.375})
    result = seismic(p)
    rb = q(D(32) * D(22.5) / 2, 2)  # 360.00
    rc = q(D(32) * D(12.9) / 2, 2)  # 206.40
    assert [value(row.n) for row in result.train.rows] == [rb, rc]
    m = q(rb * D(-0.325), 2) + q(rc * D(0.675), 2)  # −117.00 + 139.32 = 22.32
    assert points(result.basic(C.TRAIN)) == {1: (float(rb + rc), 0.0, float(m))}
    # Train inertia: movable B (2 × 360.00) × 0.20 / 2 = 72.00, fixed C (2 × 206.40) × 0.20 = 82.56.
    origin, end = q(q(2 * rb * D("0.20"), 2) / 2, 2), q(2 * rc * D("0.20"), 2)
    assert (value(result.train_inertia.forces.origin.force), value(result.train_inertia.forces.end.force)) == (
        origin, end)
    assert value(result.basic(C.TRAIN_INERTIA).points[0].h) == -(origin + end) == Decimal("-154.56")


def test_swapped_fixed_and_movable_bearings():
    data = document(**{"上部構造/支承データ/起点側/支承名": "固定", "上部構造/支承データ/終点側/支承名": "可動"})
    result = seismic(parse_input(data))
    # Origin girder fixed on this pier: the whole T = 5740 + 5740 + 660 + 520 + 460 + 460 = 13580.00;
    # end girder movable: (1860 + 1860 + 260 + 260 + 250 + 250) / 2 = 4740 / 2 = 2370.00.
    girder = result.girder_inertia.forces
    assert (girder.origin.force.value, girder.end.force.value) == (13580.0, 2370.0)
    assert points(result.basic(C.GIRDER_INERTIA)) == {1: (0.0, -15950.0, 0.0)}
    # Train: fixed origin (320 + 320) × 0.20 = 128.00, movable end (160 + 160) × 0.20 / 2 = 32.00.
    assert points(result.basic(C.TRAIN_INERTIA)) == {1: (0.0, -160.0, 0.0)}


# The pedestal centre (2·1.025 + 1.0 − 2.7)/2 = 0.175, half 0.500: the bearing lines −0.325 and +0.675 on its edges.
PEDESTAL = dims(B2=1.025, B3=1.0, W2=1.0, W3=7.0, H1=0.3)


def test_pedestal_inertia_and_bearing_loads_at_the_pedestal_top():
    _, reaction, _, result = chain(pier(**PEDESTAL))
    frame = result.frame
    top, base = frame.node(NodeRole.PEDESTAL_TOP), frame.node(NodeRole.PEDESTAL_BASE)
    assert (base.x.value, base.y.value, top.x.value, top.y.value) == (0.175, 10.3, 0.175, 10.6)
    # 桁受け: B3 × W3 × γ × Kh = 1.000 × 7.000 × 24.5 × 1.00 = 171.50 kN/m over its height H1 = 0.300 m,
    # resultant 51.45 kN = the 0600 pedestal weight, at 0.150 m above the beam top.
    pedestal = result.self_weight.pedestal
    assert (pedestal.along.value, pedestal.across.value, pedestal.value.value) == (1.0, 7.0, 171.5)
    assert value(pedestal.value) * D(0.3) == value(reaction.self_weight.pedestal.weight) == Decimal("51.45")
    member = next(m for m in frame.members if m.region is Region.PEDESTAL)
    loads = {load.member: (load.start.value, load.end.value) for load in result.basic(C.SELF_INERTIA).member_loads}
    assert loads[member.number] == (-171.5, -171.5)
    # Decisions 29, 80: the bearing loads act at the pedestal top, so the frame carries H × H1.
    # Moment about the footing base of case 6: 11530.00 × 10.600 = 122218.00 (= 11530 × 10.300 + 11530 × 0.300).
    (girder,) = result.basic(C.GIRDER_INERTIA).points
    assert (girder.anchor, girder.node, girder.h.value, girder.m.value) == (NodeRole.PEDESTAL_TOP, top.number,
                                                                            -11530.0, 0.0)
    assert -D(girder.h.value) * D(top.y.value) == Decimal("122218.000")
    (train,) = result.basic(C.TRAIN_INERTIA).points
    assert (train.node, train.h.value) == (top.number, -128.0)
    # The train table keeps the levers −f / +f from the column axis (M = −104.00 + 108.00 = 4.00); at the seat,
    # 0.175 m toward the end side, M = 4.00 − 480.00 × 0.175 = −80.00.
    assert result.train.m.value == 4.0
    (vertical,) = result.basic(C.TRAIN).points
    assert (vertical.node, vertical.n.value, vertical.h.value, vertical.m.value) == (top.number, 480.0, 0.0, -80.0)
    # D1: the girder loads at the seat, the levers from the pedestal centre, the beam at the beam top, as in 0610.
    d1 = points(result.basic(C.D1))
    assert d1[top.number][0] == 7600.0  # 5740 + 1860
    # 5740 × (−0.500) + 1860 × 0.500 = −1940.00 (= −610.00 − 7600.00 × 0.175)
    assert d1[top.number][2] == float(q(D(-610.0) - D(7600) * D("0.175"), 2)) == -1940.0
    assert set(d1) == {top.number, frame.node(NodeRole.CAP_TOP).number, frame.node(NodeRole.FOOTING_CENTROID).number}


def test_asymmetric_haunched_footing():
    changes = dims(B7=2.5, B9=1.8, H5=0.5, H6=2.2, B8=3.0, W8=5.0) | {"下部構造/土かぶり/終点側_df2": 1.5}
    _, reaction, longitudinal, result = chain(pier(**changes))
    footing = reaction.self_weight.footing
    inertia = result.self_weight.footing
    # H = V × (γ − γ') × Kh with the 0600 footing volume (haunch + prism), not the bounding B × W × H.
    assert inertia.volume == footing.volume
    assert value(inertia.force) == q(value(footing.volume) * (D(24.5) - D(18.0)) * D(1), 2)
    assert value(footing.volume) != D(7.0) * D(9.0) * D(2.7)
    frame = result.frame
    assert frame.node(NodeRole.FOOTING_TOP).x.value == 0.35  # column axis (B7 − B9)/2
    assert frame.node(NodeRole.FOOTING_CENTROID).y == footing.y
    assert points(result.basic(C.SELF_INERTIA)) == {frame.node(NodeRole.FOOTING_CENTROID).number: (
        0.0, -inertia.force.value, 0.0)}
    # The vertical cases are still those of 0610, with the asymmetric footing moments.
    theirs = longitudinal.basic(BasicCase.D1).points
    assert [(p.n, p.m) for p in result.basic(C.D1).points] == [(p.n, p.m) for p in theirs]


def test_displaced_soil_and_footing_unit_weights():
    # 170.100 × (25.0 − 19.5) × 1.00 = 935.55
    result = seismic(pier(**{WEIGHTS + "フーチング": 25.0, SURFACE_WET: 19.5}))
    footing = result.self_weight.footing
    assert (footing.unit_weight.value, footing.displaced.value, footing.force.value) == (25.0, 19.5, 935.55)


def test_buoyancy_is_the_normal_water_level():
    p = pier(**{"下部構造/水位/高水位_hw1": 4.5, "下部構造/水位/平水位_hw2": 1.2, "下部構造/水位/低水位_hw3": 0.5})
    _, reaction, longitudinal, result = chain(p)
    # Normal water 1.200 above the base: 63.000 × 1.200 = 75.600 m3 × −10.0 = −756.00 kN at the footing centroid.
    assert result.buoyancy == longitudinal.buoyancy[1]
    assert points(result.basic(C.BUOYANCY)) == {6: (-756.0, 0.0, 0.0)}
    dry = seismic(pier(**{"下部構造/水位/平水位_hw2": 0.0}))
    assert points(dry.basic(C.BUOYANCY)) == {6: (0.0, 0.0, 0.0)}


def test_snow_is_the_2_year_snow():
    p = pier(**{f"{ORIGIN_SLOTS}/0/雪荷重_2年確率": 210.0, f"{END_SLOTS}/1/雪荷重_2年確率": 135.0})
    _, _, longitudinal, result = chain(p)
    assert result.snow == longitudinal.snow[0]
    assert points(result.basic(C.SNOW)) == {1: (longitudinal.snow[0].n.value, 0.0, longitudinal.snow[0].m.value)}
    assert result.snow.n.value == 730.0  # 470 + 260


def test_bearing_side_signs_of_the_train_moment():
    result = seismic(pier(**{"上部構造/起点側/支承位置_f": 0.0, "上部構造/終点側/支承位置_f": 1.2}))
    rb, rc = result.train.row(Item.ORIGIN), result.train.row(Item.END)
    assert (rb.arm.value, rb.m.value) == (0.0, 0.0)
    assert value(rc.m) == q(D(160) * D(1.2), 2) == Decimal("192.00")


def test_footing_lighter_than_the_displaced_soil_stops_0710():
    # Decision 32: γ < γ' would give a footing inertia against the earthquake.
    with pytest.raises(InputError, match=r"下部構造\.単位体積重量\.フーチング.*地盤データ\.層\[0\]\.単位体積重量\.湿潤"):
        seismic(pier(**{WEIGHTS + "フーチング": 17.9}))


def test_footing_as_heavy_as_the_displaced_soil_has_no_inertia():
    # γ = γ': the footing moves as the soil it replaces; H = 170.100 × 0.0 × 1.00 = 0.00, a valid zero load.
    result = seismic(pier(**{WEIGHTS + "フーチング": 18.0}))
    assert result.self_weight.footing.force.value == 0.0
    assert points(result.basic(C.SELF_INERTIA)) == {6: (0.0, 0.0, 0.0)}

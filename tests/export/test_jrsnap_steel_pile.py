"""The NDU of a 鋼管ソイルセメント杭 (decision 122): the joint with the footing and the steel pipe of each pile row.

The input is Example橋脚4 (.claude/docs/Example橋脚4/pre/input.json: φ800 t18 (腐食代 1) SKK490, the joint D38-16 SD390 at 75 mm
with a fill of f'ck 27) with the conditions of JRSNAP of these tests, on the .sdc the real SOIL-JR 5.2 returned for it
(tests/fixtures/soiljr/pile_steel_grid.sdc, a regular grid: one column of springs for every row). The expected values are those of
the example (IV-14, IV-18, 表2.2.4〜2.2.7: the pipe less the corrosion, the virtual RC section of the joint of radius D/2), of the
JRSNAP manual (表2-53〜2-56, 4-6: the micro member of the M-θ of the joint, ≤ 10 mm, the rigid zone of 1.0D below it, then the
M-φ of the pipe) and of the .sdc.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

from steel_pile_ndu_support import SPRINGS, model
from webpier.core.errors import InputError
from webpier.export.jrsnap import LONGITUDINAL, TRANSVERSE, write_pile_ndu
from webpier.export.jrsnap.pile_model import COLUMN, M_PHI, M_THETA, PILE, RIGID
from webpier.export.jrsnap.records import UNSET


def records(found):
    return {key: values for group in found.sections for key, values in group}


def numbers(values):
    return [v if v is UNSET or isinstance(v, (int, str, Decimal)) else Decimal(repr(v.value)) for v in values]


def test_the_joint_is_section_2_the_virtual_rc_circle_of_the_pipe_with_its_anchor_bars():
    section = records(model())
    assert section["SectTitle2"] == ("結合部(R400)",)
    # 501, radius D/2 = 400, the effective thickness 18 − 1 = 17; the axial force of the analysis
    assert numbers(section["SectInfo2"]) == [1, 501, 0, 1, 400, 17, 0, 0, 0, 0, UNSET, 0, 0, 0]
    # the fill's f'ck, its 接合部圧縮強度 f'cck confined by the pipe (tests/calc/test_pile_joint.py), the aggregate of 結合部
    assert numbers(section["SectConc2"]) == [27, 0, 0, Decimal("74.5"), 25]
    assert numbers(section["SectJikuNum2"]) == [1, 0, 0, 0, 0, 0]
    assert numbers(section["SectJiku2"]) == [390, 200, 0, 0, 0, 0, 45, 0, 0]  # SD390, Es, the yield at 45°
    assert numbers(section["SectRein2-1"]) == [75, 38, 16]
    assert numbers(section["SectCFT2"]) == [0, 315, 200, 0, 0, 0, 0, 0]  # SKK490
    assert numbers(section["SectSher2"]) == [0] * 10
    # γc 1.3, γr 1.0, γs 1.05, the member factors 1.0, γb of the shear of the pipe 1.1, the Y point raised by k 0.9 (IV-10)
    assert numbers(section["SectSafe2"]) == [Decimal("1.3"), 1, Decimal("1.05"), 1, 1, 1, Decimal("1.1"), 0, 0,
                                             Decimal("0.9"), 0, 0]


def test_the_pipe_is_section_3_a_steel_circle_of_the_kind_steel_pipe_pile_less_the_corrosion():
    section = records(model())
    assert section["SectTitle3"] == ("鋼管杭(φ798×t17)",)
    # shape 8 of the kind 1 (鋼管杭); D 800 − 2 × 1, t 18 − 1; no shear span; the axial force of the analysis
    assert numbers(section["SectInfo3"]) == [1, 8, 1, 1, 798, 17, 0, 0, 0, 0, UNSET, 0, 0, 0]
    assert numbers(section["SectConc3"]) == [0] * 5 and numbers(section["SectJikuNum3"]) == [0] * 6
    assert numbers(section["SectJiku3"]) == [0] * 9 and not any(key.startswith("SectRein3") for key in section)
    assert numbers(section["IntSectMpile3"]) == [0, 0]
    # no diaphragm, no buckling length, f_syk 315, Es ν G automatic, the factor on the yield point 1.0 of a pile
    assert numbers(section["SectMpile3"]) == [0, 0, 315, 0, 0, 0, 1, 0]
    assert numbers(section["SectSher3"]) == [0] * 10
    # γs 1.05, the member factors of the damage levels 1.0, 1.1, 1.1 (IV-16), ALF 1.0, the Y point 0.9
    assert numbers(section["SectSafe3"]) == [0, 0, Decimal("1.05"), 1, Decimal("1.1"), Decimal("1.1"), 1, 1, 1,
                                             Decimal("0.9"), 0, 0]
    assert [key for key, _ in model().sections[2]] == [
        "SectTitle3", "SectInfo3", "TanbuShiji3", "SectConc3", "SectJikuNum3", "SectJiku3", "IntSectMpile3", "SectMpile3",
        "SectSher3", "SectSafe3"]


@pytest.mark.parametrize("profile", [LONGITUDINAL, TRANSVERSE])
def test_each_row_starts_with_the_micro_member_of_the_joint_then_the_rigid_zone_of_1d_then_the_pipe(profile):
    found = model(profile)
    joints = {joint.number: joint for joint in found.joints}
    elements = {element.number: element for element in found.elements}
    nonlinear = dict(enumerate(found.nonlinear, 1))
    members = {member.number: member for member in found.members}
    for pile in found.piles:
        member = members[pile.member]
        micro, rigid, first = elements[pile.first], elements[pile.first + 1], elements[pile.first + 2]
        head = joints[member.i]
        assert micro.i == member.i and (micro.kind, nonlinear[micro.nonlinear].section) == (COLUMN, 2)
        assert joints[micro.j].x == head.x and Decimal(repr(joints[micro.j].y.value)) - Decimal(repr(head.y.value)) == \
            Decimal("0.01")
        joint = nonlinear[micro.nonlinear]
        assert (joint.model, joint.failure, joint.ends, joint.depth_piles) == (M_THETA, 1, (1, 1), member.depth_piles)
        assert joint.title.startswith(f"結合部（{'３' if member.depth_piles == 3 else '２'}本杭）：要素番号　{micro.number}")
        assert (rigid.kind, rigid.nonlinear, rigid.i) == (RIGID, 0, micro.j)
        # the rigid zone ends 1.0D = 0.8 m below the head, where the pipe begins
        assert Decimal(repr(joints[rigid.j].y.value)) - Decimal(repr(head.y.value)) == Decimal("0.8")
        pipes = [elements[n] for n in range(pile.first + 2, pile.last + 1)]
        assert first.i == rigid.j and all(e.kind == PILE for e in pipes)
        for element in pipes:
            row = nonlinear[element.nonlinear]
            assert (row.section, row.model, row.failure, row.ends) == (3, M_PHI, 1, (0, 0))
            assert row.title.startswith("鋼管杭（") and row.title.endswith(f"：要素番号　{element.number}")
        assert [(length.value, count) for length, count in member.divisions[:2]] == [(0.01, 1), (0.79, 1)]
        assert Decimal(repr(member.length.value)) == Decimal("26.5")


def test_the_micro_member_and_the_rigid_zone_share_the_ground_of_the_first_element_of_the_pipe():
    """The pile row's first element (0 to 0.8 m of the layer 1 of the .sdc: k 56833 kN/m2, the pressure 1188.6 at the top and
    1188.6 + 431.4 × 0.8 / 3.75 = 1280.6 at 0.8 m, kN/m) is cut 0.01 m below the head: the pressure there is
    1188.6 + 431.4 × 0.01 / 3.75 = 1189.75, written 1189.8."""
    found = model()
    elements = {element.number: element for element in found.elements}
    pile = found.piles[0]
    micro, rigid = elements[pile.first].ground, elements[pile.first + 1].ground
    assert (micro.horizontal.value, micro.pressure_top.value, micro.pressure_bottom.value) == (56833.0, 1188.6, 1189.8)
    assert (rigid.horizontal.value, rigid.pressure_top.value, rigid.pressure_bottom.value) == (56833.0, 1189.8, 1280.6)


def test_the_sections_are_the_column_the_joint_and_the_pipe_whatever_the_hoops_of_a_cast_in_place_pile():
    found = model(TRANSVERSE)
    assert len(found.sections) == 3 and found.sections[0][0] == ("SectTitle1", found.sections[0][0][1])
    assert sum(1 for row in found.nonlinear if row.section == 1) == 1


def test_the_rows_of_a_grid_take_the_springs_of_their_place_from_the_front_of_the_push():
    """直角方向 of the .sdc: the pressure of the layer 3 at its top is 2267.1 for the 1列目, 1813.7 for the 2列目 and 1587.0 for
    the 3列目以降. 0720 pushes toward +x (the front row is the one at the largest x); its reversed combinations the other way."""
    def top_of_layer_3(found):
        elements = {element.number: element for element in found.elements}
        joints = {joint.number: joint for joint in found.joints}
        found_rows = []
        for pile in found.piles:
            head = Decimal(repr(joints[elements[pile.first].i].y.value))
            row = next(elements[n].ground.pressure_top.value for n in range(pile.first, pile.last + 1)
                       if Decimal(repr(joints[elements[n].i].y.value)) - head == Decimal("11.25"))
            found_rows.append((joints[elements[pile.first].i].x.value, row))
        return [pressure for _, pressure in sorted(found_rows)]

    assert top_of_layer_3(model(TRANSVERSE)) == [1587.0, 1813.7, 2267.1]
    assert top_of_layer_3(model(TRANSVERSE, reverse=True)) == [2267.1, 1813.7, 1587.0]


def test_the_ndu_is_written_with_the_records_of_the_two_sections():
    text = write_pile_ndu(model()).decode("cp932")
    assert "\r\nSectInfo3=1,8,1,1,798,17,0,0,0,0,-3.402823E+38,0,0,0\r\n" in text
    assert "\r\nIntSectMpile3=0,0\r\nSectMpile3=0,0,315,0,0,0,1,0\r\nSectSher3=" in text
    assert "\r\nSectRein2-1=75,38,16\r\nSectCFT2=0,315,200,0,0,0,0,0\r\nSectSher2=" in text


def test_the_rigid_zone_must_end_at_a_node_of_the_pipe():
    """The elements of the .sdc's layers begin at the head; a first layer thinner than 1.0D leaves no node at 0.8 m."""
    along = SPRINGS.direction("橋軸方向")
    layers = (replace(along.layers[0], thickness=0.5), replace(along.layers[1], thickness=10.75), *along.layers[2:])
    springs = replace(SPRINGS, directions=(replace(along, layers=layers), *SPRINGS.directions[1:]))
    with pytest.raises(InputError, match="結合部の剛域（1.0D＝0.8 m）の下端に杭の節点がありません"):
        model(springs=springs)


def test_a_pile_row_must_be_its_joint_its_rigid_zone_and_its_pipe_in_this_order():
    from webpier.export.jrsnap.pile_validate import check_model
    found = model()
    first = found.piles[0].first
    elements = list(found.elements)
    swapped = list(elements)
    swapped[first - 1] = replace(elements[first - 1], kind=RIGID)  # no micro member of the joint
    with pytest.raises(InputError, match="結合部の材端回転ばね・剛域・杭の順"):
        check_model(replace(found, elements=tuple(swapped)))
    piled = list(elements)
    piled[first + 2] = replace(elements[first + 2], kind=RIGID)  # a rigid element after a pile element
    piled[first + 3] = replace(elements[first + 3], kind=PILE)
    with pytest.raises(InputError, match="結合部の材端回転ばね・剛域・杭の順"):
        check_model(replace(found, elements=tuple(piled[:first + 2] + [replace(piled[first + 2], kind=PILE),
                                                                        replace(piled[first + 3], kind=RIGID)]
                                                    + piled[first + 4:])))
    with pytest.raises(InputError, match="要素 .* の種類と地盤ばねが杭の要素の範囲と合いません"):
        check_model(replace(found, elements=tuple(replace(e, ground=None) if e.number == first else e for e in elements)))

"""The NDU of a pile foundation (decision 93): its records are the ones JRSNAP saved for its sample RC橋脚L.

The sample (tests/fixtures/jrsnap/pile_s.ndu) is the file JRSNAP 5.3 saved after linking the .sdc of SOIL-JR 5.3 (pile_s53.sdc)
to a wall pier on 8 場所打ち杭. ``pile_ndu_support.sample_model`` builds the model of it: the column, the footing and a load
are written out, the piles come from ``calc.pile_seismic`` and ``pile_build``. Every record up to the loads is the sample's
but the ones listed in ``KNOWN`` (what the sample has because of the person or the program that made it, or the last digit of a
tie JRSNAP's Single arithmetic rounds the other way); the records after the loads are the shared ones of the NDU of a direct
foundation, which differ in the display settings and the soil layers the sample keeps.
"""

from dataclasses import replace
from decimal import Decimal

import pytest
from pile_ndu_support import pile_section, printed, sample_model, sample_records

from webpier.core.errors import InputError
from webpier.core.printed import LENGTH
from webpier.export.jrsnap.pile_build import pile_row_parts, support_values
from webpier.export.jrsnap.pile_model import PILE, RIGID, GroundElement, PileRange, Support
from webpier.export.jrsnap.pile_records import PILE_SAFETY, pile_section_records, records
from webpier.export.jrsnap.writer import line, write_pile_ndu

KNOWN = {
    "DataName", "DataTitle1", "DataTitle2", "DataTitle3", "DataTitle4",  # the names the person gave
    "DataInfo", "ExOptDisp",  # the analysis flags and the display option the program of the sample saved
    "SuppotInfo15", "SuppotInfo49",  # Kv2 2086.25: JRSNAP rounds down (Single), the exact decimal rounds up
}
LOADS = ("LoadNum", "MLoadNum", "JLoadNum", "LoadTitle", "LoadCase", "LoadAlph", "MLoadRow", "MLoadInfo", "JLoadRow",
         "JLoadInfo", "ELoad", "DLoad", "SNAPConb", "ConbNum", "ConbAlpf")
TAIL_KNOWN = {"TishouNum", "Tisou", "GanmaA", "FontSize", "SRenkeiNum", "SoilRenkeiFile1", "SoilRenkeiInfo1"}


def written(model=None):
    return [(key, line((key, values)).partition("=")[2]) for key, values in records(model or sample_model())]


def test_the_records_of_the_frame_the_sections_and_the_supports_are_the_samples():
    ours, sample = dict(written()), dict(sample_records())
    keys = [key for key, _ in written()]
    before = keys[:keys.index("LoadNum")]
    assert len(before) == 653  # the header, 69 joints, 6 members, 68 elements, 3 sections, 51 supports, …
    different = {key for key in before if ours[key] != sample[key]}
    assert different == KNOWN
    assert [key for key, _ in sample_records() if key not in ours and not key.startswith(LOADS)] == [
        "SRenkeiNum", "SoilRenkeiFile1", "SoilRenkeiInfo1"] and [
        key for key, _ in sample_records()[:len(before)] if key not in ours] == []
    # the sample's Kv2 at the two nodes is one tenth lower in its four columns of Kv2 (and what is copied from it)
    for node in ("SuppotInfo15", "SuppotInfo49"):
        got, want = ours[node].split(","), sample[node].split(",")
        assert [i for i, (g, w) in enumerate(zip(got, want)) if g != w] == [6, 9, 11, 12]
        assert [Decimal(got[i]) - Decimal(want[i]) for i in (6, 9, 11, 12)] == [Decimal("0.1")] * 4


def test_the_records_after_the_loads_are_the_shared_ones():
    ours, sample = dict(written()), dict(sample_records())
    keys = [key for key, _ in written()]
    after = keys[keys.index("PickNum"):]
    assert {key for key in after if ours[key] != sample[key]} == TAIL_KNOWN - {"SRenkeiNum", "SoilRenkeiFile1", "SoilRenkeiInfo1"}


def test_the_nonlinear_rows_name_the_head_the_2d_zone_and_the_rest_of_each_pile():
    rows = {key: value for key, value in written() if key.startswith("NonLinInfo")}
    assert rows["NonLinInfo1"] == "1,1,1,1,1,1,1,1,0,壁式橋脚く体：要素番号　2"
    assert rows["NonLinInfo2"] == "1,2,2,1,1,1,1,3,0,杭頭（３本杭）：要素番号　7"
    assert rows["NonLinInfo3"] == "1,2,2,1,1,0,0,3,0,杭（３本杭）(2D)：要素番号　8"
    assert rows["NonLinInfo4"] == "1,3,2,1,1,0,0,3,0,杭（３本杭）：要素番号　9"
    assert rows["NonLinInfo22"] == "1,2,2,1,1,1,1,2,0,杭頭（２本杭）：要素番号　28"


def test_a_circular_section_has_the_axial_force_only_when_it_is_given():
    section = dict(pile_section_records(2, pile_section(100)))
    assert section["SectInfo2"][5].value == 210 and section["SectConc2"][1:3] == (-3, -3)
    assert section["SectSher2"][2] == 2 and section["SectRein2-1"][0].value == 156
    assert dict(pile_section_records(2, pile_section(100, None)))["SectInfo2"][5] == 0
    assert section["SectSafe2"] == PILE_SAFETY and len(PILE_SAFETY) == 12


def test_the_nodes_of_a_row_have_the_supports_that_have_springs_and_the_sections_of_their_depths():
    model = sample_model()
    left = next(m for m in model.members if m.title == "杭（３本杭）")
    assert (left.i, left.j, left.length.value, left.depth_piles) == (4, 27, 20.307, 3)
    assert [(length.value, count) for length, count in left.divisions] == [
        (1.307, 1), (1.0, 2), (0.6, 1), (1.0, 13), (0.7, 2), (1.0, 2)]
    nodes = [support.node for support in model.supports]
    assert nodes == sorted(nodes) and len(nodes) == 51 and 10 not in nodes and 11 in nodes
    assert [r.section for r in model.nonlinear[1:3]] == [2, 2] and model.nonlinear[3].section == 3
    assert model.piles == (PileRange(4, 7, 26), PileRange(5, 28, 47), PileRange(6, 49, 68))
    rigid = [e for e in model.elements if e.kind == RIGID and e.ground is None]
    assert len(rigid) == 7 and all(e.ground is None for e in rigid)
    assert all(e.ground is not None for e in model.elements if e.kind == PILE)


def test_the_bytes_are_cp932_with_a_crlf_after_every_record():
    data = write_pile_ndu(sample_model())
    text = data.decode("cp932")
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "") and text.startswith("Virsion=5.2.3.S.4\r\n")
    assert "SoilRenkei" not in text and "SRenkeiNum" not in text  # the link is not written (decision 93)
    assert len(text.split("\r\n")) - 1 == len(records(sample_model()))


def test_a_text_that_does_not_fit_is_an_error():
    model = sample_model()
    long_title = replace(model.members[0], title="あ" * 21)
    with pytest.raises(InputError, match="40バイト以内"):
        write_pile_ndu(replace(model, members=(long_title, *model.members[1:])))


def broken(**changes):
    return replace(sample_model(), **changes)


def invalid(match: str, **changes):
    with pytest.raises(InputError, match=match):
        write_pile_ndu(broken(**changes))


def test_the_joints_must_be_numbered_from_one_and_stand_apart():
    model = sample_model()
    invalid("節点の番号は 1 から順に", joints=(replace(model.joints[0], number=2), *model.joints[1:]))
    invalid("同じ位置の節点", joints=(model.joints[0], replace(model.joints[1], x=model.joints[0].x, y=model.joints[0].y),
                                   *model.joints[2:]))
    invalid("原点または制御点", origin=999)
    invalid("原点または制御点", control=999)


def test_the_members_and_elements_must_be_numbered_from_one():
    model = sample_model()
    invalid("部材の番号は 1 から順に", members=(replace(model.members[0], number=9), *model.members[1:]))
    invalid("要素の番号は 1 から順に", elements=(replace(model.elements[0], number=9), *model.elements[1:]))


def test_a_member_must_join_joints_that_are_there_and_its_divisions_must_make_its_length_and_its_elements():
    model = sample_model()
    first = model.members[0]
    invalid("部材 1 の節点がありません", members=(replace(first, i=999), *model.members[1:]))
    invalid("部材 1 の分割の長さの合計", members=(replace(first, length=LENGTH(9.0)), *model.members[1:]))
    split = replace(first, divisions=((LENGTH(4), 2), *first.divisions[1:]))
    invalid("要素の数と違います", members=(split, *model.members[1:]))
    invalid("要素 1 の節点がありません", elements=(replace(model.elements[0], j=999), *model.elements[1:]))


def test_the_nonlinear_models_must_be_numbered_and_name_a_section_that_is_there():
    model = sample_model()
    invalid("非線形のある要素の番号", elements=(model.elements[0], replace(model.elements[1], nonlinear=5), *model.elements[2:]))
    invalid("断面番号 9 の断面がありません", nonlinear=(replace(model.nonlinear[0], section=9), *model.nonlinear[1:]))


def test_the_pile_rows_must_be_the_members_that_are_piles_and_their_elements_below_the_rigid_one():
    model = sample_model()
    invalid("部材 1 は杭の部材ではありません", piles=(PileRange(1, 7, 26), *model.piles[1:]))
    invalid("部材 9 は杭の部材ではありません", piles=(PileRange(9, 7, 26), *model.piles[1:]))
    invalid("KGInfo の要素（8〜26）", piles=(PileRange(4, 8, 26), *model.piles[1:]))
    elements = list(model.elements)
    elements[6] = replace(elements[6], kind=RIGID, ground=None)
    invalid("種類と地盤ばね", elements=tuple(elements))
    elements[6] = replace(model.elements[6], ground=None)
    invalid("種類と地盤ばね", elements=tuple(elements))


def test_the_supports_must_be_on_the_joints_in_order_with_their_values():
    model = sample_model()
    invalid("支点の節点は", supports=tuple(reversed(model.supports)))
    invalid("支点の節点は", supports=(replace(model.supports[0], node=999), *model.supports[1:]))
    invalid("支点の種類または値の数", supports=(replace(model.supports[0], kind=4), *model.supports[1:]))
    invalid("支点の種類または値の数", supports=(Support(model.supports[0].node, 2, ()), *model.supports[1:]))


def test_the_combinations_must_have_a_coefficient_for_each_case():
    model = sample_model()
    invalid("組合せの係数の数", combinations=(replace(model.combinations[0], coefficients=(1, 1)),))
    invalid("組合せの係数の数", cases=())


def test_the_support_values_are_in_the_order_jrsnap_saves_them():
    model = sample_model()
    row = next(s for s in model.supports if s.node == 12)
    assert [v.value for v in row.values] == [86169, 1153.6, 1153.6, 2350, 1357.2, 1357.2, 2350, 86169, 2350, 2350]
    assert [v.value for v in support_values(sample_model_springs())] == [v.value for v in row.values]


def sample_model_springs():
    from pile_ndu_support import SDC

    from webpier.calc.pile_seismic import pile_row
    from webpier.export.soiljr.sdc_seismic import parse_seismic

    row = pile_row(parse_seismic(SDC.read_bytes()).direction("橋軸方向"), 3, LENGTH(1.0))
    return row.nodes[5].springs  # node 12 of the left pile


def test_a_row_below_the_zone_and_a_ground_element_are_what_the_titles_and_the_springs_say():
    ground = GroundElement(printed(1, 0), printed(2, 1), printed(3, 1))
    assert (ground.horizontal.value, ground.pressure_bottom.value) == (1, 3)
    parts = pile_row_parts(
        _row(), member=4, head_joint=4, first_joint=7, x=printed(-3), top=LENGTH(1.307), rigid=LENGTH(1.307),
        first_element=6, first_nonlinear=2, section=lambda depth: 1, zone=LENGTH(0.0), title="杭")
    assert [r.title.split("：")[0] for r in parts.nonlinear][:3] == ["杭頭（３本杭）", "杭（３本杭）", "杭（３本杭）"]


def _row():
    from pile_ndu_support import SDC

    from webpier.calc.pile_seismic import pile_row
    from webpier.export.soiljr.sdc_seismic import parse_seismic

    return pile_row(parse_seismic(SDC.read_bytes()).direction("橋軸方向"), 3, LENGTH(1.0))

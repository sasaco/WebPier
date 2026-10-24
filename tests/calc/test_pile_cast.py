"""The pile body of a cast-in-place pile (decision 91): the section from the input, the design force cases WebPier chooses and the result
it holds; Capacita's check itself (RcDan's circular section) is the engine's, tried on the real runner."""

import pytest

from pile_cast_support import COMPRESSED, LINES, cast_input, cast_result, line
from webpier.calc.pile_body import PileResponseError
from webpier.calc.pile_cast import Kind, section, select
from webpier.core.errors import InputError


def test_the_section_is_the_input_with_the_centre_of_the_bars_from_the_clear_cover_hoop_and_half_a_bar():
    found = section(cast_input())
    assert (found.diameter.value, found.fck.value, found.condition) == (1000.0, 18.8, "自然泥水")
    assert (found.bar_diameter.value, found.bar_count, found.bar_area.value) == (32.0, 20, 15884.0)  # 794.2 mm2 × 20
    assert (found.cover.value, found.centre.value) == (100.0, 132.0)  # 100 + 16 + 32 / 2
    assert (found.bar_steel.fsy.value, found.bar_steel.fsu.value, found.hoop_steel.grade) == (345.0, 490.0, "SD345")
    assert (found.hoop_diameter.value, found.hoop_pitch.value) == (16.0, 200.0)


@pytest.mark.parametrize("group, key, name", [
    ("軸方向鉄筋", "径", "軸方向鉄筋.径"), ("軸方向鉄筋", "本数", "軸方向鉄筋.本数"), ("軸方向鉄筋", "材質", "軸方向鉄筋.材質"),
    ("軸方向鉄筋", "純かぶり", "軸方向鉄筋.純かぶり"), ("帯鉄筋", "径", "帯鉄筋.径"), ("帯鉄筋", "材質", "帯鉄筋.材質"),
    ("帯鉄筋", "間隔", "帯鉄筋.間隔")])
def test_a_blank_item_of_the_bars_is_named(group, key, name):
    bars = {"軸方向鉄筋": {"径": 32, "本数": 20, "材質": "SD345", "純かぶり": 100.0},
            "帯鉄筋": {"径": 16, "材質": "SD345", "間隔": 200.0}}
    bars[group][key] = None
    with pytest.raises(InputError, match=f"杭基礎.場所打ち杭.{name}: 杭体の照査に必要です"):
        section(cast_input(**bars))


def test_a_cover_that_leaves_no_room_for_the_bars_is_an_input_error():
    with pytest.raises(InputError, match="軸方向鉄筋.純かぶり: 杭径に対して大きすぎます"):
        section(cast_input(軸方向鉄筋={"径": 32, "本数": 20, "材質": "SD345", "純かぶり": 480.0}))


def test_a_size_with_no_nominal_area_is_an_input_error():
    with pytest.raises(InputError, match="軸方向鉄筋.径: D33 の公称断面積がありません"):
        section(cast_input(軸方向鉄筋={"径": 33, "本数": 20, "材質": "SD345", "純かぶり": 100.0}))
    with pytest.raises(InputError, match="帯鉄筋.径: D17 の公称断面積がありません"):
        section(cast_input(帯鉄筋={"径": 17, "材質": "SD345", "間隔": 200.0}))


def test_the_cases_are_the_largest_moment_shear_compression_and_tension_below_the_head_per_pile():
    row = select(1, 7, 3, LINES)
    assert (row.row, row.member, row.piles) == (1, 7, 3)
    assert [case.kind for case in row.cases] == [Kind.MOMENT, Kind.SHEAR, Kind.COMPRESSION, Kind.TENSION]
    moment, shear, compression, tension = row.cases
    # |1500| over the three piles, with its axial force 3000 as compression (FEMPython's −3000) and its shear 200
    assert (moment.md.value, moment.nd.value, moment.vd.value, moment.combination, moment.distance.value) == (
        500.0, 1000.0, 66.7, 5, 3.0)
    assert (shear.md.value, shear.nd.value, shear.vd.value, shear.combination) == (300.0, 966.7, 150.0, 7)
    assert (compression.nd.value, compression.combination, compression.distance.value) == (1600.0, 10, 19.0)
    assert (tension.nd.value, tension.combination) == (-200.0, 9)  # a tension is negative: Capacita's compression is positive


def test_the_moment_and_the_shear_are_their_absolute_values():
    lines = [line("M", "1", 1.0, (100.0, 10.0, -300.0, 1), (-900.0, -60.0, -300.0, 2)),
             line("S", "1", 1.0, (0.0, 30.0, -300.0, 3), (0.0, -120.0, -300.0, 4)),
             line("N", "1", 1.0, (0.0, 0.0, -300.0, 5), (0.0, 0.0, -300.0, 6))]
    moment, shear, *_ = select(1, 7, 3, lines).cases
    assert (moment.md.value, moment.vd.value, moment.combination) == (300.0, 20.0, 2)
    assert (shear.vd.value, shear.combination) == (40.0, 4)


def test_a_row_with_no_tension_has_no_tension_case():
    assert [case.kind for case in select(1, 7, 3, COMPRESSED).cases] == [Kind.MOMENT, Kind.SHEAR, Kind.COMPRESSION]


def test_a_member_with_no_point_below_the_head_for_a_case_is_named():
    with pytest.raises(PileResponseError, match="杭列 2（部材 8）の杭頭より下の断面力（曲げ最大）がありません"):
        select(2, 8, 3, [LINES[0], LINES[2], LINES[3]])
    with pytest.raises(PileResponseError, match="（圧縮最大）"):
        select(2, 8, 3, LINES[:3])


def test_the_result_holds_the_conditions_the_forces_and_capacitas_pages_but_no_judgement():
    found = cast_result()
    assert (found.engineering_status, found.engine_version, found.skipped) == ("not_evaluated", "5.0.1", ())
    assert (found.safety.id, found.safety.ri.value, found.safety.m_rbs.value) == (5, 1.2, 1.1)  # RC標準 R5, 安全性（破壊）
    assert found.pile_factor == ("pile-001", "泥水中に打込む", 0.8, 0.7, 0.8, 0.9)
    assert [row.piles for row in found.rows] == [3, 2] and set(found.pages) == {
        "bending_safety_destruction", "shear_safety_destruction"}


def test_the_stabilizing_fluid_selects_the_bentonite_row_of_the_pile_factors():
    from webpier.calc.pile_cast import pile_factor

    assert pile_factor(section(cast_input()))[0] == "pile-001"
    assert pile_factor(section(cast_input(施工条件="安定液使用")))[:2] == ("pile-003", "ベントナイト泥水")

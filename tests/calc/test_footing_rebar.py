"""0800 / 0810 / 0820 フーチングの配筋 (decision 60): what the footing section check is given from 鉄筋.フーチング.

The expected values are the sample 12_フーチング.pdf 255・258 (along the track D25@125 → 8本/m at centre 100,
across it D29@125 → 8本/m at 127, stirrups D16 2本/m @250, SD390, f'ck 27) and hand calculation; nothing is computed
by the code under test. Each direction reads its one lower main row and its one stirrup row; the upper rows are not
read. A blank, a pitch that does not divide 1 m, two layers or more, or a direction without exactly one lower main
row or one stirrup row is an input error naming its path.
"""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.calc.footing_rebar import LONGITUDINAL, TRANSVERSE, footing_reinforcement
from webpier.core.errors import InputError
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
FOOTING = "鉄筋.フーチング"
AT = "鉄筋/フーチング"  # the slash path document() takes


def row(direction, face, diameter=None, pitch=None, cover_mode="自動", center=None, stack_order=1, layers=1,
        material=None):
    return {"diameter_mm": diameter, "material": material, "cover_mode": cover_mode, "center_mm": center,
            "clear_gap_mm": None, "direction": direction, "face": face, "pitch_mm": pitch, "layers": layers,
            "stack_order": stack_order}


def stirrup(direction, diameter=16, pitch=250, mode="密度", density=2, width_pitch=None, material=None):
    return {"type": "内側", "direction": direction, "diameter_mm": diameter, "material": material, "sets": None,
            "pitch_mm": pitch, "start_mm": None, "end_mm": None, "legs_mode": "指定", "effective_legs": None,
            "distribution_mode": mode, "width_pitch_mm": width_pitch, "density_per_m": density}


def sample():
    """The sample's footing bars: main_rows 0 線路上, 1 線路下, 2 直角上, 3 直角下; band_rows 0 線路, 1 直角."""
    return {"materials": {"main": "SD390", "transverse": "SD390"}, "concrete_strength_mpa": 27, "aggregate_max_mm": 25,
            "pure_cover_mm": None,
            "main_rows": [row("線路", "上"), row("線路", "下", 25, 125, "指定", 100, 1), row("直角", "上", stack_order=2),
                          row("直角", "下", 29, 125, "指定", 127, 2)],
            "side_rows": [], "band_rows": [stirrup("線路"), stirrup("直角")], "manual_positions": [],
            "position_mode": "基本"}


def document(**changes):
    """current.json with the sample's footing bars, then each 'a/b/0/c' path replaced by its value."""
    data = deepcopy(CURRENT)
    data["鉄筋"]["フーチング"] = sample()
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value
    return data


def bars(direction=LONGITUDINAL, **changes):
    return footing_reinforcement(parse_input(document(**changes)), direction)


def fails(message, direction=LONGITUDINAL, **changes):
    with pytest.raises(InputError, match=re.escape(message)):
        bars(direction, **changes)


def test_along_the_track_the_lower_bars_and_stirrups_are_the_samples():
    found = bars()
    assert found.direction == "線路"
    assert (found.main.diameter.value, found.main.count, found.main.pitch.value, found.main.cover.value,
            found.main.grade) == (25, 8, 125, 100, "SD390")
    assert (found.stirrups.diameter.value, found.stirrups.legs, found.stirrups.pitch.value,
            found.stirrups.grade) == (16, 2, 250, "SD390")
    assert found.fck.value == 27


def test_across_the_track_the_lower_bars_are_the_other_direction():
    found = bars(TRANSVERSE)
    assert found.direction == "直角"
    assert (found.main.diameter.value, found.main.count, found.main.cover.value) == (29, 8, 127)
    assert (found.stirrups.diameter.value, found.stirrups.legs, found.stirrups.pitch.value) == (16, 2, 250)


def test_an_automatic_cover_adds_the_outer_layers_and_half_the_bar():
    # Hand calculation: 87.5 + 25 / 2 = 100.0 for the outermost layer; 87.5 + 25 + 29 / 2 = 127.0 inside it.
    automatic = {f"{AT}/pure_cover_mm": 87.5, f"{AT}/main_rows/1/cover_mode": "自動",
                 f"{AT}/main_rows/1/center_mm": None, f"{AT}/main_rows/3/cover_mode": "自動",
                 f"{AT}/main_rows/3/center_mm": None}
    assert bars(**automatic).main.cover.value == 100.0
    assert bars(TRANSVERSE, **automatic).main.cover.value == 127.0
    # The stack order decides which layer is outside: 87.5 + 29 + 25 / 2 = 129.0 when 直角 is outermost.
    swapped = {**automatic, f"{AT}/main_rows/1/stack_order": 2, f"{AT}/main_rows/3/stack_order": 1}
    assert bars(**swapped).main.cover.value == 129.0
    assert bars(TRANSVERSE, **swapped).main.cover.value == 102.0


@pytest.mark.parametrize("width_pitch,legs", [(500, 2), (250, 4), (125, 8)])
def test_stirrups_spaced_across_the_width_count_per_metre(width_pitch, legs):
    found = bars(**{f"{AT}/band_rows/0/distribution_mode": "間隔", f"{AT}/band_rows/0/density_per_m": None,
                    f"{AT}/band_rows/0/width_pitch_mm": width_pitch})
    assert found.stirrups.legs == legs


def test_the_row_material_comes_before_the_member_material():
    found = bars(**{f"{AT}/main_rows/1/material": "SD345", f"{AT}/band_rows/0/material": "SD295"})
    assert (found.main.grade, found.stirrups.grade) == ("SD345", "SD295")


def test_the_upper_rows_are_not_read():
    assert bars(**{f"{AT}/main_rows/0/stack_order": None, f"{AT}/main_rows/0/cover_mode": None}
                ).main.cover.value == 100


@pytest.mark.parametrize("changes,message", [
    ({f"{AT}/main_rows/1/diameter_mm": None}, f"{FOOTING}.main_rows[1].diameter_mm: 値が必要です"),
    ({f"{AT}/main_rows/1/pitch_mm": None}, f"{FOOTING}.main_rows[1].pitch_mm: 値が必要です"),
    ({f"{AT}/main_rows/1/pitch_mm": 150},
     f"{FOOTING}.main_rows[1].pitch_mm: 1 m 当たりの本数が整数になりません（1000／150.0）"),
    ({f"{AT}/main_rows/1/layers": None}, f"{FOOTING}.main_rows[1].layers: 値が必要です"),
    ({f"{AT}/main_rows/1/layers": 2}, f"{FOOTING}.main_rows[1].layers: 2段以上は表せません"),
    ({f"{AT}/main_rows/0/face": "下"}, f"{FOOTING}.main_rows: 線路方向の下側の主鉄筋の行がちょうど1行必要です（2行）"),
    ({f"{AT}/main_rows/1/face": "上"}, f"{FOOTING}.main_rows: 線路方向の下側の主鉄筋の行がちょうど1行必要です（0行）"),
    ({f"{AT}/main_rows/1/cover_mode": None}, f"{FOOTING}.main_rows[1].cover_mode: 値が必要です"),
    ({f"{AT}/main_rows/1/center_mm": None}, f"{FOOTING}.main_rows[1].center_mm: 値が必要です"),
    ({f"{AT}/main_rows/1/cover_mode": "自動"}, f"{FOOTING}.pure_cover_mm: 値が必要です"),
    ({f"{AT}/main_rows/1/cover_mode": "自動", f"{AT}/pure_cover_mm": 87.5,
      f"{AT}/main_rows/1/stack_order": None}, f"{FOOTING}.main_rows[1].stack_order: 値が必要です"),
    ({f"{AT}/main_rows/3/cover_mode": "自動", f"{AT}/pure_cover_mm": 87.5,
      f"{AT}/main_rows/1/diameter_mm": None}, f"{FOOTING}.main_rows[1].diameter_mm: 値が必要です"),
    ({f"{AT}/main_rows/1/cover_mode": "自動", f"{AT}/pure_cover_mm": 87.5,
      f"{AT}/main_rows/1/stack_order": 2},
     f"{FOOTING}.main_rows: 下側の主鉄筋の重ね順 2 が2行にあります"),
    ({f"{AT}/materials/main": None},
     f"{FOOTING}.main_rows[1].material: 値が必要です（行と{FOOTING}.materials.main が空欄）"),
    ({f"{AT}/band_rows/0/direction": "直角"}, f"{FOOTING}.band_rows: 線路方向のスターラップの行がちょうど1行必要です（0行）"),
    ({f"{AT}/band_rows/1/direction": "線路"}, f"{FOOTING}.band_rows: 線路方向のスターラップの行がちょうど1行必要です（2行）"),
    ({f"{AT}/band_rows/0/diameter_mm": None}, f"{FOOTING}.band_rows[0].diameter_mm: 値が必要です"),
    ({f"{AT}/band_rows/0/pitch_mm": None}, f"{FOOTING}.band_rows[0].pitch_mm: 値が必要です"),
    ({f"{AT}/band_rows/0/distribution_mode": None}, f"{FOOTING}.band_rows[0].distribution_mode: 値が必要です"),
    ({f"{AT}/band_rows/0/density_per_m": None}, f"{FOOTING}.band_rows[0].density_per_m: 値が必要です"),
    ({f"{AT}/band_rows/0/density_per_m": 2.5},
     f"{FOOTING}.band_rows[0].density_per_m: 1 m 当たりの本数が整数になりません（2.5）"),
    ({f"{AT}/band_rows/0/distribution_mode": "間隔"}, f"{FOOTING}.band_rows[0].width_pitch_mm: 値が必要です"),
    ({f"{AT}/band_rows/0/distribution_mode": "間隔", f"{AT}/band_rows/0/width_pitch_mm": 300},
     f"{FOOTING}.band_rows[0].width_pitch_mm: 1 m 当たりの本数が整数になりません（1000／300.0）"),
    ({f"{AT}/materials/transverse": None},
     f"{FOOTING}.band_rows[0].material: 値が必要です（行と{FOOTING}.materials.transverse が空欄）"),
])
def test_a_layout_the_check_cannot_be_given_is_an_input_error(changes, message):
    fails(message, **changes)


def test_across_the_track_the_errors_name_that_directions_rows():
    fails(f"{FOOTING}.main_rows[3].diameter_mm: 値が必要です", TRANSVERSE, **{f"{AT}/main_rows/3/diameter_mm": None})
    fails(f"{FOOTING}.band_rows: 直角方向のスターラップの行がちょうど1行必要です（0行）", TRANSVERSE,
          **{f"{AT}/band_rows/1/direction": "線路"})

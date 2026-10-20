"""0800 / 0810 / 0820 フーチングの配筋 (decision 60): what the footing section check is given from 鉄筋.フーチング.

The expected values are the sample 12_フーチング.pdf 255・258 (along the track D25@125 → 8本/m at centre 100,
across it D29@125 → 8本/m at 127, stirrups D16 2本/m @250, SD390, f'ck 27) and hand calculation; nothing is computed
by the code under test. Each direction reads its bars on the lower face and its stirrups; the upper face is not read.
The bars per metre may be fractional and lie in layers as Capacita splits them (decision 68); a blank or what
Capacita cannot be given is an input error naming its path.
"""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.calc.footing_rebar import LONGITUDINAL, TRANSVERSE, footing_reinforcement
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
FOOTING = "鉄筋.フーチング"
AT = "鉄筋/フーチング"  # the slash path document() takes
LOWER = f"{AT}/faces/下"
RAIL = f"{LOWER}/線路"


def _bars(diameter=None, pitch=None, cover_mode="自動", center=None):
    return {"diameter_mm": diameter, "pitch_mm": pitch, "cover_mode": cover_mode, "center_mm": center,
            "inner_layers": []}


def stirrup(diameter=16, pitch=250, mode="密度", density=2, width_pitch=None):
    return {"diameter_mm": diameter, "pitch_mm": pitch, "distribution_mode": mode, "width_pitch_mm": width_pitch,
            "density_per_m": density}


def sample():
    """The sample's footing bars: on the lower face 線路 D25@125 at 100 (outside) and 直角 D29@125 at 127; the upper
    face blank; the stirrups of both directions D16 2本/m @250."""
    return {"materials": {"main": "SD390", "transverse": "SD390"}, "concrete_strength_mpa": 27, "aggregate_max_mm": 25,
            "pure_cover_mm": None,
            "faces": {"上": {"outer_direction": "線路", "線路": _bars(), "直角": _bars()},
                      "下": {"outer_direction": "線路", "線路": _bars(25, 125, "指定", 100),
                             "直角": _bars(29, 125, "指定", 127)}},
            "stirrups": {"線路": stirrup(), "直角": stirrup()}}


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
    main = found.main
    assert (main.diameter.value, main.count.value, main.pitch.value, main.cover.value, main.grade) == (
        25, 8, 125, 100, "SD390")
    assert (main.counts, main.layer_spacing, main.centroid) == ((Printed(8, 2, "本"),), None, main.cover)
    assert (found.stirrups.diameter.value, found.stirrups.legs.value, found.stirrups.pitch.value,
            found.stirrups.grade) == (16, 2, 250, "SD390")
    assert found.fck.value == 27


def test_across_the_track_the_lower_bars_are_the_other_direction():
    found = bars(TRANSVERSE)
    assert found.direction == "直角"
    assert (found.main.diameter.value, found.main.count.value, found.main.cover.value) == (29, 8, 127)
    assert (found.stirrups.diameter.value, found.stirrups.legs.value, found.stirrups.pitch.value) == (16, 2, 250)


def test_a_pitch_that_does_not_divide_a_metre_gives_a_fraction():
    assert bars(**{f"{RAIL}/pitch_mm": 130}).main.count == Printed(7.69, 2, "本")  # 1000／130 = 7.692…


def test_an_automatic_cover_adds_the_outer_layer_and_half_the_bar():
    # Hand calculation: 87.5 + 25 / 2 = 100.0 for the direction outside; 87.5 + 25 + 29 / 2 = 127.0 inside it.
    automatic = {f"{AT}/pure_cover_mm": 87.5, f"{RAIL}/cover_mode": "自動", f"{RAIL}/center_mm": None,
                 f"{LOWER}/直角/cover_mode": "自動", f"{LOWER}/直角/center_mm": None}
    assert bars(**automatic).main.cover.value == 100.0
    assert bars(TRANSVERSE, **automatic).main.cover.value == 127.0
    # The direction outside is chosen: 87.5 + 29 + 25 / 2 = 129.0 when 直角 is outside, 87.5 + 29 / 2 = 102.0.
    swapped = {**automatic, f"{LOWER}/outer_direction": "直角"}
    assert bars(**swapped).main.cover.value == 129.0
    assert bars(TRANSVERSE, **swapped).main.cover.value == 102.0


def test_layers_inside_lie_a_bar_and_the_gap_further_in():
    two = bars(**{f"{RAIL}/inner_layers": [{"pitch_mm": 125, "clear_gap_mm": 25}]}).main
    # 8 + 8 per metre; 100 and 100 + 25 + 25 = 150; the centroid (8 × 100 + 8 × 150) / 16 = 125.
    assert (two.count.value, two.counts, two.layer_spacing.value, two.centroid.value) == (
        16, (Printed(8, 2, "本"), Printed(8, 2, "本")), 50, 125)
    fewer = bars(**{f"{RAIL}/inner_layers": [{"pitch_mm": 250, "clear_gap_mm": 25}]}).main
    assert (fewer.count.value, fewer.centroid.value) == (12, 116.7)  # (8 × 100 + 4 × 150) / 12 = 116.67


@pytest.mark.parametrize("width_pitch,legs", [(500, 2), (250, 4), (125, 8), (300, 3.33)])
def test_stirrups_spaced_across_the_width_count_per_metre(width_pitch, legs):
    found = bars(**{f"{AT}/stirrups/線路/distribution_mode": "間隔", f"{AT}/stirrups/線路/density_per_m": None,
                    f"{AT}/stirrups/線路/width_pitch_mm": width_pitch})
    assert found.stirrups.legs == Printed(legs, 2, "本")


def test_a_fractional_density_is_kept():
    assert bars(**{f"{AT}/stirrups/線路/density_per_m": 2.5}).stirrups.legs == Printed(2.5, 2, "本")


def test_the_grades_are_the_members():
    found = bars(**{f"{AT}/materials/main": "SD345", f"{AT}/materials/transverse": "SD295"})
    assert (found.main.grade, found.stirrups.grade) == ("SD345", "SD295")


def test_the_upper_face_is_not_read():
    assert bars(**{f"{AT}/faces/上/outer_direction": None, f"{AT}/faces/上/線路/cover_mode": None}
                ).main.cover.value == 100


@pytest.mark.parametrize("changes,message", [
    ({f"{RAIL}/diameter_mm": None}, f"{FOOTING}.faces.下.線路.diameter_mm: 値が必要です"),
    ({f"{RAIL}/pitch_mm": None}, f"{FOOTING}.faces.下.線路.pitch_mm: 値が必要です"),
    ({f"{RAIL}/cover_mode": None}, f"{FOOTING}.faces.下.線路.cover_mode: 値が必要です"),
    ({f"{RAIL}/center_mm": None}, f"{FOOTING}.faces.下.線路.center_mm: 値が必要です"),
    ({f"{RAIL}/cover_mode": "自動"}, f"{FOOTING}.pure_cover_mm: 値が必要です"),
    ({f"{RAIL}/cover_mode": "自動", f"{AT}/pure_cover_mm": 87.5, f"{LOWER}/outer_direction": None},
     f"{FOOTING}.faces.下.outer_direction: 値が必要です"),
    ({f"{RAIL}/inner_layers": [{"pitch_mm": None, "clear_gap_mm": 25}]},
     f"{FOOTING}.faces.下.線路.inner_layers[0].pitch_mm: 値が必要です"),
    ({f"{RAIL}/inner_layers": [{"pitch_mm": 125, "clear_gap_mm": None}]},
     f"{FOOTING}.faces.下.線路.inner_layers[0].clear_gap_mm: 値が必要です"),
    ({f"{RAIL}/inner_layers": [{"pitch_mm": 125, "clear_gap_mm": 25}, {"pitch_mm": 125, "clear_gap_mm": 30}]},
     f"{FOOTING}.faces.下.線路.inner_layers: 段のあきが一定ではないため表せません"),
    ({f"{RAIL}/inner_layers": [{"pitch_mm": 100, "clear_gap_mm": 25}]},  # 10 per metre after 8
     f"{FOOTING}.faces.下.線路.inner_layers: 段の 1 m 当たり本数は"),
    ({f"{RAIL}/inner_layers": [{"pitch_mm": 250, "clear_gap_mm": 25}, {"pitch_mm": 125, "clear_gap_mm": 25}]},
     f"{FOOTING}.faces.下.線路.inner_layers: 段の 1 m 当たり本数は"),
    ({f"{RAIL}/pitch_mm": 150, f"{RAIL}/inner_layers": [{"pitch_mm": 150, "clear_gap_mm": 25}] * 2},  # 20.01／6.67
     f"{FOOTING}.faces.下.線路.inner_layers: 1 m 当たり本数の合計 20.01 を1段目の 6.67 で割ると、"
     "Capacita では3段になりません"),
    ({f"{AT}/materials/main": None}, f"{FOOTING}.materials.main: 値が必要です"),
    ({f"{AT}/stirrups/線路/diameter_mm": None}, f"{FOOTING}.stirrups.線路.diameter_mm: 値が必要です"),
    ({f"{AT}/stirrups/線路/pitch_mm": None}, f"{FOOTING}.stirrups.線路.pitch_mm: 値が必要です"),
    ({f"{AT}/stirrups/線路/distribution_mode": None}, f"{FOOTING}.stirrups.線路.distribution_mode: 値が必要です"),
    ({f"{AT}/stirrups/線路/density_per_m": None}, f"{FOOTING}.stirrups.線路.density_per_m: 値が必要です"),
    ({f"{AT}/stirrups/線路/distribution_mode": "間隔"}, f"{FOOTING}.stirrups.線路.width_pitch_mm: 値が必要です"),
    ({f"{AT}/materials/transverse": None}, f"{FOOTING}.materials.transverse: 値が必要です"),
])
def test_a_layout_the_check_cannot_be_given_is_an_input_error(changes, message):
    fails(message, **changes)


def test_across_the_track_the_errors_name_that_directions_bars():
    fails(f"{FOOTING}.faces.下.直角.diameter_mm: 値が必要です", TRANSVERSE, **{f"{LOWER}/直角/diameter_mm": None})
    fails(f"{FOOTING}.stirrups.直角.pitch_mm: 値が必要です", TRANSVERSE, **{f"{AT}/stirrups/直角/pitch_mm": None})
    # inside, the automatic cover needs the size of the direction outside
    fails(f"{FOOTING}.faces.下.線路.diameter_mm: 値が必要です", TRANSVERSE,
          **{f"{AT}/pure_cover_mm": 87.5, f"{LOWER}/直角/cover_mode": "自動", f"{RAIL}/diameter_mm": None})

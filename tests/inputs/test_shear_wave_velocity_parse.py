"""The shear wave velocity Vs of a layer (decision 97, CONTEXT.md 地盤変位).

The 地盤変位 of a pile foundation on G3〜G5 is calculated from the layers' Vs and 湿潤 unit weight; the key may be left out,
so an input made before decision 97 reads as blank, and a blank is an input error only where the 地盤変位 needs it.
"""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.inputs import parse_input

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
KEY = "せん断弾性波速度_Vs"


def test_a_layer_without_the_key_has_a_blank_vs():
    pier = parse_input(deepcopy(CURRENT))
    assert all(layer.shear_wave_velocity is None for layer in pier.soil.layers)


def test_a_layer_may_enter_vs_in_whole_metres_per_second_or_leave_it_blank():
    data = deepcopy(CURRENT)
    data["地盤データ"]["層"][1][KEY] = 170
    data["地盤データ"]["層"][0][KEY] = None
    layers = parse_input(data).soil.layers
    assert layers[1].shear_wave_velocity.value == 170 and layers[1].shear_wave_velocity.unit == "m/s"
    assert layers[0].shear_wave_velocity is None


@pytest.mark.parametrize("value,message", [(0, "正の数値が必要です"), (-10, "正の数値が必要です"),
                                           (170.5, "小数0桁までで入力してください")])
def test_vs_is_a_positive_whole_number(value, message):
    data = deepcopy(CURRENT)
    data["地盤データ"]["層"][1][KEY] = value
    with pytest.raises(InputError, match=re.escape(f"地盤データ.層[1].{KEY}: ") + ".*" + re.escape(message)):
        parse_input(data)

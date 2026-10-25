"""The cover of the footing on a pile foundation (decision 93): the layers go on below the footing along the piles, so the
soil the footing displaces is what the layers fill of Df, from the ground (tests/fixtures/inputs/pile.json: 表層 2.8 m = Df)."""

from dataclasses import replace
from pathlib import Path

import pytest

from webpier.calc.embedment import displaced_soil, pile_cover_layers
from webpier.calc.foundation import surface_thickness
from webpier.core.errors import InputError
from webpier.core.integrity import load_json
from webpier.core.printed import LENGTH
from webpier.inputs import parse_input

PIER = parse_input(load_json((Path(__file__).parents[1] / "fixtures" / "inputs" / "pile.json").read_bytes()))


def with_layers(**first):
    layers = list(PIER.soil.layers)
    layers[0] = replace(layers[0], **first)
    return replace(PIER, soil=replace(PIER.soil, layers=tuple(layers)))


def test_the_cover_is_the_first_layer_when_it_fills_df():
    layers = pile_cover_layers(PIER, surface_thickness(PIER))
    assert [(layer.index, layer.thickness.value, layer.bottom.value) for layer in layers] == [(0, 2.8, 0.0)]


def test_a_layer_is_cut_at_df_and_a_blank_thickness_takes_what_is_left():
    layers = pile_cover_layers(PIER, LENGTH(4.0))
    assert [(layer.index, layer.thickness.value, layer.bottom.value) for layer in layers] == [(0, 2.8, 1.2), (1, 1.2, 0.0)]
    blank = pile_cover_layers(with_layers(thickness=None), LENGTH(2.8))
    assert [(layer.index, layer.thickness.value) for layer in blank] == [(0, 2.8)]


def test_the_layers_must_fill_df_and_have_their_unit_weights():
    layers = list(PIER.soil.layers)
    layers[-1] = replace(layers[-1], thickness=LENGTH(1.0))  # every layer has its thickness: nothing takes what is left
    thick = replace(PIER, soil=replace(PIER.soil, layers=tuple(layers)))
    with pytest.raises(InputError, match="層厚の合計が Df（100.000 m）に足りません"):
        pile_cover_layers(thick, LENGTH(100.0))
    with pytest.raises(InputError, match=r"層\[0\]\.単位体積重量\.湿潤"):
        pile_cover_layers(with_layers(unit_weight_wet=None), LENGTH(2.8))
    with pytest.raises(InputError, match=r"層\[0\]\.単位体積重量\.水中"):
        pile_cover_layers(with_layers(unit_weight_submerged=None), LENGTH(2.8))


def test_the_soil_a_footing_on_piles_displaces_is_the_cover_within_its_height():
    soil = displaced_soil(PIER, LENGTH(1.35))
    assert soil.height.value == 1.35 and [layer.index for layer, _ in soil.parts] == [0]
    assert soil.unit_weight.value == PIER.soil.layers[0].unit_weight_wet.value

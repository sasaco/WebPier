"""The 出力項目 of the input (decision 72, ADR-0011, CONTEXT.md 出力項目).

Twelve items, each true or false and all required; an item may be true only with every item it uses, and at least
one must be chosen. Nothing is filled in: an input without them is an input error (no compatibility reading).
"""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.inputs import parse_input
from webpier.inputs.fields import field
from webpier.inputs.outputs import OUTPUT_KEYS, requires, users, uses

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
CURRENT_ITEMS = ("ground_model", "reactions", "longitudinal", "transverse", "longitudinal_seismic", "transverse_seismic")


def choosing(*items):
    document = deepcopy(CURRENT)
    document["outputs"] = {key: key in items for key in OUTPUT_KEYS}
    return document


def fails(document, message):
    with pytest.raises(InputError, match=re.escape(message)):
        parse_input(document)


def test_the_items_and_what_each_uses():
    """The table of decision 72, in the order of the screen."""
    assert OUTPUT_KEYS == ("ground_model", "reactions", "longitudinal", "longitudinal_frame_analysis", "transverse",
                           "transverse_frame_analysis", "longitudinal_seismic", "longitudinal_nonlinear_analysis",
                           "transverse_seismic", "transverse_nonlinear_analysis", "footing", "cantilever")
    assert {key: requires(key) for key in OUTPUT_KEYS} == {
        "ground_model": (), "reactions": (), "longitudinal": ("ground_model", "reactions"),
        "longitudinal_frame_analysis": ("longitudinal",), "transverse": ("ground_model", "reactions"),
        "transverse_frame_analysis": ("transverse",), "longitudinal_seismic": ("longitudinal",),
        "longitudinal_nonlinear_analysis": ("longitudinal_seismic",), "transverse_seismic": ("transverse",),
        "transverse_nonlinear_analysis": ("transverse_seismic",),
        "footing": ("longitudinal_frame_analysis", "transverse_frame_analysis", "longitudinal_nonlinear_analysis",
                    "transverse_nonlinear_analysis"),
        "cantilever": ("longitudinal_nonlinear_analysis", "transverse_nonlinear_analysis")}


def test_uses_and_users_follow_the_table_through_other_items():
    assert uses("cantilever") == {"longitudinal_nonlinear_analysis", "transverse_nonlinear_analysis",
                                  "longitudinal_seismic", "transverse_seismic", "longitudinal", "transverse",
                                  "ground_model", "reactions"}
    assert uses("ground_model") == frozenset()
    assert users("longitudinal_seismic") == ("longitudinal_nonlinear_analysis", "footing", "cantilever")
    assert users("reactions") == tuple(key for key in OUTPUT_KEYS if key not in ("ground_model", "reactions"))
    assert users("cantilever") == ()


def test_the_current_input_chooses_the_items_without_analyses():
    assert parse_input(deepcopy(CURRENT)).outputs == CURRENT_ITEMS
    assert parse_input(choosing(*OUTPUT_KEYS)).outputs == OUTPUT_KEYS
    assert parse_input(choosing("reactions")).outputs == ("reactions",)


def test_every_item_is_a_true_or_false_field():
    assert all(field(f"outputs.{key}").kind == "boolean" for key in OUTPUT_KEYS)


@pytest.mark.parametrize("value", [None, 1, 0, "true", []])
def test_an_item_is_true_or_false_only(value):
    document = choosing(*CURRENT_ITEMS)
    document["outputs"]["ground_model"] = value
    fails(document, f"outputs.ground_model: true か false が必要です（入力: {value!r}）")


def test_the_items_are_required_and_nothing_else_is_allowed():
    document = deepcopy(CURRENT)
    del document["outputs"]
    fails(document, "入力項目がありません: outputs")
    document = choosing(*CURRENT_ITEMS)
    del document["outputs"]["footing"]
    fails(document, "入力項目がありません: outputs.footing")
    document = choosing(*CURRENT_ITEMS)
    document["outputs"]["all"] = True
    fails(document, "outputs.all: 未知の入力項目です")
    document = deepcopy(CURRENT)
    document["outputs"] = ["ground_model"]
    fails(document, "outputs: オブジェクトが必要です")


@pytest.mark.parametrize("items,message", [
    (("longitudinal",), "outputs.longitudinal: outputs.ground_model・outputs.reactions も true が必要です"),
    (("ground_model", "reactions", "longitudinal_frame_analysis"),
     "outputs.longitudinal_frame_analysis: outputs.longitudinal も true が必要です"),
    ((*CURRENT_ITEMS, "longitudinal_frame_analysis", "transverse_frame_analysis", "longitudinal_nonlinear_analysis",
      "footing"), "outputs.footing: outputs.transverse_nonlinear_analysis も true が必要です"),
    ((*CURRENT_ITEMS, "cantilever"),
     "outputs.cantilever: outputs.longitudinal_nonlinear_analysis・outputs.transverse_nonlinear_analysis も true が必要です"),
])
def test_an_item_is_chosen_only_with_every_item_it_uses(items, message):
    fails(choosing(*items), message)


def test_an_input_choosing_nothing_is_an_error():
    """Decision 72: a generation that makes nothing is not a success."""
    fails(choosing(), "outputs: 出力項目が選ばれていません（どれかを true にしてください）")

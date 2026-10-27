"""The 0600 result as a whole: printed values only, immutable, and input errors for impossible numbers."""

import dataclasses
from enum import Enum

import pytest

from reaction_support import pier
from webpier.calc.reaction import ReactionResult, calculate_reaction
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs.model import Bearing


def leaves(node, path="result"):
    if isinstance(node, (Printed, Enum, Bearing)) or node is None:
        yield path, node
    elif dataclasses.is_dataclass(node):
        for field in dataclasses.fields(node):
            yield from leaves(getattr(node, field.name), f"{path}.{field.name}")
    elif isinstance(node, tuple):
        for index, item in enumerate(node):
            yield from leaves(item, f"{path}[{index}]")
    else:
        yield path, node


def test_every_number_is_a_printed_value():
    result = calculate_reaction(pier())
    assert isinstance(result, ReactionResult)
    loose = [(path, leaf) for path, leaf in leaves(result)
             if not isinstance(leaf, (Printed, Enum, Bearing, bool)) and leaf is not None and not path.endswith(".slot")
             and not path.endswith("loading.train")]  # the adopted train's name (decision 101)
    assert loose == []


def test_result_is_immutable():
    result = calculate_reaction(pier())
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.dead = None


def test_symmetric_pier_has_no_transverse_moment():
    weight = calculate_reaction(pier()).self_weight
    assert weight.pier_bottom.moment_c.value == 0.0
    assert weight.footing_centre.moment_c.value == 0.0


def test_numbers_too_large_to_calculate_are_input_errors():
    with pytest.raises(InputError, match="0600"):
        calculate_reaction(pier(**{"下部構造/寸法/側面/B6": 1e200, "下部構造/寸法/正面/W6": 1e200}))


def test_input_errors_pass_through_unchanged():
    with pytest.raises(InputError, match="スパン長"):
        calculate_reaction(pier(**{"上部構造/起点側/桁長/スパン長": 250.0}))

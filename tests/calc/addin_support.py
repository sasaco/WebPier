"""The test load model (tests/fixtures/addin/minimal) on the input current.json, for the calculations of decision 70.

The module is read by its path, as the pipeline reads an add-in; the result is checked like the pipeline checks it.
"""

from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from webpier.calc.bearing_actions import load_model_context
from webpier.calc.foundation import calculate_foundation
from webpier.calc.reaction import calculate_dead_reaction
from webpier.inputs import parse_input
from webpier.loadmodel import validate

FIXTURES = Path(__file__).parents[1] / "fixtures"
ADDIN = FIXTURES / "addin" / "minimal"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))


def addin_module():
    spec = spec_from_file_location("minimal_load_model_for_tests", ADDIN / "minimal_load_model.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def document():
    """current.json with the train left in it, as P7 keeps the values the editor wrote."""
    return deepcopy(CURRENT)


def pier(data=None):
    return parse_input(document() if data is None else data, load_model=True)


def model(p=None):
    p = p or pier()
    context = load_model_context(p, Path("input.json"))
    return validate(addin_module().load_model().calculate(context), context)


def chain(p=None):
    """(pier, 0500, the 0600 of a load model, the load model's result)."""
    p = p or pier()
    return p, calculate_foundation(p), calculate_dead_reaction(p), model(p)

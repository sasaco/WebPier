"""The generic results of the test load model (tests/fixtures/addin/minimal) for the export tests (decision 70)."""

from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from webpier.calc.bearing_actions import load_model_context
from webpier.calc.foundation import calculate_foundation
from webpier.calc.frame import Direction
from webpier.calc.generic.frame import calculate_generic_frame
from webpier.calc.reaction import calculate_dead_reaction
from webpier.inputs import parse_input
from webpier.loadmodel import validate

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))


def generic_chain():
    """(pier, 0500, the 0600 of a load model, the load model's result) of current.json."""
    pier = parse_input(deepcopy(CURRENT), load_model=True)
    spec = spec_from_file_location("minimal_load_model_for_export", FIXTURES / "addin" / "minimal" / "minimal_load_model.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    context = load_model_context(pier, Path("input.json"))
    return pier, calculate_foundation(pier), calculate_dead_reaction(pier), validate(
        module.load_model().calculate(context), context)


def generic_frame(direction: Direction = Direction.LONGITUDINAL):
    pier, foundation, reaction, model = generic_chain()
    stage = "0610" if direction is Direction.LONGITUDINAL else "0620"
    return calculate_generic_frame(pier, foundation, reaction, model, direction, stage)


def generic_seismic(direction: Direction = Direction.LONGITUDINAL):
    """(pier, 0500, the generic 0710 / 0720) of current.json and the test load model."""
    from webpier.calc.generic.seismic import calculate_generic_seismic
    pier, foundation, reaction, model = generic_chain()
    along = direction is Direction.LONGITUDINAL
    frame = calculate_generic_frame(pier, foundation, reaction, model, direction, "0610" if along else "0620")
    return pier, foundation, calculate_generic_seismic(pier, foundation, reaction, frame, model, direction,
                                                       "0710" if along else "0720")

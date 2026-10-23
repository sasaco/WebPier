"""The generic results of the test load model (tests/fixtures/addin/minimal) for the report tests (decision 70)."""

from copy import deepcopy
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from webpier.calc.bearing_actions import load_model_context
from webpier.calc.cantilever.response import MaxResponse, ResponseValue
from webpier.calc.foundation import calculate_foundation
from webpier.calc.frame import Direction
from webpier.calc.reaction import calculate_dead_reaction
from webpier.core.printed import Precision
from webpier.inputs import parse_input
from webpier.loadmodel import validate

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
KH = Precision(3, "")


def generic_inputs():
    """(pier, 0500, the 0600 of a load model, the load model's result) of current.json."""
    pier = parse_input(deepcopy(CURRENT), load_model=True)
    spec = spec_from_file_location("minimal_load_model_for_reports", FIXTURES / "addin" / "minimal" / "minimal_load_model.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    context = load_model_context(pier, Path("input.json"))
    return pier, calculate_foundation(pier), calculate_dead_reaction(pier), validate(
        module.load_model().calculate(context), context)


def frame(direction: Direction):
    from webpier.calc.generic.frame import calculate_generic_frame
    pier, foundation, reaction, model = generic_inputs()
    stage = "0610" if direction is Direction.LONGITUDINAL else "0620"
    return pier, reaction, calculate_generic_frame(pier, foundation, reaction, model, direction, stage)


def seismic(direction: Direction):
    """(pier, the dead 0600, the generic 0710 / 0720)."""
    from webpier.calc.generic.seismic import calculate_generic_seismic
    pier, foundation, reaction, model = generic_inputs()
    stage = "0710" if direction is Direction.LONGITUDINAL else "0720"
    return pier, reaction, calculate_generic_seismic(pier, foundation, reaction, model, direction, stage)


def response(kh: str) -> MaxResponse:
    value = ResponseValue(1, "Case1", "安全性", KH(float(Decimal(kh))))
    return MaxResponse("x_Aggre-SE.xlsx", (value,), value)


def cantilever():
    from webpier.calc.generic.cantilever import calculate_generic_cantilever, complete_generic_cantilever
    pier, _, reaction, model = generic_inputs()
    basis = calculate_generic_cantilever(pier, reaction, model)
    return pier, complete_generic_cantilever(pier, reaction, basis, response("0.400"), response("0.552"))

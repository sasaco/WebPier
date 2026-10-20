"""The FrameWeb input of 0610 / 0620 with a load model (decision 70).

The tables are those of the generic frame result as they are: a load case per basic case (the symbol its id, the name
its name), a Define per Define case (its candidates, −n reversed), a Combine per combination with the printed
factors, a Pickup per extraction group with the names of 8-11. The zero case of the groups without a combination is
one node row with ty = 0, which FEMPython keeps (its pickup is 0, 2026-10-20). The document and the validator are
those of the train path (``build``, ``validate``).
"""

from __future__ import annotations

from typing import Any

from ...calc.generic.frame import GenericFrameResult
from ...calc.longitudinal.combinations import EXTRACTION_NAMES
from ...loadmodel import SpringTerm
from .build import frameweb_document
from .cases import Cases, Combine, LoadCase, Pickup
from .profile import LONG_TERM, SHORT_TERM
from .validate import validate_frameweb

SPRINGS = {SpringTerm.LONG: LONG_TERM, SpringTerm.SHORT: SHORT_TERM}


def generic_cases(result: GenericFrameResult) -> Cases:
    number = {case.id: case.number for case in result.basic_cases}
    loads = tuple(LoadCase(symbol=case.id, name=case.name, spring=SPRINGS[case.spring], points=case.points,
                           line_loads=case.line_loads, member_loads=case.member_loads, zero=case.zero)
                  for case in result.basic_cases)
    defines = tuple(tuple(sign * number[case] for case, sign in define.candidates) for define in result.define_cases)
    combines = tuple(Combine(name=c.name, terms=tuple(sorted(((t.define, t.factor) for t in c.terms if t.factor.value),
                                                             key=lambda term: term[0])))
                     for c in result.combinations)
    pickups = tuple(Pickup(name=EXTRACTION_NAMES[e.group], combines=e.combinations) for e in result.extractions)
    return Cases(loads=loads, defines=defines, combines=combines, pickups=pickups)


def build_frameweb_generic(result: GenericFrameResult) -> dict[str, Any]:
    """The FrameWeb input document of a generic 0610 / 0620; ``core.integrity.dump_json`` gives its bytes."""
    document = frameweb_document(result.frame, generic_cases(result))
    validate_frameweb(document)
    return document

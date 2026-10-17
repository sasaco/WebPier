"""The FrameWeb case tables of a resolved calc result, independent of the direction.

FrameWeb analyses every load case once with its spring set and combines the responses linearly, so a
combination is the printed factor times the printed action (Example2 08 pp.8-9 to 8-11):

- a load case per basic case, numbered as the basic cases;
- a load case per other action a factor applies to (``ResolvedAction.basis`` other than the basic one, e.g. the
  serviceability impact of 0610), after the basic cases, with a Define of its own;
- a Define per Define case of the calc, listing the load case in each of its signs (−n reverses it);
- a Combine per combination: each component as (Define, printed factor); a factor printed 0.00 (a load factor
  below 0.005) adds nothing and is left out;
- a Pickup per extraction group.

Nothing is computed: the actions and factors are the printed values of the calc result. FrameWeb multiplies
them without rounding, while the report rounds each resolved action once (factor × action -> 2 decimals), so a
FrameWeb combination differs from the printed one by up to 0.005 per action; this is accepted for the external
analysis (decision 38).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from ...calc.frame import Frame, LineLoad, PointLoad
from ...core.printed import Printed
from .profile import Profile


class Action(Protocol):
    @property
    def case(self) -> Enum: ...
    @property
    def spring(self) -> Enum: ...
    @property
    def points(self) -> tuple[PointLoad, ...]: ...
    @property
    def line_loads(self) -> tuple[LineLoad, ...]: ...


class DefineSource(Protocol):
    @property
    def number(self) -> int: ...
    @property
    def case(self) -> Enum: ...
    @property
    def signs(self) -> tuple[int, ...]: ...


class Component(Protocol):
    @property
    def case(self) -> Enum: ...
    @property
    def basis(self) -> Enum: ...
    @property
    def factor(self) -> Printed: ...
    @property
    def source(self) -> Action: ...


class CombinationSource(Protocol):
    @property
    def number(self) -> int: ...
    @property
    def components(self) -> Sequence[Component]: ...


class ExtractionSource(Protocol):
    @property
    def number(self) -> int: ...
    @property
    def combinations(self) -> tuple[int, ...]: ...


class Result(Protocol):
    """What a stage result gives: 0610 ``LongitudinalResult`` (one basic case per Define case)."""

    @property
    def frame(self) -> Frame: ...
    @property
    def basic_cases(self) -> Sequence[Action]: ...
    @property
    def define_cases(self) -> Sequence[DefineSource]: ...
    @property
    def combinations(self) -> Sequence[CombinationSource]: ...
    @property
    def extractions(self) -> Sequence[ExtractionSource]: ...


@dataclass(frozen=True)
class LoadCase:
    symbol: str
    name: str
    spring: int  # FrameWeb fix_node set
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...]


@dataclass(frozen=True)
class Combine:
    name: str
    terms: tuple[tuple[int, Printed], ...]  # (Define number, factor), by Define number


@dataclass(frozen=True)
class Pickup:
    name: str
    combines: tuple[int, ...]


@dataclass(frozen=True)
class Cases:
    loads: tuple[LoadCase, ...]  # load case n is loads[n − 1]
    defines: tuple[tuple[int, ...], ...]  # Define n: the load cases it takes, negative reversed
    combines: tuple[Combine, ...]
    pickups: tuple[Pickup, ...]


def _numbered(rows: Sequence[DefineSource | CombinationSource | ExtractionSource], what: str) -> None:
    if [row.number for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError(f"{what} must be numbered 1, 2, ... in order to keep their printed numbers")


def frameweb_cases(result: Result, profile: Profile) -> Cases:
    for rows, what in ((result.define_cases, "Define cases"), (result.combinations, "combinations"),
                       (result.extractions, "extractions")):
        _numbered(rows, what)
    basic = list(result.basic_cases)
    load_of = {action.case: number for number, action in enumerate(basic, 1)}
    define_of = {define.case: define for define in result.define_cases}

    # The action each (case, basis) stands for; every combination must use the same one.
    sources: dict[tuple[Enum, Enum], Action] = {}
    for combination in result.combinations:
        for component in combination.components:
            key = (component.case, component.basis)
            first = basic[load_of[component.case] - 1] if component.basis is profile.basic else component.source
            if sources.setdefault(key, first) != component.source:
                raise ValueError(f"combination {combination.number}: {key} is not the action of the other uses")
    bases = {basis: order for order, basis in enumerate(type(profile.basic))}
    auxiliary = sorted((key for key in sources if key[1] is not profile.basic),
                       key=lambda key: (load_of[key[0]], bases[key[1]]))

    def load(label_key: Enum | tuple[Enum, Enum], action: Action) -> LoadCase:
        label = profile.loads[label_key] if isinstance(label_key, Enum) else profile.auxiliary[label_key]
        return LoadCase(symbol=label.symbol, name=label.name, spring=profile.springs[action.spring],
                        points=action.points, line_loads=action.line_loads)

    loads = [load(action.case, action) for action in basic]
    defines = [tuple(sign * load_of[define.case] for sign in define.signs) for define in result.define_cases]
    define_number = {(case, profile.basic): define.number for case, define in define_of.items()}
    for key in auxiliary:
        loads.append(load(key, sources[key]))
        defines.append(tuple(sign * len(loads) for sign in define_of[key[0]].signs))
        define_number[key] = len(defines)

    combines = []
    for combination in result.combinations:
        terms = sorted(((define_number[(c.case, c.basis)], c.factor) for c in combination.components if c.factor.value),
                       key=lambda term: term[0])
        combines.append(Combine(name=profile.combinations[combination.number], terms=tuple(terms)))
    pickups = tuple(Pickup(name=profile.extractions[e.number], combines=e.combinations) for e in result.extractions)
    return Cases(loads=tuple(loads), defines=tuple(defines), combines=tuple(combines), pickups=pickups)

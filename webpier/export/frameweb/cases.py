"""The FrameWeb case tables of a resolved calc result, independent of the direction.

FrameWeb analyses every load case once with its spring set and combines the responses linearly, so a
combination is the printed factor times the printed action (Example2 08 pp.8-9 to 8-11, 09 pp.9-13 to 9-15):

- a load case per basic case, numbered as the basic cases;
- a Define per Define case of the calc, listing the load case of each of its basic cases (the alternatives, as
  the up and down track of 0620) in each of its signs (−n reverses it);
- a load case per basic case and other action a factor applies to (``basis`` other than the basic one, e.g. the
  serviceability impact), after the basic cases, with a Define of their own per Define case and basis;
- a Combine per combination: each component as (Define, printed factor); a factor printed 0.00 (a load factor
  below 0.005) adds nothing and is left out;
- a Pickup per extraction group.

Each direction reads its calc result into ``Source`` (``frameweb_cases`` for 0610 here, ``transverse`` for 0620)
and ``assemble`` builds the tables with the labels of its ``Profile``. Nothing is computed: the actions and factors
are the printed values of the calc result. FrameWeb multiplies them without rounding, while the report rounds each
resolved action once (factor × action -> 2 decimals), so a FrameWeb combination differs from the printed one by up
to 0.005 per action; this is accepted for the external analysis (decision 38).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from ...calc.frame import Frame, LineLoad, PointLoad
from ...calc.transverse.wind import MemberLoad
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
    """What 0610 ``LongitudinalResult`` gives: one basic case per Define case."""

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
class Load:
    """What one load case carries: the loads of one calc action, unscaled, and its spring term."""

    spring: Enum
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...]
    member_loads: tuple[MemberLoad, ...] = ()


@dataclass(frozen=True)
class Group:
    """A Define case of the calc: its basic cases as alternatives, each in its signs."""

    number: int
    cases: tuple[Enum, ...]
    signs: tuple[int, ...]


@dataclass(frozen=True)
class Term:
    """A component of a combination: the factor on the actions of a Define case in one basis."""

    define: int
    basis: Enum
    factor: Printed
    loads: tuple[Load, ...]  # the action the factor applies to, by case of the Define case


@dataclass(frozen=True)
class Combination:
    number: int
    terms: tuple[Term, ...]


@dataclass(frozen=True)
class Source:
    """A calc result read for FrameWeb."""

    basic: tuple[tuple[Enum, Load], ...]  # by basic case, in order
    groups: tuple[Group, ...]
    combinations: tuple[Combination, ...]
    extractions: tuple[tuple[int, tuple[int, ...]], ...]  # (number, combinations)


@dataclass(frozen=True)
class LoadCase:
    symbol: str
    name: str
    spring: int  # FrameWeb fix_node set
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...]
    member_loads: tuple[MemberLoad, ...] = ()


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


def load(action: Action) -> Load:
    return Load(spring=action.spring, points=action.points, line_loads=action.line_loads)


def _numbered(numbers: Sequence[int], what: str) -> None:
    if list(numbers) != list(range(1, len(numbers) + 1)):
        raise ValueError(f"{what} must be numbered 1, 2, ... in order to keep their printed numbers")


def assemble(source: Source, profile: Profile) -> Cases:
    for numbers, what in (([g.number for g in source.groups], "Define cases"),
                          ([c.number for c in source.combinations], "combinations"),
                          ([number for number, _ in source.extractions], "extractions")):
        _numbered(numbers, what)
    load_of = {case: number for number, (case, _) in enumerate(source.basic, 1)}
    basic = dict(source.basic)

    # The actions each (Define case, basis) stands for; every combination must use the same ones.
    actions: dict[tuple[int, Enum], tuple[Load, ...]] = {}
    for combination in source.combinations:
        for term in combination.terms:
            key = (term.define, term.basis)
            group = source.groups[term.define - 1]
            first = tuple(basic[case] for case in group.cases) if term.basis is profile.basic else term.loads
            if actions.setdefault(key, first) != term.loads:
                raise ValueError(f"combination {combination.number}: Define {term.define} in {term.basis} is not "
                                 "the action of the other uses")
    bases = {basis: order for order, basis in enumerate(type(profile.basic))}
    auxiliary = sorted((key for key in actions if key[1] is not profile.basic), key=lambda k: (k[0], bases[k[1]]))

    def load_case(label_key: Enum | tuple[Enum, Enum], action: Load) -> LoadCase:
        label = profile.loads[label_key] if isinstance(label_key, Enum) else profile.auxiliary[label_key]
        return LoadCase(symbol=label.symbol, name=label.name, spring=profile.springs[action.spring],
                        points=action.points, line_loads=action.line_loads, member_loads=action.member_loads)

    loads = [load_case(case, action) for case, action in source.basic]
    defines = [tuple(sign * load_of[case] for case in group.cases for sign in group.signs) for group in source.groups]
    define_number = {(group.number, profile.basic): group.number for group in source.groups}
    for number, basis in auxiliary:
        group = source.groups[number - 1]
        first = len(loads) + 1
        loads.extend(load_case((case, basis), action) for case, action in zip(
            group.cases, actions[(number, basis)], strict=True))
        defines.append(tuple(sign * (first + index) for index in range(len(group.cases)) for sign in group.signs))
        define_number[(number, basis)] = len(defines)

    combines = []
    for combination in source.combinations:
        terms = sorted(((define_number[(t.define, t.basis)], t.factor) for t in combination.terms if t.factor.value),
                       key=lambda term: term[0])
        combines.append(Combine(name=profile.combinations[combination.number], terms=tuple(terms)))
    pickups = tuple(Pickup(name=profile.extractions[number], combines=members) for number, members in
                    source.extractions)
    return Cases(loads=tuple(loads), defines=tuple(defines), combines=tuple(combines), pickups=pickups)


def frameweb_cases(result: Result, profile: Profile) -> Cases:
    """The case tables of a result with one basic case per Define case (0610)."""
    define_of = {define.case: define.number for define in result.define_cases}
    return assemble(Source(
        basic=tuple((action.case, load(action)) for action in result.basic_cases),
        groups=tuple(Group(number=d.number, cases=(d.case,), signs=d.signs) for d in result.define_cases),
        combinations=tuple(Combination(number=c.number, terms=tuple(
            Term(define=define_of[t.case], basis=t.basis, factor=t.factor, loads=(load(t.source),))
            for t in c.components)) for c in result.combinations),
        extractions=tuple((e.number, e.combinations) for e in result.extractions),
    ), profile)

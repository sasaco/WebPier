"""The horizontal forces along the track at the bearings on the cantilever (0900 13.1 (2), decision 125; Example橋脚4
V-13 to V-25, CONTEXT.md 片持ち梁の支承の水平荷重).

The force T on a girder is 0600's (calc.reaction.longitudinal): LR + B of the longitudinal combination of the case,
with the braking of the train layout of its loading (decisions 101, 102: B+C支点最大 the layout ① on both girders,
B支点最大 ② on the origin girder only, C支点最大 ③ on the end girder only; a case without the train ①), and in the
seismic case T = 最大応答震度 along the track × 0600's girder inertia at Kh 1.00 + 0600's seismic train inertia. Each
bearing of the girder end takes T / n, n the occupied bearing slots of the girder (上部工反力); at a movable end
(上部構造.支承データ.*.支承名) the bearing's own vertical force Ni in the same case caps it, Hi = min(T / n, μ·Ni) (the
horizontal shear resistance of the rubber bearing), at a fixed end there is no cap. Ni is what the case gives that
bearing (its factors, loading and snow; the seismic case D1 + D2 + its snow + the seismic train), which the
combinations supply. The cantilever carries the bearings on it (geometry), each twisting it with Mt = Hi × Y.

Example2 13's shares between rubber bearings and stoppers (decision 59) and the counts of them are gone (decision 125).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from ...core.printed import FORCE, MOMENT, Printed
from ...inputs import PierInput
from .._exact import d, put, total
from ..moving_load import Girder
from ..reaction.longitudinal import BEARING_CHOICES, DEFINITIONS, BearingType, LongitudinalCase, LongitudinalResult
from ..reaction.train import Layout
from .geometry import CantileverBearing, Geometry, GirderBearings
from .loads import Loading

SEISMIC = "地震時"
# The train layout of 0600 whose braking goes with a loading of the cantilever (decision 125)
LAYOUTS = {Loading.ORIGIN_MAX: Layout.ORIGIN, Loading.END_MAX: Layout.END, Loading.BOTH_MAX: Layout.BOTH}


@dataclass(frozen=True)
class GirderForce:
    """T on one girder in one case and its share per bearing."""

    girder: Girder
    bearing: BearingType  # of the girder end on this pier
    applied: Printed  # T, kN
    count: int  # n: the occupied bearing slots of the girder
    share: Printed | None  # T / n; None for a girder without a bearing
    inertia: Printed | None  # the girder inertia Kh × 0600's force at Kh 1.00 (the seismic case only)
    terms: tuple[tuple[Printed | None, Printed], ...] = ()  # T = Σ factor × value (None: the value alone), as printed


@dataclass(frozen=True)
class BearingShare:
    """What one bearing on the cantilever takes in one case."""

    bearing: CantileverBearing
    share: Printed  # T / n of its girder
    vertical: Printed | None  # Ni (a movable end only)
    cap: Printed | None  # μ·Ni (a movable end only)
    force: Printed  # Hi: min(T / n, μ·Ni) at a movable end, T / n at a fixed end
    arm: Printed  # Y, m
    moment: Printed  # Mt = Hi × Y, kN m


@dataclass(frozen=True)
class BearingCase:
    """The bearing forces of one combination case on one cantilever."""

    number: int  # the case (combinations.DEFINITIONS)
    combination: LongitudinalCase | None  # None: the seismic case
    loading: Loading | None  # the train loading of the case; None: no train or the seismic train
    label: str  # 1.0 LR + 1.23B, or 地震時
    origin: GirderForce
    end: GirderForce
    bearings: tuple[BearingShare, ...]  # on this cantilever, origin girder first

    @property
    def force(self) -> Printed:
        """The horizontal force on the cantilever, kN."""
        return put(FORCE, total(item.force for item in self.bearings))

    @property
    def moment(self) -> Printed:
        """Mt on the cantilever, kN m."""
        return put(MOMENT, total(item.moment for item in self.bearings))


def label(case: LongitudinalCase, result: LongitudinalResult) -> str:
    """1.0 LR + 1.23B, as 0600 prints the combination (the brake factor includes ρ)."""
    brake = result.case(case).origin.brake_factor
    lr = f"{DEFINITIONS[case].lr_factor} LR"
    return lr if brake is None else f"{lr} + {brake.value:.2f}B"


def _factor(value: Decimal) -> Printed:
    """A factor of 0600's table with the digits it is written with (1.0, 1.1)."""
    return Printed(float(value), max(0, -int(value.as_tuple().exponent)), "")


def _girder(pier: PierInput, girder: Girder, girders: dict[Girder, GirderBearings],
            terms: tuple[tuple[Printed | None, Printed], ...], inertia: Printed | None = None) -> GirderForce:
    span = pier.spans.origin if girder is Girder.ORIGIN else pier.spans.end
    applied = put(FORCE, total(value if by is None else d(by) * d(value) for by, value in terms))
    count = len(girders[girder].bearings)
    share = put(FORCE, d(applied) / count) if count else None
    return GirderForce(girder, BEARING_CHOICES[span.bearing], applied, count, share, inertia, terms)


def girder_force(pier: PierInput, result: LongitudinalResult, girders: dict[Girder, GirderBearings], girder: Girder,
                 combination: LongitudinalCase, loading: Loading | None) -> GirderForce:
    """T of *girder* in *combination* with the braking of the layout of *loading* (① without a train): the terms
    γB × B (none without a braking factor or with no train on the girder, as the sample's ①-2 end girder) and the LR
    factor × LR, whose sum is 0600's T of the case."""
    layout = Layout.BOTH if loading is None else LAYOUTS[loading]
    source = result if layout is Layout.BOTH else next(item for item in result.one_girder if item.layout is layout)
    origin = girder is Girder.ORIGIN
    forces = (source.case(combination).origin if origin else source.case(combination).end)
    definition = DEFINITIONS[combination]
    brake = (source.origin if origin else source.end).braking_adopted
    rails = result.origin if origin else result.end
    rail = rails.long_rail_service if definition.service_rail else rails.long_rail
    terms: tuple[tuple[Printed | None, Printed], ...] = ((_factor(definition.lr_factor), rail),)
    if forces.brake_factor is not None and brake.value:
        terms = ((forces.brake_factor, brake), *terms)
    found = _girder(pier, girder, girders, terms)
    assert found.applied == forces.applied  # 0600's T
    return found


def seismic_force(pier: PierInput, result: LongitudinalResult, girders: dict[Girder, GirderBearings], girder: Girder,
                  kh: Printed) -> GirderForce:
    """T = Kh × 0600's girder inertia at Kh 1.00 + 0600's seismic train inertia."""
    forces = result.origin if girder is Girder.ORIGIN else result.end
    inertia = put(FORCE, d(forces.seismic_girder) * d(kh))
    return _girder(pier, girder, girders, ((kh, forces.seismic_girder), (None, forces.seismic_train)), inertia)


def bearing_case(pier: PierInput, number: int, combination: LongitudinalCase | None, loading: Loading | None,
                 text: str, forces: dict[Girder, GirderForce], geometry: Geometry,
                 vertical: Callable[[CantileverBearing], Printed]) -> BearingCase:
    """The bearings of *geometry* in one case; *vertical* gives Ni of a bearing in that case."""
    shares = []
    for bearing in geometry.bearings:
        force = forces[bearing.girder]
        assert force.share is not None  # the girder has this bearing
        n = cap = None
        adopted = force.share
        if force.bearing is BearingType.MOVABLE:
            mu = (pier.spans.origin if bearing.girder is Girder.ORIGIN else pier.spans.end).mu
            n = vertical(bearing)
            cap = put(FORCE, d(mu) * d(n))
            adopted = cap if cap.value < force.share.value else force.share
        shares.append(BearingShare(bearing, force.share, n, cap, adopted, geometry.torsion_arm,
                                   put(MOMENT, d(adopted) * d(geometry.torsion_arm))))
    return BearingCase(number, combination, loading, text, forces[Girder.ORIGIN], forces[Girder.END], tuple(shares))

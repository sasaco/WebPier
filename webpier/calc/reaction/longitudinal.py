"""0600 longitudinal horizontal forces: on each girder, then at its bearing on this pier.

Example2 07 7-4 to 7-13. Each girder has two bearing lines (n = 2): the one on
this pier (B or C) and the far one (A or D), of opposite types. At a movable
bearing the force is limited by friction under its own vertical load Rm; at a
fixed bearing the force is T less the friction at the far (movable) bearing.

    movable: H = min(T/n, max(μ·Rm, μ·T/n))  (decision 11: μ, not 0.1)
    fixed:   H = max(T − ½μ·Rm(far), T/n)

Train and braking factors are the load factor ρf times the nominal combination
factor γ, printed to 2 decimals (07 7-7: 1.231 × 1.1 = 1.3541 -> 1.35).

Rm takes the double-track train with impact, ρ·L·(1 + i), except in the
braking-governed safety 1.0 LR + 1.1 B, which takes the train without impact
(decision 119), as 0610's braking-maximum combination does.

The safety 1.1 LR + 1.0 B and 1.0 LR + 1.1 B are also taken with the reduced dead
loads 0.9 D1 + 0.8 D2 (decision 120; Example橋脚4 III-45〜III-57 ⑤ and ③), with the
same train, impact and LR and B factors as their unreduced twins: ten non-seismic
combinations in all.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import Enum

from ...core.printed import FORCE, Precision, Printed
from ...inputs import BrakingRule, PierInput
from ...inputs.model import Span
from .._exact import d, put, total
from ..moving_load import Girder, MovingLoadResult, girder_length
from ..vehicles import vehicle
from .dead import DeadResult, GirderDead, SupportLoads
from .train import Layout, LayoutTrain, TrainResult

FACTOR = Precision(2, "")  # effective combination factor ρf × γ (07 7-7 to 7-11)

LONG_RAIL = Decimal(10)  # kN/m per track (07 7-4 1)(a))
LONG_RAIL_SERVICE = Decimal(8)  # kN/m per track for the serviceability 0.8 LR case (07 7-4 1)(b))
LONG_RAIL_CAP = Decimal(2000)  # kN per track, as in the 0600 sheet (MIN(10 × L, 2000))
BEARING_LINES = Decimal(2)  # n: bearing lines per girder
FRICTION_SHARE = Decimal("0.5")  # T − ½μ·Rm at the fixed bearing
SEISMIC_KH = Decimal("1.00")  # girder inertia, Kh = 1.00 (07 7-4 3))
ADHESION = Decimal("0.20")  # seismic train inertia: wheel-rail adhesion μ = 0.20 (07 7-5 4))
# Braking and starting (07 7-4 2)): (a + b/Lv·L)·P by axle load. EA-17 (decision 101, 【橋りょう編 5.4.7】,
# Example橋脚4 I-41, III-43, III-44): braking 25 % of the train load on the girder, starting 25 % of its driving axles.
AXLE_BRAKING, AXLE_STARTING = (Decimal("0.20"), Decimal("0.80")), (Decimal("0.19"), Decimal("0.76"))
EA17_BRAKING = EA17_STARTING = Decimal("0.25")


class BearingType(Enum):
    FIXED = "fixed"
    MOVABLE = "movable"


BEARING_CHOICES = {"固定": BearingType.FIXED, "可動": BearingType.MOVABLE}  # 上部構造.支承データ.*.支承名


class Snow(Enum):
    S2 = "snow2"
    S10 = "snow10"
    S30 = "snow30"


class LongitudinalCase(Enum):
    """The bearing load combinations of 07 7-5 to 7-12 and the reduced-dead-load ones of decision 120, named by their
    nominal factors.

    The printed B factor includes ρf: B10 is printed 1.23B and B11 1.35B in Example2.
    """

    SERVICE_LR08 = "service 0.8 LR"  # D1 + D2 + S2, 8 kN/m rail
    SERVICE_LR10 = "service 1.0 LR"  # D1 + D2 + double (L + I) + S2
    SAFETY_LR10_B10 = "safety 1.0 LR + 1.0 B"  # 1.1D1 + 1.2D2 + 1.1 double (L + I) + S10
    SAFETY_LR11_B10 = "safety 1.1 LR + 1.0 B"  # train 1.0
    SAFETY_LR11_B10_REDUCED = "safety 1.1 LR + 1.0 B, 0.9 D1 + 0.8 D2"  # decision 120
    SAFETY_LR10_B11 = "safety 1.0 LR + 1.1 B"  # train 1.0, the train without impact (decision 119)
    SAFETY_LR10_B11_REDUCED = "safety 1.0 LR + 1.1 B, 0.9 D1 + 0.8 D2"  # decision 120, without impact
    SAFETY_LR10 = "safety 1.0 LR"  # 1.1D1 + 1.2D2 + S30
    RESTORABILITY_LR10_B10 = "restorability 1.0 LR + 1.0 B"  # D1 + D2 + 1.0 double (L + I) + S10
    RESTORABILITY_LR10 = "restorability 1.0 LR"  # D1 + D2 + S30


@dataclass(frozen=True)
class _Definition:
    lr_factor: Decimal
    service_rail: bool  # 8 kN/m rail force
    brake: Decimal | None  # nominal γB
    d1: Decimal
    d2: Decimal
    live: Decimal | None  # nominal γ of the double-track train
    service_train: bool  # serviceability ρf and impact; otherwise the safety (ultimate) group
    snow: Snow
    restorability: bool
    impact: bool = True  # the train in Rm with impact (1 + i); False: without impact (decision 119)


_ONE, _D1_SAFETY, _D2_SAFETY = Decimal("1.0"), Decimal("1.1"), Decimal("1.2")
REDUCED_D1, REDUCED_D2 = Decimal("0.9"), Decimal("0.8")  # reduced dead loads (decision 120)
DEFINITIONS = {
    LongitudinalCase.SERVICE_LR08: _Definition(_ONE, True, None, _ONE, _ONE, None, True, Snow.S2, False),
    LongitudinalCase.SERVICE_LR10: _Definition(_ONE, False, None, _ONE, _ONE, _ONE, True, Snow.S2, False),
    LongitudinalCase.SAFETY_LR10_B10: _Definition(_ONE, False, _ONE, _D1_SAFETY, _D2_SAFETY, Decimal("1.1"),
                                                  False, Snow.S10, False),
    LongitudinalCase.SAFETY_LR11_B10: _Definition(Decimal("1.1"), False, _ONE, _D1_SAFETY, _D2_SAFETY, _ONE,
                                                  False, Snow.S10, False),
    LongitudinalCase.SAFETY_LR11_B10_REDUCED: _Definition(Decimal("1.1"), False, _ONE, REDUCED_D1, REDUCED_D2,
                                                          _ONE, False, Snow.S10, False),
    LongitudinalCase.SAFETY_LR10_B11: _Definition(_ONE, False, Decimal("1.1"), _D1_SAFETY, _D2_SAFETY, _ONE,
                                                  False, Snow.S10, False, impact=False),
    LongitudinalCase.SAFETY_LR10_B11_REDUCED: _Definition(_ONE, False, Decimal("1.1"), REDUCED_D1, REDUCED_D2,
                                                          _ONE, False, Snow.S10, False, impact=False),
    LongitudinalCase.SAFETY_LR10: _Definition(_ONE, False, None, _D1_SAFETY, _D2_SAFETY, None, False, Snow.S30, False),
    LongitudinalCase.RESTORABILITY_LR10_B10: _Definition(_ONE, False, _ONE, _ONE, _ONE, _ONE, False, Snow.S10, True),
    LongitudinalCase.RESTORABILITY_LR10: _Definition(_ONE, False, None, _ONE, _ONE, None, False, Snow.S30, True),
}
# The combinations with the train or braking, made again for ② and ③ (decision 102; Example橋脚4 III-45〜III-57)
LAYOUT_CASES = tuple(case for case, item in DEFINITIONS.items() if item.live is not None or item.brake is not None)


@dataclass(frozen=True)
class GirderForces:
    """Longitudinal forces on one girder (07 7-4, 7-5)."""

    length: Printed  # girder length L = L1 + span + L2
    track_total: Printed  # loaded tracks
    long_rail: Printed  # LR = min(10 × L, 2000) × tracks
    long_rail_service: Printed  # min(8 × L, 2000) × tracks, for service 0.8 LR
    braking_rule: BrakingRule  # from the selected vehicle
    braking: Printed  # braking force
    starting: Printed  # starting force
    braking_adopted: Printed  # B = max(braking, starting)
    seismic_girder: Printed  # T = (D1 + D2 + S2 at both bearings) × Kh
    seismic_train: Printed  # T = (R + R seismic train) × 0.20
    driving_axles: Printed | None = field(default=None, metadata={"json": "set"})  # EA-17: ΣP of the starting


@dataclass(frozen=True)
class BearingForce:
    """One combination at the bearing of one girder on this pier."""

    bearing: BearingType
    live_factor: Printed | None  # ρf × γ on the double-track train (with impact unless decision 119); None if no train
    brake_factor: Printed | None  # ρu × γB, or the entered restorability braking factor; None if no braking
    applied: Printed  # T = LR factor × LR + brake factor × B
    vertical: Printed  # Rm: at this bearing if movable, at the far bearing if fixed
    share: Printed  # T / n
    friction: Printed | None  # movable: μ·Rm
    friction_floor: Printed | None  # movable: μ·T/n
    fixed_candidate: Printed | None  # fixed: T − ½μ·Rm
    force: Printed  # H


@dataclass(frozen=True)
class CaseForces:
    case: LongitudinalCase
    origin: BearingForce  # at B
    end: BearingForce  # at C
    total: Printed  # H_B + H_C (07 7-13 summary)


@dataclass(frozen=True)
class SeismicBearing:
    bearing: BearingType
    applied: Printed  # T on the girder
    force: Printed  # fixed: T; movable: T / n (no friction limit, 07 7-13)


@dataclass(frozen=True)
class SeismicForces:
    origin: SeismicBearing
    end: SeismicBearing
    total: Printed


@dataclass(frozen=True)
class BrakeForces:
    """Braking and starting on one girder for a placing on one girder only (decision 102)."""

    braking: Printed
    starting: Printed
    braking_adopted: Printed  # B = max(braking, starting)
    driving_axles: Printed | None = field(default=None, metadata={"json": "set"})  # EA-17: ΣP of the starting


@dataclass(frozen=True)
class LayoutForces:
    """The bearing forces of ② or ③: the braking of each girder and the combinations with the train or braking."""

    layout: Layout
    origin: BrakeForces
    end: BrakeForces
    cases: tuple[CaseForces, ...]  # LAYOUT_CASES, in LongitudinalCase order

    def case(self, which: LongitudinalCase) -> CaseForces:
        return next(case for case in self.cases if case.case is which)


@dataclass(frozen=True)
class LongitudinalResult:
    origin: GirderForces
    end: GirderForces
    cases: tuple[CaseForces, ...]  # the ten non-seismic combinations of ① (decision 120), in LongitudinalCase order
    seismic_girder: SeismicForces  # girder inertia (Kh = 1.00)
    seismic_train: SeismicForces  # seismic train inertia
    one_girder: tuple[LayoutForces, LayoutForces]  # ② and ③ (decision 102)

    def case(self, which: LongitudinalCase) -> CaseForces:
        return next(case for case in self.cases if case.case is which)


@dataclass(frozen=True)
class _Side:
    """Everything one girder contributes to its bearing forces."""

    span: Span
    dead: GirderDead
    forces: GirderForces
    r_pier: Printed
    r_far: Printed
    i_ultimate: Printed  # double-track girder impact, safety
    i_service: Printed  # double-track girder impact, serviceability


def _larger(a: Printed, b: Printed) -> Printed:
    return a if a.value >= b.value else b


def _smaller(a: Printed, b: Printed) -> Printed:
    return a if a.value <= b.value else b


def _rail(per_metre: Decimal, length: Printed, tracks: Printed) -> Printed:
    return put(FORCE, min(per_metre * d(length), LONG_RAIL_CAP) * d(tracks))


def driving_axles(loading: MovingLoadResult, girder: Girder) -> Printed:
    """ΣP of the axles on the girder: EA-17's axles are the locomotives' driving axles, its line load is not."""
    return FORCE.total(loading.load(axle) for axle in loading.on(girder))


def _brake(pier: PierInput, length: Printed, r_far: Printed, r_pier: Printed, driving: Printed) -> BrakeForces:
    """One track's braking and starting on a girder (decision 102: also in a double-track combination)."""
    t = vehicle(pier.train)
    if t.braking_rule is BrakingRule.EA17:
        braking = put(FORCE, EA17_BRAKING * (d(r_far) + d(r_pier)))
        starting = put(FORCE, EA17_STARTING * d(driving))
        return BrakeForces(braking, starting, _larger(braking, starting), driving)
    assert t.car_length is not None and t.axle_load is not None
    if not d(r_far) + d(r_pier):  # a girder without the train of ② or ③ has no train to brake
        return BrakeForces(FORCE(0), FORCE(0), FORCE(0))
    braking = put(FORCE, (AXLE_BRAKING[0] + AXLE_BRAKING[1] / d(t.car_length) * d(length)) * d(t.axle_load))
    starting = put(FORCE, (AXLE_STARTING[0] + AXLE_STARTING[1] / d(t.car_length) * d(length)) * d(t.axle_load))
    return BrakeForces(braking, starting, _larger(braking, starting))


def _girder(pier: PierInput, span: Span, dead: GirderDead, r_far: Printed, r_pier: Printed,
            eq_reaction: Printed, driving: Printed) -> GirderForces:
    t = vehicle(pier.train)
    length = girder_length(span)
    brake = _brake(pier, length, r_far, r_pier, driving)
    loads = (dead.far.d1, dead.pier.d1, dead.far.d2, dead.pier.d2, dead.far.snow2, dead.pier.snow2)
    return GirderForces(
        length=length, track_total=dead.track_total,
        long_rail=_rail(LONG_RAIL, length, dead.track_total),
        long_rail_service=_rail(LONG_RAIL_SERVICE, length, dead.track_total),
        braking_rule=t.braking_rule, braking=brake.braking, starting=brake.starting,
        driving_axles=brake.driving_axles, braking_adopted=brake.braking_adopted,
        seismic_girder=put(FORCE, total(loads) * SEISMIC_KH),
        seismic_train=put(FORCE, (d(eq_reaction) + d(eq_reaction)) * ADHESION),
    )


def _vertical(definition: _Definition, loads: SupportLoads, live: Printed | None, reaction: Printed,
              tracks: Printed, impact: Printed) -> Printed:
    snow: Printed = getattr(loads, definition.snow.value)
    vertical = definition.d1 * d(loads.d1) + definition.d2 * d(loads.d2) + d(snow)
    if live is not None:
        train = d(live) * d(reaction) * d(tracks)
        vertical += train * (1 + d(impact)) if definition.impact else train
    return put(FORCE, vertical)


def _bearing(pier: PierInput, definition: _Definition, side: _Side) -> BearingForce:
    t, span = pier.train, side.span
    rho_live = t.factor_service if definition.service_train else t.factor_ultimate
    live = None if definition.live is None else put(FACTOR, d(rho_live) * definition.live)
    if definition.brake is None:
        brake = None
    elif definition.restorability and span.recovery_brake_coefficient is not None:
        brake = span.recovery_brake_coefficient
    else:
        brake = put(FACTOR, d(t.factor_ultimate) * definition.brake)
    rail = side.forces.long_rail_service if definition.service_rail else side.forces.long_rail
    applied = definition.lr_factor * d(rail)
    if brake is not None:
        applied += d(brake) * d(side.forces.braking_adopted)
    applied_force = put(FORCE, applied)
    share = put(FORCE, d(applied_force) / BEARING_LINES)
    impact = side.i_service if definition.service_train else side.i_ultimate
    mu = d(span.mu)
    if BEARING_CHOICES[span.bearing] is BearingType.MOVABLE:
        vertical = _vertical(definition, side.dead.pier, live, side.r_pier, side.dead.track_total, impact)
        friction, floor = put(FORCE, mu * d(vertical)), put(FORCE, mu * d(share))
        force = _smaller(share, _larger(friction, floor))
        return BearingForce(BearingType.MOVABLE, live, brake, applied_force, vertical, share,
                            friction, floor, None, force)
    vertical = _vertical(definition, side.dead.far, live, side.r_far, side.dead.track_total, impact)
    candidate = put(FORCE, d(applied_force) - FRICTION_SHARE * mu * d(vertical))
    force = _larger(candidate, share)
    return BearingForce(BearingType.FIXED, live, brake, applied_force, vertical, share, None, None, candidate, force)


def _seismic(origin: tuple[Span, Printed], end: tuple[Span, Printed]) -> SeismicForces:
    bearings = []
    for span, applied in (origin, end):
        bearing = BEARING_CHOICES[span.bearing]
        force = applied if bearing is BearingType.FIXED else put(FORCE, d(applied) / BEARING_LINES)
        bearings.append(SeismicBearing(bearing, applied, force))
    return SeismicForces(bearings[0], bearings[1], put(FORCE, total((bearings[0].force, bearings[1].force))))


def calculate_longitudinal(pier: PierInput, dead: DeadResult, train: TrainResult) -> LongitudinalResult:
    loading, spans = train.loading, pier.spans
    origin_forces = _girder(pier, spans.origin, dead.origin, loading.ra, loading.rb, train.seismic.origin,
                            driving_axles(loading, Girder.ORIGIN))
    end_forces = _girder(pier, spans.end, dead.end, loading.rd, loading.rc, train.seismic.end,
                         driving_axles(loading, Girder.END))
    sides = (
        _Side(spans.origin, dead.origin, origin_forces, r_pier=loading.rb, r_far=loading.ra,
              i_ultimate=train.ultimate.origin_impact.double, i_service=train.service.origin_impact.double),
        _Side(spans.end, dead.end, end_forces, r_pier=loading.rc, r_far=loading.rd,
              i_ultimate=train.ultimate.end_impact.double, i_service=train.service.end_impact.double),
    )
    return LongitudinalResult(
        origin=origin_forces, end=end_forces, cases=_cases(pier, sides, tuple(DEFINITIONS)),
        seismic_girder=_seismic((spans.origin, origin_forces.seismic_girder), (spans.end, end_forces.seismic_girder)),
        seismic_train=_seismic((spans.origin, origin_forces.seismic_train), (spans.end, end_forces.seismic_train)),
        one_girder=(_layout(pier, train.layout(Layout.ORIGIN), sides), _layout(pier, train.layout(Layout.END), sides)),
    )


def _cases(pier: PierInput, sides: tuple[_Side, _Side], cases: tuple[LongitudinalCase, ...]) -> tuple[CaseForces, ...]:
    found = []
    for case in cases:
        origin, end = (_bearing(pier, DEFINITIONS[case], item) for item in sides)
        found.append(CaseForces(case, origin, end, put(FORCE, total((origin.force, end.force)))))
    return tuple(found)


def _layout(pier: PierInput, placed: LayoutTrain, both: tuple[_Side, _Side]) -> LayoutForces:
    """② or ③: the girders' braking from that loading, and the bearing cases with the train or braking."""
    loading = placed.loading
    brakes, sides = [], []
    reactions = ((loading.ra, loading.rb, Girder.ORIGIN), (loading.rd, loading.rc, Girder.END))
    for side, (r_far, r_pier, girder) in zip(both, reactions, strict=True):
        brake = _brake(pier, side.forces.length, r_far, r_pier, driving_axles(loading, girder))
        brakes.append(brake)
        forces = replace(side.forces, braking=brake.braking, starting=brake.starting,
                         braking_adopted=brake.braking_adopted, driving_axles=brake.driving_axles)
        sides.append(replace(side, forces=forces, r_pier=r_pier, r_far=r_far))
    return LayoutForces(placed.layout, brakes[0], brakes[1], _cases(pier, (sides[0], sides[1]), LAYOUT_CASES))

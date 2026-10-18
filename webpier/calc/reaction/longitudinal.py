"""0600 longitudinal horizontal forces: on each girder, then at its bearing on this pier.

Example2 07 7-4 to 7-13. Each girder has two bearing lines (n = 2): the one on
this pier (B or C) and the far one (A or D), of opposite types. At a movable
bearing the force is limited by friction under its own vertical load Rm; at a
fixed bearing the force is T less the friction at the far (movable) bearing.

    movable: H = min(T/n, max(μ·Rm, μ·T/n))  (decision 11: μ, not 0.1)
    fixed:   H = max(T − ½μ·Rm(far), T/n)

Train and braking factors are the load factor ρf times the nominal combination
factor γ, printed to 2 decimals (07 7-7: 1.231 × 1.1 = 1.3541 -> 1.35).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ...core.printed import FORCE, Precision, Printed
from ...inputs import BrakingRule, PierInput
from ...inputs.model import Span
from .._exact import d, put, total
from ..moving_load import girder_length
from .dead import DeadResult, GirderDead, SupportLoads
from .train import TrainResult

FACTOR = Precision(2, "")  # effective combination factor ρf × γ (07 7-7 to 7-11)

LONG_RAIL = Decimal(10)  # kN/m per track (07 7-4 1)(a))
LONG_RAIL_SERVICE = Decimal(8)  # kN/m per track for the serviceability 0.8 LR case (07 7-4 1)(b))
LONG_RAIL_CAP = Decimal(2000)  # kN per track, as in the 0600 sheet (MIN(10 × L, 2000))
BEARING_LINES = Decimal(2)  # n: bearing lines per girder
FRICTION_SHARE = Decimal("0.5")  # T − ½μ·Rm at the fixed bearing
SEISMIC_KH = Decimal("1.00")  # girder inertia, Kh = 1.00 (07 7-4 3))
ADHESION = Decimal("0.20")  # seismic train inertia: wheel-rail adhesion μ = 0.20 (07 7-5 4))
# Braking and starting (07 7-4 2)): (a + b/Lv·L)·P by axle load, or (a + b/Lv)·ΣR for EA-17.
AXLE_BRAKING, AXLE_STARTING = (Decimal("0.20"), Decimal("0.80")), (Decimal("0.19"), Decimal("0.76"))
EA17_BRAKING, EA17_STARTING = (Decimal("0.27"), Decimal("1.00")), (Decimal("0.25"), Decimal("0.95"))


class BearingType(Enum):
    FIXED = "fixed"
    MOVABLE = "movable"


BEARING_CHOICES = {"固定": BearingType.FIXED, "可動": BearingType.MOVABLE}  # 上部構造.支承データ.*.支承名


class Snow(Enum):
    S2 = "snow2"
    S10 = "snow10"
    S30 = "snow30"


class LongitudinalCase(Enum):
    """The bearing load combinations of 07 7-5 to 7-12, named by their nominal factors.

    The printed B factor includes ρf: B10 is printed 1.23B and B11 1.35B in Example2.
    """

    SERVICE_LR08 = "service 0.8 LR"  # D1 + D2 + S2, 8 kN/m rail
    SERVICE_LR10 = "service 1.0 LR"  # D1 + D2 + double (L + I) + S2
    SAFETY_LR10_B10 = "safety 1.0 LR + 1.0 B"  # 1.1D1 + 1.2D2 + 1.1 double (L + I) + S10
    SAFETY_LR11_B10 = "safety 1.1 LR + 1.0 B"  # train 1.0
    SAFETY_LR10_B11 = "safety 1.0 LR + 1.1 B"  # train 1.0
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
    live: Decimal | None  # nominal γ of the double-track train with impact
    service_train: bool  # serviceability ρf and impact; otherwise the safety (ultimate) group
    snow: Snow
    restorability: bool


_ONE, _D1_SAFETY, _D2_SAFETY = Decimal("1.0"), Decimal("1.1"), Decimal("1.2")
DEFINITIONS = {
    LongitudinalCase.SERVICE_LR08: _Definition(_ONE, True, None, _ONE, _ONE, None, True, Snow.S2, False),
    LongitudinalCase.SERVICE_LR10: _Definition(_ONE, False, None, _ONE, _ONE, _ONE, True, Snow.S2, False),
    LongitudinalCase.SAFETY_LR10_B10: _Definition(_ONE, False, _ONE, _D1_SAFETY, _D2_SAFETY, Decimal("1.1"),
                                                  False, Snow.S10, False),
    LongitudinalCase.SAFETY_LR11_B10: _Definition(Decimal("1.1"), False, _ONE, _D1_SAFETY, _D2_SAFETY, _ONE,
                                                  False, Snow.S10, False),
    LongitudinalCase.SAFETY_LR10_B11: _Definition(_ONE, False, Decimal("1.1"), _D1_SAFETY, _D2_SAFETY, _ONE,
                                                  False, Snow.S10, False),
    LongitudinalCase.SAFETY_LR10: _Definition(_ONE, False, None, _D1_SAFETY, _D2_SAFETY, None, False, Snow.S30, False),
    LongitudinalCase.RESTORABILITY_LR10_B10: _Definition(_ONE, False, _ONE, _ONE, _ONE, _ONE, False, Snow.S10, True),
    LongitudinalCase.RESTORABILITY_LR10: _Definition(_ONE, False, None, _ONE, _ONE, None, False, Snow.S30, True),
}


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


@dataclass(frozen=True)
class BearingForce:
    """One combination at the bearing of one girder on this pier."""

    bearing: BearingType
    live_factor: Printed | None  # ρf × γ on the double-track train with impact; None if no train
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
class LongitudinalResult:
    origin: GirderForces
    end: GirderForces
    cases: tuple[CaseForces, ...]  # the eight non-seismic combinations, in LongitudinalCase order
    seismic_girder: SeismicForces  # girder inertia (Kh = 1.00)
    seismic_train: SeismicForces  # seismic train inertia

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


def _girder(pier: PierInput, span: Span, dead: GirderDead, r_far: Printed, r_pier: Printed,
            eq_reaction: Printed) -> GirderForces:
    t = pier.train
    length = girder_length(span)
    if t.braking_rule is BrakingRule.EA17:
        reactions = d(r_far) + d(r_pier)
        braking = put(FORCE, (EA17_BRAKING[0] + EA17_BRAKING[1] / d(t.car_length)) * reactions)
        starting = put(FORCE, (EA17_STARTING[0] + EA17_STARTING[1] / d(t.car_length)) * reactions)
    else:
        braking = put(FORCE, (AXLE_BRAKING[0] + AXLE_BRAKING[1] / d(t.car_length) * d(length)) * d(t.axle_load))
        starting = put(FORCE, (AXLE_STARTING[0] + AXLE_STARTING[1] / d(t.car_length) * d(length)) * d(t.axle_load))
    loads = (dead.far.d1, dead.pier.d1, dead.far.d2, dead.pier.d2, dead.far.snow2, dead.pier.snow2)
    return GirderForces(
        length=length, track_total=dead.track_total,
        long_rail=_rail(LONG_RAIL, length, dead.track_total),
        long_rail_service=_rail(LONG_RAIL_SERVICE, length, dead.track_total),
        braking_rule=t.braking_rule, braking=braking, starting=starting,
        braking_adopted=_larger(braking, starting),
        seismic_girder=put(FORCE, total(loads) * SEISMIC_KH),
        seismic_train=put(FORCE, (d(eq_reaction) + d(eq_reaction)) * ADHESION),
    )


def _vertical(definition: _Definition, loads: SupportLoads, live: Printed | None, reaction: Printed,
              tracks: Printed, impact: Printed) -> Printed:
    snow: Printed = getattr(loads, definition.snow.value)
    vertical = definition.d1 * d(loads.d1) + definition.d2 * d(loads.d2) + d(snow)
    if live is not None:
        vertical += d(live) * d(reaction) * d(tracks) * (1 + d(impact))
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
    origin_forces = _girder(pier, spans.origin, dead.origin, loading.ra, loading.rb, train.seismic.origin)
    end_forces = _girder(pier, spans.end, dead.end, loading.rd, loading.rc, train.seismic.end)
    sides = (
        _Side(spans.origin, dead.origin, origin_forces, r_pier=loading.rb, r_far=loading.ra,
              i_ultimate=train.ultimate.origin_impact.double, i_service=train.service.origin_impact.double),
        _Side(spans.end, dead.end, end_forces, r_pier=loading.rc, r_far=loading.rd,
              i_ultimate=train.ultimate.end_impact.double, i_service=train.service.end_impact.double),
    )
    cases = []
    for case, definition in DEFINITIONS.items():
        origin, end = (_bearing(pier, definition, item) for item in sides)
        cases.append(CaseForces(case, origin, end, put(FORCE, total((origin.force, end.force)))))
    return LongitudinalResult(
        origin=origin_forces, end=end_forces, cases=tuple(cases),
        seismic_girder=_seismic((spans.origin, origin_forces.seismic_girder), (spans.end, end_forces.seismic_girder)),
        seismic_train=_seismic((spans.origin, origin_forces.seismic_train), (spans.end, end_forces.seismic_train)),
    )

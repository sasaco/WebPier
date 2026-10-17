"""0600 train loads: moving-load reactions, impact on the girders, seismic train.

Example2 07 7-1/7-2 print the reactions (kN, 2 decimals), the load factors ρf
and the impact coefficients (3 decimals). The later stages use these girder
coefficients as they are (decision 26); no pier reduction is computed (decision 27).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...core.errors import InputError
from ...core.printed import COEFFICIENT, FORCE, LENGTH, Printed
from ...inputs import PierInput
from ...inputs.model import Span
from .._exact import d, put
from ..moving_load import MovingLoadResult, search_reactions
from .dead import DeadResult, GirderDead

IMPACT = COEFFICIENT  # impact coefficient i (07 7-2)
SERVICE_RATIO = Decimal("0.75")  # serviceability and fatigue use 3/4 of the impact (07 7-2: 0.245 -> 0.184)
DOUBLE_TRACK_SPAN = Decimal(200)  # i × (1 − L/200) for both tracks loaded; valid for L < 200 m (decisions 13, 23)
SEISMIC_SHARE = Decimal("0.5")  # seismic train line load × girder length × 1/2 at each end (07 7-2)


@dataclass(frozen=True)
class GirderImpact:
    """Impact coefficients of one girder for one load group."""

    single: Printed  # one track loaded
    double: Printed  # both tracks loaded: i_single × (1 − L/200) in one expression, rounded once (decision 23)


@dataclass(frozen=True)
class SupportTrain:
    """Train load, impact coefficient and impact load at one support."""

    load: Printed  # L
    coefficient: Printed  # i
    impact: Printed  # I = L × i


@dataclass(frozen=True)
class TrackTrain:
    a: SupportTrain
    b: SupportTrain
    c: SupportTrain
    d: SupportTrain


@dataclass(frozen=True)
class GroupTrain:
    """Girder train and impact table for one load group."""

    load_factor: Printed  # ρf of the group
    origin_impact: GirderImpact  # coefficients at A and B
    end_impact: GirderImpact  # coefficients at C and D
    single: TrackTrain  # L = R × ρf
    double: TrackTrain  # L = (R × ρf) × track total of the girder


@dataclass(frozen=True)
class SeismicTrain:
    """Seismic train reactions, one track, without shares (07 7-2)."""

    line_load: Printed  # seismic train load per metre
    origin_length: Printed  # origin girder length L1 + span + L2
    end_length: Printed
    origin: Printed  # RA = RB = e × L × 1/2
    end: Printed  # RC = RD


@dataclass(frozen=True)
class TrainResult:
    loading: MovingLoadResult  # adopted train loading: RA..RD of one track without load factors
    ultimate: GroupTrain  # safety (failure) and restorability
    service: GroupTrain  # serviceability
    fatigue: GroupTrain  # safety (fatigue)
    seismic: SeismicTrain


def girder_length(span: Span) -> Printed:
    """Girder length L1 + span + L2."""
    return LENGTH.total((span.l1, span.span, span.l2))


def _double_impact(span: Span, side: str) -> Printed:
    """i = i_single × (1 − L/200), L the span; only the result is rounded (decision 23)."""
    if d(span.span) >= DOUBLE_TRACK_SPAN:
        raise InputError(f"上部構造.{side}.桁長.スパン長: 複線の衝撃低減 1 − L/200 の適用範囲外です"
                         f"（L < 200 m が必要、入力 {span.span.value} m）")
    return put(IMPACT, d(span.impact) * (1 - d(span.span) / DOUBLE_TRACK_SPAN))


def _support(load: Printed, coefficient: Printed) -> SupportTrain:
    return SupportTrain(load=load, coefficient=coefficient, impact=put(FORCE, d(load) * d(coefficient)))


def _group(factor: Printed, loading: MovingLoadResult, origin: GirderDead, end: GirderDead,
           impacts: tuple[GirderImpact, GirderImpact]) -> GroupTrain:
    reactions = (loading.ra, loading.rb, loading.rc, loading.rd)
    girders = (origin, origin, end, end)
    girder_impacts = (impacts[0], impacts[0], impacts[1], impacts[1])
    single = [put(FORCE, d(reaction) * d(factor)) for reaction in reactions]
    double = [put(FORCE, d(load) * d(girder.track_total)) for load, girder in zip(single, girders)]
    return GroupTrain(
        load_factor=factor, origin_impact=impacts[0], end_impact=impacts[1],
        single=TrackTrain(*(_support(load, impact.single) for load, impact in zip(single, girder_impacts))),
        double=TrackTrain(*(_support(load, impact.double) for load, impact in zip(double, girder_impacts))),
    )


def calculate_train(pier: PierInput, dead: DeadResult) -> TrainResult:
    t, spans = pier.train, pier.spans
    loading = search_reactions(spans.origin, spans.end, axle_load=t.axle_load, cars=t.cars,
                               car_length=t.car_length, a1=t.a1, a2=t.a2)
    ultimate = (GirderImpact(spans.origin.impact, _double_impact(spans.origin, "起点側")),
                GirderImpact(spans.end.impact, _double_impact(spans.end, "終点側")))
    service = tuple(GirderImpact(put(IMPACT, d(impact.single) * SERVICE_RATIO),
                                 put(IMPACT, d(impact.double) * SERVICE_RATIO)) for impact in ultimate)
    groups = {
        "ultimate": _group(t.factor_ultimate, loading, dead.origin, dead.end, (ultimate[0], ultimate[1])),
        "service": _group(t.factor_service, loading, dead.origin, dead.end, (service[0], service[1])),
        "fatigue": _group(t.factor_fatigue, loading, dead.origin, dead.end, (service[0], service[1])),
    }
    lengths = (girder_length(spans.origin), girder_length(spans.end))
    seismic = SeismicTrain(
        line_load=t.earthquake_load, origin_length=lengths[0], end_length=lengths[1],
        origin=put(FORCE, d(t.earthquake_load) * d(lengths[0]) * SEISMIC_SHARE),
        end=put(FORCE, d(t.earthquake_load) * d(lengths[1]) * SEISMIC_SHARE))
    return TrainResult(
        loading=loading,
        ultimate=groups["ultimate"], service=groups["service"], fatigue=groups["fatigue"],
        seismic=seismic,
    )

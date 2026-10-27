"""0600 train loads: moving-load reactions, impact on the girders and on the pier body, seismic train.

Example2 07 7-1/7-2 print the reactions (kN, 2 decimals), the load factors ρf
and the impact coefficients (3 decimals). The impact on the pier body is the girder
coefficient times the ratio 1 − Ds/(L + Du + Ds) of RC標準 解4.4.4 (decision 77, Example3
Ⅱ-2-6); the ratio is one value per track case, shared by every load group and both girders.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ...core.errors import InputError
from ...core.printed import COEFFICIENT, FORCE, Printed
from ...inputs import PierInput
from ...inputs.model import Span
from .._exact import d, put
from ..moving_load import Girder, MovingLoadResult, girder_length, search_reactions
from ..vehicles import vehicle
from .dead import DeadResult, GirderDead
from .self_weight import SelfWeightResult

IMPACT = COEFFICIENT  # impact coefficient i (07 7-2)
SERVICE_RATIO = Decimal("0.75")  # serviceability and fatigue use 3/4 of the impact (07 7-2: 0.245 -> 0.184)
DOUBLE_TRACK_SPAN = Decimal(200)  # i × (1 − L/200) for both tracks loaded; valid for L < 200 m (decisions 13, 23)
PIER_IMPACT_LIMIT = Decimal("0.9")  # Ds / (L + Du + Ds) of 0.9 or more: no impact on the pier body (decision 77)
SEISMIC_SHARE = Decimal("0.5")  # seismic train line load × girder length × 1/2 at each end (07 7-2)


@dataclass(frozen=True)
class GirderImpact:
    """Impact coefficients of one girder for one load group."""

    single: Printed  # one track loaded
    double: Printed  # both tracks loaded: i_single × (1 − L/200) in one expression, rounded once (decision 23)


@dataclass(frozen=True)
class PierImpactRatio:
    """Ratio 1 − Ds/(L + Du + Ds) of one track case (decision 77)."""

    train: Printed  # L: characteristic train loads of both girders on this pier, without ρf
    ratio: Printed  # printed ratio; 0 when Ds/(L + Du + Ds) reaches the limit
    limited: bool  # Ds/(L + Du + Ds) ≥ 0.9, so the impact on the pier body is zero


@dataclass(frozen=True)
class PierImpact:
    """Impact reduction to the pier body (RC標準 解4.4.4); also used for the foundation."""

    dead: Printed  # Du: D1 + D2 of both girders on this pier, without snow
    weight: Printed  # Ds: pier-bottom weight (pedestal, beam, column), buoyancy not deducted
    single: PierImpactRatio
    double: PierImpactRatio


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
    origin_impact: GirderImpact  # girder coefficients at A and B
    end_impact: GirderImpact  # girder coefficients at C and D
    origin_pier_impact: GirderImpact  # coefficients on the pier body: girder coefficient × ratio (decision 77)
    end_pier_impact: GirderImpact
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


class Layout(Enum):
    """列車の配置 (decision 102, CONTEXT.md; Example橋脚4 I-40 表7.1.2): the girders a train is put on."""

    BOTH = "両側の桁"  # ①: RB + RC maximised
    ORIGIN = "起点側の桁"  # ②: on the origin girder only
    END = "終点側の桁"  # ③: on the end girder only


LOADED = {Layout.BOTH: None, Layout.ORIGIN: Girder.ORIGIN, Layout.END: Girder.END}


@dataclass(frozen=True)
class LayoutTrain:
    """The train of one placing on one girder only (② or ③), as TrainResult holds ①'s."""

    layout: Layout
    loading: MovingLoadResult
    ultimate: GroupTrain
    service: GroupTrain
    fatigue: GroupTrain
    pier_impact: PierImpact


@dataclass(frozen=True)
class TrainResult:
    loading: MovingLoadResult  # adopted train loading of ① (both girders): RA..RD of one track without load factors
    ultimate: GroupTrain  # safety (failure) and restorability
    service: GroupTrain  # serviceability
    fatigue: GroupTrain  # safety (fatigue)
    pier_impact: PierImpact
    seismic: SeismicTrain
    one_girder: tuple[LayoutTrain, LayoutTrain]  # ② and ③, for the longitudinal checks other than seismic

    def layout(self, layout: Layout) -> LayoutTrain:
        if layout is Layout.BOTH:
            return LayoutTrain(Layout.BOTH, self.loading, self.ultimate, self.service, self.fatigue, self.pier_impact)
        return self.one_girder[0] if layout is Layout.ORIGIN else self.one_girder[1]


def _double_impact(span: Span, side: str) -> Printed:
    """i = i_single × (1 − L/200), L the span; only the result is rounded (decision 23)."""
    if d(span.span) >= DOUBLE_TRACK_SPAN:
        raise InputError(f"上部構造.{side}.桁長.スパン長: 複線の衝撃低減 1 − L/200 の適用範囲外です"
                         f"（L < 200 m が必要、入力 {span.span.value} m）")
    return put(IMPACT, d(span.impact) * (1 - d(span.span) / DOUBLE_TRACK_SPAN))


def _support(load: Printed, coefficient: Printed) -> SupportTrain:
    return SupportTrain(load=load, coefficient=coefficient, impact=put(FORCE, d(load) * d(coefficient)))


def _pier_ratio(train: Printed, du: Printed, ds: Printed) -> PierImpactRatio:
    denominator = d(train) + d(du) + d(ds)
    if denominator == 0:
        raise InputError("0600 橋脚く体の衝撃: 低減式の分母 L + Du + Ds が0になります（死荷重の入力を確認）")
    share = d(ds) / denominator
    if share >= PIER_IMPACT_LIMIT:
        return PierImpactRatio(train=train, ratio=put(IMPACT, Decimal(0)), limited=True)
    return PierImpactRatio(train=train, ratio=put(IMPACT, 1 - share), limited=False)


def _pier_impact(loading: MovingLoadResult, origin: GirderDead, end: GirderDead, ds: Printed) -> PierImpact:
    du = FORCE.total((origin.pier.d1, origin.pier.d2, end.pier.d1, end.pier.d2))
    single = FORCE.total((loading.rb, loading.rc))
    double = FORCE.total((put(FORCE, d(loading.rb) * d(origin.track_total)),
                         put(FORCE, d(loading.rc) * d(end.track_total))))
    return PierImpact(dead=du, weight=ds, single=_pier_ratio(single, du, ds), double=_pier_ratio(double, du, ds))


def _on_pier(impact: GirderImpact, pier: PierImpact) -> GirderImpact:
    return GirderImpact(put(IMPACT, d(impact.single) * d(pier.single.ratio)),
                        put(IMPACT, d(impact.double) * d(pier.double.ratio)))


def _group(factor: Printed, loading: MovingLoadResult, origin: GirderDead, end: GirderDead,
           impacts: tuple[GirderImpact, GirderImpact], pier: PierImpact) -> GroupTrain:
    reactions = (loading.ra, loading.rb, loading.rc, loading.rd)
    girders = (origin, origin, end, end)
    girder_impacts = (impacts[0], impacts[0], impacts[1], impacts[1])
    single = [put(FORCE, d(reaction) * d(factor)) for reaction in reactions]
    double = [put(FORCE, d(load) * d(girder.track_total)) for load, girder in zip(single, girders)]
    return GroupTrain(
        load_factor=factor, origin_impact=impacts[0], end_impact=impacts[1],
        origin_pier_impact=_on_pier(impacts[0], pier), end_pier_impact=_on_pier(impacts[1], pier),
        single=TrackTrain(*(_support(load, impact.single) for load, impact in zip(single, girder_impacts))),
        double=TrackTrain(*(_support(load, impact.double) for load, impact in zip(double, girder_impacts))),
    )


def calculate_train(pier: PierInput, dead: DeadResult, self_weight: SelfWeightResult) -> TrainResult:
    t, spans = pier.train, pier.spans
    train = vehicle(t)
    ultimate = (GirderImpact(spans.origin.impact, _double_impact(spans.origin, "起点側")),
                GirderImpact(spans.end.impact, _double_impact(spans.end, "終点側")))
    service = tuple(GirderImpact(put(IMPACT, d(impact.single) * SERVICE_RATIO),
                                 put(IMPACT, d(impact.double) * SERVICE_RATIO)) for impact in ultimate)

    def placed(layout: Layout) -> LayoutTrain:
        loading = search_reactions(spans.origin, spans.end, train.trains, loaded=LOADED[layout])
        on_pier = _pier_impact(loading, dead.origin, dead.end, self_weight.pier_bottom.weight)
        groups = (_group(factor, loading, dead.origin, dead.end, impacts, on_pier)
                  for factor, impacts in ((t.factor_ultimate, ultimate), (t.factor_service, service),
                                          (t.factor_fatigue, service)))
        return LayoutTrain(layout, loading, *groups, on_pier)  # type: ignore[arg-type]

    both = placed(Layout.BOTH)
    lengths = (girder_length(spans.origin), girder_length(spans.end))
    seismic = SeismicTrain(
        line_load=train.seismic_load, origin_length=lengths[0], end_length=lengths[1],
        origin=put(FORCE, d(train.seismic_load) * d(lengths[0]) * SEISMIC_SHARE),
        end=put(FORCE, d(train.seismic_load) * d(lengths[1]) * SEISMIC_SHARE))
    return TrainResult(
        loading=both.loading, ultimate=both.ultimate, service=both.service, fatigue=both.fatigue,
        pier_impact=both.pier_impact, seismic=seismic, one_girder=(placed(Layout.ORIGIN), placed(Layout.END)),
    )

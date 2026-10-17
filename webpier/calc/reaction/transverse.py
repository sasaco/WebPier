"""0600 transverse horizontal forces at the bearings on this pier (Example2 07 7-14 to 7-18).

Each action is a force H at a height y above the pier top (the bearing seat)
and its moment M = H × y. Heights: h1 bearing, h2 girder, h3 track, h4 the
wind-receiving height above the track (shelter or barrier).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...core.printed import COEFFICIENT, FORCE, LENGTH, MOMENT, PRESSURE, Printed
from ...inputs import PierInput
from ...inputs.model import Span
from .._exact import d, put
from ..moving_load import MovingLoadResult, search_reactions
from .dead import SupportLoads
from .train import TrainResult, TrackTrain, girder_length

WIND_WITH_TRAIN = PRESSURE.exact(1.5)  # ω1 with the train (07 7-15)
WIND_WITHOUT_TRAIN = PRESSURE.exact(3.0)  # ω1 without the train (07 7-17)
LATERAL_RATIO = Decimal("0.2")  # vehicle lateral load LF = 0.2 × P per axle (07 7-14)
CENTRIFUGAL_DIVISOR = Decimal(127)  # α = V² / (127 R), V in km/h, R in m
SEISMIC_KH_GIRDER = Decimal("1.00")  # girder inertia (07 7-18 (3))
SEISMIC_KH_TRAIN = Decimal("0.30")  # seismic train inertia across the track (07 7-18 (4))
HALF = Decimal("0.5")


@dataclass(frozen=True)
class TransverseForce:
    force: Printed  # H
    height: Printed  # y above the pier top
    moment: Printed  # M = H × y


@dataclass(frozen=True)
class TransverseSide:
    """Transverse actions at the bearing of one girder on this pier (B or C)."""

    centrifugal_coefficient: Printed  # α = V²/(127 R); 0 on a straight track (R = 0)
    rail_height: Printed  # h1 + h2 + h3
    centrifugal_height: Printed  # rail height + centrifugal centroid of the train
    wind_height_with_train: Printed  # receiving height h = h2 + h3 + max(train wind height, h4)
    wind_height_without_train: Printed  # h = h2 + h3 + h4
    centrifugal_ultimate: TransverseForce  # single-track safety/restorability train (R × ρf) × α
    centrifugal_service: TransverseForce
    centrifugal_fatigue: TransverseForce
    vehicle_lateral: TransverseForce  # from the lateral moving-load search, at rail height
    wind_with_train: TransverseForce  # ω1 = 1.5: H = ω × h × L / 2, y = h / 2 + h1
    wind_without_train: TransverseForce  # ω1 = 3.0
    seismic_girder: TransverseForce  # (D1 + D2 + S2) × Kh 1.00 at the equivalent height hs
    seismic_train: TransverseForce  # seismic train reaction × Kh 0.30 at rail height + seismic centroid


@dataclass(frozen=True)
class TransverseResult:
    lateral_axle_load: Printed  # LF = 0.2 × P per axle, without ρf
    lateral_loading: MovingLoadResult  # one car junction: axles a2, a1, a2 apart; RB+RC maximised
    origin: TransverseSide  # at B
    end: TransverseSide  # at C


def _force(force: Printed, height: Printed) -> TransverseForce:
    return TransverseForce(force=force, height=height, moment=put(MOMENT, d(force) * d(height)))


def _side(pier: PierInput, span: Span, loads: SupportLoads, lateral: Printed, seismic_reaction: Printed,
          train_single: tuple[TrackTrain, TrackTrain, TrackTrain], support: str) -> TransverseSide:
    t, h = pier.train, span.heights
    radius = d(span.radius)
    alpha = put(COEFFICIENT, d(span.speed) ** 2 / (CENTRIFUGAL_DIVISOR * radius)) if radius else COEFFICIENT(0)
    rail = LENGTH.total((h[1], h[2], h[3]))
    centrifugal_height = put(LENGTH, d(rail) + d(t.height_centrifugal))
    with_train = put(LENGTH, d(h[2]) + d(h[3]) + max(d(t.height_wind), d(h[4])))
    without_train = LENGTH.total((h[2], h[3], h[4]))
    length = d(girder_length(span))
    centrifugal = [_force(put(FORCE, d(getattr(track, support).load) * d(alpha)), centrifugal_height)
                   for track in train_single]

    def wind(pressure: Printed, height: Printed) -> TransverseForce:
        return _force(put(FORCE, d(pressure) * d(height) * length * HALF), put(LENGTH, d(height) * HALF + d(h[1])))

    girder_weight = put(FORCE, (d(loads.d1) + d(loads.d2) + d(loads.snow2)) * SEISMIC_KH_GIRDER)
    return TransverseSide(
        centrifugal_coefficient=alpha, rail_height=rail, centrifugal_height=centrifugal_height,
        wind_height_with_train=with_train, wind_height_without_train=without_train,
        centrifugal_ultimate=centrifugal[0], centrifugal_service=centrifugal[1], centrifugal_fatigue=centrifugal[2],
        vehicle_lateral=_force(lateral, rail),
        wind_with_train=wind(WIND_WITH_TRAIN, with_train),
        wind_without_train=wind(WIND_WITHOUT_TRAIN, without_train),
        seismic_girder=_force(girder_weight, span.hs),
        seismic_train=_force(put(FORCE, d(seismic_reaction) * SEISMIC_KH_TRAIN),
                             put(LENGTH, d(rail) + d(t.height_seismic))),
    )


def calculate_transverse(pier: PierInput, dead_origin: SupportLoads, dead_end: SupportLoads,
                         train: TrainResult) -> TransverseResult:
    t, spans = pier.train, pier.spans
    axle = put(FORCE, LATERAL_RATIO * d(t.axle_load))
    # One car junction: a car of length 2(a1 + a2) gives axles a2, a1, a2 apart (07 7-14 diagram).
    lateral = search_reactions(spans.origin, spans.end, axle_load=axle, cars=1,
                               car_length=put(LENGTH, 2 * (d(t.a1) + d(t.a2))), a1=t.a1, a2=t.a2)
    single = (train.ultimate.single, train.service.single, train.fatigue.single)
    return TransverseResult(
        lateral_axle_load=axle, lateral_loading=lateral,
        origin=_side(pier, spans.origin, dead_origin, lateral.rb, train.seismic.origin, single, "b"),
        end=_side(pier, spans.end, dead_end, lateral.rc, train.seismic.end, single, "c"),
    )

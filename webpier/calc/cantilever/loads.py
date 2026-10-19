"""The vertical loads of the girders on the cantilever beam (0900 13.1 (1), decision 59; Example2 13-1 to 13-14).

Three train loadings are searched with 0600's moving load (calc.moving_load): the one that maximises RB (B支点最大),
the one that maximises RC (C支点最大) and 0600's own, which maximises RB + RC (B+C支点最大). For each loading every
bearing of a girder gets the girder's reaction times its train share: one track (the larger of the two tracks'
shares) and both tracks (the double share of 0600), each with the impact of that track count (the girder's
coefficients of 0600: 安全性 and 使用性, decision 26); the larger load, with its impact, is what the cantilever
carries (Example2 13-25: the origin girder's G1 by one track, the end girder's by both). The seismic train loads a
bearing by one track with 0600's seismic reaction (13-8 (c)).

A horizontal force H at height y above the bearing seat twists the girder about the pier axis with M = H·y and
loads bearing i with ±M·|xi| / Σxi² (13-9 to 13-14): the vehicle lateral load of a loading (0.2 P per axle, so
0.2 × the girder's reaction of that loading at this pier; for B+C支点最大 0600's one-car junction of 0620, and only
at the girder the loading maximises, as 13-27 sums them), the wind with and without the train and the seismic
inertia of the girder and of the train, all with 0600's transverse forces, heights and moments (decision 59: no
snow shelter; the girder inertia is 0600's force at Kh 1.00 times the 最大応答震度 across the track). The vertical
on a bearing is kept as a magnitude; the cantilever takes it downward.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...core.printed import FORCE, MOMENT, Printed
from ...inputs import PierInput
from .._exact import d, put
from ..moving_load import Girder, MovingLoadResult, Objective, search_reactions
from ..reaction.train import GirderImpact, TrainResult
from ..reaction.transverse import LATERAL_RATIO, TransverseForce, TransverseResult, TransverseSide
from .geometry import GirderBearings, NumberedBearing


class Loading(Enum):
    ORIGIN_MAX = "B支点最大"
    END_MAX = "C支点最大"
    BOTH_MAX = "B+C支点最大"


OBJECTIVES = {Loading.ORIGIN_MAX: Objective.ORIGIN, Loading.END_MAX: Objective.END, Loading.BOTH_MAX: Objective.PIER}


class Wind(Enum):
    WITH_TRAIN = "列車荷重がある場合"
    WITHOUT_TRAIN = "列車荷重がない場合"


@dataclass(frozen=True)
class TrackLoad:
    """The train on one bearing for one track count."""

    share: Printed  # the bearing's share of the girder's reaction
    load: Printed  # L = R × share, kN
    impact_ultimate: Printed  # I = L × i (安全性, the girder's coefficient of this track count)
    impact_service: Printed  # 使用性


@dataclass(frozen=True)
class BearingTrain:
    bearing: NumberedBearing
    single: TrackLoad  # one track: the larger of the two tracks' shares
    double: TrackLoad  # both tracks: the double share
    adopted_double: bool  # the cantilever carries the larger load with its impact

    @property
    def adopted(self) -> TrackLoad:
        return self.double if self.adopted_double else self.single


@dataclass(frozen=True)
class GirderTrain:
    girder: Girder
    reaction: Printed  # R of the girder at this pier for the loading (RB or RC)
    impact_ultimate: GirderImpact
    impact_service: GirderImpact
    bearings: tuple[BearingTrain, ...]

    def bearing(self, number: int) -> BearingTrain:
        return next(item for item in self.bearings if item.bearing.number == number)


@dataclass(frozen=True)
class LoadingResult:
    loading: Loading
    result: MovingLoadResult  # RA..RD and the axle positions
    girders: dict[Girder, GirderTrain]


@dataclass(frozen=True)
class SeismicTrainLoad:
    bearing: NumberedBearing
    reaction: Printed  # 0600's seismic reaction of the girder (one track)
    share: Printed  # the larger of the two tracks' shares
    load: Printed  # kN


@dataclass(frozen=True)
class TorqueVertical:
    bearing: NumberedBearing
    force: Printed  # M·|xi| / Σxi², kN, a magnitude


@dataclass(frozen=True)
class Torque:
    """A horizontal force on one girder and the vertical it puts on each bearing."""

    girder: Girder
    force: Printed  # H, kN
    height: Printed  # y, m
    moment: Printed  # M = H × y, kN m
    sum_squares: Printed  # Σ xi², m²
    verticals: tuple[TorqueVertical, ...]

    def vertical(self, number: int) -> Printed:
        return next(item.force for item in self.verticals if item.bearing.number == number)


def _single_share(bearing: NumberedBearing) -> Printed:
    shares = bearing.loads.bearing.shares
    return shares.l1 if shares.l1.value >= shares.l2.value else shares.l2


def _track(share: Printed, reaction: Printed, ultimate: Printed, service: Printed) -> TrackLoad:
    load = put(FORCE, d(reaction) * d(share))
    return TrackLoad(share, load, put(FORCE, d(load) * d(ultimate)), put(FORCE, d(load) * d(service)))


def _girder(girder: Girder, reaction: Printed, train: TrainResult, bearings: GirderBearings) -> GirderTrain:
    ultimate = train.ultimate.origin_impact if girder is Girder.ORIGIN else train.ultimate.end_impact
    service = train.service.origin_impact if girder is Girder.ORIGIN else train.service.end_impact
    found = []
    for bearing in bearings.bearings:
        single = _track(_single_share(bearing), reaction, ultimate.single, service.single)
        double = _track(bearing.loads.double, reaction, ultimate.double, service.double)
        found.append(BearingTrain(bearing, single, double, double.load.value > single.load.value))
    return GirderTrain(girder, reaction, ultimate, service, tuple(found))


def train_loadings(pier: PierInput, train: TrainResult, girders: dict[Girder, GirderBearings]
                   ) -> tuple[LoadingResult, ...]:
    """The three loadings and the train on every bearing for each (13-1 to 13-8)."""
    t, spans = pier.train, pier.spans
    found = []
    for loading in Loading:
        result = search_reactions(spans.origin, spans.end, axle_load=t.axle_load, cars=t.cars,
                                  car_length=t.car_length, a1=t.a1, a2=t.a2, objective=OBJECTIVES[loading])
        found.append(LoadingResult(loading, result, {
            Girder.ORIGIN: _girder(Girder.ORIGIN, result.rb, train, girders[Girder.ORIGIN]),
            Girder.END: _girder(Girder.END, result.rc, train, girders[Girder.END])}))
    return tuple(found)


def seismic_train(train: TrainResult, girders: dict[Girder, GirderBearings]) -> dict[Girder, tuple[SeismicTrainLoad, ...]]:
    """The seismic train on every bearing by one track (13-8 (c))."""
    found = {}
    for girder, reaction in ((Girder.ORIGIN, train.seismic.origin), (Girder.END, train.seismic.end)):
        found[girder] = tuple(SeismicTrainLoad(bearing, reaction, _single_share(bearing),
                                               put(FORCE, d(reaction) * d(_single_share(bearing))))
                              for bearing in girders[girder].bearings)
    return found


def torque(girder: GirderBearings, force: Printed, height: Printed) -> Torque:
    moment = put(MOMENT, d(force) * d(height))
    verticals = tuple(TorqueVertical(bearing, put(FORCE, abs(d(moment) * d(bearing.position)) / d(girder.sum_squares)))
                      for bearing in girder.bearings)
    return Torque(girder.girder, force, height, moment, girder.sum_squares, verticals)


def _torque_of(girder: GirderBearings, action: TransverseForce) -> Torque:
    return torque(girder, action.force, action.height)


def _sides(transverse: TransverseResult) -> tuple[tuple[Girder, TransverseSide], ...]:
    return ((Girder.ORIGIN, transverse.origin), (Girder.END, transverse.end))


def lateral_torques(loadings: tuple[LoadingResult, ...], transverse: TransverseResult,
                    girders: dict[Girder, GirderBearings]) -> dict[Loading, dict[Girder, Torque]]:
    """The vehicle lateral load of each loading (13-9 to 13-11): 0.2 × the maximised girder's reaction at the
    rail height, or 0600's junction loading for B+C支点最大."""
    found: dict[Loading, dict[Girder, Torque]] = {}
    for item in loadings:
        found[item.loading] = {}
        for girder, side in _sides(transverse):
            if item.loading is Loading.BOTH_MAX:
                force = transverse.lateral_loading.rb if girder is Girder.ORIGIN else transverse.lateral_loading.rc
            elif (item.loading is Loading.ORIGIN_MAX) == (girder is Girder.ORIGIN):
                force = put(FORCE, LATERAL_RATIO * d(item.girders[girder].reaction))
            else:
                force = FORCE(0)
            found[item.loading][girder] = torque(girders[girder], force, side.rail_height)
    return found


def wind_torques(transverse: TransverseResult, girders: dict[Girder, GirderBearings]) -> dict[Wind, dict[Girder, Torque]]:
    """The wind with and without the train (13-12), with 0600's forces and heights."""
    return {Wind.WITH_TRAIN: {girder: _torque_of(girders[girder], side.wind_with_train)
                              for girder, side in _sides(transverse)},
            Wind.WITHOUT_TRAIN: {girder: _torque_of(girders[girder], side.wind_without_train)
                                 for girder, side in _sides(transverse)}}


def seismic_girder_torques(transverse: TransverseResult, kh: Printed,
                           girders: dict[Girder, GirderBearings]) -> dict[Girder, Torque]:
    """The girder inertia across the track (13-13): 0600's force at Kh 1.00 times the 最大応答震度 *kh*, at hs."""
    return {girder: torque(girders[girder], put(FORCE, d(side.seismic_girder.force) * d(kh)), side.seismic_girder.height)
            for girder, side in _sides(transverse)}


def seismic_train_torques(transverse: TransverseResult, girders: dict[Girder, GirderBearings]) -> dict[Girder, Torque]:
    """The seismic train inertia across the track (13-14): 0600's force (Kh 0.30) and height."""
    return {girder: _torque_of(girders[girder], side.seismic_train) for girder, side in _sides(transverse)}


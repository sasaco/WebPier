"""車両の定義 (decision 101, CONTEXT.md): the loads a 車両名 stands for, owned by the program.

The input names the vehicle and, for a vehicle of repeated cars, how many (編成数); everything else is here, with its
source:

- EA-17 (標準列車荷重, RC標準【橋りょう編 5.4.3】; Example橋脚4 I-38 図7.1.1, I-41): E-17, twelve 170 kN axles
  2.8・2.0・2.8・2.0・2.8・4.0・2.8・2.0・2.8・2.0・2.8 m apart and 50 kN/m from 2.0 m behind the last, and A-17,
  130・190・190 kN 1.9・2.0 m apart; the one giving the larger reaction is adopted. The vehicle lateral load is 15 % of the
  driving axle load of the two locomotives at their coupling, four axles 2.8・4.0・2.8 m apart (図7.1.3, 【橋りょう編
  5.4.6】); the seismic train 35 kN/m (【橋りょう編 5.4.3】).
- P-16: a 20 m car of 160 kN axles, a1 (the coupling) 2.8 m and a2 2.2 m, repeated; its vehicle lateral load 20 % of the
  axle load on one car junction (a2, a1, a2); the seismic train 32 kN/m. These are Example橋脚2's (the input of the
  example, .claude/docs/Example橋脚/pre/input-上部構造.pdf), until a table of the standard is at hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.printed import FORCE, LENGTH, LINE_LOAD, Printed
from ..inputs.model import BrakingRule, Train
from ._exact import d, put
from .moving_load import AxleTrain, car_offsets


def _offsets(gaps: tuple[str, ...]) -> tuple[Decimal, ...]:
    found, position = [Decimal(0)], Decimal(0)
    for gap in gaps:
        position += Decimal(gap)
        found.append(position)
    return tuple(found)


E17_AXLE = FORCE.exact(170)
E17 = AxleTrain("E-17", (E17_AXLE,) * 12,
                _offsets(("2.8", "2.0", "2.8", "2.0", "2.8", "4.0", "2.8", "2.0", "2.8", "2.0", "2.8")),
                tail_load=LINE_LOAD.exact(50), tail_gap=Decimal("2.0"))
A17 = AxleTrain("A-17", (FORCE.exact(130), FORCE.exact(190), FORCE.exact(190)), _offsets(("1.9", "2.0")))
EA17_LATERAL_RATIO = Decimal("0.15")
EA17_LATERAL_GAPS = ("2.8", "4.0", "2.8")
EA17_SEISMIC = LINE_LOAD.exact(35)

P16_CAR = LENGTH.exact(20)
P16_A1, P16_A2 = LENGTH.exact(2.8), LENGTH.exact(2.2)
P16_AXLE = FORCE.exact(160)
P16_LATERAL_RATIO = Decimal("0.2")
P16_SEISMIC = LINE_LOAD.exact(32)


@dataclass(frozen=True)
class Vehicle:
    name: str
    braking_rule: BrakingRule
    trains: tuple[AxleTrain, ...]  # searched in turn, the larger reaction adopted
    lateral_ratio: Decimal  # LF = ratio × the axle load
    lateral_base: Printed  # the axle load the ratio applies to
    lateral: AxleTrain  # LF on its axles
    seismic_load: Printed  # kN/m per track
    car_length: Printed | None  # Lv of the axle-load braking formula; None for EA-17
    axle_load: Printed | None  # P of that formula


def _lateral(ratio: Decimal, base: Printed, offsets: tuple[Decimal, ...]) -> AxleTrain:
    return AxleTrain("LF", (put(FORCE, ratio * d(base)),) * len(offsets), offsets)


def vehicle(train: Train) -> Vehicle:
    if train.braking_rule is BrakingRule.EA17:
        lateral = _lateral(EA17_LATERAL_RATIO, E17_AXLE, _offsets(EA17_LATERAL_GAPS))
        return Vehicle(train.vehicle, train.braking_rule, (E17, A17), EA17_LATERAL_RATIO, E17_AXLE, lateral,
                       EA17_SEISMIC, None, None)
    assert train.cars is not None  # the parser asks a vehicle of repeated cars for its 編成数
    offsets = car_offsets(train.cars, d(P16_CAR), d(P16_A1), d(P16_A2))
    cars = AxleTrain(train.vehicle, (P16_AXLE,) * len(offsets), offsets)
    # One car junction: a car of length 2(a1 + a2) gives axles a2, a1, a2 apart (07 7-14 diagram).
    junction = car_offsets(1, 2 * (d(P16_A1) + d(P16_A2)), d(P16_A1), d(P16_A2))
    lateral = _lateral(P16_LATERAL_RATIO, P16_AXLE, junction)
    return Vehicle(train.vehicle, train.braking_rule, (cars,), P16_LATERAL_RATIO, P16_AXLE, lateral, P16_SEISMIC,
                   P16_CAR, P16_AXLE)

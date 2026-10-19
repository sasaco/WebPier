"""The horizontal forces at the bearings and what the cantilever beam takes of them (0900 13.1 (2), decision 59;
Example2 13-15 to 13-22, 13-28, 13-29).

The girder forces T (LR + B of each combination, the seismic inertia) and the vertical loads Rm are 0600's
(calc.reaction.longitudinal): the four 安全性（破壊） combinations 1.0LR+1.23B, 1.1LR+1.23B, 1.0LR+1.35B and 1.0LR,
and the seismic case with T = 最大応答震度 along the track × 0600's girder inertia at Kh 1.00 + 0600's seismic train
inertia. Example2 chapter 13 shares each girder's force between its rubber bearings and its stoppers (decision 59,
unlike chapter 7's one movable or fixed bearing, which 0600 follows and keeps):

- at a movable girder end the rubber bearings take Hbd = μ·Rm (no upper bound) and the stoppers nothing, but in the
  seismic case the stoppers take T/n (n the bearing lines of 0600) and the rubber bearings nothing;
- at a fixed end the rubber bearings take nothing and the stoppers Hsd = max(T − ½μ·Rm, T/n), in the seismic case T.

Each device takes an equal share of its girder's force (the counts of 上部構造.支承データ: ゴム支承の箇所数,
ストッパーの箇所数), and the cantilever carries those on it (片持ち梁上のゴム支承, 片持ち梁上のストッパー) with the
torsion arm Y of its geometry. A count that is blank, or zero while the device carries a force, is an input error.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.errors import InputError
from ...core.printed import FORCE, MOMENT, Printed
from ...inputs import PierInput
from ...inputs.model import Span
from .._exact import d, put, total
from ..moving_load import Girder
from ..reaction.longitudinal import (BEARING_CHOICES, BEARING_LINES, DEFINITIONS, BearingForce, BearingType,
                                     LongitudinalCase, LongitudinalResult)
from .geometry import GIRDER_SIDES

# The combinations of 0600 whose bearing forces load the cantilever (13-16 to 13-19), in report order.
COMBINATIONS = (LongitudinalCase.SAFETY_LR10_B10, LongitudinalCase.SAFETY_LR11_B10, LongitudinalCase.SAFETY_LR10_B11,
                LongitudinalCase.SAFETY_LR10)
SEISMIC = "地震時"
_SUPPORT = "上部構造.支承データ"


@dataclass(frozen=True)
class Device:
    """One kind of device (rubber bearings or stoppers) at one girder end, for one case."""

    total: Printed  # the force on the girder this kind takes, kN
    count: int  # on the girder
    each: Printed  # per device: total / count (0 for no force)
    on_cantilever: int
    force: Printed  # on the cantilever: each × on_cantilever, kN
    arm: Printed  # Y, m
    moment: Printed  # Mt = force × Y, kN m


@dataclass(frozen=True)
class GirderDevices:
    girder: Girder
    bearing: BearingType
    applied: Printed  # T on the girder, kN
    vertical: Printed | None  # Rm of 0600 (at this bearing if movable, at the far bearing if fixed); None: seismic
    friction: Printed | None  # μ·Rm (movable, not seismic)
    candidate: Printed | None  # T − ½μ·Rm (fixed, not seismic)
    share: Printed  # T / n
    inertia: Printed | None  # the girder inertia Kh × 0600's force at Kh 1.00 (seismic only)
    rubber: Device
    stopper: Device


@dataclass(frozen=True)
class BearingCase:
    case: LongitudinalCase | None  # None: the seismic case
    label: str  # 1.0 LR + 1.23B …, or 地震時
    origin: GirderDevices
    end: GirderDevices

    @property
    def force(self) -> Printed:
        """The horizontal force on the cantilever, kN (13-28: 合計)."""
        return put(FORCE, total(device.force for girder in (self.origin, self.end)
                                for device in (girder.rubber, girder.stopper)))

    @property
    def moment(self) -> Printed:
        """Mt on the cantilever, kN m."""
        return put(MOMENT, total(device.moment for girder in (self.origin, self.end)
                                 for device in (girder.rubber, girder.stopper)))


def _count(value: int | None, path: str) -> int:
    if value is None:
        raise InputError(f"{path}: 値が必要です")
    return value


def _device(total_force: Printed, count: int, on_cantilever: int, arm: Printed, path: str, what: str) -> Device:
    if on_cantilever > count:
        raise InputError(f"{path}.片持ち梁上の{what}: {what}の箇所数（{count}）以下が必要です（{on_cantilever}）")
    if total_force.value and not count:
        raise InputError(f"{path}.{what}の箇所数: {what}に水平荷重 {total_force.value:g} kN が働くのに箇所数が 0 です")
    each = put(FORCE, d(total_force) / count) if count else FORCE(0)
    force = put(FORCE, d(each) * on_cantilever)
    return Device(total_force, count, each, on_cantilever, force, arm, put(MOMENT, d(force) * d(arm)))


def _devices(girder: Girder, span: Span, applied: Printed, rubber_total: Printed, stopper_total: Printed,
             vertical: Printed | None, friction: Printed | None, candidate: Printed | None, share: Printed,
             arm: Printed, inertia: Printed | None = None) -> GirderDevices:
    path = f"{_SUPPORT}.{GIRDER_SIDES[girder]}"
    rubber = _device(rubber_total, _count(span.rubber_count, f"{path}.ゴム支承の箇所数"),
                     _count(span.rubber_on_cantilever, f"{path}.片持ち梁上のゴム支承"), arm, path, "ゴム支承")
    stopper = _device(stopper_total, _count(span.stopper_count, f"{path}.ストッパーの箇所数"),
                      _count(span.stopper_on_cantilever, f"{path}.片持ち梁上のストッパー"), arm, path, "ストッパー")
    return GirderDevices(girder, BEARING_CHOICES[span.bearing], applied, vertical, friction, candidate, share,
                         inertia, rubber, stopper)


def _combination(girder: Girder, span: Span, force: BearingForce, arm: Printed) -> GirderDevices:
    zero = FORCE(0)
    if force.bearing is BearingType.MOVABLE:
        assert force.friction is not None
        return _devices(girder, span, force.applied, force.friction, zero, force.vertical, force.friction, None,
                        force.share, arm)
    return _devices(girder, span, force.applied, zero, force.force, force.vertical, None, force.fixed_candidate,
                    force.share, arm)


def label(case: LongitudinalCase, result: LongitudinalResult) -> str:
    """1.0 LR + 1.23B, as 0600 prints the combination (the brake factor includes ρ)."""
    brake = result.case(case).origin.brake_factor
    lr = f"{DEFINITIONS[case].lr_factor} LR"
    return lr if brake is None else f"{lr} + {brake.value:.2f}B"


def _seismic(girder: Girder, span: Span, kh: Printed, result: LongitudinalResult, arm: Printed) -> GirderDevices:
    forces = result.origin if girder is Girder.ORIGIN else result.end
    girder_inertia = put(FORCE, d(forces.seismic_girder) * d(kh))
    applied = put(FORCE, total((girder_inertia, forces.seismic_train)))
    share = put(FORCE, d(applied) / BEARING_LINES)
    zero = FORCE(0)
    stopper = share if BEARING_CHOICES[span.bearing] is BearingType.MOVABLE else applied
    return _devices(girder, span, applied, zero, stopper, None, None, None, share, arm, girder_inertia)


def bearing_cases(pier: PierInput, result: LongitudinalResult, kh_longitudinal: Printed,
                  arm: Printed) -> tuple[BearingCase, ...]:
    """The four combinations and the seismic case at both girder ends, with *arm* = Y of the cantilever."""
    spans = pier.spans
    cases = []
    for case in COMBINATIONS:
        forces = result.case(case)
        cases.append(BearingCase(case, label(case, result),
                                 _combination(Girder.ORIGIN, spans.origin, forces.origin, arm),
                                 _combination(Girder.END, spans.end, forces.end, arm)))
    cases.append(BearingCase(None, SEISMIC, _seismic(Girder.ORIGIN, spans.origin, kh_longitudinal, result, arm),
                             _seismic(Girder.END, spans.end, kh_longitudinal, result, arm)))
    return tuple(cases)


def seismic_girder_force(result: LongitudinalResult, girder: Girder, kh: Printed) -> Printed:
    """The seismic inertia of the girder along the track at *kh* (13-15 (c)), without the train."""
    forces = result.origin if girder is Girder.ORIGIN else result.end
    return put(FORCE, d(forces.seismic_girder) * d(kh))

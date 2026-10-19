"""Moving point loads on the two girders resting on the pier (0600 train, 0600/0620 vehicle lateral).

The girders are two simple beams in a row: the origin girder (overhang L1 at
its far bearing A, span, overhang L2 at the pier bearing B) and the end girder
(overhang L1 at the pier bearing C, span, overhang L2 at its far bearing D).

The search keeps the source semantics: every axle in turn is aligned with each
of the seven support/joint points (from the far end backwards); axles off the
bridge are skipped; an axle exactly at the joint goes to the girder where it
gives the larger pier reaction (ties to the end girder); the candidate with the
largest objective (RB + RC for 0600 and 0620; RB alone or RC alone for the
B支点最大 and C支点最大 loadings of 0900, decision 59) is adopted, and an equal
value keeps the earlier candidate.

The search is not rounded (ADR-0003: iterations are exempt), but it runs on
exact decimal positions: every input length is a printed millimetre value, so
an axle that lands exactly on the girder end stays at 0 instead of -1e-15 (in
binary floating point Example2 7-1 would lose its axle at x = 0 and give
RB = 277.35 instead of 272.47). Only the adopted loading is printed: each
axle's lever to the far bearing to 3 decimals, and RA..RD recomputed from those
printed levers. The loading figure prints the spacings of the far bearings and
the axles, and the girder lengths (Example2 07 7-1/7-14).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..core.errors import InputError
from ..core.printed import FORCE, LENGTH, Precision, Printed
from ..inputs.model import Span
from ._exact import d, put, total


AXLES = Precision(0, "")  # a number of axles, printed in RA = P × (axles) − RB


class Objective(Enum):
    """What a loading maximises: the reactions on this pier (Example2 07 7-1, 13-1 c)), or one of them."""

    PIER = "RB+RC"  # both supports on this pier (0600, 0620)
    ORIGIN = "RB"  # the origin girder's support B (0900 B支点最大)
    END = "RC"  # the end girder's support C (0900 C支点最大)


class Girder(Enum):
    ORIGIN = "origin"  # carries A and B
    END = "end"  # carries C and D


@dataclass(frozen=True)
class LoadedAxle:
    """One axle of the adopted loading."""

    girder: Girder
    lever: Printed  # distance from the girder's far bearing (A or D); negative on the far overhang


@dataclass(frozen=True)
class MovingLoadResult:
    axle_load: Printed  # P per axle
    axles: tuple[LoadedAxle, ...]  # axles on the bridge, in train order
    ra: Printed  # P × (axles on the origin girder) − RB
    rb: Printed  # P × Σ lever / span of the origin girder
    rc: Printed  # P × Σ lever / span of the end girder
    rd: Printed  # P × (axles on the end girder) − RC
    origin_axles: Printed  # number of axles on the origin girder (RA = P × origin_axles − RB)
    end_axles: Printed  # number of axles on the end girder (RD = P × end_axles − RC)
    spacings: tuple[Printed, ...]  # between the bearings A and D and the axles, from the origin end (figure)
    girder_lengths: tuple[Printed, Printed]  # origin and end girder L1 + span + L2 (figure)


def girder_length(span: Span) -> Printed:
    """Girder length L1 + span + L2."""
    return LENGTH.total((span.l1, span.span, span.l2))


def _axle_offsets(cars: int, car_length: Decimal, a1: Decimal, a2: Decimal) -> list[Decimal]:
    """Axle offsets from the first axle: (a2, a4, a2, a1) per car, or (a4, a1) when a2 = 0."""
    if a2 > 0:
        intervals = (a2, car_length - a1 - 2 * a2, a2, a1)
    else:
        intervals = (car_length - a1, a1)
    offsets, position = [], Decimal(0)
    for _ in range(cars):
        for gap in intervals:
            offsets.append(position)
            position += gap
    return offsets


def search_reactions(origin: Span, end: Span, *, axle_load: Printed, cars: int, car_length: Printed,
                     a1: Printed, a2: Printed, objective: Objective = Objective.PIER) -> MovingLoadResult:
    o_far, o_span, o_pier = d(origin.l1), d(origin.span), d(origin.l2)
    e_pier, e_span, e_far = d(end.l1), d(end.span), d(end.l2)
    points = [Decimal(0)]
    for length in (o_far, o_span, o_pier, e_pier, e_span, e_far):
        points.append(points[-1] + length)
    joint, bridge_end = points[3], points[6]
    end_length = points[6] - points[3]
    load = d(axle_load)

    def origin_lever(x: Decimal) -> Decimal:
        return x - o_far

    def end_lever(x: Decimal) -> Decimal:
        return end_length - (x - joint) - e_far

    def on_origin(x: Decimal) -> bool:
        if x != joint:
            return x < joint
        return load * origin_lever(x) / o_span > load * end_lever(x) / e_span

    offsets = _axle_offsets(cars, d(car_length), d(a1), d(a2))
    best: list[Decimal] | None = None
    best_score = Decimal(0)
    for anchor in offsets:
        for point in reversed(points):
            candidate = []
            for offset in offsets:
                x = point - (offset - anchor)
                if x < 0:
                    break
                if x <= bridge_end:
                    candidate.append(x)
            rb = sum((load * origin_lever(x) / o_span for x in candidate if on_origin(x)), Decimal(0))
            rc = sum((load * end_lever(x) / e_span for x in candidate if not on_origin(x)), Decimal(0))
            score = {Objective.PIER: rb + rc, Objective.ORIGIN: rb, Objective.END: rc}[objective]
            if score > best_score:
                best, best_score = candidate, score
    if best is None:
        raise InputError(f"移動荷重: 正の反力となる載荷位置がなく、{objective.value}の最大を求められません（軸重・寸法を確認）")

    axles = tuple(
        LoadedAxle(Girder.ORIGIN, put(LENGTH, origin_lever(x))) if on_origin(x)
        else LoadedAxle(Girder.END, put(LENGTH, end_lever(x)))
        for x in best)
    origin_axles = [axle for axle in axles if axle.girder is Girder.ORIGIN]
    end_axles = [axle for axle in axles if axle.girder is Girder.END]
    counts = AXLES(len(origin_axles)), AXLES(len(end_axles))
    rb = put(FORCE, d(axle_load) * total(axle.lever for axle in origin_axles) / d(origin.span))
    rc = put(FORCE, d(axle_load) * total(axle.lever for axle in end_axles) / d(end.span))
    # An axle on a far bearing is one point of the figure: no zero spacing.
    marks = sorted({*best, o_far, bridge_end - e_far})
    return MovingLoadResult(
        axle_load=axle_load, axles=axles,
        ra=put(FORCE, d(axle_load) * d(counts[0]) - d(rb)), rb=rb,
        rc=rc, rd=put(FORCE, d(axle_load) * d(counts[1]) - d(rc)),
        origin_axles=counts[0], end_axles=counts[1],
        spacings=tuple(put(LENGTH, after - before) for before, after in zip(marks, marks[1:])),
        girder_lengths=(girder_length(origin), girder_length(end)),
    )

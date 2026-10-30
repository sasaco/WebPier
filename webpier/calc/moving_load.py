"""Moving point loads on the two girders resting on the pier (0600 train, 0600/0620 vehicle lateral).

The girders are two simple beams in a row: the origin girder (overhang L1 at
its far bearing A, span, overhang L2 at the pier bearing B) and the end girder
(overhang L1 at the pier bearing C, span, overhang L2 at its far bearing D).

A train (decision 101) is its axles, front first, each with its own load, and an
optional line load following its last axle (E-17's 50 kN/m). The search keeps
the source semantics: every axle in turn is aligned with each of the seven
support/joint points (from the far end backwards), then the head of the line
load; axles off the bridge are skipped and the line load is cut at the bridge
ends; an axle exactly at the joint goes to the girder whose reaction the
objective counts: for RB + RC the one where it gives the larger pier reaction
(ties to the end girder), for RB alone the origin girder and for RC alone the
end girder (decision 125: the C支点最大 of Example橋脚4 counts the axle at the
joint on the end girder, R_C 913.75); the candidate with the largest
objective (RB + RC for 0600 and 0620; RB alone or RC alone for the B支点最大
and C支点最大 loadings of 0900, decision 59) is adopted, and an equal value
keeps the earlier candidate. The train runs towards D first, then towards A,
and the trains of a vehicle (E-17, A-17) are searched in turn: the larger wins,
a tie keeps the earlier.

The search is not rounded (ADR-0003: iterations are exempt), but it runs on
exact decimal positions: every input length is a printed millimetre value, so
an axle that lands exactly on the girder end stays at 0 instead of -1e-15 (in
binary floating point Example2 7-1 would lose its axle at x = 0 and give
RB = 272.47 instead of 277.35). Only the adopted loading is printed: each
axle's lever to the far bearing to 3 decimals, the length of the line load on
each girder and its centroid's lever, and RA..RD recomputed from those printed
values. The loading figure prints the spacings of the far bearings, the axles
and the head of the line load, and the girder lengths (Example2 07 7-1/7-14).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
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
class AxleTrain:
    """One train of a vehicle (decision 101): its axle loads and their offsets from the first axle, front first, and
    the line load following the last axle at a gap."""

    name: str  # E-17, A-17, P-16, or the vehicle lateral load
    loads: tuple[Printed, ...]
    offsets: tuple[Decimal, ...]  # increasing, the first 0
    tail_load: Printed | None = None  # kN/m behind the last axle
    tail_gap: Decimal = Decimal(0)


@dataclass(frozen=True)
class LoadedAxle:
    """One axle of the adopted loading."""

    girder: Girder
    lever: Printed  # distance from the girder's far bearing (A or D); negative on the far overhang
    # P of this axle when the train's axle loads differ (A-17); else the result's axle_load
    load: Printed | None = field(default=None, metadata={"json": "set"})


@dataclass(frozen=True)
class LoadedTail:
    """The part of the following line load on one girder."""

    girder: Girder
    load: Printed  # q, kN/m
    length: Printed  # a, on this girder
    lever: Printed  # e: its centroid's distance from the girder's far bearing


@dataclass(frozen=True)
class MovingLoadResult:
    train: str  # the adopted train's name
    axle_load: Printed | None  # P of every axle; None when they differ, and each axle has its own (A-17)
    axles: tuple[LoadedAxle, ...]  # axles on the bridge, in train order
    tails: tuple[LoadedTail, ...]  # the line load on each girder it reaches, origin first
    ra: Printed  # Σ P (axles on the origin girder) + q × a − RB
    rb: Printed  # (Σ P × lever + q × a × e) / span of the origin girder
    rc: Printed  # (Σ P × lever + q × a × e) / span of the end girder
    rd: Printed  # Σ P (axles on the end girder) + q × a − RC
    origin_axles: Printed  # number of axles on the origin girder
    end_axles: Printed  # number of axles on the end girder
    spacings: tuple[Printed, ...]  # between the bearings A and D, the axles and the line load's head (figure)
    girder_lengths: tuple[Printed, Printed]  # origin and end girder L1 + span + L2 (figure)
    # x of the line load's head from the origin girder's far end, when it is on the bridge (figure)
    tail_head: Printed | None = field(default=None, metadata={"json": "set"})

    def load(self, axle: LoadedAxle) -> Printed:
        return axle.load if self.axle_load is None else self.axle_load  # type: ignore[return-value]

    def on(self, girder: Girder) -> tuple[LoadedAxle, ...]:
        return tuple(axle for axle in self.axles if axle.girder is girder)

    def tail(self, girder: Girder) -> LoadedTail | None:
        return next((part for part in self.tails if part.girder is girder), None)


def girder_length(span: Span) -> Printed:
    """Girder length L1 + span + L2."""
    return LENGTH.total((span.l1, span.span, span.l2))


def car_offsets(cars: int, car_length: Decimal, a1: Decimal, a2: Decimal) -> tuple[Decimal, ...]:
    """Axle offsets from the first axle of repeated cars: (a2, a4, a2, a1) per car, or (a4, a1) when a2 = 0."""
    if a2 > 0:
        intervals = (a2, car_length - a1 - 2 * a2, a2, a1)
    else:
        intervals = (car_length - a1, a1)
    offsets, position = [], Decimal(0)
    for _ in range(cars):
        for gap in intervals:
            offsets.append(position)
            position += gap
    return tuple(offsets)


class _Bridge:
    """The two girders in a row: x from the origin girder's far end; *loaded* the only girder the train is on (列車の配置,
    decision 102), else both; *objective* decides the girder of an axle at the joint."""

    def __init__(self, origin: Span, end: Span, loaded: Girder | None, objective: Objective = Objective.PIER) -> None:
        self.origin, self.end, self.loaded, self.objective = origin, end, loaded, objective
        points = [Decimal(0)]
        for length in (origin.l1, origin.span, origin.l2, end.l1, end.span, end.l2):
            points.append(points[-1] + d(length))
        self.points = tuple(points)
        self.joint, self.length = points[3], points[6]
        self.lo = self.joint if loaded is Girder.END else Decimal(0)
        self.hi = self.joint if loaded is Girder.ORIGIN else self.length

    def on(self, x: Decimal) -> bool:
        return self.lo <= x <= self.hi

    def origin_lever(self, x: Decimal) -> Decimal:
        return x - d(self.origin.l1)

    def end_lever(self, x: Decimal) -> Decimal:
        return self.length - x - d(self.end.l2)

    def lever(self, girder: Girder, x: Decimal) -> Decimal:
        return self.origin_lever(x) if girder is Girder.ORIGIN else self.end_lever(x)

    def on_origin(self, x: Decimal) -> bool:
        if self.loaded is not None:
            return self.loaded is Girder.ORIGIN
        if x != self.joint:
            return x < self.joint
        if self.objective is not Objective.PIER:  # the girder whose reaction is maximised
            return self.objective is Objective.ORIGIN
        return self.origin_lever(x) / d(self.origin.span) > self.end_lever(x) / d(self.end.span)

    def tail_parts(self, head: Decimal, sign: int) -> list[tuple[Girder, Decimal, Decimal]]:
        """(girder, lo, hi) of a line load from its head away from the train's front."""
        lo, hi = (self.lo, min(head, self.hi)) if sign > 0 else (max(head, self.lo), self.hi)
        parts = []
        for girder, start, stop in ((Girder.ORIGIN, Decimal(0), self.joint), (Girder.END, self.joint, self.length)):
            a, b = max(lo, start), min(hi, stop)
            if b > a:
                parts.append((girder, a, b))
        return parts


@dataclass(frozen=True)
class _Candidate:
    train: AxleTrain
    axles: tuple[tuple[Decimal, Printed], ...]  # (x, P) of the axles on the bridge, in train order
    head: Decimal | None  # x of the line load's head, None without one
    tails: tuple[tuple[Girder, Decimal, Decimal], ...]


def _place(bridge: _Bridge, train: AxleTrain, front: Decimal, sign: int) -> _Candidate:
    axles = ((front - sign * offset, load) for offset, load in zip(train.offsets, train.loads, strict=True))
    head, tails = None, ()
    if train.tail_load is not None:
        head = front - sign * (train.offsets[-1] + train.tail_gap)
        tails = tuple(bridge.tail_parts(head, sign))
    return _Candidate(train, tuple((x, load) for x, load in axles if bridge.on(x)), head, tails)


def _score(bridge: _Bridge, candidate: _Candidate, objective: Objective) -> Decimal:
    reactions = {Girder.ORIGIN: Decimal(0), Girder.END: Decimal(0)}
    spans = {Girder.ORIGIN: d(bridge.origin.span), Girder.END: d(bridge.end.span)}
    for x, load in candidate.axles:
        girder = Girder.ORIGIN if bridge.on_origin(x) else Girder.END
        reactions[girder] += d(load) * bridge.lever(girder, x) / spans[girder]
    q = d(candidate.train.tail_load) if candidate.tails else Decimal(0)  # type: ignore[arg-type]
    for girder, a, b in candidate.tails:
        reactions[girder] += q * (b - a) * bridge.lever(girder, (a + b) / 2) / spans[girder]
    rb, rc = reactions[Girder.ORIGIN], reactions[Girder.END]
    return {Objective.PIER: rb + rc, Objective.ORIGIN: rb, Objective.END: rc}[objective]


def search_reactions(origin: Span, end: Span, trains: Sequence[AxleTrain],
                     objective: Objective = Objective.PIER, loaded: Girder | None = None) -> MovingLoadResult:
    """The adopted loading of *trains*; with *loaded*, the train is on that girder only (the other carries nothing)."""
    bridge = _Bridge(origin, end, loaded, objective)
    best: _Candidate | None = None
    best_score = Decimal(0)
    for train in trains:
        anchors = list(train.offsets)
        if train.tail_load is not None:
            anchors.append(train.offsets[-1] + train.tail_gap)
        for sign in (1, -1):
            for anchor in anchors:
                for point in reversed(bridge.points):
                    candidate = _place(bridge, train, point + sign * anchor, sign)
                    score = _score(bridge, candidate, objective)
                    if score > best_score:
                        best, best_score = candidate, score
    if best is None:
        raise InputError(f"移動荷重: 正の反力となる載荷位置がなく、{objective.value}の最大を求められません（車両・寸法を確認）")
    return _result(bridge, best)


def _result(bridge: _Bridge, best: _Candidate) -> MovingLoadResult:
    origin, end = bridge.origin, bridge.end
    common = best.train.loads[0] if len({load.value for load in best.train.loads}) == 1 else None
    axles = tuple(LoadedAxle(girder, put(LENGTH, bridge.lever(girder, x)), None if common is not None else load)
                  for x, load in best.axles
                  for girder in (Girder.ORIGIN if bridge.on_origin(x) else Girder.END,))
    tails = tuple(LoadedTail(girder, best.train.tail_load, put(LENGTH, b - a),  # type: ignore[arg-type]
                             put(LENGTH, bridge.lever(girder, (a + b) / 2)))
                  for girder, a, b in best.tails)

    def reactions(girder: Girder, span: Span) -> tuple[Printed, Printed, Printed]:
        mine = [axle for axle in axles if axle.girder is girder]
        moment = total(d(common or axle.load) * d(axle.lever) for axle in mine)  # type: ignore[arg-type]
        weight = total(d(common or axle.load) for axle in mine)  # type: ignore[arg-type]
        for part in tails:
            if part.girder is girder:
                moment += d(part.load) * d(part.length) * d(part.lever)
                weight += d(part.load) * d(part.length)
        near = put(FORCE, moment / d(span.span))
        return near, put(FORCE, weight - d(near)), AXLES(len(mine))

    rb, ra, origin_count = reactions(Girder.ORIGIN, origin)
    rc, rd, end_count = reactions(Girder.END, end)
    # An axle on a far bearing is one point of the figure: no zero spacing.
    marks = {x for x, _ in best.axles} | {d(origin.l1), bridge.length - d(end.l2)}
    head = best.head if best.head is not None and bridge.on(best.head) else None
    if head is not None:
        marks.add(head)
    ordered = sorted(marks)
    return MovingLoadResult(
        train=best.train.name, axle_load=common, axles=axles, tails=tails, ra=ra, rb=rb, rc=rc, rd=rd,
        origin_axles=origin_count, end_axles=end_count,
        spacings=tuple(put(LENGTH, after - before) for before, after in zip(ordered, ordered[1:])),
        girder_lengths=(girder_length(origin), girder_length(end)),
        tail_head=None if head is None else put(LENGTH, head),
    )

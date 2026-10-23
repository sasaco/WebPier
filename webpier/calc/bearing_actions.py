"""支承作用 → 橋脚天端の等価作用 (CONTEXT.md, decisions 70, 81): the bearing actions of a load model's basic case on a frame.

Each bearing of the case is a row on the seat of its girder (decision 81: the pedestal top when the girder's bearing
line is on the pedestal, the beam top otherwise): its vertical force N with the lever from the axis of that seat (along
the track −f of the origin girder and +f of the end girder from the column axis, across it the entered 支承位置, less
the pedestal offset on the pedestal), and its horizontal force H in the plane of the frame at its height y above the
seat. The row prints N × lever and H × y (2 decimals) and their sum M; each seat is ΣN, ΣH and ΣM of its printed rows
(ADR-0003), which act at the seat. On a frame with the girder levels (0720) the horizontal forces of a girder act at its
level instead, h1 + h2 above its seat, with ΣH × (y − (h1 + h2)); N and N × lever stay at the seat (decision 81).

A seat, or a girder, without any load of the case has no point; a case without any load keeps one zero load at the beam
top, so that it has a row where it acts.

A seismic case of the earthquake direction gives its horizontal forces as magnitudes toward the earthquake: the frame
signs them with *earthquake* (calc.seismic_longitudinal.toward), so the table prints the frame components.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ..core.printed import FORCE, LENGTH, MOMENT, Precision, Printed
from ..inputs import PierInput
from ..loadmodel import BasicCase, BearingRef, BearingSlot, Context, Side
from ._exact import d, put, total
from .frame import Direction, Frame, NodeRole, PointLoad, point_load
from .longitudinal.actions import seat_lever


@dataclass(frozen=True)
class BearingRow:
    bearing: BearingRef
    n: Printed  # vertical, downward positive
    arm: Printed  # lever of N from the axis of the seat: ∓f along the track, the 支承位置 across it (decision 81)
    nm: Printed  # N × arm
    h: Printed  # horizontal in the plane of the frame, +x
    y: Printed  # height of H above the seat
    hm: Printed  # H × y
    m: Printed  # N × arm + H × y


@dataclass(frozen=True)
class SeatTable:
    """The bearings of a case on one seat and their sums there."""

    anchor: NodeRole  # CAP_TOP or PEDESTAL_TOP
    rows: tuple[BearingRow, ...]
    n: Printed  # Σ N
    nm: Printed  # Σ N × arm
    h: Printed  # Σ H
    m: Printed  # Σ M about the seat

    @property
    def loaded(self) -> bool:
        return any(row.n.value or row.h.value for row in self.rows)


@dataclass(frozen=True)
class GirderForce:
    """The horizontal forces of the bearings of one girder where they act: at its seat, or at its level on a frame
    with the girder levels (0720, decision 81)."""

    side: Side
    anchor: NodeRole  # the seat, or GIRDER_ORIGIN / GIRDER_END
    h: Printed  # Σ H
    height: Printed | None  # y above the node it acts at, the same for every bearing of the girder; None if not
    m: Printed  # Σ H × that height of each bearing


@dataclass(frozen=True)
class BearingTable:
    """The 支承作用 of one basic case on one frame: by seat, the horizontal forces by girder, and the point loads."""

    seats: tuple[SeatTable, ...]  # the beam top first; those with a load, or all of them when none has
    girders: tuple[GirderForce, ...]  # the origin and the end girder, those with a horizontal force
    points: tuple[PointLoad, ...]

    @property
    def h(self) -> Printed:
        """Σ H of the girders."""
        return put(FORCE, total(girder.h for girder in self.girders))


def _value(precision: Precision, value: Decimal) -> Printed:
    return precision(float(value))  # the contract's values are at these digits (loadmodel.validate)


def _lever(pier: PierInput, direction: Direction, positions: dict[BearingRef, Printed], ref: BearingRef) -> Printed:
    if direction is Direction.TRANSVERSE:
        return positions[ref]
    f = pier.spans.origin.f if ref.side is Side.ORIGIN else pier.spans.end.f
    return put(LENGTH, -d(f)) if ref.side is Side.ORIGIN else f


def bearing_positions(pier: PierInput) -> dict[BearingRef, Printed]:
    """The 支承位置 of every bearing of the input, by the reference a load model gives."""
    found = {}
    for side, slots in ((Side.ORIGIN, pier.reactions.b), (Side.END, pier.reactions.c)):
        for index, bearing in enumerate(slots):
            if bearing is not None:
                found[BearingRef(side, index + 1)] = bearing.position
    return found


def load_model_context(pier: PierInput, input_path: Path) -> Context:
    """What a load model is told of the input: its path and the bearings that are not empty slots."""
    return Context(input_path, tuple(BearingSlot(ref, Decimal(repr(position.value)))
                                     for ref, position in bearing_positions(pier).items()))


def _sum(precision: Precision, values: list[Printed]) -> Printed:
    return put(precision, total(values))


def _girder(frame: Frame, side: Side, rows: list[BearingRow]) -> GirderForce:
    """The horizontal forces of the girder of *side*: at its level when the frame has it, else at its seat."""
    level = frame.girder(side)
    if level is None:
        anchor, above = frame.seat_role(side), Decimal(0)
    else:
        anchor = NodeRole.GIRDER_ORIGIN if side is Side.ORIGIN else NodeRole.GIRDER_END
        above = d(level.y) - d(frame.node(frame.seat_role(side)).y)
    heights = [put(LENGTH, d(row.y) - above) for row in rows]
    moments = [put(MOMENT, d(row.h) * d(height)) for row, height in zip(rows, heights, strict=True)]
    return GirderForce(side=side, anchor=anchor, h=_sum(FORCE, [row.h for row in rows]),
                       height=heights[0] if len(set(heights)) == 1 else None, m=_sum(MOMENT, moments))


def bearing_table(pier: PierInput, frame: Frame, case: BasicCase, earthquake: Decimal = Decimal(1)) -> BearingTable:
    """*case* on *frame* (its direction decides the lever and the components); *earthquake* signs the horizontal
    forces (±1) of a seismic case of the earthquake direction."""
    positions = bearing_positions(pier)
    longitudinal = frame.direction is Direction.LONGITUDINAL
    rows: dict[Side, list[BearingRow]] = {Side.ORIGIN: [], Side.END: []}
    for action in case.actions:
        side = action.bearing.side
        n = _value(FORCE, action.vertical)
        arm = seat_lever(frame, side, _lever(pier, frame.direction, positions, action.bearing))
        h = _value(FORCE, (action.longitudinal if longitudinal else action.transverse) * earthquake)
        y = _value(LENGTH, action.longitudinal_height if longitudinal else action.transverse_height)
        nm, hm = put(MOMENT, d(n) * d(arm)), put(MOMENT, d(h) * d(y))
        rows[side].append(BearingRow(action.bearing, n, arm, nm, h, y, hm, put(MOMENT, d(nm) + d(hm))))
    seats = []
    for anchor in (NodeRole.CAP_TOP, NodeRole.PEDESTAL_TOP):
        on = [row for side in Side if frame.seat_role(side) is anchor for row in rows[side]]
        if on:
            seats.append(SeatTable(anchor, tuple(on), _sum(FORCE, [r.n for r in on]), _sum(MOMENT, [r.nm for r in on]),
                                   _sum(FORCE, [r.h for r in on]), _sum(MOMENT, [r.m for r in on])))
    loaded = [seat for seat in seats if seat.loaded] or seats
    girders = [_girder(frame, side, rows[side]) for side in Side if rows[side]]
    if frame.girder(Side.ORIGIN) is None:  # the horizontal forces at the seats
        points = [point_load(frame, s.anchor, n=s.n, h=s.h, m=s.m) for s in loaded if s.loaded]
    else:  # N at the seats, H at the girder levels (0720)
        points = [point_load(frame, s.anchor, n=s.n, m=s.nm) for s in loaded if s.n.value or s.nm.value]
        points += [point_load(frame, g.anchor, h=g.h, m=g.m) for g in girders if g.h.value or g.m.value]
    return BearingTable(tuple(loaded), tuple(g for g in girders if g.h.value),
                        tuple(points) or (point_load(frame, NodeRole.CAP_TOP),))


__all__ = ["BearingRow", "BearingTable", "GirderForce", "SeatTable", "bearing_positions", "bearing_table",
           "load_model_context"]

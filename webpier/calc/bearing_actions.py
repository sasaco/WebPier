"""支承作用 → 橋脚天端の等価作用 (CONTEXT.md, decision 70): the bearing actions of a load model's basic case on a frame.

Each bearing of the case is a row: its vertical force N with the lever of the bearing (along the track −f of the
origin girder and +f of the end girder, across it the entered 支承位置), and its horizontal force H in the plane of
the frame at its height y above the bearing seat. The row prints N × lever and H × y (2 decimals) and their sum M;
the case is ΣN, ΣH and ΣM of the printed rows (ADR-0003), which act at the bearing seat (decision 29) as
``bearing_point`` puts them: M′ = M − N × offset when the seat is not on the column axis.

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
from .frame import Direction, Frame, PointLoad
from .longitudinal.actions import bearing_point


@dataclass(frozen=True)
class BearingRow:
    bearing: BearingRef
    n: Printed  # vertical, downward positive
    arm: Printed  # lever of N from the column axis: ∓f along the track, the 支承位置 across it
    nm: Printed  # N × arm
    h: Printed  # horizontal in the plane of the frame, +x
    y: Printed  # height of H above the bearing seat
    hm: Printed  # H × y
    m: Printed  # N × arm + H × y


@dataclass(frozen=True)
class BearingTable:
    """The 支承作用 of one basic case on one frame and their sum at the bearing seat."""

    rows: tuple[BearingRow, ...]
    n: Printed  # Σ N
    h: Printed  # Σ H
    m: Printed  # Σ M about the column axis
    point: PointLoad  # at the bearing seat: M′ = M − N × offset

    @property
    def vertical(self) -> bool:
        return any(row.n.value for row in self.rows)


def _value(precision: Precision, value: Decimal) -> Printed:
    return precision(float(value))  # the contract's values are at these digits (loadmodel.validate)


def _arm(pier: PierInput, direction: Direction, positions: dict[BearingRef, Printed], ref: BearingRef) -> Printed:
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


def bearing_table(pier: PierInput, frame: Frame, case: BasicCase, earthquake: Decimal = Decimal(1)) -> BearingTable:
    """*case* on *frame* (its direction decides the lever and the components); *earthquake* signs the horizontal
    forces (±1) of a seismic case of the earthquake direction."""
    positions = bearing_positions(pier)
    longitudinal = frame.direction is Direction.LONGITUDINAL
    rows = []
    for action in case.actions:
        n = _value(FORCE, action.vertical)
        arm = _arm(pier, frame.direction, positions, action.bearing)
        h = _value(FORCE, (action.longitudinal if longitudinal else action.transverse) * earthquake)
        y = _value(LENGTH, action.longitudinal_height if longitudinal else action.transverse_height)
        nm, hm = put(MOMENT, d(n) * d(arm)), put(MOMENT, d(h) * d(y))
        rows.append(BearingRow(action.bearing, n, arm, nm, h, y, hm, put(MOMENT, d(nm) + d(hm))))
    n, h, m = (put(precision, total(getattr(row, field) for row in rows))
               for precision, field in ((FORCE, "n"), (FORCE, "h"), (MOMENT, "m")))
    return BearingTable(tuple(rows), n, h, m, bearing_point(frame, n, m, h))


__all__ = ["BearingRow", "BearingTable", "bearing_positions", "bearing_table", "load_model_context"]

"""Wind on the pier body across the track (decision 12; Example2 9-7, 9-8, 9-12).

The wind blows across the track, so each member is exposed over its width
along the track: the beam B1, the haunch a trapezoid from B1 at its top to its
lower face B1 − B4 − B5, and the column B6. Only the part above the ground
surface is loaded; the ground is the lower soil surface, footing top +
min(df1, df2), and a member that the ground crosses is loaded from its top
down to the ground. The footing and the pedestal are not loaded (decision 12
names the beam, the haunch and the column).

Every height, width and line load is printed (3, 3 and 2 decimals): the line
load is pressure × width, and a haunch cut by the ground has its width at the
ground interpolated linearly in one expression.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...core.printed import LENGTH, LINE_LOAD, Printed
from ...inputs import PierInput
from .._exact import d, put
from ..frame import Frame, NodeRole, Region


@dataclass(frozen=True)
class MemberLoad:
    """A load per metre on part of one member, varying linearly from *start* to *end*.

    *start* and *end* are distances along the member from its start node (the
    upper node on the column line); h is horizontal, positive in +x.
    """

    member: int
    start: Printed
    end: Printed
    h_start: Printed
    h_end: Printed


@dataclass(frozen=True)
class WindSegment:
    """The loaded part of one member (9-12)."""

    region: Region  # BEAM, HAUNCH or COLUMN
    member: int
    top: Printed  # height of the loaded top above the footing base (the member top)
    bottom: Printed  # height of the loaded bottom: the member bottom or the ground
    length: Printed  # top − bottom
    width_top: Printed  # exposed width at the top
    width_bottom: Printed  # exposed width at the bottom
    load_top: Printed  # pressure × width_top
    load_bottom: Printed  # pressure × width_bottom


@dataclass(frozen=True)
class PierWind:
    pressure: Printed  # ω1 (07 7-15 / 7-17: 1.5 with the train, 3.0 without)
    ground: Printed  # ground surface above the footing base: footing top + min(df1, df2)
    exposure: Printed  # beam top − ground, 0 when the ground is at or above the beam top (受風高さ)
    segments: tuple[WindSegment, ...]  # from the beam top down

    def member_loads(self) -> tuple[MemberLoad, ...]:
        return tuple(MemberLoad(member=s.member, start=LENGTH(0), end=s.length, h_start=s.load_top,
                                h_end=s.load_bottom) for s in self.segments)


def _widths(pier: PierInput) -> dict[Region, tuple[Decimal, Decimal]]:
    """Exposed width at the top and the bottom of each wind-loaded region."""
    b = {i: d(v) for i, v in pier.substructure.b.items()}
    return {Region.BEAM: (b[1], b[1]), Region.HAUNCH: (b[1], b[1] - b[4] - b[5]), Region.COLUMN: (b[6], b[6])}


def pier_wind(pier: PierInput, frame: Frame, pressure: Printed) -> PierWind:
    s = pier.substructure
    footing_top = d(frame.node(NodeRole.FOOTING_TOP).y)
    ground = put(LENGTH, footing_top + min(d(s.df1), d(s.df2)))
    top = d(frame.node(NodeRole.CAP_TOP).y)
    exposure = put(LENGTH, max(top - d(ground), Decimal(0)))
    widths = _widths(pier)
    nodes = {node.number: node for node in frame.nodes}
    p = d(pressure)
    segments = []
    for member in frame.column_line:
        upper, lower = d(nodes[member.start].y), d(nodes[member.end].y)
        if upper <= d(ground):
            continue
        width_top, width_bottom = widths[member.region]
        bottom = max(lower, d(ground))
        if bottom > lower:  # the ground cuts the member: the width there, linear in height
            width_bottom = width_bottom + (width_top - width_bottom) * (bottom - lower) / (upper - lower)
        w_top, w_bottom = put(LENGTH, width_top), put(LENGTH, width_bottom)
        segments.append(WindSegment(
            region=member.region, member=member.number, top=nodes[member.start].y, bottom=put(LENGTH, bottom),
            length=put(LENGTH, upper - bottom), width_top=w_top, width_bottom=w_bottom,
            load_top=put(LINE_LOAD, p * d(w_top)), load_bottom=put(LINE_LOAD, p * d(w_bottom))))
    return PierWind(pressure=pressure, ground=ground, exposure=exposure, segments=tuple(segments))


__all__ = ["MemberLoad", "PierWind", "WindSegment", "pier_wind"]

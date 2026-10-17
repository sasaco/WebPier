"""Wind on the pier body across the track (decision 12; Example2 9-7, 9-8, 9-12).

The wind blows across the track, so each member is exposed over its width
along the track: the beam B1, the haunch a trapezoid from B1 at its top to its
lower face B1 − B4 − B5, the column B6 and a pedestal (H1 > 0) B3 (decision
35). Only the part above the ground surface is loaded; the ground is the lower
soil surface, footing top + min(df1, df2), and a member that the ground crosses
is loaded from its top down to the ground. The footing is not loaded.

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
    upper node on the column line, the base of the pedestal); h is horizontal,
    positive in +x.
    """

    member: int
    start: Printed
    end: Printed
    h_start: Printed
    h_end: Printed


@dataclass(frozen=True)
class WindSegment:
    """The loaded part of one member (9-12)."""

    region: Region  # PEDESTAL, BEAM, HAUNCH or COLUMN
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
    exposure: Printed  # pier top − ground, 0 when the ground is at or above the pier top (受風高さ)
    segments: tuple[WindSegment, ...]  # from the top down
    member_loads: tuple[MemberLoad, ...]  # the segments on their members


def _widths(pier: PierInput) -> dict[Region, tuple[Decimal, Decimal]]:
    """Exposed width at the top and the bottom of each wind-loaded region."""
    b = {i: d(v) for i, v in pier.substructure.b.items()}
    return {Region.PEDESTAL: (b[3], b[3]), Region.BEAM: (b[1], b[1]), Region.HAUNCH: (b[1], b[1] - b[4] - b[5]),
            Region.COLUMN: (b[6], b[6])}


def pier_wind(pier: PierInput, frame: Frame, pressure: Printed) -> PierWind:
    s = pier.substructure
    footing_top = d(frame.node(NodeRole.FOOTING_TOP).y)
    ground = put(LENGTH, footing_top + min(d(s.df1), d(s.df2)))
    exposure = put(LENGTH, max(d(frame.bearing_seat.y) - d(ground), Decimal(0)))  # the pedestal top or beam top
    widths = _widths(pier)
    nodes = {node.number: node for node in frame.nodes}
    p = d(pressure)
    segments, loads = [], []
    members = sorted((m for m in frame.members if m.region in widths), key=lambda m: -max(
        d(nodes[m.start].y), d(nodes[m.end].y)))
    for member in members:
        start, end = nodes[member.start], nodes[member.end]
        upper, lower = (start, end) if d(start.y) > d(end.y) else (end, start)
        top, base = d(upper.y), d(lower.y)
        if top <= d(ground):
            continue
        width_top, width_bottom = widths[member.region]
        bottom = max(base, d(ground))
        if bottom > base:  # the ground cuts the member: the width there, linear in height
            width_bottom = width_bottom + (width_top - width_bottom) * (bottom - base) / (top - base)
        w_top, w_bottom = put(LENGTH, width_top), put(LENGTH, width_bottom)
        segment = WindSegment(
            region=member.region, member=member.number, top=upper.y, bottom=put(LENGTH, bottom),
            length=put(LENGTH, top - bottom), width_top=w_top, width_bottom=w_bottom,
            load_top=put(LINE_LOAD, p * d(w_top)), load_bottom=put(LINE_LOAD, p * d(w_bottom)))
        segments.append(segment)
        if upper is start:  # the column line runs down: the load starts at the member top
            loads.append(MemberLoad(member.number, LENGTH(0), segment.length, segment.load_top, segment.load_bottom))
        else:  # the pedestal runs up from its base: the load starts at the ground or the base
            loads.append(MemberLoad(member.number, put(LENGTH, bottom - base), member.height, segment.load_bottom,
                                    segment.load_top))
    return PierWind(pressure=pressure, ground=ground, exposure=exposure, segments=tuple(segments),
                    member_loads=tuple(loads))


__all__ = ["MemberLoad", "PierWind", "WindSegment", "pier_wind"]

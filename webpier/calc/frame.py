"""The plane frame of the pier, shared by 0610, 0620, 0710 and 0720.

One line of members follows the pier from the beam top down to the footing
base (Example2 08 p.8-1, 09 p.9-1, 10 p.10-1): beam (H2), haunch (H3), column
(H4) and the footing as two rigid members through its centroid. The springs of
0500 sit at the footing base. The direction only decides which plan sizes are
in the plane: B along the track (longitudinal), W across it (transverse).

Coordinates: x in the plane from the footing centre (positive toward the end
side, or toward W9 across the track), y up from the footing base. The column
axis is at the column centroid of 0600 ((B7 − B9)/2), so with an asymmetric
footing the rigid member from the footing top to the footing centroid is
inclined and the springs stay at the centre of the base they belong to.

Example2 gives the beam, haunch and column the column section (8-2 / 9-2
print only the column) and makes the footing rigid. A pedestal (H1 > 0) is a
B3 × W3 stub on the beam top at its own centre, joined by a rigid arm; the
bearing loads act at its top (decision 29), so the frame carries H × H1.

0710 cuts a 0.010 m micro member from the bottom of the column (CONTEXT.md
柱下端の微小部材) and makes the rest rigid; ``column_base_micro_member`` and
``elastic_regions`` express that. 0720 adds the girder level of each side,
h1 + h2 above the bearing seat (Example2 11-1 node 1, 2.750), joined to the
seat by rigid members and numbered first (``girder_levels``). No drawing data
is kept here.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum

from ..core.errors import InputError
from ..core.printed import AREA, FORCE, INERTIA, LENGTH, LINE_LOAD, MOMENT, Printed
from ..inputs import PierInput
from ._exact import d, put
from .foundation import FoundationResult, SpringSet
from .materials import Concrete, MaterialsResult
from .reaction.self_weight import SelfWeightResult

MICRO_MEMBER = LENGTH.exact(0.010)  # column-base micro member of 0710 (Example2 10-1: 4.890 + 0.010)


class Direction(Enum):
    LONGITUDINAL = "longitudinal"  # in the plane of the track: B sizes, Kr_longitudinal
    TRANSVERSE = "transverse"  # across the track: W sizes, Kr_transverse


class NodeRole(Enum):
    CAP_TOP = "cap_top"  # beam top: the bearing loads act here (load anchor)
    BEAM_BOTTOM = "beam_bottom"  # H2 / H3
    COLUMN_TOP = "column_top"  # H3 / H4
    MICRO_TOP = "micro_top"  # top of the column-base micro member (0710)
    FOOTING_TOP = "footing_top"
    FOOTING_CENTROID = "footing_centroid"  # footing loads act here (load anchor)
    FOOTING_BOTTOM = "footing_bottom"  # the spring support
    PEDESTAL_BASE = "pedestal_base"
    PEDESTAL_TOP = "pedestal_top"
    GIRDER_ORIGIN = "girder_origin"  # h1 + h2 of the origin girder above the bearing seat (0720)
    GIRDER_END = "girder_end"  # h1 + h2 of the end girder above the bearing seat (0720)


class Region(Enum):
    BEAM = "beam"  # H2
    HAUNCH = "haunch"  # H3
    COLUMN = "column"  # H4 (less the micro member)
    COLUMN_BASE = "column_base"  # the 0.010 m micro member
    FOOTING_UPPER = "footing_upper"  # footing top to centroid
    FOOTING_LOWER = "footing_lower"  # centroid to base
    PEDESTAL_ARM = "pedestal_arm"  # beam top to the pedestal centre, horizontal
    PEDESTAL = "pedestal"  # H1
    GIRDER = "girder"  # bearing seat up to a girder level, rigid (0720)


BODY_REGIONS = frozenset({Region.BEAM, Region.HAUNCH, Region.COLUMN, Region.COLUMN_BASE, Region.PEDESTAL})
COLUMN_LINE = (Region.BEAM, Region.HAUNCH, Region.COLUMN, Region.COLUMN_BASE)  # beam top to footing top
_BEAM_CONCRETE = frozenset({Region.BEAM, Region.HAUNCH, Region.PEDESTAL})  # the pedestal is cast on the beam


@dataclass(frozen=True)
class Node:
    number: int
    x: Printed
    y: Printed
    roles: frozenset[NodeRole]


@dataclass(frozen=True)
class Section:
    width: Printed  # b, normal to the plane
    depth: Printed  # h, in the plane
    area: Printed  # A = b × h
    inertia: Printed  # I = 1/12 × b × h^3


@dataclass(frozen=True)
class Member:
    number: int
    start: int  # node number
    end: int
    region: Region
    height: Printed  # vertical extent |y_end − y_start|
    offset: Printed  # x_end − x_start
    section: Section | None  # None for a rigid member
    material: Concrete | None

    @property
    def rigid(self) -> bool:
        return self.section is None


@dataclass(frozen=True)
class Springs:
    kv: Printed
    ks: Printed
    kr: Printed  # about the axis normal to the plane


@dataclass(frozen=True)
class Support:
    node: int
    long_term: Springs
    short_term: Springs


@dataclass(frozen=True)
class Frame:
    direction: Direction
    nodes: tuple[Node, ...]
    members: tuple[Member, ...]
    column_section: Section
    pedestal_section: Section | None  # None without a pedestal (H1 = 0)
    materials: MaterialsResult
    support: Support
    pier_height: Printed  # H2 + H3 + H4: the beam top above the footing top (Example2 8-1 7.600)

    def node(self, role: NodeRole) -> Node:
        for node in self.nodes:
            if role in node.roles:
                return node
        raise KeyError(role)

    @property
    def bearing_seat(self) -> Node:
        """Where the bearing loads act (decision 29): the pedestal top, or the beam top without a pedestal."""
        return self.node(NodeRole.PEDESTAL_TOP if self.pedestal_section is not None else NodeRole.CAP_TOP)

    @property
    def bearing_offset(self) -> Printed:
        """x of the bearing seat from the beam-top node: shifts a lever from the column axis to the seat."""
        return put(LENGTH, d(self.bearing_seat.x) - d(self.node(NodeRole.CAP_TOP).x))

    @property
    def column_line(self) -> tuple[Member, ...]:
        """Members from the beam top to the footing top: the column line load acts on them."""
        return tuple(member for member in self.members if member.region in COLUMN_LINE)


@dataclass(frozen=True)
class PointLoad:
    """A load at a node: N downward, H in +x, M positive as N × (+x lever)."""

    anchor: NodeRole
    node: int
    n: Printed
    h: Printed
    m: Printed


@dataclass(frozen=True)
class LineLoad:
    """A uniform load along members, per metre: n downward, h in +x."""

    members: tuple[int, ...]
    n: Printed
    h: Printed


def point_load(frame: Frame, anchor: NodeRole, *, n: Printed = FORCE(0), h: Printed = FORCE(0),
               m: Printed = MOMENT(0)) -> PointLoad:
    return PointLoad(anchor=anchor, node=frame.node(anchor).number, n=n, h=h, m=m)


def column_line_load(frame: Frame, *, n: Printed = LINE_LOAD(0), h: Printed = LINE_LOAD(0)) -> LineLoad:
    return LineLoad(members=tuple(member.number for member in frame.column_line), n=n, h=h)


def _section(width: Printed, depth: Printed, path: str) -> Section:
    area = put(AREA, d(width) * d(depth))
    inertia = put(INERTIA, d(width) * d(depth) ** 3 / 12)
    if area.value <= 0 or inertia.value <= 0:
        raise InputError(f"{path}: 断面積または断面二次モーメントが印字桁に丸めると0になります")
    return Section(width=width, depth=depth, area=area, inertia=inertia)


def _springs(springs: SpringSet, direction: Direction) -> Springs:
    kr = springs.Kr_longitudinal if direction is Direction.LONGITUDINAL else springs.Kr_transverse
    return Springs(kv=springs.Kv, ks=springs.Ks, kr=kr)


def _girder_levels(pier: PierInput, nodes: list[Node], links: list[tuple[int, int, Region]]
                   ) -> tuple[list[Node], list[tuple[int, int, Region]]]:
    """The girder levels above the bearing seat, numbered first from the top (Example2 11-1, 11-2).

    Sides at the same height share a node; a level at the seat (h1 + h2 = 0) is the seat itself.
    """
    seat = next((node for node in nodes if NodeRole.PEDESTAL_TOP in node.roles), nodes[0])
    levels: dict[Printed, set[NodeRole]] = {}
    for role, span in ((NodeRole.GIRDER_ORIGIN, pier.spans.origin), (NodeRole.GIRDER_END, pier.spans.end)):
        levels.setdefault(LENGTH.total((seat.y, span.heights[1], span.heights[2])), set()).add(role)
    above = sorted((y for y in levels if y != seat.y), key=lambda y: y.value, reverse=True)
    shift = len(above)
    added = [Node(number, seat.x, y, frozenset(levels[y])) for number, y in enumerate(above, 1)]
    moved = [Node(node.number + shift, node.x, node.y, node.roles | frozenset(levels.get(node.y, ()))
                  if node is seat else node.roles) for node in nodes]
    chain = [(number, number + 1, Region.GIRDER) for number in range(1, shift)]
    if shift:
        chain.append((shift, seat.number + shift, Region.GIRDER))
    return added + moved, chain + [(start + shift, end + shift, region) for start, end, region in links]


def build_frame(pier: PierInput, self_weight: SelfWeightResult, foundation: FoundationResult,
                materials: MaterialsResult, direction: Direction, *, column_base_micro_member: bool = False,
                elastic_regions: Collection[Region] = BODY_REGIONS, girder_levels: bool = False) -> Frame:
    unknown = set(elastic_regions) - BODY_REGIONS
    if unknown:
        raise ValueError(f"elastic regions need a section: {sorted(region.name for region in unknown)}")
    s = pier.substructure
    h = s.h
    longitudinal = direction is Direction.LONGITUDINAL
    plane, normal, dims = (s.b, s.w, "B") if longitudinal else (s.w, s.b, "W")
    other = "W" if longitudinal else "B"
    column_section = _section(normal[6], plane[6], f"下部構造.寸法 B6/W6（{dims}6 が面内）")
    axis = self_weight.column.x_l if longitudinal else self_weight.column.x_c

    zf = LENGTH.total((h[5], h[6]))
    zc = LENGTH.total((zf, h[4]))
    zb = LENGTH.total((zc, h[3]))
    zt = LENGTH.total((zb, h[2]))
    pier_height = LENGTH.total((h[2], h[3], h[4]))
    line: list[tuple[NodeRole, Printed, Printed, Region | None]] = [
        (NodeRole.CAP_TOP, axis, zt, None), (NodeRole.BEAM_BOTTOM, axis, zb, Region.BEAM),
        (NodeRole.COLUMN_TOP, axis, zc, Region.HAUNCH)]
    if column_base_micro_member:
        if h[4].value <= MICRO_MEMBER.value:
            raise InputError(f"下部構造.寸法.高さ.H4: 柱下端の微小部材 {MICRO_MEMBER.value:.3f} m より長い必要があります"
                             f"（入力 {h[4].value} m）")
        line.append((NodeRole.MICRO_TOP, axis, LENGTH.total((zf, MICRO_MEMBER)), Region.COLUMN))
        line.append((NodeRole.FOOTING_TOP, axis, zf, Region.COLUMN_BASE))
    else:
        line.append((NodeRole.FOOTING_TOP, axis, zf, Region.COLUMN))
    zero = LENGTH(0)
    line += [(NodeRole.FOOTING_CENTROID, zero, self_weight.footing.y, Region.FOOTING_UPPER),
             (NodeRole.FOOTING_BOTTOM, zero, zero, Region.FOOTING_LOWER)]

    pedestal_section = None
    if h[1].value > 0:
        for key, size in ((f"{dims}3", plane[3]), (f"{other}3", normal[3])):
            if size.value <= 0:
                raise InputError(f"下部構造.寸法.{key}: H1 > 0（桁受けあり）では正の値が必要です")
        pedestal_section = _section(normal[3], plane[3], "下部構造.寸法 B3/W3")
        offset = self_weight.pedestal.x_l if longitudinal else self_weight.pedestal.x_c
        x_p = LENGTH.total((axis, offset))
        line += [(NodeRole.PEDESTAL_BASE, x_p, zt, Region.PEDESTAL_ARM),
                 (NodeRole.PEDESTAL_TOP, x_p, LENGTH.total((zt, h[1])), Region.PEDESTAL)]

    # Points closer than the printed digits do not exist: a zero height merges two points into one node.
    nodes: list[Node] = []
    links: list[tuple[int, int, Region]] = []
    previous = 0
    for role, x, y, region in line:
        start = 1 if region is Region.PEDESTAL_ARM else previous  # the arm starts at the beam top
        if start and (nodes[start - 1].x, nodes[start - 1].y) == (x, y):
            nodes[start - 1] = Node(start, x, y, nodes[start - 1].roles | {role})
            previous = start
            continue
        nodes.append(Node(len(nodes) + 1, x, y, frozenset({role})))
        previous = len(nodes)
        if start:
            links.append((start, previous, region))  # type: ignore[arg-type]  # only the beam top has no region
    if girder_levels:
        nodes, links = _girder_levels(pier, nodes, links)

    by_number = {node.number: node for node in nodes}
    members = []
    for number, (start, end, region) in enumerate(links, 1):
        a, b = by_number[start], by_number[end]
        elastic = region in elastic_regions
        section = (pedestal_section if region is Region.PEDESTAL else column_section) if elastic else None
        material = (materials.beam if region in _BEAM_CONCRETE else materials.column) if elastic else None
        members.append(Member(number=number, start=start, end=end, region=region,
                              height=put(LENGTH, abs(d(a.y) - d(b.y))), offset=put(LENGTH, d(b.x) - d(a.x)),
                              section=section, material=material))
    support = Support(node=next(n.number for n in nodes if NodeRole.FOOTING_BOTTOM in n.roles),
                      long_term=_springs(foundation.long_term, direction),
                      short_term=_springs(foundation.short_term, direction))
    return Frame(direction=direction, nodes=tuple(nodes), members=tuple(members), column_section=column_section,
                 pedestal_section=pedestal_section, materials=materials, support=support, pier_height=pier_height)

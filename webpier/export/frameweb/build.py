"""The FrameWeb input document (FEMPython / FrameWebforCS, 2D) of a frame and its case tables.

The format is that of the FrameWeb file of Example2 (.claude/docs/Example橋脚2/08_線路/frameWebForJS.json),
without the GUI view state ``three``:

- ``node``: x, y in m; ``member``: end nodes and the section number; ``element``: one section type "1" with
  E (kN/m2), A, Iz per section. Example2 gives the rigid footing a finite stiffness (E = 26,500,000,
  A = Iz = 1000) and Xp = 1e-5 to every section; we keep both conventions.
- ``fix_node``: 1 long-term, 2 short-term springs at the support: tx = Ks, ty = Kv, rz = Kr.
- ``load``: tx = H, ty = −N (N downward), rz = −M (M positive as N × +x lever: Example2 D1 M = −610.00 is
  rz = 610); a zero component is null and a point load without components has no row. Member loads are one row
  per member in global axes: a line load uniform over the whole member (gy = −n, gx = h), then a load on part of
  a member varying linearly (gx = h: the 0620 wind on the pier body) from L1 = its start after the member start
  to L2 = the margin before the member end, P1 at its start and P2 at its end. A load without intensity has no
  row, and a load case without loads has no rows at all (FrameWeb skips it, as Example2 case 5).
- ``define`` / ``combine`` / ``pickup`` as in ``cases``.

A whole number is written as an integer (Example2 writes 0, 26500000, 1); nothing is rounded. The margin L2 is
the member length less the end of the load, exact in decimals on a vertical or horizontal member; on an inclined
member the length is not a printed number, so a partial load there is refused.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ...calc.frame import Frame, Member, Region, Springs
from ...calc.transverse.wind import MemberLoad
from .cases import Cases, LoadCase
from .profile import LONG_TERM, SHORT_TERM

SECTION_TYPE = 1  # the one element type; every load case uses it
RIGID = {"E": 26_500_000, "A": 1000, "Iz": 1000}  # Example2 element 2 "剛域": a finite stiffness, not a tie
XP = 1e-5  # Example2: Xp of every section
LL_PITCH = 0.1  # Example2: moving-load pitch, unused by a static case
RATE = 1  # Example2: the load-case multiplier
RIGID_NAME = "剛域"
REGION_NAMES = {Region.BEAM: "はり", Region.HAUNCH: "ハンチ", Region.COLUMN: "柱", Region.COLUMN_BASE: "柱下端",
                Region.PEDESTAL: "桁受け"}


def _number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _component(value: float) -> int | float | None:
    return _number(value) if value else None


def _elements(frame: Frame) -> tuple[dict[str, Any], list[int]]:
    """One section per (section, concrete) in member order; all rigid members share the rigid one."""
    numbers: dict[object, int] = {}
    regions: dict[object, dict[Region, None]] = {}
    members = []
    for member in frame.members:
        key = None if member.rigid else (member.section, member.material)
        members.append(numbers.setdefault(key, len(numbers) + 1))
        regions.setdefault(key, {})[member.region] = None
    sections = {}
    for key, number in numbers.items():
        if key is None:
            e, a, iz, name = RIGID["E"], RIGID["A"], RIGID["Iz"], RIGID_NAME
        else:
            section, material = key  # type: ignore[misc]
            e, a, iz = _number(material.ec), _number(section.area.value), _number(section.inertia.value)
            name = "・".join(REGION_NAMES[region] for region in regions[key])
        sections[str(number)] = {"E": e, "G": None, "Xp": XP, "A": a, "J": None, "Iy": None, "Iz": iz, "n": name}
    return {str(SECTION_TYPE): sections}, members


def _support(node: int, springs: Springs) -> list[dict[str, Any]]:
    return [{"row": 1, "n": str(node), "tx": _number(springs.ks.value), "ty": _number(springs.kv.value),
             "tz": None, "rx": None, "ry": None, "rz": _number(springs.kr.value)}]


def _margin(member: Member, load: MemberLoad) -> int | float:
    """L2: the length of the member after the end of the load."""
    if member.height.value and member.offset.value:
        raise ValueError(f"member {member.number}: a partial load on an inclined member cannot be written exactly")
    length = Decimal(repr(member.height.value or abs(member.offset.value)))
    return _number(float(length - Decimal(repr(load.end.value))))


def _member_row(member: str, direction: str, start: int | float, margin: int | float, p1: float, p2: float,
                row: int) -> dict[str, Any]:
    return {"m1": member, "m2": member, "direction": direction, "mark": 2, "L1": start, "L2": margin,
            "P1": _number(p1), "P2": _number(p2), "row": row}


def _load(case: LoadCase, members: dict[int, Member]) -> dict[str, Any]:
    result: dict[str, Any] = {"fix_node": case.spring, "element": SECTION_TYPE, "symbol": case.symbol,
                              "LL_pitch": LL_PITCH, "rate": RATE, "name": case.name}
    nodes = []
    for point in case.points:
        tx, ty, rz = point.h.value, -point.n.value, -point.m.value
        if tx or ty or rz:
            nodes.append({"n": str(point.node), "tx": _component(tx), "ty": _component(ty), "tz": None, "rx": None,
                          "ry": None, "rz": _component(rz), "row": len(nodes) + 1})
    rows: list[dict[str, Any]] = []
    for line in case.line_loads:
        for direction, intensity in (("gx", line.h.value), ("gy", -line.n.value)):
            if intensity:
                for member in line.members:
                    rows.append(_member_row(str(member), direction, 0, 0, intensity, intensity, len(rows) + 1))
    for load in case.member_loads:
        if load.h_start.value or load.h_end.value:
            rows.append(_member_row(str(load.member), "gx", _number(load.start.value),
                                    _margin(members[load.member], load), load.h_start.value, load.h_end.value,
                                    len(rows) + 1))
    if nodes:
        result["load_node"] = nodes
    if rows:
        result["load_member"] = rows
    return result


def frameweb_document(frame: Frame, cases: Cases) -> dict[str, Any]:
    elements, member_sections = _elements(frame)
    members = {member.number: member for member in frame.members}
    support = frame.support
    return {
        "node": {str(node.number): {"x": _number(node.x.value), "y": _number(node.y.value), "z": None}
                 for node in frame.nodes},
        "fix_node": {str(LONG_TERM): _support(support.node, support.long_term),
                     str(SHORT_TERM): _support(support.node, support.short_term)},
        "member": {str(member.number): {"ni": member.start, "nj": member.end, "e": section, "cg": None}
                   for member, section in zip(frame.members, member_sections, strict=True)},
        "element": elements,
        "load": {str(number): _load(case, members) for number, case in enumerate(cases.loads, 1)},
        "define": {str(number): {"row": number, **{f"C{i}": load for i, load in enumerate(loads, 1)}}
                   for number, loads in enumerate(cases.defines, 1)},
        "combine": {str(number): {"row": number, "name": combine.name,
                                  **{f"C{define}": _number(factor.value) for define, factor in combine.terms}}
                    for number, combine in enumerate(cases.combines, 1)},
        "pickup": {str(number): {"row": number, "name": pickup.name,
                                 **{f"C{i}": combine for i, combine in enumerate(pickup.combines, 1)}}
                   for number, pickup in enumerate(cases.pickups, 1)},
        "dimension": 2,
    }

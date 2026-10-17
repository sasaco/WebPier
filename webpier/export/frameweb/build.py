"""The FrameWeb input document (FEMPython / FrameWebforCS, 2D) of a frame and its case tables.

The format is that of the FrameWeb file of Example2 (.claude/docs/Example橋脚2/08_線路/frameWebForJS.json),
without the GUI view state ``three``:

- ``node``: x, y in m; ``member``: end nodes and the section number; ``element``: one section type "1" with
  E (kN/m2), A, Iz per section. Example2 gives the rigid footing a finite stiffness (E = 26,500,000,
  A = Iz = 1000) and Xp = 1e-5 to every section; we keep both conventions.
- ``fix_node``: 1 long-term, 2 short-term springs at the support: tx = Ks, ty = Kv, rz = Kr.
- ``load``: tx = H, ty = −N (N downward), rz = −M (M positive as N × +x lever: Example2 D1 M = −610.00 is
  rz = 610); a zero component is null and a point load without components has no row. Line loads are one row
  per member in global axes, uniform over the whole member: gy = −n, gx = h. A load case without loads has no
  rows at all (FrameWeb skips it, as Example2 case 5).
- ``define`` / ``combine`` / ``pickup`` as in ``cases``.

A whole number is written as an integer (Example2 writes 0, 26500000, 1); nothing is rounded.
"""

from __future__ import annotations

from typing import Any

from ...calc.frame import Frame, Region, Springs
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


def _load(case: LoadCase) -> dict[str, Any]:
    result: dict[str, Any] = {"fix_node": case.spring, "element": SECTION_TYPE, "symbol": case.symbol,
                              "LL_pitch": LL_PITCH, "rate": RATE, "name": case.name}
    nodes = []
    for point in case.points:
        tx, ty, rz = point.h.value, -point.n.value, -point.m.value
        if tx or ty or rz:
            nodes.append({"n": str(point.node), "tx": _component(tx), "ty": _component(ty), "tz": None, "rx": None,
                          "ry": None, "rz": _component(rz), "row": len(nodes) + 1})
    members = []
    for line in case.line_loads:
        for direction, intensity in (("gx", line.h.value), ("gy", -line.n.value)):
            if intensity:
                for member in line.members:
                    members.append({"m1": str(member), "m2": str(member), "direction": direction, "mark": 2,
                                    "L1": 0, "L2": 0, "P1": _number(intensity), "P2": _number(intensity),
                                    "row": len(members) + 1})
    if nodes:
        result["load_node"] = nodes
    if members:
        result["load_member"] = members
    return result


def frameweb_document(frame: Frame, cases: Cases) -> dict[str, Any]:
    elements, member_sections = _elements(frame)
    support = frame.support
    return {
        "node": {str(node.number): {"x": _number(node.x.value), "y": _number(node.y.value), "z": None}
                 for node in frame.nodes},
        "fix_node": {str(LONG_TERM): _support(support.node, support.long_term),
                     str(SHORT_TERM): _support(support.node, support.short_term)},
        "member": {str(member.number): {"ni": member.start, "nj": member.end, "e": section, "cg": None}
                   for member, section in zip(frame.members, member_sections, strict=True)},
        "element": elements,
        "load": {str(number): _load(case) for number, case in enumerate(cases.loads, 1)},
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

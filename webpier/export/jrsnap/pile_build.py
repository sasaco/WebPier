"""The members, elements and supports of a pile row in the NDU model (decision 93).

A pile row of ``calc.pile_seismic`` becomes, as JRSNAP's 連携 of a .sdc makes it (``pile-ndu-fields.md``), one member from
its head joint down to its tip: a rigid element from the head to the top of the ground layers (where the footing ends),
then an element for each element of the row with its ground springs and the M-φ of the section that is at its depth, and
a support row for each node with a spring. The section of an element is the one of the part of the pile its upper end is
in (decision 93); the head element and those of the 2D zone are titled so.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from ...calc._exact import d, put
from ...calc.pile_seismic import PRESSURE, NodeSprings, PileRowModel
from ...core.errors import InputError
from ...core.printed import LENGTH, Printed
from .model import Joint
from .pile_model import (
    COLUMN, M_PHI, M_THETA, PILE, RIGID, FrameElement, GroundElement, Member, NonLinear, PileRange, Support,
)

_FULL_WIDTH = str.maketrans("0123456789", "０１２３４５６７８９")
SUPPORT_KIND = 2  # the vertical spring of the surface of the pile (JRSNAP's Dst)


@dataclass(frozen=True)
class PileRowParts:
    joints: tuple[Joint, ...]
    member: Member
    elements: tuple[FrameElement, ...]
    nonlinear: tuple[NonLinear, ...]
    pile: PileRange
    supports: tuple[Support, ...]


def row_title(piles: int) -> str:
    """The title of the member of a pile row: 杭（３本杭）, the piles in the depth in full-width digits."""
    return f"杭（{str(piles).translate(_FULL_WIDTH)}本杭）"


def support_values(springs: NodeSprings) -> tuple[Printed, ...]:
    """The ten values of a SuppotInfo row, in the order JRSNAP saves them (Kv2 is written twice, and Kv4)."""
    return (springs.push_first, springs.push_yield, springs.pull_yield, springs.push_second, springs.push_ultimate,
            springs.pull_ultimate, springs.push_second, springs.pull_first, springs.pull_second, springs.pull_second)


def _runs(lengths: list[Decimal]) -> list[tuple[Decimal, int]]:
    runs: list[tuple[Decimal, int]] = []
    for length in lengths:
        if runs and runs[-1][0] == length:
            runs[-1] = (length, runs[-1][1] + 1)
        else:
            runs.append((length, 1))
    return runs


def pile_row_parts(row: PileRowModel, *, member: int, head_joint: int, first_joint: int, x: Printed, top: Printed,
                   rigid: Printed | None, first_element: int, first_nonlinear: int, section: Callable[[Printed], int],
                   zone: Printed, title: str | None = None) -> PileRowParts:
    """The parts of *row*: its head is joint *head_joint*; its nodes are the joints from *first_joint* at *x*, the first one
    at *top* (y downward) and the others at their depth below it; *rigid* is the length from the head to *top*, or None
    when the head is the first node of the row (the pile starts at the head joint: *first_joint* is then the number of the
    second node).

    *section* gives the number of the section of the part of the pile at a depth (m), *zone* is the length of the 2D zone
    (m) the titles name. *first_element* is the number of the rigid element, *first_nonlinear* the number of the first
    pile element among those that have a nonlinear model."""
    digits = str(row.piles).translate(_FULL_WIDTH)
    title = title or row_title(row.piles)
    shift = 0 if rigid is not None else 1  # the node 0 is the head when there is no rigid element
    numbers = [first_joint + index - shift for index in range(len(row.nodes))]
    if rigid is None:
        numbers[0] = head_joint
    joints = tuple(Joint(numbers[index], x, put(LENGTH, d(top) + d(node.depth)))
                   for index, node in enumerate(row.nodes) if rigid is not None or index > 0)
    last_joint = numbers[-1]
    lengths = [d(e.bottom) - d(e.top) for e in row.elements]
    runs = tuple((LENGTH(float(length)), count) for length, count in _runs(lengths))
    divisions = runs if rigid is None else ((rigid, 1), *runs)
    owner = Member(number=member, title=title, i=head_joint, j=last_joint,
                   length=row.length if rigid is None else put(LENGTH, d(rigid) + d(row.length)),
                   divisions=divisions, depth_piles=row.piles, nonlinear=True, pile=True)
    elements = [] if rigid is None else [FrameElement(first_element, head_joint, numbers[0], RIGID, 0)]
    nonlinear = []
    for index, element in enumerate(row.elements):
        number = first_element + len(elements)
        elements.append(FrameElement(number, numbers[index], numbers[index + 1], PILE, first_nonlinear + index,
                                     GroundElement(element.horizontal, element.pressure_top, element.pressure_bottom)))
        if index == 0:
            name, ends = f"杭頭（{digits}本杭）", (1, 1)
        elif element.top.value < zone.value:
            name, ends = f"杭（{digits}本杭）(2D)", (0, 0)
        else:
            name, ends = f"杭（{digits}本杭）", (0, 0)
        nonlinear.append(NonLinear(section=section(element.top), model=M_PHI, failure=1, ends=ends,
                                   depth_piles=row.piles, title=f"{name}：要素番号　{number}"))
    supports = tuple(Support(numbers[index], SUPPORT_KIND, support_values(node.springs))
                     for index, node in enumerate(row.nodes) if node.springs is not None)
    return PileRowParts(joints=joints, member=owner, elements=tuple(elements), nonlinear=tuple(nonlinear),
                        pile=PileRange(member, elements[-len(row.elements)].number, elements[-1].number), supports=supports)


MICRO = Decimal("0.01")  # m: the micro member of the M-θ of the joint (manual 4-6: 10 mm or less)


@dataclass(frozen=True)
class SteelHead:
    """The head of a row of 鋼管ソイルセメント杭 (decision 122, manual 4-6, example 図2.2.5): the micro member of the M-θ of the
    joint (section *joint*) below the head joint, the rigid zone of the fill down to *rigid* (1.0D, m below the head), then the
    M-φ of the pipe (section *pipe*)."""

    joint: int
    pipe: int
    rigid: Printed


def _cut(element, depth: Decimal) -> Printed:
    """The effective resistance earth pressure of *element* at *depth* below the head, on the line between its ends."""
    top, bottom = d(element.top), d(element.bottom)
    upper, lower = d(element.pressure_top), d(element.pressure_bottom)
    return put(PRESSURE, upper + (lower - upper) * (depth - top) / (bottom - top))


def steel_row_parts(row: PileRowModel, *, member: int, head_joint: int, first_joint: int, x: Printed, top: Printed,
                    first_element: int, first_nonlinear: int, head: SteelHead, title: str) -> PileRowParts:
    """The parts of the row *row* of 鋼管ソイルセメント杭 whose head is the joint *head_joint* at *top* (y downward): the joint
    below the micro member is *first_joint*, the nodes of the row follow. The micro member and the rigid zone keep the ground
    of the elements they are on (the first element of the row is cut at the micro member, its pressure there on the line
    between its ends); the rigid zone must end at a node of the row."""
    digits = str(row.piles).translate(_FULL_WIDTH)
    rigid = d(head.rigid)
    ends = [d(e.bottom) for e in row.elements]
    if rigid not in ends:
        raise InputError(f"結合部の剛域（1.0D＝{head.rigid.value:g} m）の下端に杭の節点がありません"
                         "（地層の境が杭頭から 1.0D の間にある鋼管ソイルセメント杭は未対応です）")
    zone = ends.index(rigid) + 1  # the elements of the row the rigid zone takes
    micro_joint = first_joint
    numbers = [head_joint] + [first_joint + index for index in range(1, len(row.nodes))]
    joints = (Joint(micro_joint, x, put(LENGTH, d(top) + MICRO)),
              *(Joint(numbers[index], x, put(LENGTH, d(top) + d(node.depth)))
                for index, node in enumerate(row.nodes) if index > 0))
    first = row.elements[0]
    cut = _cut(first, MICRO)
    lengths = [MICRO, d(first.bottom) - d(first.top) - MICRO, *(d(e.bottom) - d(e.top) for e in row.elements[1:])]
    divisions = tuple((LENGTH(float(length)), count) for length, count in _runs(lengths))
    owner = Member(number=member, title=title, i=head_joint, j=numbers[-1], length=row.length, divisions=divisions,
                   depth_piles=row.piles, nonlinear=True, pile=True)
    elements = [FrameElement(first_element, head_joint, micro_joint, COLUMN, first_nonlinear,
                             GroundElement(first.horizontal, first.pressure_top, cut))]
    nonlinear = [NonLinear(section=head.joint, model=M_THETA, failure=1, ends=(1, 1), depth_piles=row.piles,
                           title=f"結合部（{digits}本杭）：要素番号　{first_element}")]
    for index, element in enumerate(row.elements):
        number = first_element + 1 + index
        i = micro_joint if index == 0 else numbers[index]
        ground = GroundElement(element.horizontal, cut if index == 0 else element.pressure_top, element.pressure_bottom)
        if index < zone:
            elements.append(FrameElement(number, i, numbers[index + 1], RIGID, 0, ground))
            continue
        elements.append(FrameElement(number, i, numbers[index + 1], PILE, first_nonlinear + len(nonlinear), ground))
        nonlinear.append(NonLinear(section=head.pipe, model=M_PHI, failure=1, ends=(0, 0), depth_piles=row.piles,
                                   title=f"鋼管杭（{digits}本杭）：要素番号　{number}"))
    supports = tuple(Support(numbers[index], SUPPORT_KIND, support_values(node.springs))
                     for index, node in enumerate(row.nodes) if node.springs is not None)
    return PileRowParts(joints=joints, member=owner, elements=tuple(elements), nonlinear=tuple(nonlinear),
                        pile=PileRange(member, first_element, elements[-1].number), supports=supports)

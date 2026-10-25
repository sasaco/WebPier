"""The ground of a pile row as the JRSNAP model of a pile foundation takes it (decision 93, 0710 and 0720).

JRSNAP reads the ground springs of a pile as it saves them when a .sdc of SOIL-JR is linked to the model
(``JRSNAP_Input``, the 連携 of the pile members: the rules below are the ones it applies, checked against the numbers of
its sample 01_サンプル(V53)：RC橋脚L, whose 51 rows of nodes and 60 pile elements they give but for the last digit of two
Kv2 values, a tie that JRSNAP's Single arithmetic rounds down; ``.claude/docs/plans/pile-ndu-fields.md``):

- the pile is cut at the boundaries of the layers into elements of D (the diameter): a length of 1.5 D or more gives
  an element of D and what is left is cut the same way, one over D and under 1.5 D is halved, up to D is one element;
- each element has the horizontal spring of its layer (短期(非線形)) and the effective resistance earth pressure along
  the layer, from its upper value at the top to its lower value at the bottom, by the length of the elements;
- each node has the vertical springs of the surface of the two half-elements next to it, and the bearing capacity of
  the surface: the length of a half-element inside the part of its layer that has the spring (⊿l) times the value of
  the layer, for the push side and the pull side; the node at the tip adds the springs and the bearing capacity of the
  tip. A part without a spring is the upper part of a layer down to 1/β and, on the push side, the lowest part, the
  least embedment into the bearing layer: ⊿l of the table says how much, and where.

The springs are as printed in the .sdc, per column; the sums are exact decimals rounded as JRSNAP rounds: a spring to
0.1 (0.01 below 0.1) and a bearing capacity first to 0.01, then to 0.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import LENGTH, Precision, Printed
from ._exact import d, put
from .pile_springs import SeismicDirection, SeismicLayer, SurfaceSide

STIFFNESS = Precision(1, "kN/m")  # a vertical spring of a node
STIFFNESS_TINY = Precision(2, "kN/m")  # JRSNAP keeps two decimals below 0.1
CAPACITY = Precision(1, "kN")  # the bearing capacity of the surface at a node
CAPACITY_TWICE = Precision(2, "kN")  # … rounded to 0.01 first
HORIZONTAL = Precision(0, "kN/m2")  # the horizontal spring of the ground
PRESSURE = Precision(1, "kN/m")  # the effective resistance earth pressure
ZERO = Decimal(0)
ONE_AND_A_HALF = Decimal("1.5")


@dataclass(frozen=True)
class PileElement:
    """One element of a pile row: from *top* to *bottom* (m below the head of the pile) in one layer."""

    layer: int  # 1 at the first layer
    top: Printed
    bottom: Printed
    horizontal: Printed  # 短期(非線形), kN/m2
    pressure_top: Printed  # effective resistance earth pressure at the top of the element, kN/m
    pressure_bottom: Printed


@dataclass(frozen=True)
class NodeSprings:
    """The vertical springs and bearing capacity of a node, in the order of the columns of JRSNAP's SuppotInfo."""

    push_first: Printed  # Kv
    push_yield: Printed  # Rmt1
    pull_yield: Printed  # Rmt3
    push_second: Printed  # Kv2
    push_ultimate: Printed  # Rmt2
    pull_ultimate: Printed  # Rmt4
    pull_first: Printed  # Kv3
    pull_second: Printed  # Kv4


@dataclass(frozen=True)
class PileNode:
    depth: Printed  # m below the head of the pile
    springs: NodeSprings | None  # None: a node without a row (everything is zero)


@dataclass(frozen=True)
class PileRowModel:
    row: int  # 1 at the first row of the direction
    column: int  # 1 at the first column of the .sdc: the column of the row
    piles: int  # 奥行き本数
    nodes: tuple[PileNode, ...]  # from the head to the tip
    elements: tuple[PileElement, ...]  # one between each two nodes

    @property
    def length(self) -> Printed:
        return self.nodes[-1].depth


def divide(thicknesses: list[Decimal], diameter: Decimal) -> list[list[Decimal]]:
    """The lengths of the elements of each layer (JRSNAP_Input, ``GET_JOINT_DATA``): D each; the part left once less
    than 1.5 D is in one layer is halved when it is over D."""
    layers = []
    for thickness in thicknesses:
        left, lengths = thickness, []
        while left >= ONE_AND_A_HALF * diameter:
            lengths.append(diameter)
            left -= diameter
        if left > diameter:
            lengths += [left / 2, left / 2]
        elif left > ZERO:
            lengths.append(left)
        layers.append(lengths)
    return layers


def _zone(side: SurfaceSide, top: Decimal, thickness: Decimal, inverse_beta: Decimal, name: str) -> tuple[Decimal, Decimal]:
    """The part of a layer that has the spring: below 1/β, and short of the bottom by what ⊿l leaves."""
    length = d(side.length)
    skipped = min(max(inverse_beta - top, ZERO), thickness)
    if length > thickness - skipped:
        raise InputError(f".sdc の{name}: ⊿l（{side.length} m）が層厚から 1/β の上の部分を除いた長さより大きい値です")
    start = top + skipped
    return start, start + length


def _overlap(low: Decimal, high: Decimal, zone: tuple[Decimal, Decimal]) -> Decimal:
    return max(ZERO, min(high, zone[1]) - max(low, zone[0]))


def _spring(value: Decimal) -> Printed:
    return put(STIFFNESS if value >= Decimal("0.1") or value == ZERO else STIFFNESS_TINY, value)


def _capacity(value: Decimal) -> Printed:
    return put(CAPACITY, d(put(CAPACITY_TWICE, value)))


def pile_row(direction: SeismicDirection, row: int, diameter: Printed) -> PileRowModel:
    """The elements and nodes of pile row *row* of *direction* (the column of the row is its number)."""
    if not 1 <= row <= direction.rows:
        raise InputError(f".sdc の{direction.name}に杭列 {row} がありません（杭列数 {direction.rows}）")
    if diameter.value <= 0:
        raise InputError("杭径が正の値ではありません")
    column = row - 1
    layers = direction.layers
    thicknesses = [d(layer.thickness) for layer in layers]
    inverse_beta = d(direction.inverse_beta)
    tip = direction.tip
    if any(tip.horizontal) or any(tip.rotation):
        raise InputError(f".sdc の{direction.name}に杭先端の水平ばねまたは回転ばねがあります（βl ≦ 2.5 の杭は未対応です）")
    division = divide(thicknesses, d(diameter))
    tops, edge = [], ZERO
    for thickness in thicknesses:
        tops.append(edge)
        edge += thickness
    # the nodes: the head, then the end of each element
    depths, owner = [ZERO], []
    for index, lengths in enumerate(division):
        for length in lengths:
            depths.append(depths[-1] + length)
            owner.append(index)
    elements = []
    for layer_index, layer in enumerate(layers):
        at = [i for i, o in enumerate(owner) if o == layer_index]
        total = sum((depths[i + 1] - depths[i] for i in at), ZERO)
        upper, lower = d(layer.pressure_upper[column]), d(layer.pressure_lower[column])
        reached, above = ZERO, put(PRESSURE, upper)
        for i in at:
            reached += depths[i + 1] - depths[i]
            below = put(PRESSURE, (lower - upper) * (reached / total) + upper)
            elements.append(PileElement(layer=layer.number, top=LENGTH(float(depths[i])), bottom=LENGTH(float(depths[i + 1])),
                                        horizontal=HORIZONTAL(layer.horizontal[column]), pressure_top=above,
                                        pressure_bottom=below))
            above = below
    zones = [(_zone(layer.push, tops[i], thicknesses[i], inverse_beta, f"{direction.name}の層 {layer.number} の押込み側"),
              _zone(layer.pull, tops[i], thicknesses[i], inverse_beta, f"{direction.name}の層 {layer.number} の引抜き側"))
             for i, layer in enumerate(layers)]
    nodes = []
    for index, depth in enumerate(depths):
        halves = []
        if index > 0:
            halves.append((depth - (depth - depths[index - 1]) / 2, depth, owner[index - 1]))
        if index + 1 < len(depths):
            halves.append((depth, depth + (depths[index + 1] - depth) / 2, owner[index]))
        sums = [ZERO] * 8  # Kv, Rmt1, Rmt3, Kv2, Rmt2, Rmt4, Kv3, Kv4
        for low, high, layer_index in halves:
            layer: SeismicLayer = layers[layer_index]
            push_zone, pull_zone = zones[layer_index]
            push, pull = _overlap(low, high, push_zone), _overlap(low, high, pull_zone)
            sums[0] += d(layer.push.first[column]) * push
            sums[1] += d(layer.push.yield_load[column]) * push
            sums[2] += d(layer.pull.yield_load[column]) * pull
            sums[3] += d(layer.push.second[column]) * push
            sums[4] += d(layer.push.ultimate[column]) * push
            sums[5] += d(layer.pull.ultimate[column]) * pull
            sums[6] += d(layer.pull.first[column]) * pull
            sums[7] += d(layer.pull.second[column]) * pull
        if index == len(depths) - 1:
            sums[0] += d(tip.first[column])
            sums[3] += d(tip.second[column])
            sums[1] += d(tip.yield_load[column])
            sums[4] += d(tip.ultimate[column])
        springs = None
        if any(sums):
            springs = NodeSprings(push_first=_spring(sums[0]), push_yield=_capacity(sums[1]), pull_yield=_capacity(sums[2]),
                                  push_second=_spring(sums[3]), push_ultimate=_capacity(sums[4]),
                                  pull_ultimate=_capacity(sums[5]), pull_first=_spring(sums[6]),
                                  pull_second=_spring(sums[7]))
        nodes.append(PileNode(depth=LENGTH(float(depth)), springs=springs))
    return PileRowModel(row=row, column=column + 1, piles=direction.depth_piles[column], nodes=tuple(nodes),
                        elements=tuple(elements))

"""The support reaction of a combination, summed by hand from the loads WebPier gives the frame (decision 77).

The frame is statically determinate (Example2 8-1: a single line of nodes, the springs at the footing bottom). The
reaction at the footing-bottom support is then the sum of the loads of the combination, whatever the real FrameWebforCS
computes: Vd = Σ N, Fx = −Σ H, Mz = −Σ (M + H × the height of the load above the support); a line load acts over its
members. This is what the real FEMPython reactions of the current generator are held to, since with the impact on the
pier body (decision 77) no sample value exists for them. A combination with a horizontal action of both directions
(Define 13-20) is analysed in both; FEMPython's row carries one of the two, the one whose Fx has the sign of ``fx``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ByHand:
    vd: float  # downward N summed (= −fy)
    fx: float | None  # None for 0620: its alternatives (up or down line, either direction) are not told by the row
    mz: float | None


def members_height(frame, line) -> list[float]:
    heights = {member.number: member.height.value for member in frame.members}
    return [heights[number] for number in line.members]


def by_hand(result, number: int, fx: float, support: int) -> ByHand:
    """Vd, Fx and Mz of combination *number* of a 0610 / 0620 *result* at node *support*.

    *fx* is the real row's Fx: its sign (a vanishing value counts as negative) picks the horizontal direction.
    """
    frame = result.frame
    combination = result.combinations[number - 1]
    if not hasattr(combination, "signed"):  # 0620: the vertical sum is that of every alternative (mirrored tracks)
        vd = 0.0
        for component in combination.components:
            action = component.alternatives[0]
            vd += sum(point.n.value for point in action.points)
            vd += sum(line.n.value * sum(members_height(frame, line)) for line in action.line_loads)
        return ByHand(vd=round(vd, 4), fx=None, mz=None)
    nodes = {node.number: node for node in frame.nodes}
    members = {member.number: member for member in frame.members}
    base = nodes[support].y.value
    sign = 1 if fx <= 0 or abs(fx) < 1e-9 else -1
    vd = horizontal = moment = 0.0
    for component in combination.signed(sign):
        for point in component.points:
            vd += point.n.value
            horizontal += point.h.value
            moment += point.m.value + point.h.value * (nodes[point.node].y.value - base)
        for line in component.line_loads:
            for member_number in line.members:
                member = members[member_number]
                length = member.height.value
                middle = (nodes[member.start].y.value + nodes[member.end].y.value) / 2 - base
                vd += line.n.value * length
                horizontal += line.h.value * length
                moment += line.h.value * length * middle
    return ByHand(vd=round(vd, 4), fx=round(-horizontal, 4), mz=round(-moment, 4))


def reference_frameweb(pier, stage: str) -> bytes:
    """The FrameWeb file of the 0610 / 0620 frame as before decision 77: the impact with the girder coefficients.

    Example2 has no impact reduction on the pier body, so its sample values are compared with the real reactions of
    this file; the file of the current generator is held to ``by_hand`` instead.
    """
    from dataclasses import replace

    from webpier.calc.foundation import calculate_foundation
    from webpier.calc.longitudinal import calculate_longitudinal
    from webpier.calc.reaction import calculate_reaction
    from webpier.calc.transverse import calculate_transverse
    from webpier.core.integrity import dump_json
    from webpier.export.frameweb import build_frameweb, build_frameweb_transverse

    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    train = reaction.train
    groups = {name: replace(getattr(train, name), origin_pier_impact=getattr(train, name).origin_impact,
                            end_pier_impact=getattr(train, name).end_impact)
              for name in ("ultimate", "service", "fatigue")}
    reference = replace(reaction, train=replace(train, **groups))
    if stage == "0610":
        return dump_json(build_frameweb(calculate_longitudinal(pier, foundation, reference)))
    return dump_json(build_frameweb_transverse(calculate_transverse(pier, foundation, reference)))


def by_hand_absolute(result, number: int, hd: float, md: float, support: int) -> ByHand:
    """``by_hand`` for a reading that keeps only |Fx| and |Mz| (Hd, Md of 0800).

    A combination with a horizontal action of both directions has two variants (equal |Fx| where the horizontal
    action is a single load, different |Mz|); the real row is one of them, so the one nearer to (*hd*, *md*) is taken.
    """
    candidates = [by_hand(result, number, fx, support) for fx in (-1.0, 1.0)]
    if candidates[0].fx is None:
        return candidates[0]
    best = min(candidates, key=lambda hand: abs(abs(hand.fx) - hd) + abs(abs(hand.mz) - md))
    return ByHand(vd=best.vd, fx=abs(best.fx), mz=abs(best.mz))

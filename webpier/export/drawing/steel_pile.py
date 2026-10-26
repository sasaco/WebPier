"""鋼管ソイルセメント杭の配筋図 (decision 99, CONTEXT.md 配筋図): the 杭とフーチングの結合部 seen from the side and at
the head, and the 杭先端部, from the sizes the 杭の構造細目 of 0400 decides (calc.detailing.steel_pile).

On the left the head: the pipe (its outer and inner faces) from its top 50 mm into the footing (the footing's base is
the line below its top) down past the filling concrete, the soil cement around it, the anchor bars on both sides from l1
above the top of the pipe down to 100 mm above the bottom of the filling with a semicircular hook at each end, the
hoops in the footing and in the pipe, the ずれ止め on the inner face and the bottom of the filling; on its right a chain
of the hoops in the footing up to l1 and of those in the pipe down to lc, and one of the ずれ止め from the top. In the middle the section at the head (the soil cement, the pipe, the
anchor bars on their circle and the ずれ止め ring). On the right the 杭先端部: the pipe ending 余裕長 above the tip of the
soil cement, its ずれ止め over the 取付長, the 根入れ長 of the bearing layer, with a chain of each.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from .sheet import GAP, TEXT, Sheet, TextEntityAlignment, Vec2, mm, number  # isort: skip

from ...calc.detailing.steel_pile import EMBEDMENT, FILL_BOTTOM, SteelPileDetailing

_SPACE = 15.0  # paper mm between the views
_BELOW = Decimal(300)  # mm of the pipe drawn below the filling


@dataclass(frozen=True)
class SteelPileFigure:
    diameter: Decimal  # D, mm
    thickness: Decimal  # t as made
    soil_cement: Decimal  # Dsc
    centroid: Decimal  # the anchor bars from the outer face
    bar_diameter: Decimal
    bar_count: int
    grade: str
    hook: Decimal  # lh, the hook's reach below (above) the end of the straight bar
    l1: Decimal  # above the top of the pipe
    filling: Decimal  # lc below it
    footing_hoop: Decimal  # diameter
    footing_hoops: tuple[Decimal, ...]  # above the top of the pipe
    footing_pitches: tuple[Decimal, Decimal]
    pipe_hoop: Decimal
    pipe_hoops: tuple[Decimal, ...]  # below the top of the pipe
    ribs: tuple[Decimal, ...]  # below the top of the pipe; none when no flat bar fits
    rib_size: tuple[Decimal, Decimal] | None  # t', B
    tip_steps: tuple[Decimal, ...]  # the 杭先端部's ずれ止め above the end of the pipe
    margin: Decimal  # 余裕長 le
    penetration: Decimal  # 貫入長 lsp0
    embedment: Decimal  # 根入れ長 Df0

    @property
    def length(self) -> Decimal:
        """The drawn height of the head: l1 above and the pipe below the filling."""
        return self.l1 + self.filling + _BELOW


def steel_pile_figure(pile: SteelPileDetailing) -> SteelPileFigure:
    """What the 鋼管ソイルセメント杭 is drawn from (*pile*: the 杭の構造細目 of 0400, which has read the input)."""
    pipe, joint = pile.pipe, pile.joint
    ribs = joint.ribs
    steps: tuple[Decimal, ...] = ()
    size = None
    if ribs.thickness is not None and ribs.width is not None and ribs.spacing is not None:
        steps = tuple(number(ribs.quarter) + index * number(ribs.spacing) for index in range(ribs.steps))
        size = (number(ribs.thickness), number(ribs.width))
    tip = pipe.tip
    tip_steps: tuple[Decimal, ...] = ()
    if tip.steps is not None and tip.first is not None and tip.pitch is not None:
        tip_steps = tuple(number(tip.first) + index * number(tip.pitch) for index in range(tip.steps))
    hoops = joint.footing_hoops
    return SteelPileFigure(
        number(pipe.diameter), number(pipe.made.value), number(pipe.soil_cement), number(joint.centroid),
        number(joint.bar_diameter), joint.bar_count, joint.grade, number(joint.filling.hook),
        number(joint.anchorage.l1), number(joint.filling.length), number(hoops.diameter), hoops.positions,
        (number(hoops.lower_pitch), number(hoops.upper_pitch)), number(joint.pipe_hoops.diameter),
        joint.pipe_hoops.positions, steps, size, tip_steps, number(tip.margin), number(tip.penetration),
        number(tip.embedment))


def draw_steel_pile(sheet: Sheet, figure: SteelPileFigure, origin: Vec2) -> None:
    """The head with the centre of the top of the pipe at *origin*, the section and the 杭先端部 on its right."""
    p = sheet.p
    outer = float(figure.diameter) / 2
    soil = float(figure.soil_cement) / 2
    inner = outer - float(figure.thickness)
    bar = outer - float(figure.centroid)  # the anchor bars from the axis
    bottom = float(figure.filling)
    end = float(figure.filling + _BELOW)
    gap = GAP * p

    def at(x: float, depth: float) -> Vec2:  # x from the axis, depth below the top of the pipe
        return origin + Vec2(x, -depth)

    base = EMBEDMENT.value
    sheet.line(at(-soil - 5 * p, base), at(soil + 5 * p, base), "躯体")
    sheet.text("フーチング下面", at(-soil - 5 * p, base) + Vec2(0, gap), TextEntityAlignment.BOTTOM_LEFT)
    for side in (-1, 1):
        sheet.line(at(side * outer, 0), at(side * outer, end), "躯体")
        sheet.line(at(side * inner, 0), at(side * inner, end), "躯体")
        sheet.line(at(side * soil, base), at(side * soil, end), "躯体")
    sheet.line(at(-outer, 0), at(outer, 0), "躯体")
    sheet.line(at(-inner, bottom), at(inner, bottom), "躯体")
    # the anchor bars: straight from l1 above the top to 100 mm above the bottom of the filling, a hook at each end
    lowest = bottom - FILL_BOTTOM.value
    hook = float(figure.hook) - float(figure.bar_diameter) / 2  # the centre line's radius
    for side in (-1, 1):
        x = side * bar
        sheet.line(at(x, -float(figure.l1) + hook), at(x, lowest - hook))
        top = at(x + side * hook, -float(figure.l1) + hook)  # the upper hook turns outwards
        sheet.msp.add_arc(top, hook, 0, 180, dxfattribs={"layer": "鉄筋"})
        low = at(x - side * hook, lowest - hook)  # the lower hook turns inwards
        sheet.msp.add_arc(low, hook, 180, 360, dxfattribs={"layer": "鉄筋"})
    # the hoops: in the footing (above the top) and in the pipe
    for height in figure.footing_hoops:
        sheet.line(at(-bar, -float(height)), at(bar, -float(height)))
    for depth in figure.pipe_hoops:
        sheet.line(at(-bar, float(depth)), at(bar, float(depth)))
    # the ずれ止め on the inner face
    if figure.rib_size is not None:
        thickness, width = (float(value) for value in figure.rib_size)
        for depth in figure.ribs:
            for side in (-1, 1):
                sheet.rectangle(min(side * inner, side * (inner - width)) + origin.x, origin.y - float(depth),
                                max(side * inner, side * (inner - width)) + origin.x,
                                origin.y - float(depth) - thickness, "鉄筋")
    # the callouts on the left
    left = -soil - 3 * p
    # the rules give three hoops in the footing at least and four in the pipe (its range is 850 mm or more)
    middle = float(figure.footing_hoops[2])
    lower, upper = (mm(pitch) for pitch in figure.footing_pitches)
    sheet.label(at(left, -middle), -1, "帯鉄筋", f"D{mm(figure.footing_hoop)} ctc{lower}・{upper}")
    sheet.line(at(left, -middle), at(-bar, -middle), "引出線")
    depth = float(figure.pipe_hoops[len(figure.pipe_hoops) // 2])
    sheet.label(at(left, depth), -1, "帯鉄筋", f"D{mm(figure.pipe_hoop)}")
    sheet.line(at(left, depth), at(-bar, depth), "引出線")
    anchor = -float(figure.l1) + 2 * hook
    sheet.label(at(left, anchor), -1, "アンカー鉄筋", f"D{mm(figure.bar_diameter)}-{figure.bar_count}本 {figure.grade}")
    sheet.line(at(left, anchor), at(-bar, anchor), "引出線")
    pipe_label = (bottom + end) / 2
    sheet.label(at(left, pipe_label), -1, "鋼管", f"t={mm(figure.thickness)}")
    sheet.line(at(left, pipe_label), at(-outer, pipe_label), "引出線")
    if figure.rib_size is not None and figure.ribs:
        depth = float(figure.ribs[0]) + float(figure.rib_size[0]) / 2
        thickness, width = figure.rib_size
        sheet.label(at(left, depth + 3 * TEXT * p), -1, "ずれ止め", f"t{mm(thickness)}×{mm(width)} SS400")
        sheet.line(at(left, depth + 3 * TEXT * p), at(-inner, depth), "引出線")
    # the chains on the right: l1, the top, the hoops in the pipe, lc; and the ずれ止め from the top to lc
    edge = soil + gap
    sheet.chain(sorted({figure.l1, *figure.footing_hoops}), edge, soil + 12 * p, True, origin)
    sheet.chain(sorted({*(-depth for depth in figure.pipe_hoops), -figure.filling}), edge, soil + 24 * p, True, origin)
    if figure.ribs:
        sheet.chain(sorted({Decimal(0), *(-depth for depth in figure.ribs), -figure.filling}), edge, soil + 36 * p,
                    True, origin)
    sheet.text(f"lc={mm(figure.filling)}", at(soil + 42 * p, bottom), TextEntityAlignment.MIDDLE_LEFT)
    sheet.text(f"l1={mm(figure.l1)}", at(soil + 42 * p, -float(figure.l1)), TextEntityAlignment.MIDDLE_LEFT)

    # the section at the head, then the 杭先端部
    right = soil + (42 + _SPACE) * p + sheet.width(f"lc={mm(figure.filling)}")
    _section(sheet, figure, at(right + soil, float(figure.l1) / 2 - float(figure.l1)))
    _tip(sheet, figure, at(right + 2 * soil + _SPACE * p + soil, end))


def _section(sheet: Sheet, figure: SteelPileFigure, centre: Vec2) -> None:
    """The section at the head with its centre at *centre*."""
    p = sheet.p
    outer = float(figure.diameter) / 2
    inner = outer - float(figure.thickness)
    circle = outer - float(figure.centroid)
    sheet.msp.add_circle(centre, float(figure.soil_cement) / 2, dxfattribs={"layer": "躯体"})
    sheet.msp.add_circle(centre, outer, dxfattribs={"layer": "躯体"})
    sheet.msp.add_circle(centre, inner, dxfattribs={"layer": "躯体"})
    for k in range(figure.bar_count):
        angle = 2 * math.pi * k / figure.bar_count + math.pi / 2
        sheet.circle(centre + Vec2(circle * math.cos(angle), circle * math.sin(angle)), float(figure.bar_diameter) / 2)
    if figure.rib_size is not None:
        sheet.msp.add_circle(centre, inner - float(figure.rib_size[1]), dxfattribs={"layer": "鉄筋"})
    soil = float(figure.soil_cement) / 2
    gap = GAP * p
    sheet.text("杭頭", centre + Vec2(0, soil + (TEXT + 2 * GAP) * p), TextEntityAlignment.BOTTOM_CENTER)
    for index, line in enumerate((f"Dsp={mm(figure.diameter)}", f"Dsc={mm(figure.soil_cement)}",
                                  f"D{mm(figure.bar_diameter)}-{figure.bar_count}本")):
        sheet.text(line, centre + Vec2(0, -soil - gap - index * (TEXT + GAP) * p), TextEntityAlignment.TOP_CENTER)


def _tip(sheet: Sheet, figure: SteelPileFigure, foot: Vec2) -> None:
    """The 杭先端部 with the centre of the tip of the soil cement at *foot*."""
    p = sheet.p
    outer = float(figure.diameter) / 2
    inner = outer - float(figure.thickness)
    soil = float(figure.soil_cement) / 2
    margin = float(figure.margin)
    top = float(figure.margin + figure.penetration) + 300.0  # the drawn height above the tip

    def at(x: float, height: float) -> Vec2:  # x from the axis, height above the tip
        return foot + Vec2(x, height)

    for side in (-1, 1):
        sheet.line(at(side * soil, 0), at(side * soil, top), "躯体")
        sheet.line(at(side * outer, margin), at(side * outer, top), "躯体")
        sheet.line(at(side * inner, margin), at(side * inner, top), "躯体")
    sheet.line(at(-soil, 0), at(soil, 0), "躯体")
    sheet.line(at(-outer, margin), at(-inner, margin), "躯体")
    sheet.line(at(inner, margin), at(outer, margin), "躯体")
    for height in figure.tip_steps:
        sheet.line(at(-inner, margin + float(height)), at(inner, margin + float(height)))
    ground = float(figure.embedment)
    sheet.line(at(-soil - 5 * p - sheet.width("支持層"), ground), at(-soil, ground), "引出線")
    sheet.text("支持層", at(-soil - GAP * p, ground) + Vec2(0, GAP * p), TextEntityAlignment.BOTTOM_RIGHT)
    edge = soil + GAP * p
    steps = sorted({Decimal(0), figure.margin, *(figure.margin + height for height in figure.tip_steps)})
    sheet.chain(steps, edge, soil + 12 * p, True, foot)
    sheet.chain(sorted({Decimal(0), figure.embedment, figure.margin + figure.penetration}), edge, soil + 24 * p, True,
                foot)
    sheet.text("杭先端部", at(0, top) + Vec2(0, (TEXT + 2 * GAP) * p), TextEntityAlignment.BOTTOM_CENTER)
    sheet.text(f"ずれ止め {len(figure.tip_steps)}段", at(soil + 30 * p, margin + float(figure.tip_steps[-1]) / 2
                                                    if figure.tip_steps else margin), TextEntityAlignment.MIDDLE_LEFT)

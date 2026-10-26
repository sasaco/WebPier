"""場所打ち杭の配筋図 (decision 98, CONTEXT.md 配筋図): the pile from its head down and its sections, from 鉄筋.杭 and the
杭頭定着長 of 0400 (calc.detailing.pile).

On the left the side of the pile: its outline from the head down to the end of the last zone of the hoops (the pile goes
on below it), the main bars on both sides from the 杭頭定着長 above the head (the base of the footing is the line at the
head) down, the hoops of each zone at their pitch (the 2D zone, the zones below it), the cut-off (the 段落し長 of the input
below the head) where the main bars change, and on the right a chain of the 杭頭定着長, the zones and their hoops. On the
right the section at the head (the main bars on the circle of their 芯かぶり, the hoop round them, the 芯かぶり) and, with a
cut-off, the section after it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from .sheet import GAP, TEXT, Sheet, TextEntityAlignment, Vec2, mm, number  # isort: skip

from ...calc.detailing.pile import PileDetailing
from ...core.errors import InputError
from ...core.printed import Printed
from ...inputs import PierInput

_REBAR = "鉄筋.杭"
_METRE = Decimal(1000)
_SPACE = 15.0  # paper mm between the side and the sections, and between the sections


@dataclass(frozen=True)
class Zone:
    name: str  # 2D区間, 第1区間, …
    top: Decimal  # mm below the head
    bottom: Decimal
    diameter: Printed  # the hoop
    sets: int
    pitch: Printed


@dataclass(frozen=True)
class Section:
    title: str  # 杭頭, 段落し後
    main_diameter: Printed
    main_count: int
    hoop_diameter: Printed
    hoop_sets: int
    hoop_pitch: Printed


@dataclass(frozen=True)
class PileFigure:
    diameter: Decimal  # D, mm
    centre: Decimal  # 芯かぶり of the main bars, mm
    anchorage: Decimal  # 杭頭定着長, mm
    zones: tuple[Zone, ...]
    cutoff: Decimal | None  # 段落し長, mm below the head; None: no cut-off
    sections: tuple[Section, ...]  # 杭頭, and 段落し後 with a cut-off

    @property
    def length(self) -> Decimal:
        """The drawn length below the head: to the end of the last zone."""
        return self.zones[-1].bottom


def _need(value, path: str):
    if value is None:
        raise InputError(f"{path}: 配筋図に必要です")
    return value


def pile_figure(pier: PierInput, pile: PileDetailing) -> PileFigure:
    """What the pile is drawn from (*pile*: the 杭の構造細目 of 0400, which has checked the bars it reads)."""
    bars = pier.rebar.pile
    found = pile.section
    head = bars.hoops.zone_2d
    diameter = number(found.diameter)
    top = 2 * diameter
    zones = [Zone("2D区間", Decimal(0), top, head.diameter, head.sets, head.pitch)]
    for index, zone in enumerate(bars.hoops.lower):  # 0400 has read each zone
        bottom = top + number(zone.length) * _METRE
        zones.append(Zone(f"第{index + 1}区間", top, bottom, zone.hoop.diameter, zone.hoop.sets, zone.hoop.pitch))
        top = bottom
    sections = [Section("杭頭", found.bar_diameter, found.bar_count, head.diameter, head.sets, head.pitch)]
    cutoff = bars.cutoff
    reach = None
    if cutoff.main_diameter is not None:
        path = f"{_REBAR}.cutoff"
        reach = number(_need(cutoff.cutoff_length, f"{path}.cutoff_length_mm"))
        hoop = cutoff.hoop
        sections.append(Section("段落し後", cutoff.main_diameter, _need(cutoff.main_count, f"{path}.main_bars.count"),
                                _need(hoop.diameter, f"{path}.hoops.diameter_mm"),
                                _need(hoop.sets, f"{path}.hoops.sets"), _need(hoop.pitch, f"{path}.hoops.pitch_mm")))
    return PileFigure(diameter, number(found.centre), number(pile.anchorage.length), tuple(zones), reach,
                      tuple(sections))


def hoop_text(diameter: Printed, sets: int, pitch: Printed) -> str:
    return f"D{mm(number(diameter))}-{sets}組 ctc{mm(number(pitch))}"


def draw_pile(sheet: Sheet, figure: PileFigure, origin: Vec2) -> None:
    """The side of the pile with the centre of its head at *origin*, and its sections on the right."""
    p = sheet.p
    radius = float(figure.diameter) / 2
    inner = radius - float(figure.centre)  # the main bars from the axis
    length = float(figure.length)
    gap = GAP * p

    def at(x: float, depth: float) -> Vec2:  # x from the axis, depth below the head
        return origin + Vec2(x, -depth)

    # the footing's base at the head, the outline of the pile and its main bars
    sheet.line(at(-radius - 5 * p, 0), at(radius + 5 * p, 0), "躯体")
    sheet.text("フーチング下面", at(-radius - 5 * p, 0) + Vec2(0, gap), TextEntityAlignment.BOTTOM_LEFT)
    for side in (-1, 1):
        sheet.line(at(side * radius, 0), at(side * radius, length), "躯体")
        sheet.line(at(side * inner, -float(figure.anchorage)), at(side * inner, length))
    sheet.line(at(-radius, length), at(radius, length), "躯体")
    # the hoops of each zone at their pitch, from its top
    for zone in figure.zones:
        pitch = float(number(zone.pitch))
        count = math.floor(float(zone.bottom - zone.top) / pitch + 1e-9)
        for k in range(count + 1):  # count × pitch is within the zone
            depth = float(zone.top) + k * pitch
            sheet.line(at(-inner, depth), at(inner, depth))
        middle = float(zone.top + zone.bottom) / 2
        sheet.label(at(-radius - 3 * p, middle), -1, zone.name, hoop_text(zone.diameter, zone.sets, zone.pitch))
        sheet.line(at(-radius - 3 * p, middle), at(-inner, middle), "引出線")
    if figure.cutoff is not None:
        cut = float(figure.cutoff)
        sheet.line(at(-radius - 5 * p, cut), at(radius + 5 * p, cut), "引出線")
        sheet.text("段落し位置", at(radius + 5 * p, cut) + Vec2(gap, gap), TextEntityAlignment.BOTTOM_LEFT)
    # the chain on the right: the 杭頭定着長 above the head, the zones below it
    points = sorted({figure.anchorage, Decimal(0), *(-zone.bottom for zone in figure.zones),
                     *((-figure.cutoff,) if figure.cutoff is not None else ())})
    edge = radius + gap
    sheet.chain(points, edge, radius + 12 * p, True, origin)
    sheet.text("杭頭定着長", at(radius + 16 * p, -float(figure.anchorage) / 2), TextEntityAlignment.MIDDLE_LEFT)

    # the sections, on the right of the chain
    left = radius + (12 + _SPACE) * p + sheet.width("杭頭定着長")
    for section in figure.sections:
        centre = at(left + radius, length / 4)
        _section(sheet, figure, section, centre)
        left += 2 * radius + _SPACE * p + sheet.width(f"D{mm(number(section.main_diameter))}-{section.main_count}本")


def _section(sheet: Sheet, figure: PileFigure, section: Section, centre: Vec2) -> None:
    """The section *section* with its centre at *centre*."""
    p = sheet.p
    radius = float(figure.diameter) / 2
    bar = float(number(section.main_diameter)) / 2
    circle = radius - float(figure.centre)
    sheet.msp.add_circle(centre, radius, dxfattribs={"layer": "躯体"})
    for k in range(section.main_count):
        angle = 2 * math.pi * k / section.main_count + math.pi / 2
        sheet.circle(centre + Vec2(circle * math.cos(angle), circle * math.sin(angle)), bar)
    sheet.msp.add_circle(centre, circle + bar + float(number(section.hoop_diameter)) / 2, dxfattribs={"layer": "鉄筋"})
    gap = GAP * p
    sheet.text(f"{section.title}", centre + Vec2(0, radius + (TEXT + 2 * GAP) * p), TextEntityAlignment.BOTTOM_CENTER)
    sheet.text(f"D{mm(number(section.main_diameter))}-{section.main_count}本", centre + Vec2(0, -radius - gap),
               TextEntityAlignment.TOP_CENTER)
    sheet.text(f"帯鉄筋 {hoop_text(section.hoop_diameter, section.hoop_sets, section.hoop_pitch)}",
               centre + Vec2(0, -radius - gap - (TEXT + GAP) * p), TextEntityAlignment.TOP_CENTER)
    sheet.text(f"芯かぶり {mm(figure.centre)}", centre + Vec2(0, -radius - gap - 2 * (TEXT + GAP) * p),
               TextEntityAlignment.TOP_CENTER)

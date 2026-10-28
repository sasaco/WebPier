"""柱の水平断面 (decision 73, CONTEXT.md 配筋図): the column section W6 × B6 with its bars as calc places them.

The drawing is the section of calc.column_rebar seen from above: x across the track (W6), y along it (B6) with the
reference face (Y = 0) at the top, as the sample Example橋脚2 06_照査の前提.pdf 6.1 (2). It shows

- the main bars in use (calc.column_rebar.ColumnLayout.bars), labelled by row: the 線路 rows under the section, the
  直角 rows beside it ('D32-29本', with the layer when a direction has more than one: '2段目D32-15本');
- the outer hoop (外巻き帯鉄筋, its own size) round the outermost bars, and the 中間帯鉄筋 on the main bars the
  calc layer hooks them to (decision 73); the legs of each direction are pointed at by one leader labelled with the
  hoop row of the column base (calc.column_check, the row the section check uses): 'D22-5組@150', 組 = 有効本数 / 2;
- the dimensions: along each axis the chain through the faces, the centres of layer 1 of the direction spaced along
  it and the 芯かぶり of the other direction's layer 1 when it lies outside them ('108 | 192 | 26×150=3900 | ...'),
  else that 芯かぶり on its own; and the totals W6 and B6.

A column whose 方向別の鉄筋配置表 is hand-made (decision 111) has no bars with a place: its figure draws the rows of
the two tables in use (calc.column_rebar.direction_table) across the section instead (decision 113), as the beam's
figure its bars: the 線路 rows as lines along X at their Y, the 直角 rows along Y at their X, each between the
outermost rows of the other table;

- the 引張鉄筋 rows labelled as the beam's faces, by layer when there are more than one ('1段目D19-44本', layer 1 the
  first row of the table above / left of the section, the last row below / right), the other rows of each table as
  the beam's side bars, one leader to three of them for each size labelled with their count ('D19-56本');
- the outer hoop round the outermost rows, and the 中間帯鉄筋 beside the rows calc.detailing.ties hooks them to with
  their leaders, as above;
- the chains of the rows' centres along each axis with the faces, and the totals W6 and B6.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from .sheet import GAP, STACK, TEXT, Sheet, TextEntityAlignment, Vec2, fan, mm, number  # isort: skip

from ...calc.column_rebar import ColumnLayout, DirectionTable, FaceRow, TableRow, column_layout, direction_table
from ...calc.detailing.ties import BaseHoops, TieLayout, base_hoops, tie_layout
from ...core.errors import InputError
from ...core.printed import Printed
from ...inputs import PierInput, choices

RAIL, CROSS = choices.REBAR_DIRECTIONS
_ENCLOSING = "鉄筋.柱.column_hoops.enclosing_diameter_mm"


@dataclass(frozen=True)
class ColumnFigure:
    layout: ColumnLayout
    enclosing: Printed  # the outer hoop's size, mm
    hoops: dict[str, BaseHoops]  # by direction: its hoop row at the column base
    ties: dict[str, TieLayout]  # by direction: the legs of those hoops (calc.detailing.ties)
    # the 方向別の鉄筋配置表 of 線路 and 直角 in use when one is hand-made (decision 111), drawn in place of the bars
    tables: tuple[DirectionTable, DirectionTable] | None = None


def column_figure(pier: PierInput) -> ColumnFigure:
    """What the column section is drawn from; a blank it needs is an input error naming its path."""
    layout = column_layout(pier)
    enclosing = pier.rebar.column.hoops.enclosing_diameter
    if enclosing is None:
        raise InputError(f"{_ENCLOSING}: 値が必要です")
    hoops = {direction: base_hoops(pier, direction) for direction in choices.REBAR_DIRECTIONS}
    ties = {direction: tie_layout(layout, direction, row.legs, row.path) for direction, row in hoops.items()}
    tables = (direction_table(layout, RAIL), direction_table(layout, CROSS)) if layout.customized else None
    return ColumnFigure(layout=layout, enclosing=enclosing, hoops=hoops, ties=ties, tables=tables)


def sets_text(value: Printed) -> str:
    """組 as the plan prints it (decision 73): a whole number without decimals (5 組), else to its printed digits
    (3.5 組)."""
    return str(int(value.value)) if value.value.is_integer() else f"{value.value:.{value.digits}f}"


def hoop_text(hoops: BaseHoops, ties: TieLayout) -> str:
    """'D22-5組@150': the size, 組 = 有効本数 / 2 and the pitch of the hoop row."""
    return f"D{mm(number(hoops.diameter))}-{sets_text(ties.sets)}組@{mm(number(hoops.pitch))}"


def row_texts(rows: Sequence[FaceRow]) -> list[str]:
    """'D32-29本' for each layer; with its layer when there are more than one."""
    return [(f"{row.layer}段目" if len(rows) > 1 else "") + f"D{mm(number(row.diameter))}-{len(row.positions)}本"
            for row in rows]


def _gap_near(values: Sequence[float], low: float, high: float, target: float) -> float:
    """The middle of the gap between neighbours of *values* (with *low* and *high*) nearest *target*: where a leader
    crosses the bars without touching them."""
    points = sorted({low, high, *values})
    middles = [(a + b) / 2 for a, b in zip(points, points[1:])]
    return min(middles, key=lambda middle: (abs(middle - target), middle))


def _chain_points(span: Decimal, along: Sequence[Decimal], centers: Sequence[Decimal], reach: Decimal
                  ) -> tuple[list[Decimal], list[Decimal]]:
    """The chain through the faces and *along* (layer 1 of the direction spaced along the axis), with the 芯かぶり
    *centers* of the other direction that lie outside *along* by more than *reach*; the others on their own."""
    first, last = (min(along), max(along)) if along else (span, Decimal(0))
    inside = [c for c in centers if not (c < first - reach or c > last + reach)]
    points = sorted({Decimal(0), span, *along, *(c for c in centers if c not in inside)})
    return points, inside


def draw_column(sheet: Sheet, figure: ColumnFigure, origin: Vec2) -> None:
    """The column section with its lower-left corner at *origin*."""
    if figure.tables is not None:
        _draw_tables(sheet, figure, *figure.tables, origin)
        return
    layout = figure.layout
    p = sheet.p
    width, height = float(layout.width.value), float(layout.height.value)

    def at(x: float, y: float) -> Vec2:  # x from the left face, y from the reference face (the top)
        return origin + Vec2(x, height - y)

    sheet.rectangle(*at(0, height), *at(width, 0))
    for bar in layout.bars:
        sheet.circle(at(bar.x.value, bar.y.value), bar.diameter.value / 2)

    # the outer hoop round the outermost bars, and the ties on the bars they hook
    half = figure.enclosing.value / 2
    left = min(bar.x.value - bar.diameter.value / 2 for bar in layout.bars) - half
    right = max(bar.x.value + bar.diameter.value / 2 for bar in layout.bars) + half
    top = min(bar.y.value - bar.diameter.value / 2 for bar in layout.bars) - half
    bottom = max(bar.y.value + bar.diameter.value / 2 for bar in layout.bars) + half
    largest = max(bar.diameter.value for bar in layout.bars)
    sheet.rounded(*at(left, bottom), *at(right, top), largest / 2 + half)
    rows = {direction: [row for row in layout.rows if row.direction == direction] for direction in (RAIL, CROSS)}
    vertical = [left, right]  # legs along Y: their x
    horizontal = [top, bottom]  # legs along X: their y
    for direction, legs in ((RAIL, vertical), (CROSS, horizontal)):
        tie = figure.hoops[direction].diameter.value / 2
        span = figure.ties[direction].span.value
        for centre in figure.ties[direction].intermediate:  # beside the bar it holds, towards the middle
            radius = next(bar.diameter.value for bar in layout.bars
                          if (direction, 1) in bar.rows and (bar.x if direction == RAIL else bar.y) == centre) / 2
            position = centre.value + (radius + tie) * (1 if centre.value < span / 2 else -1)
            legs.append(position)
            if direction == RAIL:
                sheet.line(at(position, top), at(position, bottom))
            else:
                sheet.line(at(left, position), at(right, position))
    vertical.sort()
    horizontal.sort()

    gap, line = GAP * p, (TEXT + 2 * GAP) * p
    # under the section: the 線路 rows, the leader of the 直角 legs, the 芯かぶり, the chain, the total, the direction
    cursor = -gap
    for text in row_texts(rows[RAIL]):
        sheet.text(text, at(width / 2, height - cursor), TextEntityAlignment.TOP_CENTER)
        cursor -= TEXT * p + gap
    cursor -= line
    xs = [bar.x.value for bar in layout.bars] + vertical
    x_leader = _gap_near(xs, 0.0, width, 0.8 * width)
    elbow = at(x_leader, height - cursor)
    sheet.label(elbow, -1, hoop_text(figure.hoops[CROSS], figure.ties[CROSS]))
    sheet.line(elbow, at(x_leader, horizontal[0]), "引出線")
    for y in horizontal:
        sheet.arrow(at(x_leader, y), 90.0)

    # beside the section: the 直角 rows, the leader of the 線路 legs on the left
    side = width + gap
    for text in row_texts(rows[CROSS]):
        sheet.text(text, at(side + TEXT * p, height / 2), TextEntityAlignment.BOTTOM_CENTER, rotation=90.0)
        side += TEXT * p + gap
    ys = [bar.y.value for bar in layout.bars] + horizontal
    y_leader = _gap_near(ys, 0.0, height, 0.3 * height)
    elbow = at(-3 * p, y_leader)
    sheet.label(elbow, -1, hoop_text(figure.hoops[RAIL], figure.ties[RAIL]))
    sheet.line(elbow, at(vertical[-1], y_leader), "引出線")
    for x in vertical:
        sheet.arrow(at(x, y_leader), 0.0)

    _dimensions(sheet, figure, origin, rows, cursor - line, side + gap + line)


def _dimensions(sheet: Sheet, figure: ColumnFigure, origin: Vec2, rows: dict[str, list[FaceRow]], below: float,
                beside: float) -> None:
    layout = figure.layout
    p = sheet.p
    width, height = number(layout.width), number(layout.height)
    line = (TEXT + 2 * GAP) * p
    reach = {direction: max((number(row.diameter) for row in rows[other]), default=Decimal(0))
             for direction, other in ((RAIL, CROSS), (CROSS, RAIL))}

    def centers(direction: str, span: Decimal) -> list[Decimal]:
        found = [number(row.center) for row in rows[direction][:1]]
        return [*found, *(span - c for c in found)]

    # along X: the 線路 layer 1 positions and the 直角 芯かぶり; along Y (model y = B6 − Y): the 直角 positions and
    # the 線路 芯かぶり
    along_x = [number(x) for x in rows[RAIL][0].positions] if rows[RAIL] else []
    along_y = sorted(height - number(y) for y in rows[CROSS][0].positions) if rows[CROSS] else []
    xs, inside_x = _chain_points(width, along_x, centers(CROSS, width), reach[RAIL])
    ys, inside_y = _chain_points(height, along_y, centers(RAIL, height), reach[CROSS])

    # a 芯かぶり inside the chain on its own, at the far face (the layout is symmetric)
    chain_y = below - (1.5 * line if inside_x else 0)
    if inside_x:
        sheet.chain([max(inside_x), width], 0.0, chain_y + 1.5 * line, vertical=False, origin=origin)
    sheet.chain(xs, 0.0, chain_y, vertical=False, origin=origin)
    sheet.chain([Decimal(0), width], 0.0, chain_y - 1.5 * line, vertical=False, origin=origin)

    chain_x = beside + (1.5 * line if inside_y else 0)
    if inside_y:
        sheet.chain([max(inside_y), height], float(width), chain_x - 1.5 * line, vertical=True, origin=origin)
    sheet.chain(ys, float(width), chain_x, vertical=True, origin=origin)
    sheet.chain([Decimal(0), height], float(width), chain_x + 1.5 * line, vertical=True, origin=origin)

    # the directions: 直角方向 under the section, 線路方向 beside it
    _direction(sheet, "直角方向", origin + Vec2(float(width) / 2, chain_y - 3.5 * line - 2 * p), 0.0)
    _direction(sheet, "線路方向", origin + Vec2(chain_x + 3.5 * line + 2 * p,
                                              float(height) / 2), 90.0)


def table_texts(table: DirectionTable) -> tuple[list[str], list[str]]:
    """'D19-44本' for each 引張鉄筋 row of the upper (left) and the lower (right) face, layer 1 first; with its layer
    when there are more than one."""
    def texts(rows: Sequence[TableRow]) -> list[str]:
        return [(f"{layer}段目" if table.tension > 1 else "") + f"D{mm(number(row.diameter))}-{row.count}本"
                for layer, row in enumerate(rows, 1)]
    return texts(table.upper), texts(tuple(reversed(table.lower)))


def other_groups(table: DirectionTable) -> list[tuple[Decimal, list[TableRow]]]:
    """The rows between the 引張鉄筋 rows of *table* by size, smallest first."""
    sizes = sorted({number(row.diameter) for row in table.others})
    return [(size, [row for row in table.others if number(row.diameter) == size]) for size in sizes]


def _nearest(rows: Sequence[TableRow], target: float) -> list[TableRow]:
    """The three of *rows* nearest *target* (mm from the reference face)."""
    return sorted(rows, key=lambda row: (abs(row.center.value - target), row.center.value))[:3]


def _draw_tables(sheet: Sheet, figure: ColumnFigure, rail: DirectionTable, cross: DirectionTable,
                 origin: Vec2) -> None:
    """The rows of the tables across the section (decision 113): the 線路 rows at their Y, the 直角 rows at their X."""
    layout = figure.layout
    p = sheet.p
    width, height = float(layout.width.value), float(layout.height.value)
    gap, line = GAP * p, (TEXT + 2 * GAP) * p

    def at(x: float, y: float) -> Vec2:  # x from the left face, y from the reference face (the top)
        return origin + Vec2(x, height - y)

    sheet.rectangle(*at(0, height), *at(width, 0))
    ys = [row.center.value for row in rail.rows]
    xs = [row.center.value for row in cross.rows]
    for y in ys:
        sheet.line(at(min(xs), y), at(max(xs), y))
    for x in xs:
        sheet.line(at(x, min(ys)), at(x, max(ys)))

    # the outer hoop round the outermost rows, and the ties beside the rows they hook
    half = figure.enclosing.value / 2
    left = min(row.center.value - row.diameter.value / 2 for row in cross.rows) - half
    right = max(row.center.value + row.diameter.value / 2 for row in cross.rows) + half
    top = min(row.center.value - row.diameter.value / 2 for row in rail.rows) - half
    bottom = max(row.center.value + row.diameter.value / 2 for row in rail.rows) + half
    largest = max(row.diameter.value for row in (*rail.rows, *cross.rows))
    sheet.rounded(*at(left, bottom), *at(right, top), largest / 2 + half)
    vertical = [left, right]  # legs along Y: their x
    horizontal = [top, bottom]  # legs along X: their y
    for direction, legs, hooked in ((RAIL, vertical, cross), (CROSS, horizontal, rail)):
        tie = figure.hoops[direction].diameter.value / 2
        span = figure.ties[direction].span.value
        for centre in figure.ties[direction].intermediate:  # beside the row it holds, towards the middle
            # the row it holds; a direction that is not hand-made hooks its main bars (calc.detailing.ties)
            radius = next((row.diameter.value for row in hooked.rows if row.center.value == centre.value),
                          None) or next(bar.diameter.value for bar in layout.bars if (direction, 1) in bar.rows
                                        and (bar.x if direction == RAIL else bar.y).value == centre.value)
            radius /= 2
            position = centre.value + (radius + tie) * (1 if centre.value < span / 2 else -1)
            legs.append(position)
            if direction == RAIL:
                sheet.line(at(position, top), at(position, bottom))
            else:
                sheet.line(at(left, position), at(right, position))
    vertical.sort()
    horizontal.sort()

    upper, lower = table_texts(rail)
    first, last = table_texts(cross)
    # above: the upper 引張鉄筋 rows of 線路, layer 1 on top
    cursor = height + gap
    for text in reversed(upper):
        sheet.text(text, origin + Vec2(width / 2, cursor), TextEntityAlignment.BOTTOM_CENTER)
        cursor += TEXT * p + gap
    # beside: the 直角 引張鉄筋 rows, layer 1 outermost on the left and nearest on the right
    outside = -len(first) * (TEXT * p + gap)  # the left edge of the labels on the left
    side = outside
    for text in first:
        sheet.text(text, at(side + TEXT * p, height / 2), TextEntityAlignment.BOTTOM_CENTER, rotation=90.0)
        side += TEXT * p + gap
    side = width + gap
    for text in last:
        sheet.text(text, at(side + TEXT * p, height / 2), TextEntityAlignment.BOTTOM_CENTER, rotation=90.0)
        side += TEXT * p + gap

    # under: the lower 引張鉄筋 rows of 線路, the leader of the 直角 legs
    cursor = -gap
    for text in lower:
        sheet.text(text, at(width / 2, height - cursor), TextEntityAlignment.TOP_CENTER)
        cursor -= TEXT * p + gap
    cursor -= line
    x_leader = _gap_near([*xs, *vertical], 0.0, width, 0.8 * width)
    elbow = at(x_leader, height - cursor)
    sheet.label(elbow, -1, hoop_text(figure.hoops[CROSS], figure.ties[CROSS]))
    sheet.line(elbow, at(x_leader, horizontal[0]), "引出線")
    for y in horizontal:
        sheet.arrow(at(x_leader, y), 90.0)

    # on the left: the leader of the 線路 legs near the top, the other 線路 rows by size near the bottom
    y_leader = _gap_near([*ys, *horizontal], 0.0, height, 0.15 * height)
    elbow = at(outside - 3 * p, y_leader)
    sheet.label(elbow, -1, hoop_text(figure.hoops[RAIL], figure.ties[RAIL]))
    sheet.line(elbow, at(vertical[-1], y_leader), "引出線")
    for x in vertical:
        sheet.arrow(at(x, y_leader), 0.0)
    reach = _gap_near(xs, min(xs), max(xs), min(xs))  # between the first two 直角 rows
    for index, (size, rows) in enumerate(other_groups(rail)):
        y = 0.85 * height + index * 2 * line
        elbow = at(outside - 3 * p, y)
        fan(sheet, elbow, (at(reach, row.center.value) for row in _nearest(rows, y)), 0.0)
        sheet.label(elbow, -1, f"D{mm(size)}-{sum(row.count for row in rows)}本")
    # above on the right: the other 直角 rows by size
    reach = _gap_near(ys, min(ys), max(ys), min(ys))  # between the first two 線路 rows
    for index, (size, rows) in enumerate(other_groups(cross)):
        x = 0.85 * width
        elbow = at(x, -3 * p - index * 2 * line)
        fan(sheet, elbow, (at(row.center.value, reach) for row in _nearest(rows, x)), 0.0)
        sheet.label(elbow, 1, f"D{mm(size)}-{sum(row.count for row in rows)}本")

    # the chains: the 直角 rows along X under the section, the 線路 rows along Y beside it (model y = B6 − Y)
    w, h = number(layout.width), number(layout.height)
    below = cursor - (STACK + 1) * line  # under the texts of narrow gaps stepped out (Sheet.chain)
    sheet.chain(sorted({Decimal(0), w, *(number(row.center) for row in cross.rows)}), 0.0, below, vertical=False,
                origin=origin)
    sheet.chain([Decimal(0), w], 0.0, below - 1.5 * line, vertical=False, origin=origin)
    beside = side + gap + (STACK + 1) * line
    sheet.chain(sorted({Decimal(0), h, *(h - number(row.center) for row in rail.rows)}), width, beside, vertical=True,
                origin=origin)
    sheet.chain([Decimal(0), h], width, beside + 1.5 * line, vertical=True, origin=origin)
    _direction(sheet, "直角方向", origin + Vec2(width / 2, below - 3.5 * line - 2 * p), 0.0)
    _direction(sheet, "線路方向", origin + Vec2(beside + 3.5 * line + 2 * p, height / 2), 90.0)


def _direction(sheet: Sheet, text: str, center: Vec2, rotation: float) -> None:
    """*text* over a line with arrows at both ends (a direction of the section)."""
    half = sheet.width(text) / 2 + 3 * sheet.p
    along = Vec2.from_deg_angle(rotation)
    across = along.orthogonal()
    sheet.text(text, center + across * (GAP * sheet.p), TextEntityAlignment.BOTTOM_CENTER, rotation=rotation)
    start, end = center - along * half, center + along * half
    sheet.line(start, end, "引出線")
    sheet.arrow(start, rotation + 180.0)
    sheet.arrow(end, rotation)

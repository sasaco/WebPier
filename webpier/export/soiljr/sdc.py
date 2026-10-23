"""The 解析連携データ (.sdc) SOIL-JR returns: the ground springs of the pile foundation, read for the frame (decision 88).

The file is CP932 text. Below ``【解析用地盤ばね値】`` each direction (``（１）橋軸方向``, ``（２）直角方向``) has the sections
a) the pile rows and 1/β, b) the horizontal springs, c) the effective resistance earth pressure, d) the vertical shear
springs of the pile surface (the push side and the pull side), e) the surface bearing capacities, f) the springs at the
pile tip and g) its bearing capacities (references/sdt-format.md §11 of the skill structural-jrsnap-soil).

The springs are by *column*: one column per pile row (``1列目``, ``2列目``, … when the rows are listed, K_FLG = 1) or one for
the odd rows and one for the even rows (``奇数列``, ``偶数列``, a staggered layout or a regular one with equal rows). They
are already bundled by the number of piles in the depth: SOIL-JR prints them as the ground springs "考慮した奥行き本数".
Only what the frame needs is read (a, b, the push side of d and f); the rest of the file is the report's and the
limits' (the .sdr), and a section the frame does not use is not parsed.
"""

from __future__ import annotations

import re
from itertools import dropwhile, takewhile

from ...calc.pile_springs import ALL, ODD, DirectionSprings, GroundSprings, ListedRow, SpringLayer

ENCODING = "cp932"
_SECTION = re.compile(r"^([a-h])）")
_DIRECTION = re.compile(r"^（[１２](?:）|\))(.+)$")
_ROW_COLUMN = re.compile(r"^(\d+)列目$")


class SdcError(ValueError):
    """The file is not a .sdc of SOIL-JR 5.2 the frame can read."""


def _cell(text: str) -> float | str:
    text = text.strip()
    try:
        return float(text)
    except ValueError:
        return text


def _numbers(cells: list[str]) -> tuple[float, ...]:
    values = tuple(_cell(cell) for cell in cells)
    if any(isinstance(value, str) for value in values):
        raise SdcError(f"数値でない値があります: {','.join(cells)}")
    return values  # type: ignore[return-value]


def _rows(lines: list[str], start: int) -> list[list[str]]:
    """The first run of rows of numbers at or after *start* (the first cell an integer), skipping the lines of names above."""
    parsed = ([cell.strip() for cell in line.split(",")] for line in lines[start:])
    return list(takewhile(_is_row, dropwhile(lambda cells: not _is_row(cells), parsed)))


def _is_row(cells: list[str]) -> bool:
    return len(cells) >= 3 and cells[0].isdigit()


def _header(lines: list[str], what: str) -> dict[str, float | str]:
    try:
        at = next(index for index, line in enumerate(lines) if line.startswith("杭長,突出長"))
    except StopIteration:
        raise SdcError(f"{what}: 【杭情報】に杭長の行がありません") from None
    names = lines[at].split(",")
    values = [_cell(cell) if cell.strip() else "" for cell in lines[at + 1].split(",")]
    if len(names) != len(values):
        raise SdcError("杭の見出しの項目数と値の数が違います")
    return {name.strip(): value for name, value in zip(names, values)}


def _sections(lines: list[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    key = ""
    for line in lines:
        if match := _SECTION.match(line):
            key = match.group(1)
            found[key] = []
        elif key:
            found[key].append(line)
    return found


def _arrangement(lines: list[str]) -> tuple[int, tuple[int, ...], float, tuple[ListedRow, ...]]:
    """a): 杭列数, the 奥行き本数 of each of the two column kinds, 1/β, and the listed rows."""
    try:
        at = next(index for index, line in enumerate(lines) if line.startswith("杭列数"))
    except StopIteration:
        raise SdcError("a）に杭列数の行がありません") from None
    values = _numbers([cell for cell in lines[at + 2].split(",")])
    if len(values) != 4:
        raise SdcError(f"a）の杭列数の行の項目数が違います: {lines[at + 2]}")
    rows, odd, even, inverse = values
    listed: tuple[ListedRow, ...] = ()
    table = next((index for index, line in enumerate(lines) if line.startswith("番号,")), None)
    if table is not None:
        listed = tuple(ListedRow(int(cells[0]), float(cells[1]), int(float(cells[2]))) for cells in _rows(lines, table + 1))
    return int(rows), (int(odd), int(even)), inverse, listed


def _columns(lines: list[str]) -> tuple[str, ...]:
    """The names of the columns of b): the 長期 ones of the line of column names."""
    at = next((index for index, line in enumerate(lines) if line.startswith(",,長期")), None)
    if at is None:
        raise SdcError("b）に列の見出しがありません")
    names = [cell.split("-", 1)[1] for cell in lines[at].split(",") if cell.startswith("長期-")]
    return tuple(names) or (ALL,)


def _layers(b: list[str], d: list[str], columns: int) -> tuple[SpringLayer, ...]:
    start = next(index for index, line in enumerate(b) if line.startswith(",,長期")) + 1
    horizontal = _rows(b, start)
    at = next((index for index, line in enumerate(d) if line.startswith("【押込み側】")), None)
    if at is None:
        raise SdcError("d）に【押込み側】がありません")
    shear = _rows(d, at + 1)
    pull_at = next((index for index, line in enumerate(d) if line.startswith("【引抜き側】")), None)
    if pull_at is None:
        raise SdcError("d）に【引抜き側】がありません")
    pull = _rows(d, pull_at + 1)
    if len(horizontal) != len(shear) or len(shear) != len(pull):
        raise SdcError("b）と d）の層の数が違います")
    layers = []
    for h, s, u in zip(horizontal, shear, pull):
        if len(h) != 2 + 3 * columns:
            raise SdcError(f"b）の層 {h[0]} の項目数が違います（{len(h)}）")
        if len(s) != 3 + 4 * columns or len(u) != 3 + 4 * columns:
            raise SdcError(f"d）の層 {s[0]} の項目数が違います（{len(s)}）")
        h_values, s_values, u_values = _numbers(h), _numbers(s), _numbers(u)
        layers.append(SpringLayer(
            number=int(h_values[0]), thickness=h_values[1],
            horizontal_long=h_values[2:2 + columns], horizontal_short=h_values[2 + columns:2 + 2 * columns],
            shear_thickness=s_values[1], shear_long=s_values[2:2 + columns],
            shear_short=s_values[2 + columns:2 + 2 * columns], pull_thickness=u_values[1],
            pull_long=u_values[2:2 + columns], pull_short=u_values[2 + columns:2 + 2 * columns]))
    return tuple(layers)


def _tip(f: list[str], title: str, values_per_column: int, columns: int) -> tuple[tuple[float, ...], ...]:
    """The values of the block *title* of f): the line of numbers below it, split into its groups of *columns*."""
    at = next((index for index, line in enumerate(f) if line.startswith(title)), None)
    if at is None:
        raise SdcError(f"f）に{title}がありません")
    values = next((_numbers(line.split(",")) for line in f[at + 1:]
                   if line.split(",")[0].strip().replace(".", "", 1).isdigit()), None)
    if values is None or len(values) != values_per_column * columns:
        raise SdcError(f"f）の{title}の項目数が違います")
    return tuple(values[group * columns:(group + 1) * columns] for group in range(values_per_column))


def _direction(name: str, lines: list[str]) -> DirectionSprings:
    sections = _sections(lines)
    for key in "abdf":
        if key not in sections:
            raise SdcError(f"{name}: {key}）がありません")
    rows, depth, inverse, listed = _arrangement(sections["a"])
    columns = _columns(sections["b"])
    if columns[0] not in (ODD, ALL) and not _ROW_COLUMN.match(columns[0]):
        raise SdcError(f"{name}: 列の見出し（{','.join(columns)}）を読めません")
    if columns == (ALL,) and depth[0] != depth[1]:
        raise SdcError(f"{name}: 列が1つなのに奥行き本数が奇数列と偶数列で違います（{depth[0]}、{depth[1]}）")
    per_row = columns[0] not in (ODD, ALL)
    if per_row and len(columns) != rows:
        raise SdcError(f"{name}: 列の数（{len(columns)}）が杭列数（{rows}）と違います")
    if per_row and len(listed) != rows:
        raise SdcError(f"{name}: 杭列を並べた表（{len(listed)} 行）が杭列数（{rows}）と違います")
    piles = tuple(row.piles for row in listed) if per_row else depth[:len(columns)]
    layers = _layers(sections["b"], sections["d"], len(columns))
    count = len(columns)
    tip_long, tip_short, _ = _tip(sections["f"], "杭先端の鉛直", 3, count)
    horizontal_long, horizontal_short = _tip(sections["f"], "杭先端の水平", 2, count)
    rotation_long, rotation_short = _tip(sections["f"], "杭先端の回転", 2, count)
    return DirectionSprings(name=name, rows=rows, columns=columns, depth_piles=piles, inverse_beta=inverse,
                        listed_rows=listed if per_row else (), layers=layers, tip_long=tip_long, tip_short=tip_short,
                           tip_horizontal_long=horizontal_long, tip_horizontal_short=horizontal_short,
                           tip_rotation_long=rotation_long, tip_rotation_short=rotation_short)


def parse_sdc(data: bytes) -> GroundSprings:
    try:
        lines = data.decode(ENCODING).replace("\r\n", "\n").split("\n")
    except UnicodeDecodeError as exc:
        raise SdcError(f".sdc を CP932 として読めません（{exc}）") from exc
    if len(lines) < 10 or lines[0].strip() != "【バージョン情報】" or not lines[1].startswith("Ver.5.2"):
        raise SdcError("SOIL-JR 5.2 の .sdc ではありません")
    try:
        start = lines.index("【解析用地盤ばね値】")
    except ValueError:
        raise SdcError(".sdc に【解析用地盤ばね値】がありません") from None
    title = lines[4]
    header = _header(lines[:start], "杭情報")
    blocks: list[tuple[str, list[str]]] = []
    for line in lines[start + 1:]:
        if match := _DIRECTION.match(line):
            blocks.append((match.group(1).strip(), []))
        elif blocks:
            blocks[-1][1].append(line)
    if not blocks:
        raise SdcError(".sdc に方向（（１）橋軸方向）がありません")
    return GroundSprings(version=lines[1].strip(), title=title, pile=header,
                   directions=tuple(_direction(name, body) for name, body in blocks))
